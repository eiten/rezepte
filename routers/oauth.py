from datetime import datetime, timezone
import secrets
from urllib.parse import urlencode
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
import aiosqlite

from database import get_db_connection, get_config, get_user_context
from template_config import templates
from routers.auth import pwd_context, SESSION_TTL, get_client_ip

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])

# Initialize OAuth client
oauth = OAuth()

def get_oauth_config():
    """Get OAuth configuration from config.yaml"""
    config = get_config()
    oauth_config = config.get('oauth', {})
    
    if not oauth_config.get('enabled', False):
        return None
    
    return oauth_config

def init_oauth_client():
    """Initialize OAuth client with configuration"""
    oauth_config = get_oauth_config()
    
    if not oauth_config:
        return None
    
    # Use OIDC Discovery for Authelia
    # Authelia supports the .well-known/openid-configuration endpoint
    oauth.register(
        name='authelia',
        client_id=oauth_config['client_id'],
        client_secret=oauth_config['client_secret'],
        server_metadata_url='https://auth.iten.pro/.well-known/openid-configuration',
        client_kwargs={
            'scope': ' '.join(oauth_config['scopes'])
        }
    )
    
    return oauth_config

# Initialize on module load
OAUTH_CONFIG = init_oauth_client()

@router.get("/login")
async def oauth_login(request: Request):
    """Redirect user to OAuth provider for authentication"""
    if not OAUTH_CONFIG:
        raise HTTPException(status_code=503, detail="OAuth is not configured")
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    
    # Build authorization URL
    redirect_uri = OAUTH_CONFIG['redirect_uri']
    
    client = oauth.create_client('authelia')
    return await client.authorize_redirect(request, redirect_uri, state=state)

@router.get("/callback", response_model=None)
async def oauth_callback(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """Handle OAuth callback from provider"""
    if not OAUTH_CONFIG:
        raise HTTPException(status_code=503, detail="OAuth is not configured")
    
    # Verify state to prevent CSRF
    state_from_session = request.session.get('oauth_state')
    state_from_query = request.query_params.get('state')
    
    if not state_from_session or state_from_session != state_from_query:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # Clear state from session
    del request.session['oauth_state']
    
    try:
        # Get access token
        client = oauth.create_client('authelia')
        token = await client.authorize_access_token(request)
        
        # Get user info from Authelia's userinfo endpoint
        # Note: Authelia returns minimal claims in the ID token, but full user info at the userinfo endpoint
        userinfo_resp = await client.get('https://auth.iten.pro/api/oidc/userinfo', token=token)
        userinfo = userinfo_resp.json()
        
        oauth_sub = userinfo.get('sub')
        oauth_email = userinfo.get('email')
        
        if not oauth_sub:
            raise HTTPException(status_code=400, detail="No subject in userinfo")
        
        # Check if this OAuth account is already linked
        async with db.execute(
            "SELECT user_id FROM oauth_links WHERE provider = ? AND subject = ?",
            ('authelia', oauth_sub)
        ) as cursor:
            link = await cursor.fetchone()
        
        if link:
            # Already linked - log in directly
            user_id = link[0]
            
            # Get user details
            async with db.execute(
                "SELECT id, username, display_name, role, is_active FROM users WHERE id = ?",
                (user_id,)
            ) as cursor:
                user = await cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail="Linked user not found")
            
            if not user[4]:  # is_active
                raise HTTPException(status_code=403, detail="Account is deactivated")
            
            # Create session
            session_id = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc).isoformat()
            expires = (datetime.now(timezone.utc) + SESSION_TTL).isoformat()
            
            await db.execute(
                """INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen, user_agent, ip_address)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, now, expires, now,
                 request.headers.get("user-agent", "unknown"),
                 get_client_ip(request))
            )
            await db.commit()
            
            # Set session cookie
            secure_cookie = not get_config().get("debug", False)
            response = RedirectResponse(url=str(request.url_for("index")), status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(
                key="rezepte_session_token",
                value=session_id,
                httponly=True,
                secure=secure_cookie,
                samesite="lax",
                max_age=int(SESSION_TTL.total_seconds())
            )
            
            return response
        
        else:
            # Not linked yet - show linking page
            # Store OAuth info in session for linking process
            request.session['oauth_pending'] = {
                'sub': oauth_sub,
                'email': oauth_email,
                'provider': 'authelia'
            }
            
            # Try to find user by email
            suggested_user = None
            if oauth_email:
                async with db.execute(
                    "SELECT username, display_name FROM users WHERE email = ? AND is_active = 1",
                    (oauth_email,)
                ) as cursor:
                    suggested_user = await cursor.fetchone()
            
            return templates.TemplateResponse("oauth_link.html", {
                "request": request,
                "oauth_email": oauth_email,
                "suggested_username": suggested_user[0] if suggested_user else None,
                "suggested_display_name": suggested_user[1] if suggested_user else None,
                "provider_name": OAUTH_CONFIG['provider_name']
            })
    
    except OAuthError as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

@router.post("/link", response_model=None)
async def link_oauth_account(
    request: Request,
    username: str = Form(...),
    password: str = Form(None),
    auto_link: str = Form(None),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """Link OAuth account to existing local user"""
    # Get pending OAuth info from session
    oauth_pending = request.session.get('oauth_pending')
    if not oauth_pending:
        raise HTTPException(status_code=400, detail="No pending OAuth link")
    
    # Auto-link mode: verify email match only
    if auto_link == "true" and oauth_pending.get('email'):
        async with db.execute(
            "SELECT id, is_active, email FROM users WHERE username = ? AND email = ?",
            (username, oauth_pending['email'])
        ) as cursor:
            user = await cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="Email does not match this account")
        
        if not user[1]:  # is_active
            raise HTTPException(status_code=403, detail="Account is deactivated")
        
        user_id = user[0]
    else:
        # Manual mode: verify username and password
        if not password:
            raise HTTPException(status_code=400, detail="Password required")
        
        async with db.execute(
            "SELECT id, password_hash, is_active, display_name, role FROM users WHERE username = ?",
            (username,)
        ) as cursor:
            user = await cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not user[2]:  # is_active
            raise HTTPException(status_code=403, detail="Account is deactivated")
        
        if not pwd_context.verify(password, user[1]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        user_id = user[0]
    
    # Check if user already has an OAuth link
    async with db.execute(
        "SELECT id FROM oauth_links WHERE user_id = ? AND provider = ?",
        (user_id, oauth_pending['provider'])
    ) as cursor:
        existing_link = await cursor.fetchone()
    
    if existing_link:
        raise HTTPException(status_code=400, detail="This user is already linked to another OAuth account")
    
    # Create the link
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO oauth_links (user_id, provider, subject, email, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, oauth_pending['provider'], oauth_pending['sub'], oauth_pending['email'], now)
    )
    
    # Create session
    session_id = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + SESSION_TTL).isoformat()
    
    await db.execute(
        """INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen, user_agent, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, now, expires, now,
         request.headers.get("user-agent", "unknown"),
         get_client_ip(request))
    )
    
    await db.commit()
    
    # Clear pending OAuth from session
    del request.session['oauth_pending']
    
    # Set session cookie and redirect
    secure_cookie = not get_config().get("debug", False)
    response = RedirectResponse(url=str(request.url_for("index")), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="rezepte_session_token",
        value=session_id,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds())
    )
    
    return response

@router.post("/unlink", response_model=None)
async def unlink_oauth_account(
    request: Request,
    password: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    """Unlink OAuth account from user (requires password confirmation)"""
    user = await get_user_context(request, db)
    if not user or not user.get('user_id'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = user['user_id']
    
    # Verify password
    async with db.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
    
    if not result or not pwd_context.verify(password, result[0]):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Delete OAuth link
    async with db.execute(
        "DELETE FROM oauth_links WHERE user_id = ? AND provider = ?",
        (user_id, 'authelia')
    ) as cursor:
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No OAuth link found")
    
    await db.commit()
    
    return RedirectResponse(url=str(request.url_for("profile")), status_code=status.HTTP_303_SEE_OTHER)
