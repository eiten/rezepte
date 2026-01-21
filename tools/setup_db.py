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
    cursor.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts USING fts5(
            name,
            author,
            source,
            preamble,
            ingredients,
            steps,
            content=''
        );
        """
    )

    # Clean existing triggers to avoid duplicates when rerunning setup
    trigger_names = [
        "recipe_fts_ai", "recipe_fts_au", "recipe_fts_ad",
        "recipe_fts_steps_ai", "recipe_fts_steps_au", "recipe_fts_steps_ad",
        "recipe_fts_ing_ai", "recipe_fts_ing_au", "recipe_fts_ing_ad"
    ]
    for t in trigger_names:
        cursor.execute(f"DROP TRIGGER IF EXISTS {t}")

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

    cursor.executescript(
        f"""
        CREATE TRIGGER recipe_fts_ai AFTER INSERT ON recipes BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.id);
            {insert_select_sql.replace(':recipe_id', 'NEW.id')}
        END;

        CREATE TRIGGER recipe_fts_au AFTER UPDATE ON recipes BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.id);
            {insert_select_sql.replace(':recipe_id', 'NEW.id')}
        END;

        CREATE TRIGGER recipe_fts_ad AFTER DELETE ON recipes BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', OLD.id);
        END;

        CREATE TRIGGER recipe_fts_steps_ai AFTER INSERT ON steps BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.recipe_id);
            {insert_select_sql.replace(':recipe_id', 'NEW.recipe_id')}
        END;

        CREATE TRIGGER recipe_fts_steps_au AFTER UPDATE ON steps BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', NEW.recipe_id);
            {insert_select_sql.replace(':recipe_id', 'NEW.recipe_id')}
        END;

        CREATE TRIGGER recipe_fts_steps_ad AFTER DELETE ON steps BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', OLD.recipe_id);
            {insert_select_sql.replace(':recipe_id', 'OLD.recipe_id')}
        END;

        CREATE TRIGGER recipe_fts_ing_ai AFTER INSERT ON ingredients BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', (SELECT recipe_id FROM steps WHERE id = NEW.step_id));
            {insert_select_sql.replace(':recipe_id', '(SELECT recipe_id FROM steps WHERE id = NEW.step_id)')}
        END;

        CREATE TRIGGER recipe_fts_ing_au AFTER UPDATE ON ingredients BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', (SELECT recipe_id FROM steps WHERE id = NEW.step_id));
            {insert_select_sql.replace(':recipe_id', '(SELECT recipe_id FROM steps WHERE id = NEW.step_id)')}
        END;

        CREATE TRIGGER recipe_fts_ing_ad AFTER DELETE ON ingredients BEGIN
            INSERT INTO recipe_fts(recipe_fts, rowid) VALUES('delete', (SELECT recipe_id FROM steps WHERE id = OLD.step_id));
            {insert_select_sql.replace(':recipe_id', '(SELECT recipe_id FROM steps WHERE id = OLD.step_id)')}
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
        ('Liter', 'l', r'\liter', 'si'),
        ('Grad Celsius', '°C', r'\degreeCelsius', 'si'),
        ('Esslöffel', 'EL', 'EL', 'text'),
        ('Teelöffel', 'TL', 'TL', 'text'),
        ('Prise', 'Prise', 'Prise', 'text'),
        ('Messerspitze', 'Msp.', 'Msp.', 'text'),
        ('Stück', 'Stk.', 'Stk', 'text'),
        ('Packung', 'Pkg.', 'Pkg.', 'text'),
        ('Tropfen', 'Tr.', 'Tr.', 'text')
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
    cursor.execute("INSERT INTO recipe_fts(recipe_fts) VALUES('delete-all')")
    cursor.execute(
        f"""
        INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
        SELECT
            R.id,
            COALESCE(R.name, ''),
            COALESCE(R.author, ''),
            COALESCE(R.source, ''),
            COALESCE(R.preamble, ''),
            COALESCE({ingredients_subquery}, ''),
            COALESCE({steps_subquery}, '')
        FROM recipes R;
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