"""Fixed robot assignment: the Manager gives each robot to one technician; the technician picks the robot for a job
(owner decision 2026-11-26, overrides UC-41 "Manager assigns a job to a robot and a technician").

* `technician_robots`: one row per robot (a robot belongs to at most ONE technician; a technician may hold several).
* `production_jobs.robot_id` becomes optional: the Manager schedules a job for a technician and a slot; the technician picks one
  of their robots before preparing it. `chk_job_robot_before_prepare`: only a SCHEDULED or CANCELLED job may have no robot.
  The exclusion constraint `ex_job_robot_overlap` already ignores NULL robots.
Additive: no existing row changes (every existing job has a robot). Rollback: `alembic downgrade 0031` (refused while a job
has no robot: SET NOT NULL fails).

Revision ID: 0032
Revises: 0031
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS technician_robots (
        robot_id        BIGINT PRIMARY KEY REFERENCES robots(id) ON DELETE CASCADE,
        technician_id   BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        assigned_by     BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
        assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_technician_robots_technician ON technician_robots (technician_id)",
    "ALTER TABLE technician_robots ENABLE ROW LEVEL SECURITY",
    "COMMENT ON TABLE technician_robots IS 'Fixed robot assignment: each robot belongs to at most one Technical Staff (Manager sets it)'",
    "ALTER TABLE production_jobs ALTER COLUMN robot_id DROP NOT NULL",
    """DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_job_robot_before_prepare') THEN
           ALTER TABLE production_jobs ADD CONSTRAINT chk_job_robot_before_prepare
             CHECK (robot_id IS NOT NULL OR status IN ('SCHEDULED', 'CANCELLED'));
         END IF;
       END $$""",
    "COMMENT ON COLUMN production_jobs.robot_id IS 'NULL until the technician picks one of their robots (only while SCHEDULED)'",
]

DOWNGRADE = [
    "ALTER TABLE production_jobs DROP CONSTRAINT IF EXISTS chk_job_robot_before_prepare",
    "ALTER TABLE production_jobs ALTER COLUMN robot_id SET NOT NULL",
    "DROP TABLE IF EXISTS technician_robots",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
