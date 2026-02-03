# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **OAuth/OIDC integration**: Support for external authentication providers (e.g., Authelia)
  - Optional OAuth login button on login page (configurable via `config.yaml`)
  - Auto-linking accounts when email addresses match
  - Manual account linking with password confirmation
  - OAuth link management on profile page (view/unlink with password confirmation)
- Session middleware for OAuth state management
- `oauth_links` database table (schema v7 migration) to track OAuth account associations
- Improved modal styling with backdrop blur and smooth fade/scale transitions
- Auto-formatted OAuth link dates using browser locale settings
- Dependencies: `authlib`, `httpx`, `itsdangerous`

### Changed
- Modals now use consistent styling across the app (backdrop blur, smooth transitions)
- Login page template structure improved for OAuth button integration

### Documentation
- README updated with OAuth/OIDC configuration examples and usage documentation

## [1.1.10] - 2026-01-21

### Changed
- Use specific SSH key filename (id_rezepte_deploy) for clearer identification
- SSH authentication with IdentitiesOnly option (fail fast if key doesn't work)

### Fixed
- Corrected SSH key secret (was using wrong key)

## [1.1.9] - 2026-01-21

### Added
- Debug output showing SSH private key length and first characters for secret verification

## [1.1.8] - 2026-01-21

### Added
- Display SSH key fingerprint in logs for verification

## [1.1.7] - 2026-01-21

### Fixed
- Add explicit SSH private key flag (-i) for more reliable authentication

## [1.1.6] - 2026-01-21

### Added
- Verbose SSH deployment logging (shows each step, SSH command details, remote echoes)

## [1.1.5] - 2026-01-21

### Added
- Debug diagnostics in deploy workflow (shows which secrets are set, SSH config)

## [1.1.4] - 2026-01-21

### Changed
- Remove TeX/LaTeX from workflow (ccicons.sty requires excessive package footprint)
- PDF generation moved to optional post-deploy step on server
- Smoke tests simplified (no PDF endpoint test)

## [1.1.3] - 2026-01-21

### Changed
- Remove sudo from runner (root context); keep sudo on server (systemd)

## [1.1.2] - 2026-01-21

### Added
- Gitea deploy workflow triggered on tags (v*) with verification against main
- Pre-deploy smoke tests using Python venv, local config.yaml (port 8000), DB init + seed
- PDF endpoint smoke test by installing TeX (latexmk + lualatex)
- `config.yaml.example` provided; local `config.yaml` now ignored

### Changed
- Server update script now tag-aware (`tools/update.sh`) and safer fetch/checkout
- Replaced help question mark.

### Fixed
- PDF links now open in a new tab (instead of replacing current page)

## [1.1.1] - 2026-01-21

### Fixed
- Recipe detail view breadcrumbs are now clickable and navigate to the corresponding folder

## [1.1.0] - 2026-01-21

### Added
- Sticky footer with flexbox layout (stays at bottom on short pages, scrolls with content on long pages)
- Creative Commons BY-NC-SA 4.0 license badge in footer
- Git version display in footer (shows current tag or commit hash)
- Footer styling matching navigation header (same background color and shadow)
- Help modal available on edit pages (floating button opens syntax guide)
- Development helper script: tools/watch_css.sh (Tailwind CSS watcher for local development)

### Changed
- Recipe edit now only updates `updated_at` timestamp if actual changes are detected to the recipe data
- Prevents false "recently modified" markers when saving without making changes
- Help modal event listeners now attach on `DOMContentLoaded` to ensure the floating button exists
- Help API fetch uses FastAPI `root_path` for environment-agnostic URL resolution (works on /rezepte and without prefix)
- All HTML templates now use Jinja2 comments instead of HTML comments (cleaner client output)
- Help modal fully translated to German
- Footer responsive layout improved (fixed flex-row for better spacing)

## [1.0.0] - 2026-01-21

### Initial Release
- FastAPI-based recipe management application
- SQLite database with FTS5 full-text search across recipes, steps, and ingredients
- Server-side session management (SQLite-backed, rolling expiry)
- User authentication and authorization system
- Admin panel for managing categories, paths, and users
- User profile page with display name, email, and password management
- Markdown-like editor syntax for recipe steps
- Quantity and unit formatting with special syntax (e.g., `[8g]`)
- Support for basic markdown (bold, italic, superscript, subscript)
- Emoticon shortcuts mapped to Phosphor icons
- PDF export via LaTeX with identical rendering to HTML view
- Swiss German quote conversion («guillemets»)
- Responsive design with Tailwind CSS
- Fixed navigation header with search functionality
- Mobile-optimized search interface
- Breadcrumb navigation for folder structure
- Recipe categories and folder organization

[Unreleased]: https://github.com/yourusername/rezepteapp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yourusername/rezepteapp/releases/tag/v1.0.0
