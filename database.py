# database.py
import os
import yaml
import aiosqlite
import sqlite3
from functools import lru_cache

SCHEMA_VERSION = 3

async def init_db():
    """
    Checks the database schema version and applies migrations if necessary.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS db_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        async with db.execute("SELECT value FROM db_metadata WHERE key = 'schema_version'") as cursor:
            row = await cursor.fetchone()
            current_version = int(row[0]) if row else 0

        if current_version < 1:
            print("Migrating to Schema v1: Initial setup...")
            await db.execute("INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('schema_version', '1')")
            current_version = 1

        if current_version < 2:
            print("Migrating to Schema v2: Adding 'is_active' to users...")
            try:
                await db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            except Exception as e:
                print(f"Note: Could not add column (maybe already exists): {e}")
            
            await db.execute("UPDATE db_metadata SET value = '2' WHERE key = 'schema_version'")
            current_version = 2

        if current_version < 3:
            print("Migrating to Schema v3: Adding 'email' to users...")
            try:
                await db.execute("ALTER TABLE users ADD COLUMN email TEXT")
            except Exception as e:
                print(f"Note: Could not add column (maybe already exists): {e}")
            
            await db.execute("UPDATE db_metadata SET value = '3' WHERE key = 'schema_version'")
            current_version = 3

        await db.commit()
        print(f"Database schema is up to date at version {current_version}.")

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
