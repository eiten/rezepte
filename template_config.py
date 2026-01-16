# template_config.py
# Zentrale Template-Konfiguration für alle Router
from fastapi.templating import Jinja2Templates

# Wird von allen Routern importiert
templates = Jinja2Templates(directory="templates")
