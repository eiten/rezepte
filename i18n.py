import os
from babel.support import Translations
from babel.messages import pofile, mofile

from database import get_config

LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
DOMAIN = "messages"
DEFAULT_LANG = "de"


def get_locale() -> str:
    config = get_config()
    return config.get("lang", DEFAULT_LANG)


def _ensure_compiled(locale: str) -> None:
    po_path = os.path.join(LOCALES_DIR, locale, "LC_MESSAGES", f"{DOMAIN}.po")
    mo_path = os.path.join(LOCALES_DIR, locale, "LC_MESSAGES", f"{DOMAIN}.mo")

    if not os.path.exists(po_path):
        return

    po_mtime = os.path.getmtime(po_path)
    mo_mtime = os.path.getmtime(mo_path) if os.path.exists(mo_path) else 0

    if po_mtime <= mo_mtime:
        return

    with open(po_path, "r", encoding="utf-8") as po_file:
        catalog = pofile.read_po(po_file)

    with open(mo_path, "wb") as mo_file:
        mofile.write_mo(mo_file, catalog)


def get_translations() -> Translations:
    locale = get_locale()
    _ensure_compiled(locale)

    try:
        return Translations.load(LOCALES_DIR, locales=[locale], domain=DOMAIN)
    except Exception:
        if locale != DEFAULT_LANG:
            _ensure_compiled(DEFAULT_LANG)
            return Translations.load(LOCALES_DIR, locales=[DEFAULT_LANG], domain=DOMAIN)
        return Translations.load(LOCALES_DIR, locales=[DEFAULT_LANG], domain=DOMAIN)
