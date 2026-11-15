"""Upgrade U5: customer studio (drafts before an order, revisions with undo/redo) and the AI assistant's log (Q1, Q2 = A).

* `studio_drafts`: a customer's work before it becomes an order. `mode` TEXT (writing from a template, becomes OT-3) or
  RESTORE (a photographed original, becomes OT-1). `current_revision_id` is the undo/redo cursor. `order_id` is set when the
  draft is sent to the workshop (the order is created through the existing order service; from there on the order state
  machine is unchanged). `flags` holds what the assistant or the checks raised for the Staff (e.g. a possible forgery, BR-23).
* `studio_revisions`: every change is a new row; nothing is updated in place. `parent_id` links the history (undo moves the
  cursor to the parent, redo to the latest child). `author` CUSTOMER or AI (then `tool_name` says which tool made it).
* `ai_sessions`: one per draft; the provider that answered last (a session keeps it until it fails, Q1) and when the customer
  agreed that the conversation and the draft text go to an outside AI provider.
* `ai_messages`: each customer message and each assistant reply, with provider, model, tokens, cost (NULL when no price is
  configured: never a guessed figure), latency, a SHA-256 of what was sent, and the failover attempts.
* `ai_tool_calls`: every tool the model called, its arguments, its result and the revision it produced.

Rows go with their customer (ON DELETE CASCADE) and with their draft; the link to an order is cleared if the order is deleted.
Additive only: no existing table changes. Rollback: `alembic downgrade 0020`.

Revision ID: 0021
Revises: 0020
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS studio_drafts (
        id                  BIGSERIAL PRIMARY KEY,
        customer_id         BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        mode                VARCHAR(10) NOT NULL CHECK (mode IN ('TEXT', 'RESTORE')),
        status              VARCHAR(10) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'SUBMITTED', 'ABANDONED')),
        title               VARCHAR(150),
        current_revision_id BIGINT,
        order_id            BIGINT UNIQUE REFERENCES orders(id) ON DELETE SET NULL,
        flags               JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        submitted_at        TIMESTAMPTZ,
        CONSTRAINT chk_studio_submitted CHECK (status <> 'SUBMITTED' OR submitted_at IS NOT NULL)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_studio_drafts_customer ON studio_drafts (customer_id, status)",
    """CREATE TABLE IF NOT EXISTS studio_revisions (
        id          BIGSERIAL PRIMARY KEY,
        draft_id    BIGINT NOT NULL REFERENCES studio_drafts(id) ON DELETE CASCADE,
        parent_id   BIGINT REFERENCES studio_revisions(id) ON DELETE CASCADE,
        seq         INTEGER NOT NULL CHECK (seq >= 1),
        content     JSONB NOT NULL,
        author      VARCHAR(10) NOT NULL CHECK (author IN ('CUSTOMER', 'AI')),
        tool_name   VARCHAR(40),
        note        VARCHAR(200),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (draft_id, seq),
        CONSTRAINT chk_studio_rev_tool CHECK (author <> 'AI' OR tool_name IS NOT NULL)
    )""",
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_studio_drafts_current_revision') THEN
            ALTER TABLE studio_drafts ADD CONSTRAINT fk_studio_drafts_current_revision
                FOREIGN KEY (current_revision_id) REFERENCES studio_revisions(id) ON DELETE SET NULL;
        END IF;
    END $$""",
    """CREATE TABLE IF NOT EXISTS ai_sessions (
        id              BIGSERIAL PRIMARY KEY,
        draft_id        BIGINT NOT NULL UNIQUE REFERENCES studio_drafts(id) ON DELETE CASCADE,
        customer_id     BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        provider        VARCHAR(20),
        model           VARCHAR(80),
        consented_at    TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_message_at TIMESTAMPTZ
    )""",
    """CREATE TABLE IF NOT EXISTS ai_messages (
        id              BIGSERIAL PRIMARY KEY,
        session_id      BIGINT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
        role            VARCHAR(10) NOT NULL CHECK (role IN ('USER', 'ASSISTANT')),
        content         TEXT NOT NULL,
        status          VARCHAR(10) NOT NULL DEFAULT 'OK' CHECK (status IN ('OK', 'FAILED', 'CAPPED')),
        provider        VARCHAR(20),
        model           VARCHAR(80),
        model_calls     SMALLINT NOT NULL DEFAULT 0,
        input_tokens    INTEGER,
        output_tokens   INTEGER,
        cost_usd        NUMERIC(12, 6),
        latency_ms      INTEGER,
        input_sha256    CHAR(64),
        attempts        JSONB,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ai_messages_session ON ai_messages (session_id, id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_messages_created ON ai_messages (created_at)",
    """CREATE TABLE IF NOT EXISTS ai_tool_calls (
        id          BIGSERIAL PRIMARY KEY,
        message_id  BIGINT NOT NULL REFERENCES ai_messages(id) ON DELETE CASCADE,
        name        VARCHAR(40) NOT NULL,
        args        JSONB NOT NULL DEFAULT '{}'::jsonb,
        result      JSONB,
        ok          BOOLEAN NOT NULL,
        revision_id BIGINT REFERENCES studio_revisions(id) ON DELETE SET NULL,
        duration_ms INTEGER,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ai_tool_calls_message ON ai_tool_calls (message_id)",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS ai_tool_calls",
    "DROP TABLE IF EXISTS ai_messages",
    "DROP TABLE IF EXISTS ai_sessions",
    "ALTER TABLE IF EXISTS studio_drafts DROP CONSTRAINT IF EXISTS fk_studio_drafts_current_revision",
    "DROP TABLE IF EXISTS studio_revisions",
    "DROP TABLE IF EXISTS studio_drafts",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
