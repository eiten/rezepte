from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
import aiosqlite
from database import get_db_connection, get_user_context
from template_config import templates

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Home page: List all recipes """
    user_ctx = await get_user_context(request, db)
    
    async with db.execute("SELECT id, name, author FROM recipes") as cursor:
        recipes = await cursor.fetchall()
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recipes": recipes,
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
        
    # 4. Aggregate Ingredients
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
        **user_ctx
    })

@router.get("/recipe/{recipe_id}/edit", response_class=HTMLResponse)
async def edit_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Edit recipe page (placeholder) """
    user_ctx = await get_user_context(request, db)
    
    # Check recipe exists and permission
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Only admin or owner can edit
    if not user_ctx["is_admin"] and user_ctx["user_id"] != recipe["owner_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # TODO: Implement edit form
    return HTMLResponse(content=f"<h1>Edit Recipe {recipe_id}</h1><p>Not implemented yet</p>")

@router.get("/recipe/{recipe_id}/delete", response_class=HTMLResponse)
async def delete_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Delete recipe (placeholder) """
    user_ctx = await get_user_context(request, db)
    
    # Check recipe exists and permission
    async with db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Only admin can delete
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403, detail="Only admins can delete recipes")
    
    # TODO: Implement delete confirmation
    return HTMLResponse(content=f"<h1>Delete Recipe {recipe_id}</h1><p>Not implemented yet</p>")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ User profile page (placeholder) """
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["username"]:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    # TODO: Implement profile page
    return HTMLResponse(content=f"<h1>Profile: {user_ctx['display_name']}</h1><p>Not implemented yet</p>")