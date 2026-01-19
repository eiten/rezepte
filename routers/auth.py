from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
import aiosqlite
from database import get_db_connection
from template_config import templates

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    # User in DB suchen
    async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
        user = await cursor.fetchone()

    # Passwort prüfen (wir nutzen die Logik aus deiner setup_db.py)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Ungültiger Name oder Passwort"
        })

    # Einfacher Session-Cookie (für den Anfang)
    redirect_url = request.url_for("index")
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_user", value=username, httponly=True)
    return response

@router.get("/logout")
async def logout(request: Request):
    redirect_url = request.url_for("index")
    response = RedirectResponse(url=redirect_url)
    response.delete_cookie("session_user")
    return response