from datetime import datetime, timezone, timedelta
import secrets

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
import aiosqlite
from database import get_db_connection, get_config, get_user_context
from template_config import templates

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_TTL = timedelta(days=7)

def get_client_ip(request: Request) -> str:
    """Extract real client IP from proxy headers or fallback to direct connection."""
    # Try X-Forwarded-For first (comma-separated list, leftmost is original client)
    forwarded_for = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        print(f"[Auth] IP from X-Forwarded-For: {ip}")
        return ip
    
    # Try X-Real-IP as fallback
    real_ip = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real_ip:
        ip = real_ip.strip()
        print(f"[Auth] IP from X-Real-IP: {ip}")
        return ip
    
    # Fallback to direct connection
    fallback = request.client.host if request.client else "unknown"
    print(f"[Auth] IP fallback (no proxy headers): {fallback}")
    return fallback

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    config = get_config()
    oauth_config = config.get('oauth', {})
    return templates.TemplateResponse("login.html", {
        "request": request,
        "oauth_enabled": oauth_config.get('enabled', False),
        "oauth_button_text": oauth_config.get('button_text', 'Mit OAuth anmelden'),
        "provider_name": oauth_config.get('provider_name', 'OAuth')
    })

@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    # Find user in database
    async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
        user = await cursor.fetchone()

    # Verify password
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Invalid username or password"
        })

    if not user["is_active"]:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Account is inactive"
        })

    # Create session row
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + SESSION_TTL

    # Debug: Log all request info
    print(f"\n=== Login Debug ===")
    print(f"request.client: {request.client}")
    print(f"request.client.host: {request.client.host if request.client else 'None'}")
    print(f"All headers:")
    for key, value in request.headers.items():
        print(f"  {key}: {value}")
    print(f"==================\n")

    user_agent = request.headers.get("user-agent", "")
    ip_address = get_client_ip(request)

    await db.execute(
        """
        INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen, user_agent, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            user["id"],
            now.isoformat(),
            expires.isoformat(),
            now.isoformat(),
            user_agent,
            ip_address,
        ),
    )
    await db.commit()

    # Set session cookie
    redirect_url = request.url_for("index")
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    secure_cookie = not get_config().get("debug", False)
    response.set_cookie(
        key="rezepte_session_token",
        value=session_id,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )
    # Clear legacy cookies if still present
    response.delete_cookie("session_user")
    response.delete_cookie("session_token")
    return response

@router.get("/logout")
async def logout(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    redirect_url = request.url_for("index")
    response = RedirectResponse(url=redirect_url)
    session_id = request.cookies.get("rezepte_session_token")
    if session_id:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
    response.delete_cookie("rezepte_session_token")
    response.delete_cookie("session_token")
    response.delete_cookie("session_user")
    return response


@router.get("/profile", response_class=HTMLResponse, name="profile")
async def profile_page(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["user_id"]:
        return RedirectResponse(url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER)

    async with db.execute("SELECT username, display_name, email, password_hash FROM users WHERE id = ?", (user_ctx["user_id"],)) as cursor:
        user = await cursor.fetchone()

    if not user:
        return RedirectResponse(url=request.url_for("logout"), status_code=status.HTTP_303_SEE_OTHER)

    # Check for OAuth link
    oauth_link = None
    async with db.execute(
        "SELECT provider, email, created_at FROM oauth_links WHERE user_id = ?",
        (user_ctx["user_id"],)
    ) as cursor:
        link_row = await cursor.fetchone()
        if link_row:
            oauth_link = {
                "provider": link_row["provider"],
                "email": link_row["email"],
                "created_at": link_row["created_at"]
            }
    
    # Get OAuth config for provider name
    config = get_config()
    oauth_config = config.get('oauth', {})

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "display_name": user["display_name"],
            "email": user["email"] or "",
            "oauth_link": oauth_link,
            "oauth_enabled": oauth_config.get('enabled', False),
            "provider_name": oauth_config.get('provider_name', 'OAuth'),
            "errors": [],
            "message": None,
            **user_ctx,
        },
    )


@router.post("/profile", response_class=HTMLResponse)
async def profile_update(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(""),
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db_connection),
):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["user_id"]:
        return RedirectResponse(url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER)

    async with db.execute("SELECT username, display_name, email, password_hash FROM users WHERE id = ?", (user_ctx["user_id"],)) as cursor:
        user = await cursor.fetchone()

    if not user:
        return RedirectResponse(url=request.url_for("logout"), status_code=status.HTTP_303_SEE_OTHER)

    errors = []
    display_name = display_name.strip()
    email = email.strip() if email else ""

    if not display_name:
        errors.append("Anzeigename darf nicht leer sein.")

    password_hash = user["password_hash"]
    if new_password or new_password_confirm:
        if not current_password:
            errors.append("Bitte aktuelles Passwort angeben.")
        elif not pwd_context.verify(current_password, password_hash):
            errors.append("Aktuelles Passwort ist falsch.")
        if new_password != new_password_confirm:
            errors.append("Die neuen Passwörter stimmen nicht überein.")
        if new_password and len(new_password) < 8:
            errors.append("Neues Passwort muss mindestens 8 Zeichen haben.")
        if not errors:
            password_hash = pwd_context.hash(new_password)

    if errors:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "username": user["username"],
                "display_name": display_name or user["display_name"],
                "email": email,
                "errors": errors,
                "message": None,
                **user_ctx,
            },
        )

    await db.execute(
        "UPDATE users SET display_name = ?, email = ?, password_hash = ? WHERE id = ?",
        (display_name, email or None, password_hash, user_ctx["user_id"]),
    )
    await db.commit()

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user["username"],
            "display_name": display_name,
            "email": email,
            "errors": [],
            "message": "Profil aktualisiert.",
            **user_ctx,
        },
    )