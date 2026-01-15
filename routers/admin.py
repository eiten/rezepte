# routers/admin.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
from database import get_db_connection

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# Helper: Check if user is admin based on cookie
async def is_user_admin(request: Request, db: aiosqlite.Connection):
    username = request.cookies.get("session_user")
    if not username:
        return False
    async with db.execute("SELECT role FROM users WHERE username = ?", (username,)) as cursor:
        user = await cursor.fetchone()
        return user and user["role"] == "admin"

@router.get("/categories", response_class=HTMLResponse)
async def manage_categories(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    if not await is_user_admin(request, db):
        return RedirectResponse(url="/", status_code=303)

    async with db.execute("SELECT * FROM step_categories ORDER BY label_de") as cursor:
        categories = await cursor.fetchall()
    
    # We pass is_admin=True because we checked it above
    return templates.TemplateResponse("admin_categories.html", {
        "request": request,
        "categories": categories,
        "is_admin": True 
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
    if not await is_user_admin(request, db):
        raise HTTPException(status_code=403)

    await db.execute(
        "UPDATE step_categories SET label_de = ?, html_color = ?, codepoint = ? WHERE id = ?",
        (label_de, html_color, codepoint, id)
    )
    await db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)