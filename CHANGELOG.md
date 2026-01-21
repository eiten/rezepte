# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Sticky footer with flexbox layout (stays at bottom on short pages, scrolls with content on long pages)
- Creative Commons BY-NC-SA 4.0 license badge in footer
- Git version display in footer (shows current tag or commit hash)
- Footer styling matching navigation header (same background color and shadow)

### Changed
- Recipe edit now only updates `updated_at` timestamp if actual changes are detected to the recipe data
- Prevents false "recently modified" markers when saving without making changes

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
