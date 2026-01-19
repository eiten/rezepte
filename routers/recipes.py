from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
import markdown
from database import get_db_connection, get_user_context
from template_config import templates

router = APIRouter()

def parse_amount(amount_str: str):
    """
    Parst '300', '300-400', '300-400' oder '- 450' in min/max Werte.
    Behandelt führende Bindestriche als Aufzählungszeichen.
    """
    if not amount_str:
        return None, None
    
    # 1. Komma zu Punkt, Leerzeichen außen weg
    s = amount_str.replace(',', '.').strip()
    
    # 2. NEU: Führende Bindestriche entfernen
    # Aus "-450" oder "- 450" wird "450".
    # Das verhindert, dass es fälschlicherweise als "bis 450" (Range) erkannt wird.
    if s.startswith('-'):
        s = s.lstrip('-').strip()

    # 3. Bereichsprüfung (Bindestrich IN DER MITTE)
    if '-' in s:
        parts = s.split('-')
        try:
            # Strip nochmal, falls "300 - 400" (mit Leerzeichen um Strich)
            val_min = float(parts[0].strip()) if parts[0].strip() else None
            val_max = float(parts[1].strip()) if parts[1].strip() else None
            return val_min, val_max
        except ValueError:
            return None, None
            
    # 4. Einzelwert
    try:
        return float(s), None
    except ValueError:
        return None, None
    
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Home page: List all recipes """
    user_ctx = await get_user_context(request, db)
    
    async with db.execute("SELECT id, name, author FROM recipes") as cursor:
        recipes = await cursor.fetchall()
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes,
        "is_admin": user_ctx["is_admin"],
        "current_user_id": user_ctx["user_id"],
        **user_ctx
    })

@router.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def read_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Detail view with permissions check """
    user_ctx = await get_user_context(request, db)
    
    # 1. Get Recipe
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
        
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # 2. Check Permissions
    can_edit = False
    can_delete = False
    
    if user_ctx["is_admin"]:
        can_edit = True
        can_delete = True
    elif user_ctx["user_id"] and user_ctx["user_id"] == recipe["owner_id"]:
        can_edit = True

    # 3. Get Steps
    query_steps = """
        SELECT s.*, c.html_color, c.label_de, c.codepoint
        FROM steps s
        LEFT JOIN step_categories c ON s.category_id = c.id
        WHERE s.recipe_id = ? 
        ORDER BY s.position
    """
    async with db.execute(query_steps, (recipe_id,)) as cursor:
        steps = await cursor.fetchall()
        
    # 4. Aggregate Ingredients + render markdown to HTML
    steps_data = []
    for step in steps:
        s_dict = dict(step)
        # Render markdown to HTML for display
        s_dict["html_text"] = markdown.markdown(s_dict.get("markdown_text") or "", extensions=["extra"]) 
        query = """
            SELECT i.*, u.symbol as unit_symbol 
            FROM ingredients i 
            LEFT JOIN units u ON i.unit_id = u.id 
            WHERE step_id = ? 
            ORDER BY i.position
        """
        async with db.execute(query, (step["id"],)) as i_cursor:
            s_dict["ingredients"] = await i_cursor.fetchall()
        steps_data.append(s_dict)

    return templates.TemplateResponse("view_recipe.html", {
        "request": request, 
        "recipe": recipe, 
        "steps": steps_data,
        "can_edit": can_edit,
        "can_delete": can_delete,
        **user_ctx
    })

@router.get("/recipe/{recipe_id}/edit", response_class=HTMLResponse)
async def edit_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Edit recipe page """
    user_ctx = await get_user_context(request, db)
    
    # Check recipe exists and permission
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Rezept nicht gefunden")
    
    # Only admin or owner can edit
    if not user_ctx["is_admin"] and user_ctx["user_id"] != recipe["owner_id"]:
        raise HTTPException(status_code=403, detail="Nicht autorisiert")
    
    # Get all steps with their ingredients
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
        # Fetch ingredients for this step
        async with db.execute("""
            SELECT i.*, u.symbol, u.latex_code
            FROM ingredients i
            LEFT JOIN units u ON i.unit_id = u.id
            WHERE step_id = ?
            ORDER BY i.position
        """, (step["id"],)) as i_cursor:
            s_dict["ingredients"] = await i_cursor.fetchall()
        steps_data.append(s_dict)
    
    # Get selectable categories (only non-ingredient, ids > 1)
    async with db.execute("""
        SELECT * FROM step_categories 
        WHERE is_ingredients = 0 AND id > 1
        ORDER BY label_de
    """) as cursor:
        categories = await cursor.fetchall()
    
    # Get all units for ingredient editor
    async with db.execute("SELECT * FROM units ORDER BY name") as cursor:
        units = await cursor.fetchall()
    
    return templates.TemplateResponse("edit_recipe.html", {
        "request": request,
        "recipe": recipe,
        "steps": steps_data,
        "categories": categories,
        "units": units,
        **user_ctx
    })

@router.post("/recipe/{recipe_id}/edit")
async def update_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    # 1. Rechte prüfen
    async with db.execute("SELECT owner_id FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Rezept nicht gefunden")
    
    if not user_ctx["is_admin"] and user_ctx["user_id"] != row["owner_id"]:
        raise HTTPException(status_code=403, detail="Nicht autorisiert")

    # 2. Formulardaten parsen
    form = await request.form()
    
    # Basisdaten Update
    await db.execute("""
        UPDATE recipes 
        SET name=?, author=?, source=?, preamble=?, updated_at=CURRENT_TIMESTAMP 
        WHERE id=?
    """, (
        form.get("name"), 
        form.get("author"), 
        form.get("source"), 
        form.get("preamble"), 
        recipe_id
    ))

    # 3. Schritte & Zutaten verarbeiten
    kept_step_ids = []
    
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

        # Step Upsert
        if step_id:
            await db.execute("""
                UPDATE steps SET position=?, markdown_text=?, category_id=? WHERE id=?
            """, (position, markdown_text, cat_id, step_id))
            kept_step_ids.append(step_id)
            current_step_db_id = step_id
        else:
            # RETURNING id wird von neueren SQLite Versionen unterstützt, 
            # alternativ cursor.lastrowid (siehe unten bei Zutaten)
            cursor = await db.execute("""
                INSERT INTO steps (recipe_id, position, markdown_text, category_id) 
                VALUES (?, ?, ?, ?) RETURNING id
            """, (recipe_id, position, markdown_text, cat_id))
            new_step_row = await cursor.fetchone()
            current_step_db_id = new_step_row[0]
            kept_step_ids.append(current_step_db_id)

        # Zutaten verarbeiten
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
                # Update existierende Zutat
                await db.execute("""
                    UPDATE ingredients 
                    SET position=?, amount_min=?, amount_max=?, unit_id=?, item=?, note=?
                    WHERE id=?
                """, (ing_idx + 1, amount_min, amount_max, unit_id, item, note, ing_id))
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
            
            ing_idx += 1
            
        # Aufräumen: Lösche alle Zutaten dieses Schritts, die NICHT bearbeitet/erstellt wurden
        if kept_ing_ids:
            placeholders = ",".join("?" * len(kept_ing_ids))
            await db.execute(f"DELETE FROM ingredients WHERE step_id=? AND id NOT IN ({placeholders})", (current_step_db_id, *kept_ing_ids))
        else:
            # Wenn gar keine Zutaten mehr da sind -> Alle löschen
            await db.execute("DELETE FROM ingredients WHERE step_id=?", (current_step_db_id,))
            
        step_idx += 1

    # 4. Aufräumen: Schritte löschen
    if kept_step_ids:
        placeholders = ",".join("?" * len(kept_step_ids))
        await db.execute(f"DELETE FROM steps WHERE recipe_id=? AND id NOT IN ({placeholders})", (recipe_id, *kept_step_ids))
    else:
        await db.execute("DELETE FROM steps WHERE recipe_id=?", (recipe_id,))

    await db.commit()
    
    redirect_url = request.url_for("read_recipe", recipe_id=recipe_id)
    return RedirectResponse(url=redirect_url, status_code=303)
    
@router.get("/recipe/{recipe_id}/delete")
async def delete_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    # 1. Rechte prüfen
    async with db.execute("SELECT owner_id FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        row = await cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Rezept nicht gefunden")
        
    # Nur Admin darf löschen (laut deinem Button-Check)
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403, detail="Nur Admins dürfen löschen")

    # 2. Löschen (Dank ON DELETE CASCADE in der DB werden Steps/Ingredients automatisch mitgelöscht)
    await db.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    await db.commit()
    
    # 3. Zurück zur Liste
    redirect_url = request.url_for("index")
    return RedirectResponse(url=redirect_url, status_code=303)

@router.get("/add", response_class=HTMLResponse)
async def add_recipe_form(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["user_id"]:
         return RedirectResponse(url="/auth/login", status_code=303)

    # Leeres Rezept-Gerüst
    empty_recipe = {
        "id": 0, 
        "name": "", 
        "author": user_ctx["display_name"] or "", 
        "source": "", 
        "preamble": ""
    }
    
    # Listen laden
    async with db.execute("SELECT * FROM step_categories WHERE is_ingredients = 0 AND id > 1 ORDER BY label_de") as cursor:
        categories = await cursor.fetchall()
    
    async with db.execute("SELECT * FROM units ORDER BY name") as cursor:
        units = await cursor.fetchall()

    return templates.TemplateResponse("edit_recipe.html", {
        "request": request,
        "recipe": empty_recipe,
        "steps": [],     
        "categories": categories,
        "units": units,
        "mode": "add",   # WICHTIG: Modus "add" steuert das Template
        **user_ctx
    })

# --- NEU: Neues Rezept speichern (POST) ---
@router.post("/add")
async def create_recipe(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["user_id"]:
         raise HTTPException(status_code=403, detail="Nicht eingeloggt")

    form = await request.form()
    
    # 1. Rezept INSERT
    cursor = await db.execute("""
        INSERT INTO recipes (folder_id, owner_id, name, author, source, preamble) 
        VALUES (1, ?, ?, ?, ?, ?) RETURNING id
    """, (
        user_ctx["user_id"],
        form.get("name"), 
        form.get("author"), 
        form.get("source"), 
        form.get("preamble")
    ))
    row = await cursor.fetchone()
    new_recipe_id = row[0]

    # 2. Schritte und Zutaten speichern
    step_idx = 0
    while f"steps[{step_idx}][position]" in form:
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

        # Zutaten INSERT
        ing_idx = 0
        while f"{s_prefix}[ingredients][{ing_idx}][item]" in form:
            i_prefix = f"{s_prefix}[ingredients][{ing_idx}]"
            
            # Parsing
            amt_combined = form.get(f"{i_prefix}[amount_combined]")
            amount_min, amount_max = parse_amount(amt_combined)
            
            unit_id = form.get(f"{i_prefix}[unit_id]") or None
            item = form.get(f"{i_prefix}[item]")
            note = form.get(f"{i_prefix}[note]")
            
            await db.execute("""
                INSERT INTO ingredients (step_id, position, amount_min, amount_max, unit_id, item, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (current_step_db_id, ing_idx + 1, amount_min, amount_max, unit_id, item, note))
            
            ing_idx += 1
        step_idx += 1

    await db.commit()
    
    # Weiterleitung zum neuen Rezept
    return RedirectResponse(url=request.url_for("read_recipe", recipe_id=new_recipe_id), status_code=303)