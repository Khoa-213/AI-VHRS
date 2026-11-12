"""Upgrade U4: restoration regions and the customer's restoration mode (docs/UPGRADE_AI_ROBOT_PLAN.md, III-B).

* `sketch_regions`: one row per word region of an OT-1 sketch version: page, region number (stable across edits), box in
  mm, the run of strokes [stroke_start, stroke_end) in that page of the trajectory file, provenance label
  ORIGINAL / RESTORED / INFERRED, confidence (0..1, NULL for Staff edits), measurement details, transcribed / written text,
  source AUTO / STAFF, Staff note and editor. Rows belong to one immutable sketch version (an edit makes a new version).
* `orders.restoration_mode` NULL | FAITHFUL | ASSISTED: the customer's choice for OT-1 (NULL = FAITHFUL). FAITHFUL never
  allows INFERRED regions in a sketch that is finalised.

Additive only: no existing row changes. Rollback: `alembic downgrade 0017` (drops the table and the column).

Revision ID: 0018
Revises: 0017
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UPGRADE = [
    """ALTER TABLE orders ADD COLUMN IF NOT EXISTS restoration_mode VARCHAR(10)
       CONSTRAINT chk_orders_restoration_mode CHECK (restoration_mode IN ('FAITHFUL', 'ASSISTED'))""",
    """CREATE TABLE IF NOT EXISTS sketch_regions (
        id            BIGSERIAL PRIMARY KEY,
        sketch_id     BIGINT NOT NULL REFERENCES sketches(id) ON DELETE CASCADE,
        page_no       INTEGER NOT NULL CHECK (page_no >= 1),
        region_no     INTEGER NOT NULL CHECK (region_no >= 1),
        x0            NUMERIC(7,2) NOT NULL,
        y0            NUMERIC(7,2) NOT NULL,
        x1            NUMERIC(7,2) NOT NULL,
        y1            NUMERIC(7,2) NOT NULL,
        stroke_start  INTEGER NOT NULL CHECK (stroke_start >= 0),
        stroke_end    INTEGER NOT NULL,
        label         VARCHAR(10) NOT NULL CHECK (label IN ('ORIGINAL', 'RESTORED', 'INFERRED')),
        confidence    NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
        metrics       JSONB,
        text          TEXT,
        source        VARCHAR(10) NOT NULL DEFAULT 'AUTO' CHECK (source IN ('AUTO', 'STAFF')),
        note          TEXT,
        edited_by     BIGINT REFERENCES accounts(id),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_sketch_region_strokes CHECK (stroke_end >= stroke_start),
        CONSTRAINT ux_sketch_region UNIQUE (sketch_id, page_no, region_no)
    )""",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS sketch_regions",
    "ALTER TABLE orders DROP COLUMN IF EXISTS restoration_mode",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
