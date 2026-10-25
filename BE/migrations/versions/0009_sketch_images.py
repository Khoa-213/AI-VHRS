"""sketches.image_urls: storage paths of the customer-facing JPEG of each page.

The database never stores image bytes (only object paths; the files live in the Supabase Storage bucket), so JPEG needs no
type change. This adds the list of JPEG paths (one per page, page order) next to the technical PNG `preview_url`.
Existing sketches keep an empty list; the API falls back to their PNG previews.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("ALTER TABLE sketches ADD COLUMN IF NOT EXISTS image_urls text[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.get_bind().exec_driver_sql("ALTER TABLE sketches DROP COLUMN IF EXISTS image_urls")
