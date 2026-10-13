"""Baseline: schema from migrations/sql/AI-VHRS_database_postgresql.sql.

On an empty database this revision runs that file. On a database that already has the
tables (the Supabase project, where the file was applied by hand) it does nothing, so the
revision acts as a stamp.

Revision ID: 0001
Revises:
"""
import re
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = Path(__file__).resolve().parents[1] / "sql" / "AI-VHRS_database_postgresql.sql"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.exec_driver_sql("select to_regclass('accounts')").scalar() is not None:
        return
    sql = BASELINE_SQL.read_text(encoding="utf8")
    # Alembic already wraps the migration in a transaction.
    sql = re.sub(r"^(BEGIN|COMMIT);[ \t]*$", "", sql, flags=re.MULTILINE)
    conn.exec_driver_sql(sql.replace("%", "%%"))  # psycopg treats % as a placeholder marker


def downgrade() -> None:
    raise NotImplementedError("Refusing to drop the whole schema; drop the database explicitly if needed.")
