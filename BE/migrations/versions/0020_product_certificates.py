"""Upgrade U8: physical watermark line + certificate card with a QR code to a public verification page.

* `orders.physical_watermark` BOOLEAN NOT NULL DEFAULT FALSE: the customer's choice for an OT-3 order (Q3: optional for
  OT-3). An OT-1 order always carries the watermark whatever this column says (Q3: mandatory for OT-1).
* `product_certificates`: one verification code per order ("XXXX-XXXX", 31 unambiguous characters, about 40 bits),
  created the first time a sketch of a watermarked order is saved, because the robot writes the code on the sheet.
  The status shown on the public page is derived at read time from the order, its signed snapshot and its jobs; nothing
  here is copied from them. Rows go with their order (ON DELETE CASCADE, like sketches).
* `sketches.watermark` JSONB NULL: what the watermark strokes of that sketch version say and where they are (code, text,
  font size, TOP / BOTTOM per page, stroke count per page). The strokes themselves are in the trajectory file (kind
  "watermark"), so they are covered by its SHA-256; this copy lets the signed snapshot carry the block without reading
  the file. NULL = no watermark (OT-3 without the option, or a sketch saved before U8).

Additive only: no existing row changes (the new columns default to FALSE / NULL, which is today's behaviour for every OT-3 order).
Rollback: `alembic downgrade 0019`.

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS physical_watermark BOOLEAN NOT NULL DEFAULT FALSE",
    """CREATE TABLE IF NOT EXISTS product_certificates (
        id          BIGSERIAL PRIMARY KEY,
        order_id    BIGINT NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
        code        VARCHAR(9) NOT NULL UNIQUE CHECK (code ~ '^[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$'),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "ALTER TABLE sketches ADD COLUMN IF NOT EXISTS watermark JSONB",
]

DOWNGRADE = [
    "ALTER TABLE sketches DROP COLUMN IF EXISTS watermark",
    "DROP TABLE IF EXISTS product_certificates",
    "ALTER TABLE orders DROP COLUMN IF EXISTS physical_watermark",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
