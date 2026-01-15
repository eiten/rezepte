from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import aiosqlite
from database import get_db_connection

# This was missing or empty!
router = APIRouter()

templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Home page: List all recipes """
    async with db.execute("SELECT id, name, author FROM recipes") as cursor:
        recipes = await cursor.fetchall()
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes
    })

@router.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def read_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Detail view with permissions check """
    # 1. Get Recipe
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
        
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # --- NEU: Rechteprüfung ---
    current_username = request.cookies.get("session_user")
    can_edit = False
    can_delete = False

    if current_username:
        async with db.execute("SELECT id, role FROM users WHERE username = ?", (current_username,)) as cursor:
            user = await cursor.fetchone()
            if user:
                # Admin darf alles
                if user["role"] == "admin":
                    can_edit = True
                    can_delete = True
                # User darf nur eigene bearbeiten (owner_id Vergleich)
                elif user["id"] == recipe["owner_id"]:
                    can_edit = True
    # ---------------------------

    # 2. Get Steps
    query_steps = """
        SELECT s.*, c.html_color, c.label_de, c.codepoint
        FROM steps s
        LEFT JOIN step_categories c ON s.category_id = c.id
        WHERE s.recipe_id = ? 
        ORDER BY s.position
    """
    # Hier war der IndentationError - achte darauf, dass async bündig mit den Kommentaren oben ist
    async with db.execute(query_steps, (recipe_id,)) as cursor:
        steps = await cursor.fetchall()
        
    # 3. Aggregate Ingredients
    steps_data = []
    for step in steps:
        s_dict = dict(step)
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
        "is_admin": is_admin
    })