# database.py
import os
import yaml
import aiosqlite
from functools import lru_cache

@lru_cache()
def get_config():
    env = os.getenv("APP_ENV", "development")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    
    with open(config_path, "r") as f:
        full_config = yaml.safe_load(f)
    return {**full_config['common'], **full_config[env]}

def get_db_path():
    config = get_config()
    db_url = config['database_url']
    # Pfad bereinigen
    path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    
    # Wenn relativer Pfad (./data...), dann absolut machen relativ zum App-Root
    if path.startswith("."):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, path)
        
    return os.path.normpath(path)

# Dependency für FastAPI Routen
async def get_db_connection():
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db
