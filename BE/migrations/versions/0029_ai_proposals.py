"""AI proposals on an order (owner request 2026-11-22): the order assistant no longer changes the order directly. One assistant
turn that would change the order (content, layout, materials, options, sketch) is stored as a proposal; the order changes
only when the customer applies it.

* `ai_proposals`: one row per assistant reply that proposes a change. `base_state_hash` is the order state the proposal was
  made on (a proposal applies only while the order is still in that state); `before_state` / `after_state` are the order
  form + sketch cursor before / after the assistant's changes; `changes` is the readable diff for the FE; `estimate` the
  estimated price after the change; `sketch_revision_id` the sketch revision the order shows once applied (NULL: sketch
  unchanged); `sketch_revision_ids` every revision the proposal relies on (also those of the proposal it was built on), kept
  out of redo while the proposal is not applied. `parent_proposal_id`: the pending proposal this one continued.
* status PENDING -> APPLIED | REJECTED. "Stale" (the order changed since) is computed on read, never stored.
Every foreign key to an order-owned row is ON DELETE CASCADE (deleting an order / a test order removes its proposals).
Row-level security is enabled like on the other `ai_*` tables (the API connects as the owner).
Additive only: no existing row changes. Rollback: `alembic downgrade 0028`.

Revision ID: 0029
Revises: 0028
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS ai_proposals (
        id                   BIGSERIAL PRIMARY KEY,
        order_id             BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        session_id           BIGINT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
        message_id           BIGINT NOT NULL UNIQUE REFERENCES ai_messages(id) ON DELETE CASCADE,
        parent_proposal_id   BIGINT REFERENCES ai_proposals(id) ON DELETE SET NULL,
        status               VARCHAR(10) NOT NULL DEFAULT 'PENDING'
                             CONSTRAINT chk_ai_proposals_status CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED')),
        base_state_hash      CHAR(64) NOT NULL,
        before_state         JSONB NOT NULL,
        after_state          JSONB NOT NULL,
        changes              JSONB NOT NULL DEFAULT '[]'::jsonb,
        estimate             JSONB,
        sketch_revision_id   BIGINT REFERENCES sketch_revisions(id) ON DELETE CASCADE,
        sketch_revision_ids  BIGINT[] NOT NULL DEFAULT '{}',
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        decided_at           TIMESTAMPTZ,
        CONSTRAINT chk_ai_proposals_decided CHECK ((status = 'PENDING') = (decided_at IS NULL))
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ai_proposals_order ON ai_proposals (order_id, status)",
    "ALTER TABLE ai_proposals ENABLE ROW LEVEL SECURITY",
    "COMMENT ON TABLE ai_proposals IS 'Changes the order assistant proposes; the order changes only when the customer "
    "applies one'",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS ai_proposals",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
