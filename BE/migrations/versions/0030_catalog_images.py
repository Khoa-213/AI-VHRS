"""Catalog images (owner request 2026-11-24): the workshop's own photo of each paper, pen and ink, so the web app shows the
real product instead of a drawing made from numbers or a picture taken from somewhere else.

* `paper_types`, `pen_types`, `ink_colors` get `image_path` (object path in the PUBLIC catalog media bucket, NULL: no photo
  yet) and `image_updated_at`. The file itself lives in object storage; the API answers with `image_url` built from the path.
Additive only: two nullable columns per table, no existing row changes. Rollback: `alembic downgrade 0029`.

Revision ID: 0030
Revises: 0029
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

TABLES = ("paper_types", "pen_types", "ink_colors")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS image_path TEXT")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS image_updated_at TIMESTAMPTZ")
        op.execute(f"COMMENT ON COLUMN {table}.image_path IS "
                   "'Object path of the product photo in the public catalog media bucket (NULL: none)'")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS image_updated_at")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS image_path")
