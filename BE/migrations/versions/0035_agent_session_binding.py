"""D03 / 1a (owner decision 2026-11-28): the real robot is started at its workstation only.

The desktop app on the workstation asks for the agent's session key (`POST /technician/robots/{id}/agent-session`) and
starts the Robot Agent with it. This column records WHICH login session asked. A command that moves the real arm (RUN,
DRY_RUN, ALIGN_START in REAL mode; RESUME and PAPER_CHANGED of a REAL run) is then accepted only from that same login
session: the app that runs on the workstation next to the robot. The same account signed in on another computer has
another session and is refused. PAUSE and STOP are never restricted.

Additive: one nullable column, no existing row changes (keys issued before this have NULL and are simply not bound; the
app gets a bound key the next time it renews or restarts the agent). Rollback: `alembic downgrade 0034`.

Revision ID: 0035
Revises: 0034
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE robot_agents ADD COLUMN IF NOT EXISTS auth_session_id UUID",
    "COMMENT ON COLUMN robot_agents.auth_session_id IS 'Login session (auth_sessions.id) that asked for this SESSION key: "
    "REAL motion commands are accepted only from it (D03 / 1a). NULL for Manager keys and keys issued before 0035'",
]
DOWNGRADE = ["ALTER TABLE robot_agents DROP COLUMN IF EXISTS auth_session_id"]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
