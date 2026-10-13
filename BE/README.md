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
