"""payment_gateway enum: add PAYOS (VietQR bank transfer through payOS, Phase 4c-2d).

One new enum value, nothing else: no table or column changes, existing rows are untouched. Postgres cannot drop an enum value,
so the downgrade only checks that no payment uses it and leaves the (harmless) value in place.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE may not run inside a transaction block on every Postgres version, so leave it for the autocommit block.
    with op.get_context().autocommit_block():
        op.get_bind().exec_driver_sql("ALTER TYPE payment_gateway ADD VALUE IF NOT EXISTS 'PAYOS'")


def downgrade() -> None:
    used = op.get_bind().exec_driver_sql("SELECT count(*) FROM payments WHERE gateway::text = 'PAYOS'").scalar()
    if used:
        raise RuntimeError(f"{used} payments use the PAYOS gateway: cannot downgrade 0005")
