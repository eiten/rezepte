import sqlite3
import yaml
import os
from passlib.context import CryptContext

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_path():
    """
    Reads the config.yaml to determine the database path.
    """
    env = os.getenv("APP_ENV", "dev")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")

    with open(config_path, "r") as f:
        full_config = yaml.safe_load(f)

    config = {**full_config['common'], **full_config[env]}
    db_url = config['database_url']
    if "sqlite+aiosqlite:///" in db_url:
        path = db_url.replace("sqlite+aiosqlite:///", "")
    else:
        path = db_url.replace("sqlite:///", "")
    return path

def init_db():
    db_path = get_db_path()
    print(f"--> Initializing database at: {db_path}")
    
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 2. Metadata table for schema versioning
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS db_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    
    # --- Tables ---

    # Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT DEFAULT 'guest',
        is_active INTEGER DEFAULT 1,
        email TEXT
    );
    """)

    # Sessions (server-side session store)
    cursor.execute(
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    
    # Units
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        latex_code TEXT NOT NULL,
        type TEXT DEFAULT 'si'
    );
    """)

    # Step Categories (NEU)
    # codepoint: Der Unicode-Codepunkt für das Icon (z.B. "E4E0")
    # is_ingredients: Boolean Flag (1/0), ob hier Zutaten angezeigt werden sollen oder das Icon
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS step_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, 
        label_de TEXT NOT NULL,
        codepoint TEXT,
        html_color TEXT, 
        is_ingredients INTEGER DEFAULT 0
    );
    """)
    
    # Folders
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER,
        name TEXT NOT NULL,
        FOREIGN KEY(parent_id) REFERENCES folders(id)
    );
    """)
    
    # Recipes (Erweitert um 'source' und 'preamble')
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id INTEGER,
        owner_id INTEGER,
        name TEXT NOT NULL,
        author TEXT,
        source TEXT,
        preamble TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(folder_id) REFERENCES folders(id),
        FOREIGN KEY(owner_id) REFERENCES users(id)
    );
    """)
    
    # Steps (Erweitert um 'category_id')
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL DEFAULT 1,
        position INTEGER NOT NULL,
        markdown_text TEXT,
        FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES step_categories(id)
    );
    """)
    
    # Ingredients
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step_id INTEGER NOT NULL,
        unit_id INTEGER,
        position INTEGER NOT NULL,
        amount_min REAL,
        amount_max REAL,
        item TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(step_id) REFERENCES steps(id) ON DELETE CASCADE,
        FOREIGN KEY(unit_id) REFERENCES units(id)
    );
    """)
    
    # Trigger
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS update_recipe_timestamp_after_ingredient_update
    AFTER UPDATE ON ingredients
    BEGIN
        UPDATE recipes 
        SET updated_at = CURRENT_TIMESTAMP 
        WHERE id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
    END;
    """)

    # --- Full-Text Search (FTS5) for recipes ---
    # Always rebuild as a non-contentless FTS table to keep triggers simple.
    trigger_names = [
        "recipe_fts_ai", "recipe_fts_au", "recipe_fts_ad",
        "recipe_fts_steps_ai", "recipe_fts_steps_au", "recipe_fts_steps_ad",
        "recipe_fts_ing_ai", "recipe_fts_ing_au", "recipe_fts_ing_ad"
    ]
    for t in trigger_names:
        cursor.execute(f"DROP TRIGGER IF EXISTS {t}")

    cursor.execute("DROP TABLE IF EXISTS recipe_fts")
    cursor.execute(
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

    cursor.executescript(
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

                -- Steps INSERT/UPDATE/DELETE → refresh steps column
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

                CREATE TRIGGER recipe_fts_steps_ad AFTER DELETE ON steps
                BEGIN
                    UPDATE recipe_fts SET steps = 
                        COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
                            SELECT markdown_text FROM steps WHERE recipe_id = OLD.recipe_id ORDER BY position
                        )), '')
                    WHERE rowid = OLD.recipe_id;
                END;

                -- Ingredients INSERT/UPDATE/DELETE → refresh ingredients column
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

    # --- Seeding Data ---
    # 1. Step Categories (Mit deinen neuen Codes!)
    categories_data = [
        (1, 'default', 'Zubereitung', '', None, 1),              # Kein Hintergrund
        (2, 'warning', 'Achtung', 'E4E0', "#FF0000", 0), 
        (3, 'info', 'Info', 'E2CE', "#006EFF", 0),            
        (4, 'variation', 'Variante', 'E422', "#7B00FF", 0),       
        (5, 'tip', 'Tipp', 'E2DC', "#FFCC00", 0)               
    ]
    cursor.execute("SELECT count(*) FROM step_categories")
    if cursor.fetchone()[0] == 0:
        print("--> Seeding step categories...")
        cursor.executemany("INSERT INTO step_categories (id, name, label_de, codepoint, html_color, is_ingredients) VALUES (?, ?, ?, ?, ?, ?)", categories_data)

    # 2. Units
    units_data = [
        ('Gramm', 'g', r'\gram', 'si'),
        ('Kilogramm', 'kg', r'\kilogram', 'si'),
        ('Milliliter', 'ml', r'\milli\liter', 'si'),
        ('Deziliter', 'dl', r'\deci\liter', 'si'),
        ('Liter', 'l', r'\liter', 'si'),
        ('Grad Celsius', '°C', r'\degreeCelsius', 'si'),
        ('Esslöffel', 'EL', 'EL', 'text'),
        ('Teelöffel', 'TL', 'TL', 'text'),
        ('Prise', 'Prise', 'Prise', 'text'),
        ('Messerspitze', 'Msp.', 'Msp.', 'text'),
        ('Stück', 'Stk.', 'Stk', 'text'),
        ('Packung', 'Pkg.', 'Pkg.', 'text'),
        ('Tropfen', 'Tr.', 'Tr', 'text')
    ]
    cursor.execute("SELECT count(*) FROM units")
    if cursor.fetchone()[0] == 0:
        print("--> Seeding units...")
        cursor.executemany("INSERT INTO units (name, symbol, latex_code, type) VALUES (?, ?, ?, ?)", units_data)

    # 3. Admin User
    cursor.execute("SELECT count(*) FROM users")
    if cursor.fetchone()[0] == 0:
        print("--> Creating default admin user...")
        admin_pass = pwd_context.hash("admin")
        cursor.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            ("admin", admin_pass, "System Admin", "admin")
        )

    # Root folder (v4 behavior)
    cursor.execute("SELECT COUNT(*) FROM folders")
    if cursor.fetchone()[0] == 0:
        print("--> Creating root folder...")
        cursor.execute("INSERT INTO folders (name) VALUES ('Hauptverzeichnis')")

    # Backfill FTS (covers fresh install)
    cursor.execute("DELETE FROM recipe_fts")
    cursor.execute(
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

    # Persist schema version
    cursor.execute(
        "INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('schema_version', '5')"
    )

    conn.commit()
    conn.close()
    print("--> Database initialized successfully.")

if __name__ == "__main__":
    init_db()