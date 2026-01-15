import sqlite3
import yaml
import os

def get_db_path():
    env = os.getenv("APP_ENV", "development")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")

    with open(config_path, "r") as f:
        full_config = yaml.safe_load(f)
    config = {**full_config['common'], **full_config[env]}
    db_url = config['database_url']
    if "sqlite+aiosqlite:///" in db_url:
        return db_url.replace("sqlite+aiosqlite:///", "")
    return db_url.replace("sqlite:///", "")

def seed_leckerli():
    db_path = get_db_path()
    print(f"--> Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Get Unit IDs (We assume standard order from setup)
    # g=1, kg=2, ml=3, l=4, EL=5, TL=6, Prise=7, Stk=8
    
    # 2. Create Recipe
    print("--> Inserting recipe 'Basler Leckerli'...")
    cursor.execute("""
        INSERT INTO recipes (name, author, owner_id) 
        VALUES ('Basler Leckerli', 'Eduard Iten', 1)
    """)
    recipe_id = cursor.lastrowid

    # 3. Add Steps & Ingredients
    
    # --- Step 1 ---
    cursor.execute("INSERT INTO steps (recipe_id, position, markdown_text) VALUES (?, ?, ?)", 
                   (recipe_id, 1, "Honig und Zucker langsam erwärmen. Nicht kochen!"))
    step1_id = cursor.lastrowid
    
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (step1_id, 1, 1, 450, "Honig")) # 1 = g
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (step1_id, 1, 2, 300, "Zucker"))

    # --- Step 2 ---
    cursor.execute("INSERT INTO steps (recipe_id, position, markdown_text) VALUES (?, ?, ?)", 
                   (recipe_id, 2, "Mandeln hacken, Gewürze dazu, alles mischen."))
    step2_id = cursor.lastrowid
    
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item, note) VALUES (?, ?, ?, ?, ?, ?)",
                   (step2_id, 1, 1, 200, "Mandeln", "ungeschält"))
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (step2_id, 1, 2, 100, "Orangeat"))
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (step2_id, 6, 3, 1, "Zimt")) # 6 = TL (simulated)

    # --- Step 3 ---
    cursor.execute("INSERT INTO steps (recipe_id, position, markdown_text) VALUES (?, ?, ?)", 
                   (recipe_id, 3, "Bei **200°C** ca. 15-20 Min backen."))
    
    conn.commit()
    conn.close()
    print("--> Recipe added successfully.")

if __name__ == "__main__":
    seed_leckerli()
