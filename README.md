# Rezepte-App

Rezeptverwaltung mit FastAPI, SQLite und FTS5 (Volltextsuche). Login mit serverseitigen Sessions, PDF-Export via LaTeX, und einem Markdown-ähnlichen Editor für Schritte.

## Kurzfeatures
- Serverseitige Sessions (SQLite `sessions`-Tabelle), Cookie `rezepte_session_token`, Rolling Expiry (7 Tage, wird bei Nutzung verlängert)
- Volltextsuche über Rezepte/Schritte/Zutaten (SQLite FTS5)
- Admin-Bereich für Kategorien, Pfade, Nutzer
- Profilseite zum Ändern von Anzeigename, E-Mail und Passwort
- HTML-Rendering und PDF-Export aus demselben Markdown-ähnlichen Text

## Setup (Dev)
1. Abhängigkeiten installieren: `pip install -r requirements.txt`
2. DB erstellen: `APP_ENV=dev python tools/setup_db.py`
3. Start: `APP_ENV=dev uvicorn main:app --reload`

## Login / Sessions
- Login unter `/auth/login`, Logout unter `/auth/logout`
- Cookie: `rezepte_session_token` (HttpOnly, SameSite=Lax; Secure in prod)
- Sessions liegen in SQLite (`sessions`), können gezielt invalidiert werden

## Markdown/Editor-Syntax
Die Schritt-Texte unterstützen einen schlanken Satz an Markierungen. Sie gelten für HTML und LaTeX (PDF). Spezialfälle werden zuerst verarbeitet (Mengen/Einheiten), dann Markdown/Emoticons.

### Mengen & Einheiten
- `[8g]` → 8 g
- `[2-8 g]` → 2–8 g
- `[4x6 cm]` → 4×6 cm
- Dezimaltrennzeichen `,` oder `.` sind erlaubt; Ausgabe nutzt `,`
- Unterstützte Einheiten kommen aus der `units`-Tabelle (z.B. g, kg, ml, l, dl, °C, EL, TL, Prise, Msp., Stk., Pkg., Tr.)

### Markdown-Basics
- Fett: `**Text**`
- Kursiv: `*Text*`
- Hoch-/Tiefgestellt: `^hoch^`, `_tief_`
- Zeilenumbruch: einzelne Zeile → `<br>` / `\newline`; doppelte Leerzeile → größerer Abstand
- Doppeltminus `--` → En-dash (–) im HTML
- Anführungen werden zu Schweizer Guillemets (« ») konvertiert

### Emoticon-Shortcuts (Phosphor-Icons)
- `:)` → Smiley
- `:(` → Sad
- `;)` → Wink
- `(y)` → Thumbs Up
- `<3` → Heart
- `!!` → Warning
- `@@` → Clock
- `!t` → Thermometer
- `PP` → Users/People

### Zutaten-Mengen im Text
- Im Schritt-Text kann eine Menge direkt in eckigen Klammern stehen, wird automatisch formatiert und im PDF korrekt mit siunitx ausgegeben.

## PDF
- PDF-Export nutzt LaTeX; dieselben Markdown/Emoticon-Regeln werden zu LaTeX umgesetzt (Bold/Italic, Superscript/Subscript, Mengen/Einheiten, Icons als `\picon{...}`)

## Admin/Profil
- Profil: Anzeigename, E-Mail, Passwort ändern unter `/auth/profile`
- Admin: Kategorien, Pfade, Nutzer verwalten

## Hinweise
- IP-Logging ist hinter sslh/Caddy aktuell 127.0.0.1; Sessions funktionieren dennoch.
- Root-Pfad (prod) ist `/rezepte` (siehe `config.yaml`).
