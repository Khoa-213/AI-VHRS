"""AI chat sessions and the AI chat data policy (owner request 2026-11-24).

* `ai_chat_consents`: the customer's consent to the AI chat data policy, ONE per account and policy version (asked again
  when the version changes). `withdrawn_at`: the customer took the consent back (the assistant refuses until they agree
  again). Every accept / withdraw is also in `audit_logs` with its `policy_version`.
* `ai_sessions`: an order may have several conversations ("new chat"): the unique index on `order_id` becomes a plain index.
  `title` (the customer's own name for the conversation; NULL: shown from its first message), `deleted_at` /
  `deleted_reason` (CUSTOMER: deleted by the customer while the order was a draft; RETENTION: the retention job, N days after
  the order was completed or cancelled). A deleted conversation keeps its row, its flags and its message rows (the daily
  caps count them) but its text is wiped.
Additive except the one relaxed index; no existing row changes. Rollback: `alembic downgrade 0030` (only possible while no
order has two conversations: the unique index is created again).

Revision ID: 0031
Revises: 0030
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS ai_chat_consents (
        id              BIGSERIAL PRIMARY KEY,
        account_id      BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        policy_version  VARCHAR(20) NOT NULL,
        accepted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        withdrawn_at    TIMESTAMPTZ,
        CONSTRAINT ux_ai_chat_consents_version UNIQUE (account_id, policy_version)
    )""",
    "ALTER TABLE ai_chat_consents ENABLE ROW LEVEL SECURITY",
    "COMMENT ON TABLE ai_chat_consents IS 'Customer consent to the AI chat data policy, one row per account and policy version'",
    "DROP INDEX IF EXISTS ux_ai_sessions_order",
    "CREATE INDEX IF NOT EXISTS ix_ai_sessions_order ON ai_sessions (order_id, id) WHERE order_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_ai_sessions_customer ON ai_sessions (customer_id, last_message_at DESC)",
    "ALTER TABLE ai_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(120)",
    "ALTER TABLE ai_sessions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    "ALTER TABLE ai_sessions ADD COLUMN IF NOT EXISTS deleted_reason VARCHAR(12)",
    """DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ai_sessions_deleted') THEN
           ALTER TABLE ai_sessions ADD CONSTRAINT chk_ai_sessions_deleted
             CHECK ((deleted_at IS NULL) = (deleted_reason IS NULL)
                    AND (deleted_reason IS NULL OR deleted_reason IN ('CUSTOMER', 'RETENTION')));
         END IF;
       END $$""",
    "COMMENT ON COLUMN ai_sessions.deleted_reason IS 'CUSTOMER (deleted while the order was a draft) | RETENTION (purge job)'",
]

DOWNGRADE = [
    "ALTER TABLE ai_sessions DROP CONSTRAINT IF EXISTS chk_ai_sessions_deleted",
    "ALTER TABLE ai_sessions DROP COLUMN IF EXISTS deleted_reason",
    "ALTER TABLE ai_sessions DROP COLUMN IF EXISTS deleted_at",
    "ALTER TABLE ai_sessions DROP COLUMN IF EXISTS title",
    "DROP INDEX IF EXISTS ix_ai_sessions_customer",
    "DROP INDEX IF EXISTS ix_ai_sessions_order",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_sessions_order ON ai_sessions (order_id) WHERE order_id IS NOT NULL",
    "DROP TABLE IF EXISTS ai_chat_consents",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
