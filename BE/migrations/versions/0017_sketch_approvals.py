"""Upgrade U2: record exactly what the customer approved, and why a re-quote's price changed (docs/UPGRADE_AI_ROBOT_PLAN.md).

* `quotations.revision_reason` TEXT NULL: Staff's explanation when a quote replaces one the customer asked to change
  (owner decision Q4: no limit on change rounds, every re-quote states why the price changed or stayed).
* `sketch_approvals`: one row per approved quotation, written at the moment the customer approves; pins the sketch
  version, its content hash and the customer-facing image paths that were on screen, the chosen option, the total and the
  client IP. Rows are append-only (trigger `trg_sketch_approval_immutable` blocks UPDATE); they disappear only with the
  order (ON DELETE CASCADE, used by test cleanup / account erasure).

Additive only: no existing row changes. Rollback: `alembic downgrade 0016` (drops the trigger, the table and the column;
approval records and revision reasons written meanwhile are lost).

Revision ID: 0017
Revises: 0016
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE quotations ADD COLUMN IF NOT EXISTS revision_reason TEXT",
    """CREATE TABLE IF NOT EXISTS sketch_approvals (
        id                  BIGSERIAL PRIMARY KEY,
        order_id            BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        quotation_id        BIGINT NOT NULL UNIQUE REFERENCES quotations(id) ON DELETE CASCADE,
        sketch_id           BIGINT NOT NULL REFERENCES sketches(id) ON DELETE CASCADE,
        sketch_version      INTEGER NOT NULL,
        sketch_content_hash CHAR(64),
        image_paths         TEXT[] NOT NULL DEFAULT '{}',
        customer_id         BIGINT NOT NULL REFERENCES accounts(id),
        chosen_option       INTEGER NOT NULL,
        total               NUMERIC(14,0) NOT NULL,
        ip                  VARCHAR(64),
        approved_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_sketch_approvals_order ON sketch_approvals (order_id)",
    """CREATE OR REPLACE FUNCTION fn_sketch_approval_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'sketch_approvals %% is append-only', OLD.id USING ERRCODE = 'check_violation';
    END $$""",
    "DROP TRIGGER IF EXISTS trg_sketch_approval_immutable ON sketch_approvals",
    """CREATE TRIGGER trg_sketch_approval_immutable BEFORE UPDATE ON sketch_approvals
       FOR EACH ROW EXECUTE FUNCTION fn_sketch_approval_immutable()""",
]

DOWNGRADE = [
    "DROP TRIGGER IF EXISTS trg_sketch_approval_immutable ON sketch_approvals",
    "DROP FUNCTION IF EXISTS fn_sketch_approval_immutable()",
    "DROP TABLE IF EXISTS sketch_approvals",
    "ALTER TABLE quotations DROP COLUMN IF EXISTS revision_reason",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
