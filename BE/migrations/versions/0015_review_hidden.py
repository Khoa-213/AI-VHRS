"""Phase 5c: reviews can be hidden by a Manager (FR-58: one review per completed order, shown publicly on the home page).

* `reviews.hidden_at` TIMESTAMPTZ NULL: NULL = shown. Who hid it and why go to the audit log (REVIEW_HIDE / REVIEW_UNHIDE);
  nothing is deleted, the customer still sees their own review.
* `ix_reviews_public`: the public list reads the shown reviews newest first.

Additive only: no existing row changes (every review stays shown). Rollback: `alembic downgrade 0014`.

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_reviews_public ON reviews (created_at DESC, id DESC) WHERE hidden_at IS NULL",
]

DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_reviews_public",
    "ALTER TABLE reviews DROP COLUMN IF EXISTS hidden_at",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
