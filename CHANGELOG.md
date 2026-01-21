# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- PDF links now open in a new tab (instead of replacing current page)

### Added
- Gitea deploy workflow triggered on tags (v*) with verification against main
- Pre-deploy smoke tests using Python venv, local config.yaml (port 8000), DB init + seed
- PDF endpoint smoke test by installing TeX (latexmk + lualatex)
- `config.yaml.example` provided; local `config.yaml` now ignored

### Changed
- Server update script now tag-aware (`tools/update.sh`) and safer fetch/checkout
- Replaced help question mark.

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
