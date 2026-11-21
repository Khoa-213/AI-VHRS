"""OT-2 Phase O2 (owner approved 2026-11-20, docs/OT2_LEARNED_STYLE_PLAN.md section 9): handwriting styles built from the
fixed sample sheet.

* `style_status` gains `DRAFT`: a style the customer is still filling (pages uploaded, not sent for review). The existing
  values keep their meaning (PENDING_REVIEW = waiting for the Staff, APPROVED, REJECTED, DELETED).
* `handwriting_styles` gains `sheet_version` (which sheet layout the pages follow, e.g. SHEET_V1), `review_note` (the
  Staff's reason when rejecting), `rejected_samples` (sample ids the Staff dropped before approving), `submitted_at`,
  `updated_at`.
* `handwriting_style_pages`: one row per photographed sheet page of a style (re-uploading a page replaces its row): the
  stored photo, what was read from it (`read_result`: per box status and traced strokes) and when.
Row-level security is enabled on the new table like on `handwriting_styles` (the API connects as the owner).
Additive only: no existing row changes (existing styles keep `sheet_version` NULL). Rollback: `alembic downgrade 0027`
(the enum value stays: Postgres cannot drop an enum value; harmless).

Revision ID: 0028
Revises: 0027
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TYPE style_status ADD VALUE IF NOT EXISTS 'DRAFT'",
    "ALTER TABLE handwriting_styles ADD COLUMN IF NOT EXISTS sheet_version VARCHAR(20)",
    "ALTER TABLE handwriting_styles ADD COLUMN IF NOT EXISTS review_note TEXT",
    "ALTER TABLE handwriting_styles ADD COLUMN IF NOT EXISTS rejected_samples JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE handwriting_styles ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ",
    "ALTER TABLE handwriting_styles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    """CREATE TABLE IF NOT EXISTS handwriting_style_pages (
        id           BIGSERIAL PRIMARY KEY,
        style_id     BIGINT NOT NULL REFERENCES handwriting_styles(id) ON DELETE CASCADE,
        page_no      SMALLINT NOT NULL CHECK (page_no BETWEEN 1 AND 20),
        file_url     TEXT NOT NULL,
        mime_type    VARCHAR(50) NOT NULL,
        read_result  JSONB NOT NULL,
        uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_style_page UNIQUE (style_id, page_no)
    )""",
    "ALTER TABLE handwriting_style_pages ENABLE ROW LEVEL SECURITY",
    "COMMENT ON TABLE handwriting_style_pages IS 'OT-2 Phase O2: photographed pages of a handwriting sample sheet and what was "
    "read from each box'",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS handwriting_style_pages",
    "ALTER TABLE handwriting_styles DROP COLUMN IF EXISTS updated_at",
    "ALTER TABLE handwriting_styles DROP COLUMN IF EXISTS submitted_at",
    "ALTER TABLE handwriting_styles DROP COLUMN IF EXISTS rejected_samples",
    "ALTER TABLE handwriting_styles DROP COLUMN IF EXISTS review_note",
    "ALTER TABLE handwriting_styles DROP COLUMN IF EXISTS sheet_version",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
