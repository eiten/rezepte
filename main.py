# main.py
import uvicorn
import os
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import get_config, init_db
from routers import recipes, pdf, auth, admin, oauth
from template_config import templates
from starlette.middleware.sessions import SessionMiddleware

# Load config
config = get_config()

def get_git_version():
    """Gibt das aktuelle Git-Tag oder den Git-Hash zurück"""
    try:
        # Versuche erst ein Tag zu bekommen
        tag = subprocess.check_output(
            ['git', 'describe', '--tags', '--exact-match'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        return tag
    except subprocess.CalledProcessError:
        try:
            # Fallback auf kurzen Hash
            hash_short = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            return f"#{hash_short}"
        except subprocess.CalledProcessError:
            return "dev"

# Git-Version beim Start auslesen
git_version = get_git_version()
print(f"📦 Version: {git_version}")

# Context-Processor für Templates
templates.env.globals['git_version'] = git_version

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alles hier drin wird beim Start ausgeführt
    await init_db() # Jetzt korrekt mit await!
    yield


# App setup
app = FastAPI(
    title=config['app_name'],
    debug=config['debug'],
    root_path=config.get('root_path', ""),
    lifespan=lifespan
)
print(f"App root path: {app.root_path}")

# Add session middleware for OAuth state management
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production'),
    same_site='lax',
    https_only=True
)

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
app.include_router(oauth.router)

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
