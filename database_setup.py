import sqlite3
import yaml
import os
from passlib.context import CryptContext

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_path():
    """
    Reads the config.yaml to determine the database path based on the environment.
    """
    env = os.getenv("APP_ENV", "development")
    
    with open("config.yaml", "r") as f:
        full_config = yaml.safe_load(f)
    
    # Merge config
    config = {**full_config['common'], **full_config[env]}
    
    # Extract path from connection string (e.g., "sqlite+aiosqlite:///./data/recipes.db")
    db_url = config['database_url']
    if "sqlite+aiosqlite:///" in db_url:
        path = db_url.replace("sqlite+aiosqlite:///", "")
    else:
        path = db_url.replace("sqlite:///", "")
        
    return path

def init_db():
    db_path = get_db_path()
    print(f"--> Initializing database at: {db_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Enable Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 2. Create Tables
    
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
    
    # Folders
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER,
        name TEXT NOT NULL,
        FOREIGN KEY(parent_id) REFERENCES folders(id)
    );
    """)
    
    # Recipes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id INTEGER,
        owner_id INTEGER,
        name TEXT NOT NULL,
        author TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(folder_id) REFERENCES folders(id),
        FOREIGN KEY(owner_id) REFERENCES users(id)
    );
    """)
    
    # Steps
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        markdown_text TEXT,
        FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
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
    
    # 3. Create Trigger for Timestamp Update
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS update_recipe_timestamp_after_ingredient_update
    AFTER UPDATE ON ingredients
    BEGIN
        UPDATE recipes 
        SET updated_at = CURRENT_TIMESTAMP 
        WHERE id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
    END;
    """)

    # 4. Seed Data (Initial Data)
    
    # Units
    units_data = [
        ('Gramm', 'g', r'\gram', 'si'),
        ('Kilogramm', 'kg', r'\kilogram', 'si'),
        ('Milliliter', 'ml', r'\milli\liter', 'si'),
        ('Liter', 'l', r'\liter', 'si'),
        ('Esslöffel', 'EL', 'EL', 'text'),
        ('Teelöffel', 'TL', 'TL', 'text'),
        ('Prise', 'Prise', 'Prise', 'text'),
        ('Stück', 'Stk.', '', 'text')
    ]
    
    # Check if units exist, if not, insert them
    cursor.execute("SELECT count(*) FROM units")
    if cursor.fetchone()[0] == 0:
        print("--> Seeding units...")
        cursor.executemany("INSERT INTO units (name, symbol, latex_code, type) VALUES (?, ?, ?, ?)", units_data)

    # Initial Admin User
    cursor.execute("SELECT count(*) FROM users")
    if cursor.fetchone()[0] == 0:
        print("--> Creating default admin user...")
        # WARNING: Change this password later!
        admin_pass = pwd_context.hash("admin")
        cursor.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            ("admin", admin_pass, "System Admin", "admin")
        )
        print("    User 'admin' created with password 'admin'")

    conn.commit()
    conn.close()
    print("--> Database initialized successfully.")

if __name__ == "__main__":
    init_db()
