"""V2 Phase H (owner approved 2026-11-19): the official sketch versions keep their `vhrs-sketch/2` document.

* `sketches.document_uri`: object path of the version's `vhrs-sketch/2` document (stroke / word ids, provenance, who edited
  each stroke). v1 taken from the customer is EXACTLY the customer's document (same ids); a Staff geometry edit copies the
  ids it did not change; a generation / upload / region edit starts new ids.
* `sketches.geometry_hash`: hash of the document's strokes (`sketch_geometry.geometry_hash`), equal to the hash of the
  trajectory's strokes without the U8 line, so the two files are checked against each other.

Versions saved before this migration keep NULL: their document is derived from the trajectory file when it is read (H-c:
no backfill, no existing row or file changes). Additive only. Rollback: `alembic downgrade 0024`.

Revision ID: 0025
Revises: 0024
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sketches ADD COLUMN IF NOT EXISTS document_uri TEXT")
    op.execute("ALTER TABLE sketches ADD COLUMN IF NOT EXISTS geometry_hash VARCHAR(64)")
    op.execute("COMMENT ON COLUMN sketches.document_uri IS "
               "'V2 Phase H: vhrs-sketch/2 document of this version (NULL = saved before 0025, derived from the trajectory)'")
    op.execute("COMMENT ON COLUMN sketches.geometry_hash IS "
               "'V2 Phase H: sketch_geometry.geometry_hash of the document (strokes without the U8 line)'")


def downgrade() -> None:
    op.execute("ALTER TABLE sketches DROP COLUMN IF EXISTS geometry_hash")
    op.execute("ALTER TABLE sketches DROP COLUMN IF EXISTS document_uri")
