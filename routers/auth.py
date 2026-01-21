from datetime import datetime, timezone, timedelta
import secrets

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
import aiosqlite
from database import get_db_connection, get_config
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
    return templates.TemplateResponse("login.html", {"request": request})

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