"""robot_commands: allow the command kind ALIGN_START.

ALIGN_START tells the Robot Agent to bring the arm, which the operator has put near the start by hand, to the job's fixed start pose (above
the sheet, at the pen-up height) WITH the fixed writing orientation. It removes the few-degree orientation error that makes the writing
moves refuse to start. Only the CHECK constraint on `robot_commands.kind` changes (one more allowed value); no data is touched.
Rollback: `alembic downgrade 0012` (refuses if an ALIGN_START row exists: delete those rows first).

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

OLD = "('LOAD','PREFLIGHT','DRY_RUN','RUN','PAUSE','RESUME','STOP','PAPER_CHANGED','IDENTIFY')"
NEW = "('LOAD','PREFLIGHT','DRY_RUN','RUN','PAUSE','RESUME','STOP','PAPER_CHANGED','IDENTIFY','ALIGN_START')"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE robot_commands DROP CONSTRAINT IF EXISTS chk_robot_command_kind")
    conn.exec_driver_sql(f"ALTER TABLE robot_commands ADD CONSTRAINT chk_robot_command_kind CHECK (kind IN {NEW})")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE robot_commands DROP CONSTRAINT IF EXISTS chk_robot_command_kind")
    conn.exec_driver_sql(f"ALTER TABLE robot_commands ADD CONSTRAINT chk_robot_command_kind CHECK (kind IN {OLD})")
