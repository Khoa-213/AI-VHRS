# Staff CRM presentation

The three PNGs and `PROMPT_CODEX.md` in `crm_video_reference/` guide the visual style, mapped to the existing workshop domain.

## Open the UI

Run `npm.cmd run dev` in `FE`, sign in as Staff, then open:

- `/staff`: current-order KPIs, received-orders chart (7/30 days), distribution and queues.
- `/staff/review?scope=pool`: one compact intake list, oldest submission first, 20 orders per page.
- `/staff/review?scope=mine`: personal stage groups; intake appears only when assigned SUBMITTED orders exist. Search covers the full selected tab, including orders beyond the first page.
- `/staff/fulfillment` and `/staff/refunds`: existing operations in the same visual frame.

## Source

- `src/components/ws/Shell.tsx`: Staff sticky utility header (logo, notifications, appearance, language and profile link; sign out is at the bottom of the sidebar), workflow sidebar and mobile drawer; Manager uses the same frame with its own sidebar items (see `FE/AGENTS.md`, "Manager area"); Technician retains the original shell.
- `src/components/ws/staff-ui.css`: scoped visual tokens, cards, filters, pipeline and responsive layout.
- `src/pages/staff/StaffDashboard.tsx`: KPIs and chart from the existing workshop API data.
- `src/pages/staff/Workbench.tsx`: presentation classes for pipeline versus selected-order detail.
- `src/components/ws/parts.tsx`: optional KPI arrow icon, preserving the default icon for other callers.

Production uses API data only. The existing frame, chart and workflow components stay in place. `StaffQueue.tsx` adds server-paged Staff navigation; Manager and fulfillment retain `Workbench.tsx`. The existing order query now supports `mine`, customer-name search and exact `order_ids`; `/workshop/queue-counts` supplies global pool and personal status counts. Chart periods affect chart data only. No sample records or drag-and-drop mutations are introduced.

The entire intake KPI links to the pool and shows `pool + mine.SUBMITTED`, with both parts below it. Query, stage and page live in the URL and survive opening an order. Returning restores the content pane position; a depleted final page moves to the last available page. Receiving keeps the atomic backend ownership guard and displays a success panel with sketch/queue choices. A competing receiver gets a clear conflict message and refreshed counts/list.

Deployment compatibility: if `/workshop/queue-counts` returns 404, the FE reads every authorized page from the existing order API and `/me`, derives exact counts and applies personal scope/search/batch filters locally before slicing a 20-row page. This avoids assuming that an older backend honors new query parameters. The new backend retains server-side filtering/pagination. Run the intake browser check with `STAFF_QUEUE_LEGACY=1` to cover a missing count endpoint and ignored new query parameters. Unknown counts are not rendered as zero.

New submissions notify active Staff; assignment and resubmission notify the owner. The current bell groups loaded new-order notifications by minute and read state, links a group to its explicit order ids, and opens individual notices directly. Loading more notifications extends the visible groups. Reading notices never changes order status or intake counts. SSE and periodic refresh update queue data independently of unread badges.

## Verification

```powershell
npm.cmd run build
npm.cmd run i18n:check
node scripts/check-staff-ui-browser.mjs
node scripts/check-staff-queue-browser.mjs
node scripts/check-fulfillment-browser.mjs
node scripts/check-admin-browser.mjs
```

Browser checks intercept API calls with local fixtures: no credentials, real orders or production writes. Staff checks cover English/Vietnamese/Japanese, desktop/tablet/mobile, sidebar/drawer, saved light/dark mode, pipeline-to-detail links, existing scope/stage/search behavior, chart periods and input guards. Fulfillment checks cover existing shipment/pickup behavior and Manager read-only controls. These checks do not verify a live deployment or real carrier callbacks.

The intake browser check uses 100 orders and two Staff fixtures, tests exact notification destinations, pagination, search outside page one, receive/return and conflict UI. `BE/scripts/check_staff_queue.py` separately runs the production repository/access code on local SQLite with 100 orders and two concurrent Staff transactions, plus recipient/read-independence checks. SQLite does not exercise PostgreSQL row locks, state triggers or the full HTTP service. Run the existing backend API suite against an isolated PostgreSQL test database for that coverage.

The Staff sidebar stays visible on desktop and opens from the menu button on tablet/mobile. Escape, clicking outside or choosing a route closes the drawer, with focus returned to its trigger. Content components, filters and operations retain their existing layout and handlers.

The Staff frame fills the viewport: a 72px top header, a 224px workflow sidebar (200px on smaller desktops), and an independently scrolling content pane. The header and sidebar have straight shared edges instead of floating cards. Mobile keeps a two-row 124px utility header and a navigation drawer. Content never scrolls behind the header.

The Staff account control opens the shared `/account/profile` page directly, with a link back to `/staff`. The existing `/me` API supports all signed-in roles: GET reads the account and PATCH saves name/phone (the backend also accepts structured addresses). The shared profile UI still stores its free-text address, bio and avatar on the device. Sign out remains a separate button at the bottom of the Staff sidebar.

Pipeline stage headings use a white surface in light mode and the matching card surface in dark mode, with simple hover/focus feedback and no orbit animation. The outer tinted column panel is removed. This affects presentation only.

The Staff depth layer (`staff-depth.css`) adds navy atmospheric gradients (no abstract 3D shapes), glass-like frame surfaces and layered card shadows. They do not alter artwork, data, workflows or other roles.
