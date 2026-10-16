# AI-VHRS Backend (FastAPI + PostgreSQL/Supabase)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows venv path; use .venv/bin on Linux/macOS
cp .env.example .env          # fill DATABASE_URL (Supabase *session pooler*, IPv4) and JWT_SECRET
.venv/Scripts/python -m alembic upgrade head                 # see "Database" below
.venv/Scripts/python -m uvicorn app.main:app --reload
.venv/Scripts/python -m pytest                               # runs against the DB in .env
```

## API docs (Swagger)

| URL | What |
|---|---|
| `http://localhost:8000/docs` | Swagger UI. Click **Authorize**, put the e-mail in `username`, or call `POST /auth/login` and paste the token. |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/openapi.json` | OpenAPI 3 spec (use it to generate FE / Flutter clients) |

## Database

* Baseline schema: [`migrations/sql/AI-VHRS_database_postgresql.sql`](migrations/sql/AI-VHRS_database_postgresql.sql) (unchanged original).
* `alembic upgrade head` on an **empty** database runs that file (revision `0001`), then
  `0002` (state-guard fixes, `system_settings`, unique indexes, RLS) and `0003` (`auth_sessions`).
  On a database that already has the tables (our Supabase project) `0001` is skipped.
* Supabase: use the **session pooler** string (port 5432). The direct host is IPv6-only.
  RLS is on for every table and `anon`/`authenticated` have no grants: only this backend reads the DB.

## Auth sessions

Login creates a row in `auth_sessions`; access and refresh tokens carry its id (`sid`).
`POST /auth/logout` revokes the session, a password change signs out the *other* devices,
a password reset signs out all of them.

## Layers

`api/` (routers, schemas) → `services/` (use cases) → `repositories/` (SQLAlchemy) → DB.
Pure business rules go to `domain/` (from Phase 2). Errors use one envelope:
`{"error": {"code", "message", "details"}}`; DB state-guard violations (`P0409`) become `409`.

## Security

| Area | What |
|---|---|
| Passwords | bcrypt (cost 10), min 8 chars with letter + digit; 5 wrong tries lock the account 15 min |
| Tokens | JWT HS256: access 30 min, refresh 7 days, both bound to a server-side session (`auth_sessions`) |
| Rate limit | per client IP, in-memory: login 20/min, refresh 60/min, register 10/h, password reset 5/15 min. `429` + `Retry-After`. Single process only: use Redis before running several instances |
| Headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP `default-src 'none'` and `Cache-Control: no-store` on API responses (Swagger UI excluded), HSTS when served over HTTPS |
| CORS | origins from `CORS_ORIGINS` only (no wildcard) |
| Proxy | set `TRUST_PROXY_HEADERS=true` only behind your own reverse proxy, otherwise `X-Forwarded-For` is ignored |
| Database | RLS enabled on all tables; `anon` / `authenticated` have no grants |

HTTPS termination itself is the deployment's job (reverse proxy / host).

## Phase 2: workshop intake, AI sketches, quotations

Roles: `STAFF` and `MANAGER` share `/api/v1/workshop/*`; `/api/v1/manager/*` is Manager-only; the customer side is
`/orders/{id}/privacy`, `/orders/{id}/quotation[/request-changes]`, `/orders/{id}/messages`, `/privacy-policy`.
Admin has **no** access to orders (system administration only). Staff see assigned orders plus the unassigned
`SUBMITTED` pool (read-only until they claim one); another Staff's order answers `404`.

Flow: `SUBMITTED` → accept / reject / request-info → `ACCEPTED` → sketch (AI or hand-made, one `final` version)
→ quotation (Pricing Engine, ±15% adjustment, Manager approval beyond it) → send (PDF, valid 7 days) →
`AWAITING_PRIVACY` → customer accepts the privacy policy → `QUOTED` (or cancels). State changes are plain
UPDATEs judged by the DB trigger `fn_order_state_guard` (`409 STATE_CONFLICT`); quotation statuses have no trigger
and are enforced in `services/quotations.py`.

### AI pipelines (`app/services/stroke_ai/`, no external service, no model weights)

| Order type | Pipeline |
|---|---|
| OT-1 copy / restore | illumination flattening, Otsu, deskew, **Zhang-Suen thinning**, skeleton graph, stroke pairing by direction continuity at junctions, spur pruning, reading-order + diacritic-after-word ordering, fit on paper. Similarity = pixel IoU of the original ink vs the redrawn strokes |
| OT-3 template | Hershey single-line fonts (`font_uri = hershey:<name>`), Vietnamese letters composed from base + modifier + tone mark (NFD), word wrap, alignment, pagination, seeded natural variation |
| OT-2 learned style | not generated (R&D, LI-10); Staff upload a hand-made trajectory. Customers cannot order it while `system_settings.order_types_enabled` omits it (the seed does) |

Not validated yet: OT-1 accuracy on real Vietnamese handwriting (NFR-02 needs a benchmark set; the ~82% IoU figures in
the tests are on synthetic images), stroke order/direction are heuristics, the writing-time estimate uses assumed speed
factors (`trajectory.py`), complexity (K_cx) thresholds are assumptions that Staff confirm. Trajectory format:
`vhrs-trajectory/1` (mm, origin top-left); motion planning for the FR3 is a later phase.

### Seed and tests

```bash
.venv/bin/python scripts/seed_workshop_data.py --dry-run   # papers, inks, compatibility (BR-06), single-line fonts,
.venv/bin/python scripts/seed_workshop_data.py             # privacy policy, order_types_enabled; idempotent, never overwrites
```
Prices and stock in the seed are **starting values** (the Manager must set the real ones); the privacy policy text is a
draft to be approved by the workshop. `scripts/seed_workshop_data.py` does not touch accounts or the pricing config.

`pytest` runs on whatever `DATABASE_URL` points to (it creates and removes `pytest_*` rows and temporarily lifts the
`order_types_enabled` restriction). For a throwaway local database:
`docker run -d -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=vhrs -p 55432:5432 postgres:16`, then
`DATABASE_URL=postgresql://postgres:pw@localhost:55432/vhrs JWT_SECRET=x alembic upgrade head` and run the seed + tests.
The quotation PDF uses the bundled DejaVu Sans (licence in `app/assets/fonts/`); put the workshop logo at
`app/assets/logo.png` to have it printed in the header.
