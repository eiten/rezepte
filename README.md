# Recipe App

🇩🇪 [Deutsch](README.de.md) | 🇬🇧 [English](README.md)

Recipe management system with FastAPI, SQLite and FTS5 (full-text search). Login with server-side sessions, OAuth/OIDC integration (e.g. Authelia), PDF export via LaTeX, and a Markdown-like editor for recipe steps.

📋 **[Changelog](CHANGELOG.md)** – View version history and release notes

## Key Features
- Server-side sessions (SQLite `sessions` table), cookie `rezepte_session_token`, rolling expiry (7 days, extended on use)
- **OAuth/OIDC login** (e.g. Authelia): Optional parallel login with OAuth and local password, account linking with email matching and auto-link
- Full-text search across recipes/steps/ingredients (SQLite FTS5)
- Admin area for categories, paths, users
- Profile page for changing display name, email, password, and OAuth linking
- HTML rendering and PDF export from the same Markdown-like text

## Setup (Dev)
1. Install dependencies: `pip install -r requirements.txt`
2. Start venv: `source venv/bin/activate`
3. Create DB: `APP_ENV=dev python tools/setup_db.py`
4. Start: `APP_ENV=dev python main.py`

## Starting the Production App:
1. Source venv
2. `APP_ENV=prod python main.py`

Alternatively, the app can be started directly, for example from a service unit:
```bash
APP_ENV=prod /working-directory/venv/bin/python /working-directory/main.py
```

### Tailwind CSS in Development Mode
- For CSS changes, the watcher must be running, otherwise `static/css/main.css` won't be regenerated.
- Start watcher:

```bash
./tools/watch_css.sh
```

- The watcher listens to `static/css/src.css` and writes to `static/css/main.css`.
- In production, the CSS file is not built automatically; the watcher is only for local development.

## Login / Sessions
- Login at `/auth/login`, logout at `/auth/logout`
- Cookie: `rezepte_session_token` (HttpOnly, SameSite=Lax; Secure in prod)
- Sessions are stored in SQLite (`sessions`), can be invalidated individually

## OAuth/OIDC (Optional)

### Configuration
OAuth is configured via `config.yaml`. Example for Authelia:

```yaml
oauth:
  enabled: true
  provider_name: "Authelia"              # Display name in UI
  button_text: "Sign in with Authelia"   # Button text
  client_id: "rezepte-dev"               # OIDC Client ID
  client_secret: "..."                   # OIDC Client Secret
  authorization_url: "https://auth.example.com/api/oidc/authorization"
  token_url: "https://auth.example.com/api/oidc/token"
  userinfo_url: "https://auth.example.com/api/oidc/userinfo"
  redirect_uri: "https://rezepte.example.com/auth/oauth/callback"
  scopes: ["openid", "profile", "email"]
```

The app uses OIDC Discovery (`/.well-known/openid-configuration`) for automatic configuration of OIDC endpoints.

### How it Works
1. **Login Button**: An OAuth button appears on the login page (when `enabled: true`)
2. **OAuth Flow**: User is redirected to the OIDC provider and authenticates there
3. **Account Linking**: 
   - If the email address matches a local account, a "Link directly" button is displayed
   - Alternatively, the user can specify a different local account and link with password
4. **Profile Management**: On the profile page, the OAuth link can be viewed and removed with password confirmation

### Notes
- Local accounts (with password) work in parallel with OAuth - both login methods can be used simultaneously
- The email address must be provided by the OIDC provider in the `/userinfo` endpoint (for Authelia: LDAP backend recommended)
- Each user can optionally have both a local AND an OAuth account
- Fallback in case OIDC provider fails

## Markdown/Editor Syntax
The step texts support a lean set of markings. They apply to both HTML and LaTeX (PDF). Special cases are processed first (quantities/units), then Markdown/emoticons.

### Quantities & Units
- `[8g]` → 8 g
- `[2-8 g]` → 2–8 g
- `[4x6 cm]` → 4×6 cm
- Decimal separators `,` or `.` are allowed; output uses `,`
- Supported units come from the `units` table (e.g. g, kg, ml, l, dl, °C, EL, TL, Prise, Msp., Stk., Pkg., Tr.)

### Markdown Basics
- Bold: `**Text**`
- Italic: `*Text*`
- Superscript/subscript: `^super^`, `_sub_`
- Line break: single line → `<br>` / `\newline`; double blank line → larger spacing
- Double minus `--` → En-dash (–) in HTML
- Quotes are converted to Swiss guillemets (« »)

### Emoticon Shortcuts (Phosphor Icons)
- `:)` → Smiley
- `:(` → Sad
- `;)` → Wink
- `(y)` → Thumbs Up
- `<3` → Heart
- `!!` → Warning
- `@@` → Clock
- `!t` → Thermometer
- `PP` → Users/People

### Ingredient Quantities in Text
- Quantities can be placed directly in square brackets in the step text, are automatically formatted and correctly output in PDF with siunitx.

## PDF
- PDF export uses LaTeX; the same Markdown/emoticon rules are converted to LaTeX (Bold/Italic, Superscript/Subscript, Quantities/Units, Icons as `\picon{...}`)

## Admin/Profile
- Profile: Change display name, email, password at `/auth/profile`
- Admin: Manage categories, paths, users

## Notes
- IP logging behind sslh/Caddy currently shows 127.0.0.1; sessions work nonetheless.
- Root path (prod) is `/rezepte` (see `config.yaml`).
- API URLs in templates respect the `root_path`; e.g., the help dialog loads data via `/api/help` with prefix in Dev (`/rezepte`).

## Deployment (Gitea Actions)

Automatic deployment is triggered when a tag (`v*`) is pushed to `main`. The action verifies that the tag is on `main`, runs quick smoke tests, and deploys via SSH to the server.

### Repository Secrets (Gitea)
- `DEPLOY_HOST`: Hostname or IP of the target server
- `DEPLOY_USER`: SSH user on the target server
- `DEPLOY_PATH`: Project path on the server (e.g. `/opt/rezepteapp`)
- `DEPLOY_SERVICE`: Systemd service name (e.g. `rezepte`)
- `DEPLOY_SSH_PRIVATE_KEY`: Private SSH key (ed25519) for deployment
- `DEPLOY_KNOWN_HOSTS`: Content of the `known_hosts` line for the server (optional, recommended)

### SSH Deploy Key (for deployment only)
```bash
# Generate Ed25519 key (passwordless or with deploy password)
ssh-keygen -t ed25519 -C "rezepteapp-deploy" -f ~/.ssh/rezepteapp_deploy

# Add public key to server
cat ~/.ssh/rezepteapp_deploy.pub | ssh user@host "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# Set secrets in repository
# DEPLOY_SSH_PRIVATE_KEY = Content of ~/.ssh/rezepteapp_deploy
```

### Get known_hosts Entry
```bash
# Read fingerprint/host key and save as secret
ssh-keyscan -H host.example.com
# Save line content as DEPLOY_KNOWN_HOSTS secret
```

### Systemd without Password (sudoers)
```bash
# Create limited rule with visudo
sudo visudo -f /etc/sudoers.d/<username>

# Content (only allow specific service commands)
<username> ALL=(ALL) NOPASSWD: /bin/systemctl stop rezepte, /bin/systemctl start rezepte, /bin/systemctl restart rezepte
```

### Update Script (optional, tag-based)
See `tools/update.sh`. This script can be used server-side to check out a tag and restart the service:
```bash
ssh user@host '/opt/rezepteapp/tools/update.sh v1.1.1'
```

### Pre-Deploy Smoke Tests
The action runs simple checks before deployment:
- Install dependencies (`pip install -r requirements.txt`)
- Initialize database (`tools/setup_db.py`) and seed (`tools/seed_data.py`)
- Start app locally with Uvicorn and fetch the following pages:
	- `/` (Home page)
	- `/auth/login` (Login page)
	- `/api/help` (Help API)

Note: The seed creates user `admin/admin`, so a login test would be optionally possible. By default we only check that pages load without errors.

### Configuration
- `config.yaml` is local and ignored (see `config.yaml.example`).
- For new environments copy `config.yaml.example` and adapt.
```
cp config.yaml.example config.yaml
```

### Initial Server Bootstrap (required once)
For the action to deploy, the target directory on the server must already contain a Git checkout and the systemd service must exist.

1. Prepare directory and repo
	```bash
	sudo mkdir -p /opt/rezepteapp
	sudo chown $USER:$USER /opt/rezepteapp
	cd /opt/rezepteapp
	# If repository is private: manual initial clone required
	git clone https://gitea.iten.pro/edi/rezepte.git .
	git remote -v
	```
	Note: For private repos you must perform the first clone manually (with personal token/SSH) so later `git fetch` in the action works.

2. Create configuration
	```bash
	cp config.yaml.example config.yaml
	# Adapt values for prod (database path, root_path, pdf_cache_dir, etc.)
	```

3. Python environment and dependencies
	```bash
	python3 -m venv venv
	source venv/bin/activate
	pip install -r requirements.txt
	```

4. Create systemd service (example)
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

5. (Optional) Install TeX for PDF export
	```bash
	sudo apt-get update
	sudo apt-get install -y latexmk texlive-latex-extra texlive-luatex texlive-fonts-recommended
	```

After this bootstrap, the Gitea action can automatically deploy on tags (e.g. `v1.1.2`).

### Cleanup Behavior of Action
- The runner cleans up local artifacts after smoke tests (`.venv`, `data/`, `cache/`).
- On the server, the project directory is NOT deleted; only `cache/` is cleared and the service restarted.

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License** (CC BY-NC-SA 4.0).

[![CC BY-NC-SA 4.0](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

### You are free to:
- **Share** — copy and redistribute the material in any medium or format
- **Adapt** — remix, transform, and build upon the material

### Under the following terms:
- **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made
- **NonCommercial** — You may not use the material for commercial purposes
- **ShareAlike** — If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original

See the [LICENSE](LICENSE) file for the full license text.
