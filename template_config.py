# template_config.py
# Zentrale Template-Konfiguration für alle Router
from fastapi.templating import Jinja2Templates

from i18n import get_translations, get_locale

# Wird von allen Routern importiert
templates = Jinja2Templates(directory="templates")
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_translations(get_translations())
templates.env.globals["current_lang"] = get_locale()
