# routers/admin.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
from database import get_db_connection, get_user_context
from template_config import templates

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/categories", response_class=HTMLResponse)
async def manage_categories(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)

    async with db.execute("SELECT * FROM step_categories ORDER BY label_de") as cursor:
        categories = await cursor.fetchall()
    
    return templates.TemplateResponse("admin_categories.html", {
        "request": request,
        "categories": categories,
        **user_ctx
    })

@router.post("/categories/update")
async def update_category(
    request: Request,
    id: int = Form(...),
    label_de: str = Form(...),
    html_color: str = Form(...),
    codepoint: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    await db.execute(
        "UPDATE step_categories SET label_de = ?, html_color = ?, codepoint = ? WHERE id = ?",
        (label_de, html_color, codepoint, id)
    )
    await db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@router.get("/users", response_class=HTMLResponse)
async def manage_users(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ User management page (placeholder) """
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)
    
    # TODO: Implement user management
    return HTMLResponse(content="<h1>User Management</h1><p>Not implemented yet</p>")

@router.get("/paths", response_class=HTMLResponse)
async def manage_paths(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    """ Paths/folders management page (placeholder) """
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)
    
    # TODO: Implement path/folder management
    return HTMLResponse(content="<h1>Path Management</h1><p>Not implemented yet</p>")