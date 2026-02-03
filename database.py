# database.py
import os
import yaml
import aiosqlite
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta
from functools import lru_cache

SCHEMA_VERSION = 7

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

        if current_version < 4:
            print("Migrating to Schema v4: Ensuring root folder exists...")
            # Prüfen, ob überhaupt ein Ordner existiert
            async with db.execute("SELECT COUNT(*) FROM folders") as cursor:
                count = await cursor.fetchone()
                if count[0] == 0:
                    await db.execute("INSERT INTO folders (name) VALUES ('Hauptverzeichnis')")
            
            await db.execute("UPDATE db_metadata SET value = '4' WHERE key = 'schema_version'")
            current_version = 4

        if current_version < 5:
            print("Migrating to Schema v5: Adding recipe full-text search (FTS5)...")

            trigger_names = [
                "recipe_fts_ai", "recipe_fts_au", "recipe_fts_ad",
                "recipe_fts_steps_ai", "recipe_fts_steps_au", "recipe_fts_steps_ad",
                "recipe_fts_ing_ai", "recipe_fts_ing_au", "recipe_fts_ing_ad"
            ]
            for t in trigger_names:
                await db.execute(f"DROP TRIGGER IF EXISTS {t}")

            await db.execute("DROP TABLE IF EXISTS recipe_fts")
            await db.execute(
                """
                CREATE VIRTUAL TABLE recipe_fts USING fts5(
                    name,
                    author,
                    source,
                    preamble,
                    ingredients,
                    steps
                );
                """
            )

            await db.executescript(
                """
                -- Recipes INSERT
                CREATE TRIGGER recipe_fts_ai AFTER INSERT ON recipes
                BEGIN
                    INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
                    VALUES(
                        NEW.id,
                        COALESCE(NEW.name, ''),
                        COALESCE(NEW.author, ''),
                        COALESCE(NEW.source, ''),
                        COALESCE(NEW.preamble, ''),
                        '',
                        ''
                    );
                END;

                -- Recipes UPDATE
                CREATE TRIGGER recipe_fts_au AFTER UPDATE ON recipes
                BEGIN
                    UPDATE recipe_fts SET
                        name = COALESCE(NEW.name, ''),
                        author = COALESCE(NEW.author, ''),
                        source = COALESCE(NEW.source, ''),
                        preamble = COALESCE(NEW.preamble, '')
                    WHERE rowid = NEW.id;
                END;

                -- Recipes DELETE
                CREATE TRIGGER recipe_fts_ad AFTER DELETE ON recipes
                BEGIN
                    DELETE FROM recipe_fts WHERE rowid = OLD.id;
                END;

                -- Steps INSERT/UPDATE
                CREATE TRIGGER recipe_fts_steps_ai AFTER INSERT ON steps
                BEGIN
                    UPDATE recipe_fts SET steps = 
                        COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
                            SELECT markdown_text FROM steps WHERE recipe_id = NEW.recipe_id ORDER BY position
                        )), '')
                    WHERE rowid = NEW.recipe_id;
                END;

                CREATE TRIGGER recipe_fts_steps_au AFTER UPDATE ON steps
                BEGIN
                    UPDATE recipe_fts SET steps = 
                        COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
                            SELECT markdown_text FROM steps WHERE recipe_id = NEW.recipe_id ORDER BY position
                        )), '')
                    WHERE rowid = NEW.recipe_id;
                END;

                -- Steps DELETE
                CREATE TRIGGER recipe_fts_steps_ad AFTER DELETE ON steps
                BEGIN
                    UPDATE recipe_fts SET steps = 
                        COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
                            SELECT markdown_text FROM steps WHERE recipe_id = OLD.recipe_id ORDER BY position
                        )), '')
                    WHERE rowid = OLD.recipe_id;
                END;

                -- Ingredients INSERT/UPDATE/DELETE
                CREATE TRIGGER recipe_fts_ing_ai AFTER INSERT ON ingredients
                BEGIN
                    UPDATE recipe_fts SET ingredients = 
                        COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
                            SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
                            WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id)
                            ORDER BY s.position, i.position
                        )), '')
                    WHERE rowid = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
                END;

                CREATE TRIGGER recipe_fts_ing_au AFTER UPDATE ON ingredients
                BEGIN
                    UPDATE recipe_fts SET ingredients = 
                        COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
                            SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
                            WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id)
                            ORDER BY s.position, i.position
                        )), '')
                    WHERE rowid = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
                END;

                CREATE TRIGGER recipe_fts_ing_ad AFTER DELETE ON ingredients
                BEGIN
                    UPDATE recipe_fts SET ingredients = 
                        COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
                            SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
                            WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = OLD.step_id)
                            ORDER BY s.position, i.position
                        )), '')
                    WHERE rowid = (SELECT recipe_id FROM steps WHERE id = OLD.step_id);
                END;
                """
            )

            await db.execute(
                """
                INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
                SELECT
                    r.id,
                    COALESCE(r.name, ''),
                    COALESCE(r.author, ''),
                    COALESCE(r.source, ''),
                    COALESCE(r.preamble, ''),
                    COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
                        SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
                        WHERE s.recipe_id = r.id ORDER BY s.position, i.position
                    )), ''),
                    COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
                        SELECT markdown_text FROM steps WHERE recipe_id = r.id ORDER BY position
                    )), '')
                FROM recipes r;
                """
            )

            await db.execute("UPDATE db_metadata SET value = '5' WHERE key = 'schema_version'")
            current_version = 5

        if current_version < 6:
            print("Migrating to Schema v6: Adding server-side sessions...")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    user_agent TEXT,
                    ip_address TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            await db.execute("UPDATE db_metadata SET value = '6' WHERE key = 'schema_version'")
            current_version = 6

        if current_version < 7:
            print("Migrating to Schema v7: Adding OAuth links...")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'authelia',
                    subject TEXT NOT NULL,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(provider, subject)
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_oauth_links_user_id ON oauth_links(user_id)")
            await db.execute("UPDATE db_metadata SET value = '7' WHERE key = 'schema_version'")
            current_version = 7

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
    Returns None values if user is not logged in or session is invalid/expired.
    """
    def _anon():
        return {
            "username": None,
            "display_name": None,
            "user_id": None,
            "role": None,
            "is_admin": False,
        }

    session_id = request.cookies.get("rezepte_session_token")
    if not session_id:
        return _anon()

    now = datetime.now(timezone.utc)

    async with db.execute(
        """
        SELECT s.id, s.user_id, s.expires_at, s.last_seen, u.username, u.display_name, u.role, u.is_active
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?
        """,
        (session_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return _anon()

    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
        last_seen = datetime.fromisoformat(row["last_seen"])
    except Exception:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return _anon()

    if expires_at <= now or not row["is_active"]:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return _anon()

    # Touch session with a modest cadence to avoid write on every request
    # Rolling expiry: extend expires_at each time we touch the session
    if now - last_seen > timedelta(minutes=5):
        new_expiry = now + timedelta(days=7)
        await db.execute(
            "UPDATE sessions SET last_seen = ?, expires_at = ? WHERE id = ?",
            (now.isoformat(), new_expiry.isoformat(), session_id)
        )
        await db.commit()

    return {
        "username": row["username"],
        "display_name": row["display_name"],
        "user_id": row["user_id"],
        "role": row["role"],
        "is_admin": row["role"] == "admin",
    }
