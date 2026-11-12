"""Upgrade U1: signed, immutable production snapshots (docs/UPGRADE_AI_ROBOT_PLAN.md section 3.4).

* `production_snapshots`: one row per issued package. `payload` is the canonical JSON text that was signed (kept as TEXT,
  not JSONB, so the exact signed bytes survive), `payload_sha256` its hash, `signature` + `key_id` the Ed25519 signature.
  At most one ACTIVE (not revoked) snapshot per order.
* trigger `trg_production_snapshot_immutable`: the signed columns can never change; the only allowed update is revoking
  once (revoked_at + revoked_reason), and a revoked snapshot stays revoked.
* `production_jobs.snapshot_id` NULL: jobs created before U1 keep NULL and run the old hash check ("legacy").

Additive only: no existing row changes. Rollback: `alembic downgrade 0015` (drops the column, the trigger and the table;
the snapshots written meanwhile are lost, jobs fall back to the legacy check).

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UPGRADE = [
    """CREATE TABLE IF NOT EXISTS production_snapshots (
        id              BIGSERIAL PRIMARY KEY,
        package_id      UUID NOT NULL UNIQUE,
        order_id        BIGINT NOT NULL REFERENCES orders(id),
        sketch_id       BIGINT NOT NULL REFERENCES sketches(id),
        quotation_id    BIGINT REFERENCES quotations(id),
        payment_id      BIGINT REFERENCES payments(id),
        schema_version  VARCHAR(40) NOT NULL,
        payload         TEXT NOT NULL,
        payload_sha256  CHAR(64) NOT NULL,
        signature       TEXT NOT NULL,
        key_id          VARCHAR(40) NOT NULL,
        created_by      BIGINT REFERENCES accounts(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at      TIMESTAMPTZ,
        revoked_reason  TEXT,
        CONSTRAINT chk_snapshot_sha256 CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
        CONSTRAINT chk_snapshot_revoke CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_production_snapshot_active ON production_snapshots (order_id) WHERE revoked_at IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_production_snapshots_order ON production_snapshots (order_id, created_at DESC)",
    """CREATE OR REPLACE FUNCTION fn_production_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.package_id IS DISTINCT FROM OLD.package_id OR NEW.order_id IS DISTINCT FROM OLD.order_id
           OR NEW.sketch_id IS DISTINCT FROM OLD.sketch_id OR NEW.quotation_id IS DISTINCT FROM OLD.quotation_id
           OR NEW.payment_id IS DISTINCT FROM OLD.payment_id OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
           OR NEW.payload IS DISTINCT FROM OLD.payload OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256
           OR NEW.signature IS DISTINCT FROM OLD.signature OR NEW.key_id IS DISTINCT FROM OLD.key_id
           OR NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'production snapshot %% is immutable', OLD.id USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.revoked_at IS NOT NULL AND (NEW.revoked_at IS DISTINCT FROM OLD.revoked_at
                                           OR NEW.revoked_reason IS DISTINCT FROM OLD.revoked_reason) THEN
            RAISE EXCEPTION 'production snapshot %% is already revoked', OLD.id USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$""",
    "DROP TRIGGER IF EXISTS trg_production_snapshot_immutable ON production_snapshots",
    """CREATE TRIGGER trg_production_snapshot_immutable BEFORE UPDATE ON production_snapshots
       FOR EACH ROW EXECUTE FUNCTION fn_production_snapshot_immutable()""",
    "ALTER TABLE production_jobs ADD COLUMN IF NOT EXISTS snapshot_id BIGINT REFERENCES production_snapshots(id)",
    "CREATE INDEX IF NOT EXISTS ix_production_jobs_snapshot ON production_jobs (snapshot_id) WHERE snapshot_id IS NOT NULL",
]

DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_production_jobs_snapshot",
    "ALTER TABLE production_jobs DROP COLUMN IF EXISTS snapshot_id",
    "DROP TRIGGER IF EXISTS trg_production_snapshot_immutable ON production_snapshots",
    "DROP FUNCTION IF EXISTS fn_production_snapshot_immutable()",
    "DROP TABLE IF EXISTS production_snapshots",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in UPGRADE:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for stmt in DOWNGRADE:
        conn.exec_driver_sql(stmt)
