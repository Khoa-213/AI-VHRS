"""orders: the carrier service the customer chose for delivery (GHN / GHTK, Phase 4c-2b).

Three nullable columns on `orders`; nothing else changes, no default, so existing rows are untouched. The customer picks a
carrier and one of its services (with the fee and the expected delivery shown), and the Staff later create the waybill with
exactly that choice.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_carrier carrier",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_service_code VARCHAR(30)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_eta TIMESTAMPTZ",
    """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_orders_shipping_service') THEN
    ALTER TABLE orders ADD CONSTRAINT chk_orders_shipping_service
      CHECK ((shipping_carrier IS NULL) = (shipping_service_code IS NULL));
  END IF;
END $$""",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.exec_driver_sql(stmt.replace("%", "%%"))


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in ("ALTER TABLE orders DROP CONSTRAINT IF EXISTS chk_orders_shipping_service",
                 "ALTER TABLE orders DROP COLUMN IF EXISTS shipping_eta",
                 "ALTER TABLE orders DROP COLUMN IF EXISTS shipping_service_code",
                 "ALTER TABLE orders DROP COLUMN IF EXISTS shipping_carrier"):
        conn.exec_driver_sql(stmt)
