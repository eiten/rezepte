import os
import yaml
import uvicorn
from fastapi import FastAPI

# 1. Load config
ENV = os.getenv("APP_ENV", "development")

with open("config.yaml", "r") as f:
    full_config = yaml.safe_load(f)

config = {**full_config['common'], **full_config[ENV]}

# 2. start app
app = FastAPI(title=config['app_name'], debug=config['debug'])

@app.get("/")
def read_root():
    return {
        "message": "Hallo Welt!", 
        "mode": ENV, 
        "port": config['port']
    }

# 3. Start server (only when invoked directly)
if __name__ == "__main__":
    print(f"🚀 Starte im {ENV}-Modus auf Port {config['port']}...")
    
    uvicorn.run(
        "main:app", 
        host=config['host'], 
        port=config['port'], 
        reload=config['reload']
    )
