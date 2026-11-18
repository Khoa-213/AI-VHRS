"""V2 Phase C: the AI assistant works on the order DRAFT (owner decision D1, 2026-11-17), not only on studio drafts.

* `ai_sessions.order_id`: a session belongs to EITHER a studio draft (U5, unchanged) OR an order (one session per order,
  ON DELETE CASCADE with the order). `draft_id` becomes nullable; a CHECK keeps exactly one of the two set.
* `ai_sessions.flags`: what the assistant flagged for the Staff on an order (FORGERY_RISK, PRIVACY, OTHER); studio drafts keep
  theirs in `studio_drafts.flags` as before.
* `ai_messages.client_ref`: an id the FE gives each customer message, unique per session, so a message sent twice (retry,
  double click) runs the model once and the second request gets the stored answer.
* `ai_tool_calls.sketch_revision_id`: the working-sketch revision (V2 Phase B, `sketch_revisions`) a tool call made;
  `revision_id` stays for studio revisions.

Additive: no existing row changes (every existing session has a draft, so the CHECK holds). Rollback: `alembic downgrade 0023`
(removes the order sessions and their messages, the only rows the old schema cannot hold).

Revision ID: 0024
Revises: 0023
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE ai_sessions ADD COLUMN IF NOT EXISTS order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE",
    "ALTER TABLE ai_sessions ALTER COLUMN draft_id DROP NOT NULL",
    "ALTER TABLE ai_sessions ADD COLUMN IF NOT EXISTS flags JSONB NOT NULL DEFAULT '[]'::jsonb",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_sessions_order ON ai_sessions (order_id) WHERE order_id IS NOT NULL",
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ai_sessions_target') THEN
            ALTER TABLE ai_sessions ADD CONSTRAINT chk_ai_sessions_target CHECK (num_nonnulls(draft_id, order_id) = 1);
        END IF;
    END $$""",
    "ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS client_ref VARCHAR(64)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_messages_client_ref ON ai_messages (session_id, client_ref) "
    "WHERE client_ref IS NOT NULL",
    "ALTER TABLE ai_tool_calls ADD COLUMN IF NOT EXISTS sketch_revision_id BIGINT "
    "REFERENCES sketch_revisions(id) ON DELETE SET NULL",
]

DOWNGRADE = [
    "ALTER TABLE ai_tool_calls DROP COLUMN IF EXISTS sketch_revision_id",
    "DROP INDEX IF EXISTS ux_ai_messages_client_ref",
    "ALTER TABLE ai_messages DROP COLUMN IF EXISTS client_ref",
    "ALTER TABLE ai_sessions DROP CONSTRAINT IF EXISTS chk_ai_sessions_target",
    "DELETE FROM ai_sessions WHERE draft_id IS NULL",
    "DROP INDEX IF EXISTS ux_ai_sessions_order",
    "ALTER TABLE ai_sessions DROP COLUMN IF EXISTS flags",
    "ALTER TABLE ai_sessions DROP COLUMN IF EXISTS order_id",
    "ALTER TABLE ai_sessions ALTER COLUMN draft_id SET NOT NULL",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
