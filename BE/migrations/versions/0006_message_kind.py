"""messages: a `kind` (TEXT | ORDER_CARD) so the order card can be stored and shown to both sides (chat, Phase 4f).

* `kind` VARCHAR(20) NOT NULL DEFAULT 'TEXT' with a CHECK on the two values: every existing message becomes TEXT, nothing is lost.
* An order card has neither text nor images, so `chk_message_not_empty` (body or at least one attachment) must also accept it.
* A partial index on the unread messages keeps the chat badge / conversation list cheap (they count unread per order).

Downgrade deletes the ORDER_CARD rows (they would break the old "not empty" check), then restores the old check.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE = [
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'TEXT'",
    """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_messages_kind' AND conrelid = 'public.messages'::regclass) THEN
    ALTER TABLE messages ADD CONSTRAINT chk_messages_kind CHECK (kind IN ('TEXT', 'ORDER_CARD'));
  END IF;
END $$""",
    "ALTER TABLE messages DROP CONSTRAINT IF EXISTS chk_message_not_empty",
    """ALTER TABLE messages ADD CONSTRAINT chk_message_not_empty
         CHECK (kind = 'ORDER_CARD' OR body IS NOT NULL OR jsonb_array_length(attachments) > 0)""",
    "CREATE INDEX IF NOT EXISTS ix_messages_unread ON messages (order_id) WHERE read_at IS NULL",
]

DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_messages_unread",
    "DELETE FROM messages WHERE kind = 'ORDER_CARD'",
    "ALTER TABLE messages DROP CONSTRAINT IF EXISTS chk_message_not_empty",
    "ALTER TABLE messages ADD CONSTRAINT chk_message_not_empty CHECK (body IS NOT NULL OR jsonb_array_length(attachments) > 0)",
    "ALTER TABLE messages DROP CONSTRAINT IF EXISTS chk_messages_kind",
    "ALTER TABLE messages DROP COLUMN IF EXISTS kind",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt.replace("%", "%%"))


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt.replace("%", "%%"))
