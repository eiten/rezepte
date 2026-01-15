# main.py
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import get_config
from routers import recipes, pdf, auth

# Load config
config = get_config()

# App setup
app = FastAPI(title=config['app_name'], debug=config['debug'])

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(recipes.router)
app.include_router(pdf.router)
app.include_router(auth.router)

if __name__ == "__main__":
    print(f"🚀 Starting on port {config['port']}...")
    uvicorn.run("main:app", host=config['host'], port=config['port'], reload=config['reload'])
