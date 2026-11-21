"""V2 Phase D (owner approved D-c, 2026-11-19): a working-sketch revision remembers the order inputs it was drawn from.

* `sketch_revisions.inputs_snapshot`: the order's text input (text, template, size, alignment, layout), canvas and
  materials (paper, pen, ink) when the engine drew the revision; edits copy their parent's. Undo / redo across a new drawing
  puts the form back to the target revision's snapshot, so the form and the sketch never disagree.

Revisions saved before this migration keep NULL: undo / redo over them moves the sketch only, as before (no backfill).
Additive only. Rollback: `alembic downgrade 0025`.

Revision ID: 0026
Revises: 0025
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sketch_revisions ADD COLUMN IF NOT EXISTS inputs_snapshot JSONB")
    op.execute("COMMENT ON COLUMN sketch_revisions.inputs_snapshot IS "
               "'V2 Phase D: order text / layout / canvas / materials this revision was drawn from (NULL = before 0026)'")


def downgrade() -> None:
    op.execute("ALTER TABLE sketch_revisions DROP COLUMN IF EXISTS inputs_snapshot")
