# Rezepte-App

Rezeptverwaltung mit FastAPI, SQLite und FTS5 (Volltextsuche). Login mit serverseitigen Sessions, OAuth/OIDC-Integration (z.B. Authelia), PDF-Export via LaTeX, und einem Markdown-ähnlichen Editor für Schritte.

📋 **[Changelog](CHANGELOG.md)** – View version history and release notes

## Kurzfeatures
- Serverseitige Sessions (SQLite `sessions`-Tabelle), Cookie `rezepte_session_token`, Rolling Expiry (7 Tage, wird bei Nutzung verlängert)
- **OAuth/OIDC-Login** (z.B. Authelia): Optional paralleles Login mit OAuth und lokalem Passwort, Account-Verknüpfung mit Email-Matching und Auto-Link
- Volltextsuche über Rezepte/Schritte/Zutaten (SQLite FTS5)
- Admin-Bereich für Kategorien, Pfade, Nutzer
- Profilseite zum Ändern von Anzeigename, E-Mail, Passwort und OAuth-Verknüpfung
- HTML-Rendering und PDF-Export aus demselben Markdown-ähnlichen Text

## Setup (Dev)
1. Abhängigkeiten installieren: `pip install -r requirements.txt`
2. venv starten: `source venv/bin/activate`
2. DB erstellen: `APP_ENV=dev python tools/setup_db.py`
3. Start: `APP_ENV=dev python main.py`

## Starten der produktiven APP:
1. venv sourcen
2. `APP_ENV=prod python main.py`

Alternativ kann auch direkt die app gestartet werden, zum Beispiel aus einer service unit:
```bash
APP_ENV=prod /arbeitsverzeichnis/venv/bin/python /arbeitsverzeichnis/main.py
```

### Tailwind CSS im Entwicklermodus
- Für CSS-Änderungen muss der Watcher laufen, sonst wird `static/css/main.css` nicht neu generiert.
- Watcher starten:

```bash
./tools/watch_css.sh
```

- Der Watcher lauscht auf `static/css/src.css` und schreibt nach `static/css/main.css`.
- In Produktion wird die CSS-Datei nicht automatisch gebaut; der Watcher ist nur für lokale Entwicklung gedacht. 

## Login / Sessions
- Login unter `/auth/login`, Logout unter `/auth/logout`
- Cookie: `rezepte_session_token` (HttpOnly, SameSite=Lax; Secure in prod)
- Sessions liegen in SQLite (`sessions`), können gezielt invalidiert werden

## OAuth/OIDC (Optional)

### Konfiguration
OAuth wird über `config.yaml` konfiguriert. Beispiel für Authelia:

```yaml
oauth:
  enabled: true
  provider_name: "Authelia"              # Anzeigename im UI
  button_text: "Mit Authelia anmelden"   # Button-Text
  client_id: "rezepte-dev"               # OIDC Client ID
  client_secret: "..."                   # OIDC Client Secret
  authorization_url: "https://auth.example.com/api/oidc/authorization"
  token_url: "https://auth.example.com/api/oidc/token"
  userinfo_url: "https://auth.example.com/api/oidc/userinfo"
  redirect_uri: "https://rezepte.example.com/auth/oauth/callback"
  scopes: ["openid", "profile", "email"]
```

Die App nutzt OIDC Discovery (`/.well-known/openid-configuration`) für automatisches Setup von `jwks_uri` etc.

### Funktionsweise
1. **Login-Button**: Auf der Login-Seite erscheint ein OAuth-Button (wenn enabled)
2. **OAuth-Flow**: User wird zum OIDC-Provider weitergeleitet, autorisiert die App
3. **Auto-Verknüpfung**: Wenn Email übereinstimmt, wird der Account automatisch verknüpft (mit Bestätigung)
4. **Manuelle Verknüpfung**: User kann einen anderen lokalen Account mit OAuth verknüpfen (mit Passwort-Bestätigung)
5. **Profil-Management**: Auf der Profilseite kann die OAuth-Verknüpfung angesehen und entfernt werden (mit Passwort-Bestätigung)

### Lokale Accounts und Fallback
- Lokale Accounts (mit Passwort) funktionieren parallel zu OAuth
- Jeder User kann optional einen lokalen UND einen OAuth-Account haben
- Fallback, falls OIDC-Provider ausfällt

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
 - API-URLs in Templates respektieren den `root_path`; z.B. der Hilfe-Dialog lädt Daten über `/api/help` mit Präfix in Dev (`/rezepte`).

## Deployment (Gitea Actions)

Automatisches Deployment wird ausgelöst, wenn ein Tag (`v*`) auf `main` gepusht wird. Die Action verifiziert, dass der Tag auf `main` liegt, führt kurze Smoke-Tests aus, und deployed per SSH auf den Server.

### Repository Secrets (Gitea)
- `DEPLOY_HOST`: Hostname oder IP des Zielservers
- `DEPLOY_USER`: SSH-User auf dem Zielserver
- `DEPLOY_PATH`: Projektpfad auf dem Server (z.B. `/opt/rezepteapp`)
- `DEPLOY_SERVICE`: Systemd-Service-Name (z.B. `rezepte`)
- `DEPLOY_SSH_PRIVATE_KEY`: Privater SSH-Schlüssel (ed25519) für Deployment
- `DEPLOY_KNOWN_HOSTS`: Inhalt der `known_hosts`-Zeile für den Server (optional, empfohlen)

### SSH Deploy-Key (nur für Deployment)
```bash
# Ed25519 Key erzeugen (passwortlos oder mit Deploy-Passwort)
ssh-keygen -t ed25519 -C "rezepteapp-deploy" -f ~/.ssh/rezepteapp_deploy

# Public Key auf dem Server hinterlegen
cat ~/.ssh/rezepteapp_deploy.pub | ssh user@host "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# Secrets im Repository setzen
# DEPLOY_SSH_PRIVATE_KEY = Inhalt von ~/.ssh/rezepteapp_deploy
```

### known_hosts Eintrag ermitteln
```bash
# Fingerprint/Host-Key auslesen und als Secret speichern
ssh-keyscan -H host.example.com
# Inhalt der Zeile als DEPLOY_KNOWN_HOSTS Secret speichern
```

### Systemd ohne Passwort (sudoers)
```bash
# Mit visudo eine begrenzte Regel anlegen
sudo visudo -f /etc/sudoers.d/<username>

# Inhalt (nur spezifische Service-Kommandos erlauben)
<username> ALL=(ALL) NOPASSWD: /bin/systemctl stop rezepte, /bin/systemctl start rezepte, /bin/systemctl restart rezepte
```

### Update-Skript (optional, tag-basiert)
Siehe `tools/update.sh`. Dieses Skript kann serverseitig genutzt werden, um einen Tag auszuchecken und den Service neu zu starten:
```bash
ssh user@host \'/opt/rezepteapp/tools/update.sh v1.1.1\'
```

### Pre-Deploy Smoke-Tests
Die Action führt vor dem Deployment einfache Prüfungen aus:
- Abhängigkeiten installieren (`pip install -r requirements.txt`)
- Datenbank initialisieren (`tools/setup_db.py`) und seeden (`tools/seed_data.py`)
- App lokal mit Uvicorn starten und folgende Seiten abrufen:
	- `/` (Startseite)
	- `/auth/login` (Login-Seite)
	- `/api/help` (Hilfe-API)

Hinweis: Der Seed erzeugt den Nutzer `admin/admin`, sodass ein Login-Test optional möglich wäre. Standardmäßig prüfen wir nur, dass die Seiten fehlerfrei laden.

### Konfiguration
- `config.yaml` ist lokal und wird ignoriert (siehe `config.yaml.example`).
- Für neue Umgebungen `config.yaml.example` kopieren und anpassen.
```
cp config.yaml.example config.yaml
```

### Initialer Server-Bootstrap (einmalig erforderlich)
Damit die Action deployen kann, muss das Zielverzeichnis auf dem Server bereits ein Git-Checkout enthalten und der Systemd-Service existieren.

1. Verzeichnis und Repo vorbereiten
	```bash
	sudo mkdir -p /opt/rezepteapp
	sudo chown $USER:$USER /opt/rezepteapp
	cd /opt/rezepteapp
	# Falls das Repository privat ist: initialer Clone manuell nötig
	git clone https://gitea.iten.pro/edi/rezepte.git .
	git remote -v
	```
	Hinweis: Bei privaten Repos musst du den ersten Clone manuell durchführen (mit persönlichen Token/SSH), damit spätere `git fetch` in der Action funktionieren.

2. Konfiguration anlegen
	```bash
	cp config.yaml.example config.yaml
	# Werte für prod anpassen (Datenbankpfad, root_path, pdf_cache_dir, etc.)
	```

3. Python-Umgebung und Abhängigkeiten
	```bash
	python3 -m venv venv
	source venv/bin/activate
	pip install -r requirements.txt
	```

4. Systemd-Service erstellen (Beispiel)
	```bash
	sudo tee /etc/systemd/system/rezepte.service > /dev/null << 'UNIT'
	[Unit]
	Description=Rezepte App
	After=network.target

	[Service]
	Type=simple
	WorkingDirectory=/opt/rezepteapp
	Environment=APP_ENV=prod
	ExecStart=/opt/rezepteapp/venv/bin/python /opt/rezepteapp/main.py
	Restart=on-failure
	User=<username>

	[Install]
	WantedBy=multi-user.target
	UNIT

	sudo systemctl daemon-reload
	sudo systemctl enable rezepte
	sudo systemctl start rezepte
	```

5. (Optional) TeX installieren für PDF-Export
	```bash
	sudo apt-get update
	sudo apt-get install -y latexmk texlive-latex-extra texlive-luatex texlive-fonts-recommended
	```

Nach diesem Bootstrap kann die Gitea-Action bei Tags (z.B. `v1.1.2`) automatisch deployen.

### Cleanup-Verhalten der Action
- Der Runner räumt nach den Smoke-Tests lokale Artefakte auf (`.venv`, `data/`, `cache/`).
- Auf dem Server wird NICHT das Projektverzeichnis gelöscht; es wird nur `cache/` geleert und der Service neu gestartet.
