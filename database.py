# database.py
import os
import yaml
import aiosqlite
import sqlite3
from functools import lru_cache

SCHEMA_VERSION = 5

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

            # FTS5 virtual table (contentless; rowid = recipe_id)
            await db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts USING fts5(
                    name,
                    author,
                    source,
                    preamble,
                    ingredients,
                    steps,
                    content=''
                )
                """
            )

            # Drop old triggers to ensure idempotency when rerunning migrations
            trigger_names = [
                "recipe_fts_ai", "recipe_fts_au", "recipe_fts_ad",
                "recipe_fts_steps_ai", "recipe_fts_steps_au", "recipe_fts_steps_ad",
                "recipe_fts_ing_ai", "recipe_fts_ing_au", "recipe_fts_ing_ad"
            ]
            for t in trigger_names:
                await db.execute(f"DROP TRIGGER IF EXISTS {t}")

            # Helper SQL fragments (inline in triggers)
            ingredients_subquery = """
                (SELECT group_concat(item || ' ' || COALESCE(note,''), ' ')
                 FROM (
                     SELECT i.item, i.note
                     FROM ingredients i
                     JOIN steps s ON i.step_id = s.id
                     WHERE s.recipe_id = R.id
                     ORDER BY s.position, i.position
                 ))
            """

            steps_subquery = """
                (SELECT group_concat(markdown_text, ' ')
                 FROM (
                     SELECT markdown_text
                     FROM steps
                     WHERE recipe_id = R.id
                     ORDER BY position
                 ))
            """

            # Trigger bodies reuse the same INSERT ... SELECT pattern via literal SQL
            insert_select_sql = f"""
                INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
                SELECT
                    R.id,
                    COALESCE(R.name, ''),
                    COALESCE(R.author, ''),
                    COALESCE(R.source, ''),
                    COALESCE(R.preamble, ''),
                    COALESCE({ingredients_subquery}, ''),
                    COALESCE({steps_subquery}, '')
                FROM recipes R
                WHERE R.id = :recipe_id;
            """

            # Recipes INSERT
            await db.execute(
                f"""
                CREATE TRIGGER recipe_fts_ai AFTER INSERT ON recipes BEGIN
                    INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.id);
                    {insert_select_sql.replace(':recipe_id', 'NEW.id')}
                END;
                """
            )

            # Recipes UPDATE
            await db.execute(
                f"""
                CREATE TRIGGER recipe_fts_au AFTER UPDATE ON recipes BEGIN
                    INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.id);
                    {insert_select_sql.replace(':recipe_id', 'NEW.id')}
                END;
                """
            )

            # Recipes DELETE
            await db.execute(
                """
                CREATE TRIGGER recipe_fts_ad AFTER DELETE ON recipes BEGIN
                    INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', OLD.id);
                END;
                """
            )

            # Steps INSERT/UPDATE/DELETE → recompute owning recipe
            for trigger_name, timing, ref in [
                ("recipe_fts_steps_ai", "INSERT", "NEW.recipe_id"),
                ("recipe_fts_steps_au", "UPDATE", "NEW.recipe_id"),
                ("recipe_fts_steps_ad", "DELETE", "OLD.recipe_id")
            ]:
                await db.execute(
                    f"""
                    CREATE TRIGGER {trigger_name} AFTER {timing} ON steps BEGIN
                        INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', {ref});
                        {insert_select_sql.replace(':recipe_id', ref)}
                    END;
                    """
                )

            # Ingredients INSERT/UPDATE/DELETE → recompute owning recipe
            for trigger_name, timing, ref in [
                ("recipe_fts_ing_ai", "INSERT", "(SELECT recipe_id FROM steps WHERE id = NEW.step_id)"),
                ("recipe_fts_ing_au", "UPDATE", "(SELECT recipe_id FROM steps WHERE id = NEW.step_id)"),
                ("recipe_fts_ing_ad", "DELETE", "(SELECT recipe_id FROM steps WHERE id = OLD.step_id)")
            ]:
                await db.execute(
                    f"""
                    CREATE TRIGGER {trigger_name} AFTER {timing} ON ingredients BEGIN
                        INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', {ref});
                        {insert_select_sql.replace(':recipe_id', ref)}
                    END;
                    """
                )

            # Backfill existing data
            await db.execute("INSERT INTO recipe_fts(recipe_fts) VALUES('delete-all')")
            await db.execute(
                f"""
                INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
                SELECT
                    R.id,
                    COALESCE(R.name, ''),
                    COALESCE(R.author, ''),
                    COALESCE(R.source, ''),
                    COALESCE(R.preamble, ''),
                    COALESCE({ingredients_subquery.replace('R.id', 'R.id')}, ''),
                    COALESCE({steps_subquery.replace('R.id', 'R.id')}, '')
                FROM recipes R;
                """
            )

            await db.execute("UPDATE db_metadata SET value = '5' WHERE key = 'schema_version'")
            current_version = 5

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
