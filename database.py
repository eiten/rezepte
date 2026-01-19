# database.py
import os
import yaml
import aiosqlite
from functools import lru_cache

@lru_cache()
def get_config():
    env = os.getenv("APP_ENV", "dev")
    print(f"Loading configuration for environment: {env}")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    
    with open(config_path, "r") as f:
        full_config = yaml.safe_load(f)
    return {**full_config['common'], **full_config[env]}

def get_db_path():
    config = get_config()
    db_url = config['database_url']
    # Clean up path
    path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    
    # If relative path (./data...), make it absolute relative to app root
    if path.startswith("."):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, path)
        
    return os.path.normpath(path)

# Dependency for FastAPI routes
async def get_db_connection():
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db

# User Context Helper
async def get_user_context(request, db: aiosqlite.Connection):
    """
    Returns user context dict with username, display_name, role, and is_admin.
    Returns None values if user is not logged in.
    """
    username = request.cookies.get("session_user")
    
    if not username:
        return {
            "username": None,
            "display_name": None,
            "user_id": None,
            "role": None,
            "is_admin": False
        }
    
    async with db.execute("SELECT id, username, display_name, role FROM users WHERE username = ?", (username,)) as cursor:
        user = await cursor.fetchone()
        
    if not user:
        return {
            "username": None,
            "display_name": None,
            "user_id": None,
            "role": None,
            "is_admin": False
        }
    
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "user_id": user["id"],
        "role": user["role"],
        "is_admin": user["role"] == "admin"
    }
