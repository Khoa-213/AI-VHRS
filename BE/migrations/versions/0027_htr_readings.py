"""V2 Phase E2b (owner approved 2026-11-19): what the AI read on the customer's photos of an OT-1 letter.

* `htr_readings`: one row per photo (page) read for an order, after the customer agreed to send that photo out. Holds the
  page transcript (the region text hints are computed from it on the fly, so they follow redraws and undo), who read it
  (provider, model, tokens, every provider tried in `attempts`), and the consent: who agreed, when (`created_at`) and the
  exact wording shown (`consent_text`, which names the providers). `source_key` is the SHA-256 of the photo's identity (input
  row, stored file, rotation, crop): the same photo as set is never sent twice for an order, and the hints find their
  reading without opening the file. `status` READ = a transcript, FAILED = nobody
  could read it (the regions stay UNREAD). Rows also count against the daily page cap (`htr_daily_pages`).

Rows go with their order (ON DELETE CASCADE); a deleted source photo clears `input_id`.
Additive only: no existing row changes. Rollback: `alembic downgrade 0026`.

Revision ID: 0027
Revises: 0026
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS htr_readings (
        id             BIGSERIAL PRIMARY KEY,
        order_id       BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        input_id       BIGINT REFERENCES order_inputs(id) ON DELETE SET NULL,
        source_key     CHAR(64) NOT NULL,
        status         VARCHAR(10) NOT NULL CHECK (status IN ('READ', 'FAILED')),
        provider       VARCHAR(20),
        model          VARCHAR(80),
        transcript     TEXT,
        input_tokens   INTEGER,
        output_tokens  INTEGER,
        attempts       JSONB NOT NULL DEFAULT '[]'::jsonb,
        consent_by     BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
        consent_text   TEXT NOT NULL,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_htr_read_has_text CHECK (status <> 'READ' OR (transcript IS NOT NULL AND provider IS NOT NULL))
    )""",
    "CREATE INDEX IF NOT EXISTS ix_htr_readings_order ON htr_readings (order_id, source_key)",
    "CREATE INDEX IF NOT EXISTS ix_htr_readings_created ON htr_readings (created_at)",
    "COMMENT ON TABLE htr_readings IS 'V2 Phase E2b: AI transcript of a customer photo (OT-1) read with the customer''s "
    "consent; region text hints are computed from it'",
]

DOWNGRADE = ["DROP TABLE IF EXISTS htr_readings"]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
