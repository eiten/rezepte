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
    env = os.getenv("APP_ENV", "development")
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
    
    # --- Tables ---

    # Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT DEFAULT 'guest'
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

    # --- Seeding Data ---
    # 1. Step Categories (Mit deinen neuen Codes!)
    # Warning: E4E0
    # Info: E2CE
    # Variante (Shuffle): E422
    # Tipp (Lightbulb): E2DC
    
    categories_data = [
        (1, 'default', 'Zubereitung', '', 1),
        (2, 'warning', 'Achtung', 'E4E0', 0), 
        (3, 'info', 'Info', 'E2CE', 0),            
        (4, 'variation', 'Variante', 'E422', 0),       
        (5, 'tip', 'Tipp', 'E2DC', 0)               
    ]
    cursor.execute("SELECT count(*) FROM step_categories")
    if cursor.fetchone()[0] == 0:
        print("--> Seeding step categories...")
        cursor.executemany("INSERT INTO step_categories (id, name, label_de, codepoint, is_ingredients) VALUES (?, ?, ?, ?, ?)", categories_data)

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
        ('Packung', 'Pkg.', 'Pkg.', 'text')
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

    conn.commit()
    conn.close()
    print("--> Database initialized successfully.")

if __name__ == "__main__":
    init_db()