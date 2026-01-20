# main.py
import uvicorn
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import get_config
from routers import recipes, pdf, auth, admin

# Load config
config = get_config()

# App setup
app = FastAPI(
    title=config['app_name'],
    debug=config['debug'],
    root_path=config.get('root_path', "")
)
print(f"App root path: {app.root_path}")

# Static files
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Pfad zu deiner konvertierten ICO-Datei
    file_path = os.path.join("static", "favicon.ico")
    return FileResponse(file_path)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(recipes.router)
app.include_router(admin.router)
app.include_router(pdf.router)
app.include_router(auth.router)

if __name__ == "__main__":
    print(f"🚀 Starting on port {config['port']}...")
    uvicorn.run(
        "main:app",
        host=config['host'],
        port=config['port'],
        reload=config['reload'],
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
