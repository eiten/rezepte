from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
import re
from database import get_db_connection, get_user_context
from template_config import templates

router = APIRouter()

# Mapping von deutschen zu englischen Spaltennamen für FTS-Suche
FTS_COLUMN_MAPPING = {
    'zutat': 'ingredients',
    'zutaten': 'ingredients',
    'ingredient': 'ingredients',
    'ingredients': 'ingredients',
    'rezeptname': 'name',
    'name': 'name',
    'titel': 'name',
    'autor': 'author',
    'author': 'author',
    'quelle': 'source',
    'source': 'source',
    'schritt': 'steps',
    'steps': 'steps',
    'anleitung': 'steps',
    'vortext': 'preamble',
    'preamble': 'preamble',
    'einleitung': 'preamble',
}

def transform_search_query(q: str) -> tuple:
    """
    Transform search query with potential column prefixes.
    Maps German column names to English.
    
    Examples:
        'zutat: krisch' -> 'ingredients: krisch'
        'rezeptname: pasta' -> 'name: pasta'
        'krisch' -> 'krisch' (no change)
    
    Returns:
        (transformed_query, error_message)
        error_message is None if no error, otherwise contains hint
    """
    # Check for column prefix pattern (word + colon)
    match = re.match(r'^(\w+):\s*(.+)$', q.strip())
    if match:
        column_name, search_term = match.groups()
        column_lower = column_name.lower()
        
        if column_lower in FTS_COLUMN_MAPPING:
            # Valid German or English column
            mapped_column = FTS_COLUMN_MAPPING[column_lower]
            return f"{mapped_column}: {search_term}", None
        else:
            # Invalid column
            valid_columns = ', '.join(sorted(set(FTS_COLUMN_MAPPING.values())))
            error = f"Unbekannte Spalte '{column_name}'. Verfügbar: {valid_columns}"
            return q, error
    
    return q, None

def parse_amount(amount_str: str):
    """
    Parse amount strings like '300', '300-400', or '- 450' into min/max values.
    Treats leading hyphens as list bullets (not as range indicators).
    """
    if not amount_str:
        return None, None
    
    # Normalize: comma to dot, trim whitespace
    s = amount_str.replace(',', '.').strip()
    
    # Remove leading hyphens (list bullet markers)
    # Converts "-450" or "- 450" to "450"
    if s.startswith('-'):
        s = s.lstrip('-').strip()

    # Check for range (hyphen in the middle)
    if '-' in s:
        parts = s.split('-')
        try:
            val_min = float(parts[0].strip()) if parts[0].strip() else None
            val_max = float(parts[1].strip()) if parts[1].strip() else None
            return val_min, val_max
        except ValueError:
            return None, None
            
    # Single value
    try:
        return float(s), None
    except ValueError:
        return None, None

async def get_breadcrumbs(db, folder_id):
    """Berechnet rekursiv den Pfad für die Breadcrumbs"""
    breadcrumbs = []
    current_id = folder_id
    while current_id:
        async with db.execute("SELECT id, name, parent_id FROM folders WHERE id = ?", (current_id,)) as cursor:
            folder = await cursor.fetchone()
            if folder:
                breadcrumbs.insert(0, dict(folder))
                current_id = folder['parent_id']
            else:
                break
    return breadcrumbs

async def get_all_child_folder_ids(db, folder_id):
    """Gibt eine Liste aller Unterordner-IDs inklusive der eigenen ID zurück."""
    ids = [folder_id]
    async with db.execute("SELECT id FROM folders WHERE parent_id = ?", (folder_id,)) as cursor:
        rows = await cursor.fetchall()
        for row in rows:
            child_ids = await get_all_child_folder_ids(db, row['id'])
            ids.extend(child_ids)
    return ids

async def get_folder_tree(db):
    """Baue den Ordnerbaum für die Navigation"""
    async with db.execute("SELECT * FROM folders ORDER BY parent_id, name") as cursor:
        rows = await cursor.fetchall()
        folders = [dict(r) for r in rows]

    folder_dict = {f['id']: {**f, 'children': []} for f in folders}
    folder_tree = []
    for f_id, f_data in folder_dict.items():
        if f_data['parent_id'] and f_data['parent_id'] in folder_dict:
            folder_dict[f_data['parent_id']]['children'].append(f_data)
        else:
            folder_tree.append(f_data)
    return folder_tree  
    
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request, 
    q: str = None,
    folder: int = None,
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """ Home page: List all recipes """
    user_ctx = await get_user_context(request, db)

    # Normalize search term
    q = q.strip() if q else None
    
    search_error = None
    recipes = []
    
    if q:
        # Transform query with column mapping
        q_transformed, search_error = transform_search_query(q)
        
        try:
            # Full-text search via FTS5 with lightweight column weighting (bm25)
            fts_query = """
                SELECT r.*, bm25(recipe_fts, 5.0, 3.0, 2.5, 2.0, 1.5, 1.0) AS score
                FROM recipe_fts
                JOIN recipes r ON r.id = recipe_fts.rowid
                WHERE recipe_fts MATCH ?
            """
            params = [q_transformed]

            if folder:
                allowed_ids = await get_all_child_folder_ids(db, folder)
                placeholders = ', '.join(['?'] * len(allowed_ids))
                fts_query += f" AND r.folder_id IN ({placeholders})"
                params.extend(allowed_ids)

            fts_query += " ORDER BY score, r.updated_at DESC"

            async with db.execute(fts_query, params) as cursor:
                recipes = await cursor.fetchall()
        except Exception as e:
            # FTS syntax error (e.g., invalid column in prefix search)
            search_error = f"Suchanfrage ungültig: {str(e)}"
            recipes = []
    else:
        # No search term: fallback to latest recipes (optionally filtered by folder)
        list_query = "SELECT * FROM recipes WHERE 1=1"
        params = []

        if folder:
            allowed_ids = await get_all_child_folder_ids(db, folder)
            placeholders = ', '.join(['?'] * len(allowed_ids))
            list_query += f" AND folder_id IN ({placeholders})"
            params.extend(allowed_ids)

        list_query += " ORDER BY created_at DESC"

        async with db.execute(list_query, params) as cursor:
            recipes = await cursor.fetchall()
        
    breadcrumbs = await get_breadcrumbs(db, folder) if folder else []
    folder_tree = await get_folder_tree(db)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes,
        "folder_tree": folder_tree,
        "current_folder": folder,
        "is_admin": user_ctx["is_admin"],
        "current_user_id": user_ctx["user_id"],
        "breadcrumbs": breadcrumbs,
        "search_error": search_error,
        "search_query": q,
        **user_ctx
    })

@router.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def read_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Detail view with permissions check """
    user_ctx = await get_user_context(request, db)
    
    # Fetch recipe
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe = dict(row)

    # Check permissions
    can_edit = False
    can_delete = False
    
    if user_ctx["is_admin"]:
        can_edit = True
        can_delete = True
    elif user_ctx["user_id"] and user_ctx["user_id"] == recipe["owner_id"]:
        can_edit = True

    # Fetch steps with category metadata
    query_steps = """
        SELECT s.*, c.html_color, c.label_de, c.codepoint
        FROM steps s
        LEFT JOIN step_categories c ON s.category_id = c.id
        WHERE s.recipe_id = ? 
        ORDER BY s.position
    """
    async with db.execute(query_steps, (recipe_id,)) as cursor:
        steps = await cursor.fetchall()
        
    # Fetch ingredients and render markdown
    from md import md_to_html, format_ingredient_quantity, load_unit_map
    
    # Load units from DB
    async with db.execute("SELECT symbol, latex_code FROM units ORDER BY name") as cursor:
        db_units = await cursor.fetchall()
    unit_map = load_unit_map(db_units)

    steps_data = []
    for step in steps:
        s_dict = dict(step)
        # s_dict["html_text"] = markdown.markdown(s_dict.get("markdown_text") or "", extensions=["extra"]) 
        s_dict["html_text"] = md_to_html(s_dict.get("markdown_text") or "", unit_map)
        query = """
            SELECT i.*, u.symbol as unit_symbol 
            FROM ingredients i 
            LEFT JOIN units u ON i.unit_id = u.id 
            WHERE step_id = ? 
            ORDER BY i.position
        """
        async with db.execute(query, (step["id"],)) as i_cursor:
            ingredients = await i_cursor.fetchall()
            # Format quantities for display
            formatted_ingredients = []
            for ing in ingredients:
                ing_dict = dict(ing)
                ing_dict["formatted_qty"] = format_ingredient_quantity(
                    ing["amount_min"],
                    ing["amount_max"],
                    ing["unit_symbol"],
                    format='html',
                    unit_map=unit_map
                )
                formatted_ingredients.append(ing_dict)
            s_dict["ingredients"] = formatted_ingredients
        steps_data.append(s_dict)

    # Render markdown in preamble
    preamble_html = md_to_html(recipe.get("preamble") or "", unit_map)

    # Get breadcrumbs
    breadcrumbs = await get_breadcrumbs(db, recipe["folder_id"])
    
    return templates.TemplateResponse("view_recipe.html", {
        "request": request, 
        "recipe": recipe, 
        "preamble_html": preamble_html,
        "steps": steps_data,
        "breadcrumbs": breadcrumbs,
        "can_edit": can_edit,
        "can_delete": can_delete,
        **user_ctx
    })

@router.get("/recipe/{recipe_id}/edit", response_class=HTMLResponse)
async def edit_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Edit recipe page """
    user_ctx = await get_user_context(request, db)
    
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Only admin or owner can edit
    if not user_ctx["is_admin"] and user_ctx["user_id"] != recipe["owner_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Fetch steps with ingredients
    async with db.execute("""
        SELECT s.*, c.label_de, c.id as category_id, c.is_ingredients
        FROM steps s
        LEFT JOIN step_categories c ON s.category_id = c.id
        WHERE s.recipe_id = ?
        ORDER BY s.position
    """, (recipe_id,)) as cursor:
        steps_raw = await cursor.fetchall()
    
    steps_data = []
    for step in steps_raw:
        s_dict = dict(step)
        async with db.execute("""
            SELECT i.*, u.symbol, u.latex_code
            FROM ingredients i
            LEFT JOIN units u ON i.unit_id = u.id
            WHERE step_id = ?
            ORDER BY i.position
        """, (step["id"],)) as i_cursor:
            s_dict["ingredients"] = await i_cursor.fetchall()
        steps_data.append(s_dict)
    
    # Get selectable categories (non-ingredient, id > 1)
    async with db.execute("""
        SELECT * FROM step_categories 
        WHERE is_ingredients = 0 AND id > 1
        ORDER BY label_de
    """) as cursor:
        categories = await cursor.fetchall()
    
    # Get all units for ingredient editor
    async with db.execute("SELECT * FROM units ORDER BY name") as cursor:
        units = await cursor.fetchall()
    
    # Get folders for dropdown
    folder_tree = await get_folder_tree(db)

    return templates.TemplateResponse("edit_recipe.html", {
        "request": request,
        "recipe": recipe,
        "steps": steps_data,
        "categories": categories,
        "folder_tree": folder_tree,
        "units": units,
        **user_ctx
    })

@router.post("/recipe/{recipe_id}/edit")
async def update_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    # Check permissions
    async with db.execute("SELECT owner_id, folder_id, name, author, source, preamble FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    if not user_ctx["is_admin"] and user_ctx["user_id"] != row["owner_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Parse form data
    form = await request.form()
    
    # Get new values
    new_folder_id = form.get("folder_id")
    new_name = form.get("name")
    new_author = form.get("author")
    new_source = form.get("source")
    new_preamble = form.get("preamble")
    
    # Check if base recipe data changed
    base_data_changed = (
        str(row["folder_id"] or "") != str(new_folder_id or "") or
        row["name"] != new_name or
        row["author"] != new_author or
        row["source"] != new_source or
        row["preamble"] != new_preamble
    )
    
    # Update base recipe data - only set updated_at if something changed
    if base_data_changed:
        await db.execute("""
            UPDATE recipes 
            SET folder_id=?, name=?, author=?, source=?, preamble=?, updated_at=CURRENT_TIMESTAMP 
            WHERE id=?
        """, (new_folder_id, new_name, new_author, new_source, new_preamble, recipe_id))
    else:
        await db.execute("""
            UPDATE recipes 
            SET folder_id=?, name=?, author=?, source=?, preamble=?
            WHERE id=?
        """, (new_folder_id, new_name, new_author, new_source, new_preamble, recipe_id))

    # Process steps and ingredients
    kept_step_ids = []
    steps_changed = False
    
    step_idx = 0
    while f"steps[{step_idx}][position]" in form:
        s_prefix = f"steps[{step_idx}]"
        
        step_id_str = form.get(f"{s_prefix}[id]")
        step_id = int(step_id_str) if step_id_str else None
        
        position = form.get(f"{s_prefix}[position]")
        markdown_text = form.get(f"{s_prefix}[markdown_text]")
        
        # Typ/Kategorie Logik
        step_type = form.get(f"{s_prefix}[type]")
        if step_type == 'category':
            raw_cat = form.get(f"{s_prefix}[category_id]")
            cat_id = int(raw_cat) if raw_cat and raw_cat.isdigit() else 1
        else:
            cat_id = 1

        # Upsert step
        if step_id:
            # Fetch old values to check if anything changed
            async with db.execute("SELECT position, markdown_text, category_id FROM steps WHERE id=?", (step_id,)) as cursor:
                old_step = await cursor.fetchone()
            
            step_changed = (
                old_step and (
                    str(old_step["position"]) != str(position) or
                    old_step["markdown_text"] != markdown_text or
                    old_step["category_id"] != cat_id
                )
            )
            
            if step_changed:
                await db.execute("""
                    UPDATE steps SET position=?, markdown_text=?, category_id=? WHERE id=?
                """, (position, markdown_text, cat_id, step_id))
                steps_changed = True
                
            kept_step_ids.append(step_id)
            current_step_db_id = step_id
        else:
            # RETURNING id is supported by newer SQLite versions,
            # alternatively use cursor.lastrowid (see below for ingredients)
            cursor = await db.execute("""
                INSERT INTO steps (recipe_id, position, markdown_text, category_id) 
                VALUES (?, ?, ?, ?) RETURNING id
            """, (recipe_id, position, markdown_text, cat_id))
            new_step_row = await cursor.fetchone()
            current_step_db_id = new_step_row[0]
            kept_step_ids.append(current_step_db_id)
            steps_changed = True

        # Process ingredients
        kept_ing_ids = []
        ing_idx = 0
        while f"{s_prefix}[ingredients][{ing_idx}][item]" in form:
            i_prefix = f"{s_prefix}[ingredients][{ing_idx}]"
            
            ing_id_str = form.get(f"{i_prefix}[id]")
            ing_id = int(ing_id_str) if ing_id_str else None
            
            # Parsing
            amt_combined = form.get(f"{i_prefix}[amount_combined]")
            amount_min, amount_max = parse_amount(amt_combined)
            
            unit_id = form.get(f"{i_prefix}[unit_id]") or None
            item = form.get(f"{i_prefix}[item]")
            note = form.get(f"{i_prefix}[note]")
            
            if ing_id:
                # Fetch old values to check if anything changed
                async with db.execute("SELECT position, amount_min, amount_max, unit_id, item, note FROM ingredients WHERE id=?", (ing_id,)) as cursor:
                    old_ing = await cursor.fetchone()
                
                ing_changed = (
                    old_ing and (
                        old_ing["position"] != ing_idx + 1 or
                        old_ing["amount_min"] != amount_min or
                        old_ing["amount_max"] != amount_max or
                        str(old_ing["unit_id"] or "") != str(unit_id or "") or
                        old_ing["item"] != item or
                        old_ing["note"] != note
                    )
                )
                
                if ing_changed:
                    await db.execute("""
                        UPDATE ingredients 
                        SET position=?, amount_min=?, amount_max=?, unit_id=?, item=?, note=?
                        WHERE id=?
                    """, (ing_idx + 1, amount_min, amount_max, unit_id, item, note, ing_id))
                    steps_changed = True
                    
                kept_ing_ids.append(ing_id)
            else:
                # Insert NEUE Zutat - WICHTIG: Cursor nutzen um ID zu holen!
                cursor = await db.execute("""
                    INSERT INTO ingredients (step_id, position, amount_min, amount_max, unit_id, item, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (current_step_db_id, ing_idx + 1, amount_min, amount_max, unit_id, item, note))
                
                # FIX: Die ID der neuen Zutat auf die "Behalten-Liste" setzen!
                new_ing_id = cursor.lastrowid 
                kept_ing_ids.append(new_ing_id)
                steps_changed = True
            
            ing_idx += 1
            
        # Cleanup: Delete all ingredients of this step that were NOT edited/created
        if kept_ing_ids:
            placeholders = ",".join("?" * len(kept_ing_ids))
            result = await db.execute(f"DELETE FROM ingredients WHERE step_id=? AND id NOT IN ({placeholders})", (current_step_db_id, *kept_ing_ids))
            if result.rowcount > 0:
                steps_changed = True
        else:
            # If no ingredients remain -> Delete all
            result = await db.execute("DELETE FROM ingredients WHERE step_id=?", (current_step_db_id,))
            if result.rowcount > 0:
                steps_changed = True
            
        step_idx += 1

    # Cleanup: Delete steps
    if kept_step_ids:
        placeholders = ",".join("?" * len(kept_step_ids))
        result = await db.execute(f"DELETE FROM steps WHERE recipe_id=? AND id NOT IN ({placeholders})", (recipe_id, *kept_step_ids))
        if result.rowcount > 0:
            steps_changed = True
    else:
        result = await db.execute("DELETE FROM steps WHERE recipe_id=?", (recipe_id,))
        if result.rowcount > 0:
            steps_changed = True
    
    # Only update recipe timestamp if there were actual changes to base data or steps
    if steps_changed and not base_data_changed:
        await db.execute("""
            UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?
        """, (recipe_id,))

    await db.commit()
    
    redirect_url = request.url_for("read_recipe", recipe_id=recipe_id)
    return RedirectResponse(url=redirect_url, status_code=303)
    
@router.get("/recipe/{recipe_id}/delete")
async def delete_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    # Check rights
    async with db.execute("SELECT owner_id FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
        
    # Only admins can delete
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403, detail="Only admins can delete")

    # Delete (thanks to ON DELETE CASCADE in DB, steps/ingredients are deleted automatically)
    await db.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    await db.commit()
    
    # Back to list
    redirect_url = request.url_for("index")
    return RedirectResponse(url=redirect_url, status_code=303)

@router.get("/add", response_class=HTMLResponse)
async def add_recipe_form(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["user_id"]:
         return RedirectResponse(url="/auth/login", status_code=303)

    # Empty recipe skeleton
    empty_recipe = {
        "id": 0, 
        "name": "", 
        "author": user_ctx["display_name"] or "", 
        "source": "", 
        "preamble": ""
    }
    
    # Categories
    async with db.execute("SELECT * FROM step_categories WHERE is_ingredients = 0 AND id > 1 ORDER BY label_de") as cursor:
        categories = await cursor.fetchall()
    
    # Units
    async with db.execute("SELECT * FROM units ORDER BY name") as cursor:
        units = await cursor.fetchall()

    folder_tree = await get_folder_tree(db)

    return templates.TemplateResponse("edit_recipe.html", {
        "request": request,
        "recipe": empty_recipe,
        "steps": [],     
        "categories": categories,
        "folder_tree": folder_tree,
        "units": units,
        "mode": "add",   # WICHTIG: Modus "add" steuert das Template
        **user_ctx
    })

@router.post("/add")
async def create_recipe(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["user_id"]:
         raise HTTPException(status_code=403, detail="Nicht eingeloggt")

    form = await request.form()
    print("--- DEBUG: CREATE RECIPE ---")
    print(f"Form Keys: {list(form.keys())}") # Zeigt uns ALLE gesendeten Felder

    # 1. Rezept INSERT
    cursor = await db.execute("""
        INSERT INTO recipes (folder_id, owner_id, name, author, source, preamble) 
        VALUES (?, ?, ?, ?, ?, ?) RETURNING id
    """, (
        form.get("folder_id"),
        user_ctx["user_id"],
        form.get("name"), 
        form.get("author"), 
        form.get("source"), 
        form.get("preamble")
    ))
    row = await cursor.fetchone()
    new_recipe_id = row[0]
    print(f"Rezept erstellt: ID {new_recipe_id}")

    # 2. Schritte und Zutaten speichern
    step_idx = 0
    while f"steps[{step_idx}][position]" in form:
        print(f"--> Verarbeite Schritt {step_idx}")
        s_prefix = f"steps[{step_idx}]"
        
        position = form.get(f"{s_prefix}[position]")
        markdown_text = form.get(f"{s_prefix}[markdown_text]")
        
        # Typ/Kategorie Logik
        step_type = form.get(f"{s_prefix}[type]")
        if step_type == 'category':
            raw_cat = form.get(f"{s_prefix}[category_id]")
            cat_id = int(raw_cat) if raw_cat and raw_cat.isdigit() else 1
        else:
            cat_id = 1

        # Step INSERT
        cursor = await db.execute("""
            INSERT INTO steps (recipe_id, position, markdown_text, category_id) 
            VALUES (?, ?, ?, ?) RETURNING id
        """, (new_recipe_id, position, markdown_text, cat_id))
        step_row = await cursor.fetchone()
        current_step_db_id = step_row[0]
        print(f"    Schritt DB-ID: {current_step_db_id}")

        # Zutaten INSERT
        ing_idx = 0
        # Prüfe, ob der Key existiert
        check_key = f"{s_prefix}[ingredients][{ing_idx}][item]"
        if check_key in form:
            print(f"    Zutat gefunden: {check_key}")
        else:
            print(f"    KEINE Zutat gefunden bei Key: {check_key}")

        while f"{s_prefix}[ingredients][{ing_idx}][item]" in form:
            i_prefix = f"{s_prefix}[ingredients][{ing_idx}]"
            
            # Parsing
            amt_combined = form.get(f"{i_prefix}[amount_combined]")
            amount_min, amount_max = parse_amount(amt_combined)
            
            unit_id = form.get(f"{i_prefix}[unit_id]") or None
            item = form.get(f"{i_prefix}[item]")
            note = form.get(f"{i_prefix}[note]")
            
            print(f"      -> Insert Zutat: {item} ({amount_min}-{amount_max})")
            
            await db.execute("""
                INSERT INTO ingredients (step_id, position, amount_min, amount_max, unit_id, item, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (current_step_db_id, ing_idx + 1, amount_min, amount_max, unit_id, item, note))
            
            ing_idx += 1
        step_idx += 1

    await db.commit()
    print("--- DEBUG ENDE ---")
    
    return RedirectResponse(url=request.url_for("read_recipe", recipe_id=new_recipe_id), status_code=303)    