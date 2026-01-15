# routers/recipes.py
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import aiosqlite
from database import get_db_connection # Import from our database module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Home page: List all recipes """
    async with db.execute("SELECT id, name, author FROM recipes") as cursor:
        recipes = await cursor.fetchall()
        
    # Bugfix: We now use the new index.html!
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes
    })

@router.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def read_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Detail view """
    # 1. Get recipe
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
        
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # 2. Get steps
    async with db.execute("SELECT * FROM steps WHERE recipe_id = ? ORDER BY position", (recipe_id,)) as cursor:
        steps = await cursor.fetchall()
        
    # 3. Aggregate ingredients
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
        "steps": steps_data
    })1~# routers/recipes.py
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import aiosqlite
from database import get_db_connection # Import from our database module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Home page: List all recipes """
    async with db.execute("SELECT id, name, author FROM recipes") as cursor:
        recipes = await cursor.fetchall()
        
    # Bugfix: We now use the new index.html!
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes
    })

@router.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def read_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Detail view """
    # 1. Get recipe
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
        
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # 2. Get steps
    async with db.execute("SELECT * FROM steps WHERE recipe_id = ? ORDER BY position", (recipe_id,)) as cursor:
        steps = await cursor.fetchall()
        
    # 3. Aggregate ingredients
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
        "steps": steps_data
    })
