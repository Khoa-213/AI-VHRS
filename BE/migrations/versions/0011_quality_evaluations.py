"""quality_evaluations: Service G results (photo of the written sheet vs the approved sketch), one row per evaluation.

Only completed evaluations are stored (a photo with no sheet in it answers 422 and leaves nothing). The numbers are advisory: the
technician's QC verdict on `product_photos.qc_result` stays the decision. `metrics` holds the millimetre measurements and the
thresholds that were used, so an old result is still readable after the thresholds change. Nothing existing is changed.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS quality_evaluations (
         id BIGSERIAL PRIMARY KEY,
         photo_id BIGINT NOT NULL REFERENCES product_photos(id),
         job_id BIGINT NOT NULL REFERENCES production_jobs(id),
         order_id BIGINT NOT NULL REFERENCES orders(id),
         sketch_id BIGINT REFERENCES sketches(id),
         page_no SMALLINT NOT NULL DEFAULT 1 CHECK (page_no >= 1),
         method VARCHAR(30) NOT NULL,
         verdict VARCHAR(14) NOT NULL CHECK (verdict IN ('PASS', 'NEEDS_REVIEW', 'FAIL')),
         metrics JSONB NOT NULL,
         overlay_path TEXT,
         created_by BIGINT NOT NULL REFERENCES accounts(id),
         created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_quality_evaluations_photo ON quality_evaluations (photo_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_quality_evaluations_job ON quality_evaluations (job_id, created_at DESC)",
    "ALTER TABLE quality_evaluations ENABLE ROW LEVEL SECURITY",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS quality_evaluations")
