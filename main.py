# main.py
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import get_config
from routers import recipes # Unser neuer Router

# Config laden
config = get_config()

# App Setup
app = FastAPI(title=config['app_name'], debug=config['debug'])

# Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Router einbinden
app.include_router(recipes.router)

if __name__ == "__main__":
    print(f"🚀 Starte auf Port {config['port']}...")
    uvicorn.run("main:app", host=config['host'], port=config['port'], reload=config['reload'])
