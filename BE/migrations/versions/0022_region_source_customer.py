"""Upgrade U5: a region of an OT-1 sketch may come from the customer's studio edit (source CUSTOMER).

The customer can remove a region or (ASSISTED mode) write text into it in the studio preview; the same edits are applied to
the Staff's official sketch and those rows say so with `source = 'CUSTOMER'`. The CHECK on `sketch_regions.source` only
widens (AUTO, STAFF -> AUTO, STAFF, CUSTOMER): every existing row stays valid and no data changes.
Rollback: `alembic downgrade 0021` (refused by Postgres while a CUSTOMER row exists, which is the safe outcome).

Revision ID: 0022
Revises: 0021
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sketch_regions DROP CONSTRAINT IF EXISTS sketch_regions_source_check")
    op.execute("ALTER TABLE sketch_regions ADD CONSTRAINT sketch_regions_source_check "
               "CHECK (source IN ('AUTO', 'STAFF', 'CUSTOMER'))")


def downgrade() -> None:
    op.execute("ALTER TABLE sketch_regions DROP CONSTRAINT IF EXISTS sketch_regions_source_check")
    op.execute("ALTER TABLE sketch_regions ADD CONSTRAINT sketch_regions_source_check "
               "CHECK (source IN ('AUTO', 'STAFF'))")
