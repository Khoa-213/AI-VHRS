"""Phase 4d-1: refunds after cancelling a paid order (BR-14, BR-16, FR-19).

1. `ux_payments_active_refund`: one live refund (PENDING or SUCCESS) per original payment and per kind
   (`gateway_payload->>'refund_kind'`: CANCELLATION = the order was cancelled after its deposit, ORPHAN = money that reached us
   for a payment that no longer counted). Two Staff clicking at once, or a cancel retried, can never refund the same money twice.
2. `fn_order_state_guard`: the BR-16 threshold (cumulative ETA postponement beyond which an order that has started writing may
   still be cancelled) is read from `system_settings.eta_cancel_threshold_days` instead of the literal 7. The setting already
   exists (migration 0002, value 7), so behaviour is unchanged until the Admin edits it. The function is patched in place from
   its current definition (only that one comparison changes); upgrade refuses if the expected text is not found exactly once.

No data is touched. Rollback: `alembic downgrade 0013`.

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OLD_CHECK = "NEW.eta_postponed_days <= 7"
NEW_CHECK = ("NEW.eta_postponed_days <= COALESCE((SELECT (value #>> '{}')::int FROM system_settings "
             "WHERE key = 'eta_cancel_threshold_days'), 7)")


def _patch_guard(conn, old: str, new: str) -> None:
    body = conn.exec_driver_sql("SELECT pg_get_functiondef('fn_order_state_guard()'::regprocedure)").scalar_one()
    if body.count(old) != 1:
        raise RuntimeError(f"fn_order_state_guard: expected the text {old!r} exactly once, found {body.count(old)}")
    conn.exec_driver_sql(body.replace(old, new).replace("%", "%%"))


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX ux_payments_active_refund ON payments (refund_of_id, (gateway_payload ->> 'refund_kind')) "
        "WHERE type = 'REFUND' AND status IN ('PENDING', 'SUCCESS')")
    _patch_guard(conn, OLD_CHECK, NEW_CHECK)


def downgrade() -> None:
    conn = op.get_bind()
    _patch_guard(conn, NEW_CHECK, OLD_CHECK)
    conn.exec_driver_sql("DROP INDEX IF EXISTS ux_payments_active_refund")
