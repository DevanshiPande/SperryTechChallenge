# Gridlock design handoff

This is an editable, local frontend prototype of the Gridlock application. Open `index.html` in a browser. No build step, account, API key, or network connection is required. The map fills the entire viewport; navigation, search, opportunity cards, project previews, and chat float above it. Use the left navigation and role switch to view each screen.

The Figma design remains at https://www.figma.com/design/uG5z5D3tOYbP3OxkvENwxm. The Figma Starter plan blocked export, so this package is **not** a native `.fig` file and does not contain a byte-for-byte export of that design. It recreates the screen structure and flows in HTML, CSS, and JavaScript for transfer to another developer or account.

## Included flows

- Contractor: explore both utilities on an interactive schematic map; inspect ranked overlaps and project detail; check project feasibility; compare cost scenarios; add a project through a chat-style draft or manual form; list equipment; request a reservation; post jobs; discuss a shared cost scenario in messages.
- Worker: search jobs on cards and map; inspect a role; apply; review applications and profile.

The map uses coordinates in the supplied starter workbook, plotted over an illustrative Lowcountry background image. Its geography, roads, and pin alignment are schematic, not an authoritative GIS map. The workbook contains in-service dates, not construction start/end windows. Resource listings, jobs, contacts, road closures, traffic, and savings are labeled demo data or illustrative assumptions. No data is sent to a server. The assistant is a local scripted prototype, not a Gemini connection.

## Files

- `index.html` — entry point
- `styles.css` — visual system and responsive layout
- `app.js` — navigation and interactions
- `data/challenge.js` — public-plan starter project and overlap records converted from the supplied workbook
- `assets/lowcountry-map-background.png` — illustrative full-screen map artwork
- `reference-mockups/` — five generated concept images for visual direction; these are not exports from the Figma file or screenshots of the HTML prototype

To connect a backend, replace the local data arrays and action handlers in `app.js` with API calls. Preserve source provenance and require human review before publishing AI-generated drafts or accepting proposed traffic and cost estimates.
