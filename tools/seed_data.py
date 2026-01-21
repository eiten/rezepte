import sqlite3
import yaml
import os

def get_db_path():
    env = os.getenv("APP_ENV", "dev")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")

    with open(config_path, "r") as f:
        full_config = yaml.safe_load(f)
    config = {**full_config['common'], **full_config[env]}
    db_url = config['database_url']
    if "sqlite+aiosqlite:///" in db_url:
        return db_url.replace("sqlite+aiosqlite:///", "")
    return db_url.replace("sqlite:///", "")

def seed_test_data():
    db_path = get_db_path()
    print(f"--> Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- 1. Hilfs-Daten holen (Units, Categories, User) ---
    
    # Units Mapping: {'g': 1, 'kg': 2, ...}
    cursor.execute("SELECT symbol, id FROM units")
    u = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Categories Mapping: {'default': 1, 'warning': 2, ...}
    cursor.execute("SELECT name, id FROM step_categories")
    c = {row[0]: row[1] for row in cursor.fetchall()}

    # Owner ID holen (Wir nehmen den ersten Admin oder User)
    cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    user_row = cursor.fetchone()
    if not user_row:
        print("Fehler: Kein User gefunden! Bitte erst setup_db.py ausführen.")
        conn.close()
        return
    owner_id = user_row[0]

    # ==========================================
    # REZEPT: Ultimativer PDF-Testlauf
    # ==========================================
    print(f"--> Inserting 'Ultimate Test Recipe' for Owner ID {owner_id}...")
    
    preamble_text = (
        "Dies ist ein generiertes Testrezept, um alle Funktionen des PDF-Exports zu prüfen. "
        "Es enthält Warnungen, Tipps, Varianten, Markdown-Formatierungen (**Fett**, *Kursiv*) "
        "und alle Arten von Einheiten."
    )
    
    # Check if recipe already exists (um Dopplungen zu vermeiden, da wir nicht mehr löschen)
    cursor.execute("SELECT id FROM recipes WHERE name = ?", ('Ultimativer PDF-Testlauf: Alles auf einmal',))
    if cursor.fetchone():
        print("--> Rezept existiert bereits. Überspringe Insert.")
        conn.close()
        return

    cursor.execute("""
        INSERT INTO recipes (name, author, source, preamble, owner_id) 
        VALUES (?, ?, ?, ?, ?)
    """, ('Ultimativer PDF-Testlauf: Alles auf einmal', 'Dev Team', 'Internes Testing Lab', preamble_text, owner_id))
    
    recipe_id = cursor.lastrowid

    # ------------------------------------------------
    # SCHRITT 1: Standard
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('default', 1), 1, 
          "Zuerst die trockenen Zutaten mischen. Dabei darauf achten, dass **keine Klümpchen** entstehen."))
    s1 = cursor.lastrowid
    
    # KORREKTUR: Mehl und Note getrennt
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, amount_max, item, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (s1, u.get('g'), 1, 400, 450, "Mehl", "Type 405"))
    
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item, note) VALUES (?, ?, ?, ?, ?, ?)",
                   (s1, u.get('TL'), 2, 2, "Backpulver", "gestrichen"))

    # ------------------------------------------------
    # SCHRITT 2: Info (Icon)
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('info', 1), 2, 
          "Der Backofen sollte jetzt auf **180°C** (Umluft) vorgeheizt werden. Ober-/Unterhitze benötigt ca. **200°C**."))

    # ------------------------------------------------
    # SCHRITT 3: Standard (Viele kleine Zutaten)
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('default', 1), 3, "Nun die flüssigen Zutaten verquirlen."))
    s3 = cursor.lastrowid
    
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (s3, u.get('ml'), 1, 250, "Milch"))
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (s3, u.get('Stk.'), 2, 3, "Eier"))
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item) VALUES (?, ?, ?, ?, ?)",
                   (s3, u.get('Prise'), 3, 1, "Salz"))

    # ------------------------------------------------
    # SCHRITT 4: Warnung
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('warning', 1), 4, 
          "Die Masse darf **nicht kochen**! Wenn sie zu heiß wird, gerinnt das Ei und der Teig ist ruiniert."))

    # ------------------------------------------------
    # SCHRITT 5: Langer Text
    # ------------------------------------------------
    long_text = (
        "Den Teig in eine gefettete Form geben. Nun kommt der geduldige Teil: "
        "Den Teig mindestens 45 Minuten ruhen lassen. In dieser Zeit kann man die Küche aufräumen "
        "oder einen Kaffee trinken. Nach der Ruhezeit den Teig nochmals kurz durchrühren. "
        "Er sollte jetzt leichte Blasen werfen und eine zähflüssige Konsistenz haben."
    )
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('default', 1), 5, long_text))
    s5 = cursor.lastrowid
    
    cursor.execute("INSERT INTO ingredients (step_id, unit_id, position, amount_min, item, note) VALUES (?, ?, ?, ?, ?, ?)",
                   (s5, u.get('EL'), 1, 1, "Butter", "für die Form"))

    # ------------------------------------------------
    # SCHRITT 6: Variante
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('variation', 1), 6, 
          "Für eine **vegane Variante**: Eier durch Apfelmus ersetzen und Mandelmilch statt Kuhmilch verwenden."))

    # ------------------------------------------------
    # SCHRITT 7: Tipp
    # ------------------------------------------------
    cursor.execute("""
        INSERT INTO steps (recipe_id, category_id, position, markdown_text) 
        VALUES (?, ?, ?, ?)
    """, (recipe_id, c.get('tip', 1), 7, 
          "Schmeckt am besten frisch aus dem Ofen mit etwas Puderzucker bestreut."))

    conn.commit()
    conn.close()
    print("--> Test Data seeded successfully.")

if __name__ == "__main__":
    seed_test_data()