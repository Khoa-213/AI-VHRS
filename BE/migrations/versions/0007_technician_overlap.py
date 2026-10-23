"""production_jobs: one technician cannot hold two overlapping live jobs (audit finding F-01).

The robot already had `ex_job_robot_overlap`; the technician was only checked by the scheduling service, so two concurrent
requests (two robots, same technician, same slot) both succeeded. The same exclusion rule is added for `technician_id`, over the
same live statuses, so the database refuses the second one whatever the application does. Back-to-back slots stay allowed
(`tstzrange` is half-open). Nothing is deleted or changed: if overlapping live jobs already existed the migration would stop with
an error rather than touch them (the audit found none: the production database had no jobs).

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

LIVE = "'SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED'"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(f"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ex_job_technician_overlap'
                 AND conrelid = 'public.production_jobs'::regclass) THEN
    ALTER TABLE production_jobs ADD CONSTRAINT ex_job_technician_overlap
      EXCLUDE USING gist (technician_id WITH =, tstzrange(slot_start, slot_end) WITH &&)
      WHERE (status IN ({LIVE}));
  END IF;
END $$""")


def downgrade() -> None:
    op.get_bind().exec_driver_sql("ALTER TABLE production_jobs DROP CONSTRAINT IF EXISTS ex_job_technician_overlap")
