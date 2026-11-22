# Staff CRM presentation

The three PNGs and `PROMPT_CODEX.md` in `crm_video_reference/` guide the visual style, mapped to the existing workshop domain.

## Open the UI

Run `npm.cmd run dev` in `FE`, sign in as Staff, then open:

- `/staff`: current-order KPIs, received-orders chart (7/30 days), distribution and queues.
- `/staff/review`: existing stage groups presented as pipeline columns; select a card to open `/staff/review/:id`.
- `/staff/fulfillment` and `/staff/refunds`: existing operations in the same visual frame.

## Source

- `src/components/ws/Shell.tsx`: Staff sticky utility header (logo, notifications, appearance, language and profile link; sign out is at the bottom of the sidebar), workflow sidebar and mobile drawer; Manager uses the same frame with its own sidebar items (see `FE/AGENTS.md`, "Manager area"); Technician retains the original shell.
- `src/components/ws/staff-ui.css`: scoped visual tokens, cards, filters, pipeline and responsive layout.
- `src/pages/staff/StaffDashboard.tsx`: KPIs and chart from the existing workshop API data.
- `src/pages/staff/Workbench.tsx`: presentation classes for pipeline versus selected-order detail.
- `src/components/ws/parts.tsx`: optional KPI arrow icon, preserving the default icon for other callers.

Production uses the existing APIs. **No sample data, new backend, export operation, Staff order creation or drag-and-drop status changes are introduced.** Chart periods filter chart data only. Existing order-state gates, filters, pagination, action handlers and permissions remain in their current components/services.

## Verification

```powershell
npm.cmd run build
npm.cmd run i18n:check
node scripts/check-staff-ui-browser.mjs
node scripts/check-fulfillment-browser.mjs
node scripts/check-admin-browser.mjs
```

Browser checks intercept API calls with local fixtures: no credentials, real orders or production writes. Staff checks cover English/Vietnamese/Japanese, desktop/tablet/mobile, sidebar/drawer, saved light/dark mode, pipeline-to-detail links, existing scope/stage/search behavior, chart periods and input guards. Fulfillment checks cover existing shipment/pickup behavior and Manager read-only controls. These checks do not verify a live deployment or real carrier callbacks.

The Staff sidebar stays visible on desktop and opens from the menu button on tablet/mobile. Escape, clicking outside or choosing a route closes the drawer, with focus returned to its trigger. Content components, filters and operations retain their existing layout and handlers.

The Staff frame fills the viewport: a 72px top header, a 224px workflow sidebar (200px on smaller desktops), and an independently scrolling content pane. The header and sidebar have straight shared edges instead of floating cards. Mobile keeps a two-row 124px utility header and a navigation drawer. Content never scrolls behind the header.

The Staff account control opens the shared `/account/profile` page directly, with a link back to `/staff`. The existing `/me` API supports all signed-in roles: GET reads the account and PATCH saves name/phone (the backend also accepts structured addresses). The shared profile UI still stores its free-text address, bio and avatar on the device. Sign out remains a separate button at the bottom of the Staff sidebar.

Pipeline stage headings use a white surface in light mode and the matching card surface in dark mode, with simple hover/focus feedback and no orbit animation. The outer tinted column panel is removed. This affects presentation only.

The Staff depth layer (`staff-depth.css`) adds navy atmospheric gradients (no abstract 3D shapes), glass-like frame surfaces and layered card shadows. They do not alter artwork, data, workflows or other roles.
