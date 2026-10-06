# PSYCON design system

All four workspaces extend `backend/templates/base.html`. It supplies fonts, navigation, the page container, and shared styles. The server renders Jinja templates; client behavior uses plain JavaScript.

## Color and type

`backend/static/dashboard.css` defines the common tokens: ink `#202421`, muted text `#65706a`, paper `#f3f1eb`, surface `#fbfaf6`, border `#d7d7cf`, teal `#24766b`, warning `#9b6818`, and danger `#a44232`. Manrope is the interface font, with Segoe UI as its fallback. Geist Mono labels technical data, with Consolas as its fallback.

`design-system.css` defines shared navigation, controls, headings, focus, and state styles. Main headings use 2.75rem, section headings 1.5rem, and smaller headings 1.125rem. Body copy uses a 1.65 line height and a readable line length.

## Components and layout

Use the same masthead and Home, Coach, Research, and Devices navigation everywhere. The active page has a visible mark and `aria-current`. Controls have square corners, 44px minimum height, and visible keyboard focus. Primary actions use teal; secondary actions use a teal outline. Destructive actions use the shared danger color.

Page layouts may differ by task, but their fonts, colors, borders, spacing, fields, buttons, and states come from the shared styles. Page-specific CSS contains layout rules only. Forms and workspace grids collapse at 800px. Honor reduced motion and retain native form controls.
