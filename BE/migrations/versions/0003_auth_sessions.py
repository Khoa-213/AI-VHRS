"""auth_sessions: server-side login sessions so logout / password change can revoke tokens.

Access and refresh tokens carry the session id (`sid`). A token is only honoured while its
session row exists, is not revoked and has not expired.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
CREATE TABLE IF NOT EXISTS auth_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ,
  ip_address  INET,
  user_agent  VARCHAR(255),
  CONSTRAINT chk_auth_sessions_expiry CHECK (expires_at > created_at)
)""",
    "CREATE INDEX IF NOT EXISTS ix_auth_sessions_account ON auth_sessions (account_id) WHERE revoked_at IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_auth_sessions_expiry ON auth_sessions (expires_at)",
    "ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY",
    """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON auth_sessions FROM anon, authenticated;
  END IF;
END $$""",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.exec_driver_sql(stmt.replace("%", "%%"))


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS auth_sessions")
