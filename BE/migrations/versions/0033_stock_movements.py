"""Stock in and out (owner decisions 2026-11-27, Q1-Q4): the Manager receives goods on a receipt with several lines, the
technician issues the materials of a job before Prepare, leftover paper goes back at Writing done, and every change of a
stock level is one append-only row in a ledger.

* `stock_receipts`: one goods receipt (NK-0001 ...) with its supplier, day and note. `client_ref` makes a repeated submit
  of the same form return the same receipt instead of adding the goods twice.
* `stock_movements`: one row per change of `stock_qty` of a paper, pen or ink: RECEIPT (+), ISSUE (-, for a job), RETURN
  (+, from a job), ADJUST (+/-, the Manager's count). `stock_after` is the level right after the change.
* `min_qty` on paper_types, pen_types, ink_colors: the Manager's minimum level (Q4). Defaults keep today's low-stock rule
  (paper below 10, pen and ink below 1).
Additive: no existing row changes except the new columns' defaults. Rollback: `alembic downgrade 0032` (drops the ledger).

Revision ID: 0033
Revises: 0032
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE paper_types ADD COLUMN IF NOT EXISTS min_qty INTEGER NOT NULL DEFAULT 10",
    "ALTER TABLE pen_types ADD COLUMN IF NOT EXISTS min_qty INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE ink_colors ADD COLUMN IF NOT EXISTS min_qty INTEGER NOT NULL DEFAULT 1",
    """DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_paper_min_qty') THEN
           ALTER TABLE paper_types ADD CONSTRAINT chk_paper_min_qty CHECK (min_qty >= 0);
         END IF;
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_pen_min_qty') THEN
           ALTER TABLE pen_types ADD CONSTRAINT chk_pen_min_qty CHECK (min_qty >= 0);
         END IF;
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ink_min_qty') THEN
           ALTER TABLE ink_colors ADD CONSTRAINT chk_ink_min_qty CHECK (min_qty >= 0);
         END IF;
       END $$""",
    """CREATE TABLE IF NOT EXISTS stock_receipts (
        id           BIGSERIAL PRIMARY KEY,
        code         VARCHAR(20) UNIQUE,
        supplier     VARCHAR(200),
        received_on  DATE NOT NULL DEFAULT CURRENT_DATE,
        note         TEXT,
        client_ref   VARCHAR(64) UNIQUE,
        created_by   BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS stock_movements (
        id           BIGSERIAL PRIMARY KEY,
        kind         VARCHAR(10) NOT NULL CHECK (kind IN ('RECEIPT', 'ISSUE', 'RETURN', 'ADJUST')),
        item_kind    VARCHAR(5) NOT NULL CHECK (item_kind IN ('PAPER', 'PEN', 'INK')),
        item_id      BIGINT NOT NULL,
        quantity     INTEGER NOT NULL CHECK (quantity <> 0),
        stock_after  INTEGER NOT NULL CHECK (stock_after >= 0),
        shortfall    INTEGER NOT NULL DEFAULT 0 CHECK (shortfall >= 0),
        job_id       BIGINT REFERENCES production_jobs(id) ON DELETE SET NULL,
        receipt_id   BIGINT REFERENCES stock_receipts(id) ON DELETE RESTRICT,
        actor_id     BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
        reason       TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_stock_move_sign CHECK (
            (kind IN ('RECEIPT', 'RETURN') AND quantity > 0) OR (kind = 'ISSUE' AND quantity < 0) OR kind = 'ADJUST'),
        CONSTRAINT chk_stock_move_links CHECK (
            (kind = 'RECEIPT' AND receipt_id IS NOT NULL) OR (kind IN ('ISSUE', 'RETURN') AND job_id IS NOT NULL)
            OR kind = 'ADJUST')
    )""",
    "CREATE INDEX IF NOT EXISTS ix_stock_movements_item ON stock_movements (item_kind, item_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_stock_movements_job ON stock_movements (job_id) WHERE job_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_stock_movements_created ON stock_movements (created_at DESC)",
    "ALTER TABLE stock_receipts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY",
    "COMMENT ON TABLE stock_receipts IS 'Goods receipt entered by the Manager (NK-xxxx); its lines are RECEIPT rows of stock_movements'",
    "COMMENT ON TABLE stock_movements IS 'Append-only stock ledger: every change of stock_qty of a paper, pen or ink'",
    "COMMENT ON COLUMN stock_movements.shortfall IS 'Units that were missing when an over-use at Writing done could not be covered (stock floored at 0)'",
    "COMMENT ON COLUMN paper_types.min_qty IS 'Manager minimum level: below it the item is shown as low stock'",
    "COMMENT ON COLUMN pen_types.min_qty IS 'Manager minimum level: below it the item is shown as low stock'",
    "COMMENT ON COLUMN ink_colors.min_qty IS 'Manager minimum level (unit: pens of this colour)'",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS stock_movements",
    "DROP TABLE IF EXISTS stock_receipts",
    "ALTER TABLE ink_colors DROP CONSTRAINT IF EXISTS chk_ink_min_qty",
    "ALTER TABLE pen_types DROP CONSTRAINT IF EXISTS chk_pen_min_qty",
    "ALTER TABLE paper_types DROP CONSTRAINT IF EXISTS chk_paper_min_qty",
    "ALTER TABLE ink_colors DROP COLUMN IF EXISTS min_qty",
    "ALTER TABLE pen_types DROP COLUMN IF EXISTS min_qty",
    "ALTER TABLE paper_types DROP COLUMN IF EXISTS min_qty",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
