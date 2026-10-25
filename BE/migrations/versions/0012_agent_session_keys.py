"""robot_agents: short-lived session keys issued to a Technical Staff member's own login (the desktop app).

Until now the only agent credential was a long-lived key issued by a Manager. A desktop app cannot ask a Manager for a key every
morning, so the technician who holds a live job on the robot may now obtain a SESSION key: it belongs to that account and to one
app instance, expires after a few hours and is renewed before it ends (the old key keeps working for a short grace period, so a
renewal never looks like a lost link). The Manager key keeps working as before (kind MANAGER).

Changes only `robot_agents`: four new columns, and the "one active key per robot" unique index now applies to MANAGER keys only
(several session keys of the same app instance overlap during a renewal; the service enforces "one controlling app per robot").
Existing rows become kind MANAGER and keep working. Rollback: `alembic downgrade 0011` (deletes session keys first).

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE robot_agents ADD COLUMN IF NOT EXISTS kind VARCHAR(8) NOT NULL DEFAULT 'MANAGER'",
    "ALTER TABLE robot_agents ADD COLUMN IF NOT EXISTS account_id BIGINT REFERENCES accounts(id)",
    "ALTER TABLE robot_agents ADD COLUMN IF NOT EXISTS instance_id VARCHAR(64)",
    "ALTER TABLE robot_agents ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
    """DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_robot_agents_kind'
                 AND conrelid = 'public.robot_agents'::regclass) THEN
    ALTER TABLE robot_agents ADD CONSTRAINT chk_robot_agents_kind CHECK (
      (kind = 'MANAGER' AND account_id IS NULL AND instance_id IS NULL)
      OR (kind = 'SESSION' AND account_id IS NOT NULL AND instance_id IS NOT NULL AND expires_at IS NOT NULL));
  END IF;
END $$""",
    "DROP INDEX IF EXISTS ux_robot_agents_active",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_agents_manager_active ON robot_agents (robot_id) WHERE revoked_at IS NULL AND kind = 'MANAGER'",
    "CREATE INDEX IF NOT EXISTS ix_robot_agents_session ON robot_agents (robot_id, expires_at) WHERE revoked_at IS NULL AND kind = 'SESSION'",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM robot_agents WHERE kind = 'SESSION'")
    conn.exec_driver_sql("DROP INDEX IF EXISTS ix_robot_agents_session")
    conn.exec_driver_sql("DROP INDEX IF EXISTS ux_robot_agents_manager_active")
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_robot_agents_active ON robot_agents (robot_id) WHERE revoked_at IS NULL")
    conn.exec_driver_sql("ALTER TABLE robot_agents DROP CONSTRAINT IF EXISTS chk_robot_agents_kind")
    conn.exec_driver_sql("ALTER TABLE robot_agents DROP COLUMN IF EXISTS expires_at, DROP COLUMN IF EXISTS instance_id, "
                         "DROP COLUMN IF EXISTS account_id, DROP COLUMN IF EXISTS kind")
