"""Build `database/AI-VHRS_database_full.sql`: ONE script that creates the whole database as it is now (every table, enum, index,
constraint, trigger, function and row-level-security setting from the baseline and from every migration), plus the reference
data the app needs. This is the file to hand in as the project's database script.

It must be rebuilt (and committed) whenever a migration changes the database. How it works:
  1. a scratch Postgres (default: the local Docker container `vhrs-testdb`, port 55432) is migrated to the head revision;
  2. `pg_dump --schema-only` of it is written between a header and the seed data.
The scratch database must be at the head revision (checked). Use `DB_SCRIPT_SOURCE_URL` to dump another database (a psycopg URL
`postgresql://user:pass@host:port/db`); `PG_DUMP` to choose the client binary (default: `pg_dump`, else `docker exec vhrs-testdb`).

    .venv/bin/python scripts/build_database_script.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

BE = Path(__file__).resolve().parent.parent
OUT = BE / "database" / "AI-VHRS_database_full.sql"
BASELINE = BE / "migrations" / "sql" / "AI-VHRS_database_postgresql.sql"
VERSIONS = BE / "migrations" / "versions"
CONTAINER = "vhrs-testdb"


def head_revision() -> str:
    revs = sorted(p.stem.split("_")[0] for p in VERSIONS.glob("[0-9]*.py"))
    return revs[-1]


def source_url() -> str:
    url = os.environ.get("DB_SCRIPT_SOURCE_URL")
    if url:
        return url
    pw = subprocess.run(["docker", "inspect", CONTAINER, "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
                        capture_output=True, text=True, check=True).stdout
    password = re.search(r"^POSTGRES_PASSWORD=(.*)$", pw, re.M).group(1)
    return f"postgresql://postgres:{password}@localhost:55432/postgres"


def dump_schema(url: str) -> str:
    args = ["--schema-only", "--no-owner", "--no-privileges", "--no-publications", "--no-subscriptions"]
    binary = os.environ.get("PG_DUMP") or shutil.which("pg_dump")
    u = urlsplit(url)
    if binary:
        cmd = [binary, *args, url]
    else:                                                                    # the client lives inside the scratch container
        cmd = ["docker", "exec", CONTAINER, "pg_dump", *args, "-U", u.username or "postgres", u.path.lstrip("/") or "postgres"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf8", check=True).stdout
    out = re.sub(r"^\\(un)?restrict .*\n", "", out, flags=re.M)               # psql-only guard lines of recent pg_dump releases
    out = re.sub(r"^SET transaction_timeout = 0;\n", "", out, flags=re.M)      # PostgreSQL 17+ only: the script must run on 15 and 16 too
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"


def baseline_seed() -> str:
    sql = BASELINE.read_text(encoding="utf8")
    i = sql.index("-- 9. SEED")
    i = sql.rindex("-- -----", 0, i)
    return sql[i:sql.rindex("COMMIT;")].rstrip() + "\n"


def settings_seed() -> str:
    spec = importlib.util.spec_from_file_location("m0002", VERSIONS / "0002_fixes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stmt = next(s for s in getattr(mod, "STATEMENTS", []) if "INSERT INTO system_settings" in s)
    return stmt.strip() + ";\n"


def _sql_str(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def alert_catalog_seed() -> str:
    """The robot alerts (migrations 0008 and 0010): level, plain-Vietnamese sentence, action, who is told, e-mail."""
    catalog = []
    for name, file in (("m0008", "0008_robot_ops.py"), ("m0010", "0010_robot_agent_link.py")):    # each migration adds its own rows
        spec = importlib.util.spec_from_file_location(name, VERSIONS / file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        catalog += mod.CATALOG
    rows = []
    for code, level, title, action, roles, _mail in catalog:
        arr = "ARRAY[" + ", ".join(_sql_str(r) for r in roles) + "]::text[]"
        rows.append(f"({_sql_str(code)}, {level}, {_sql_str(title)}, {_sql_str(action)}, {'true' if level == 4 else 'false'}, "
                    f"{arr}, {'true' if level == 4 else 'false'})")
    return ("INSERT INTO alert_catalog (code, level, title_vi, action_vi, estop_advised, notify_roles, send_email) VALUES\n  "
            + ",\n  ".join(rows) + "\nON CONFLICT (code) DO NOTHING;\n")


def main() -> int:
    url = source_url()
    head = head_revision()
    with create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1)).connect() as c:
        current = c.execute(text("select version_num from alembic_version")).scalar()
    if current != head:
        print(f"The source database is at revision {current}, the code is at {head}: run `alembic upgrade head` on it first.")
        return 1
    schema = dump_schema(url)
    header = f"""-- =====================================================================================================================
-- AI-VHRS (Xuong Net Viet) - full database script for PostgreSQL 15+ (Supabase uses 17).
-- Revision {head} (alembic head), generated {date.today().isoformat()} by scripts/build_database_script.py. DO NOT EDIT BY HAND:
-- change the database with an Alembic migration, then rebuild this file.
--
-- What it contains
--   1. the schema: extension, enum types, tables, constraints, indexes, functions, triggers, row-level security (all of the
--      baseline schema and every migration up to {head});
--   2. the `alembic_version` row, so the application's migrations see this database as already at {head};
--   3. reference data: the 5 roles, the demo accounts (password ChangeMe@123: CHANGE IT before any real use), the first price list,
--      the pen types, the default system settings and the robot alert catalogue.
-- It does NOT contain the catalogue and policy text that `scripts/seed_workshop_data.py` loads (papers, inks, templates, the
-- privacy policy, which order types are enabled): run that script afterwards for a working demo.
--
-- How to run (an EMPTY database):   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/AI-VHRS_database_full.sql
-- On Supabase: run it in the SQL editor of an empty project (the `anon`/`authenticated` lock-down at the end applies there).
-- =====================================================================================================================
"""
    seed = f"""

-- pg_dump empties the search_path; the data below uses plain table names.
SET search_path TO public;

-- =====================================================================================================================
-- 2. Migration marker
-- =====================================================================================================================
INSERT INTO alembic_version (version_num) VALUES ('{head}');

-- =====================================================================================================================
-- 3. Reference data (roles, demo accounts, first price list, pen types) - from the baseline script, section 9
-- =====================================================================================================================
BEGIN;
{baseline_seed()}
-- Default system settings (migration 0002)
{settings_seed()}
-- Robot alert catalogue (migration 0008): level 4 = press the physical E-Stop now
{alert_catalog_seed()}COMMIT;

-- =====================================================================================================================
-- 4. Supabase only: the REST roles must not reach the tables (the API talks to Postgres directly). Skipped elsewhere.
-- =====================================================================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END $$;
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(header + "\n-- =====================================================================================================================\n"
                   "-- 1. Schema (pg_dump --schema-only of the migrated database)\n"
                   "-- =====================================================================================================================\n"
                   + schema + seed, encoding="utf8")
    print(f"wrote {OUT.relative_to(BE)} ({OUT.stat().st_size // 1024} KB), revision {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
