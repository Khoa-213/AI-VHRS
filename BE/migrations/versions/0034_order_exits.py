"""Ways out for an order stuck after production (audit 2026-11-27, D08, owner chose the full version).

`fn_order_state_guard` let an order leave AWAITING_FINAL_PAYMENT only by being paid, READY_TO_DELIVER only by being handed
over, and DELIVERING only by being delivered. A customer who never pays the balance, never collects, or whose parcel comes
back therefore left the order open for ever. Three transitions are added, nothing else changes:

* AWAITING_FINAL_PAYMENT -> CANCELLED, READY_TO_DELIVER -> CANCELLED, DELIVERING -> CANCELLED: a Manager closes the order
  (with a reason, and a refund request for whatever is to be given back). The product exists, so production_status stays FINISHED.
* DELIVERING -> READY_TO_DELIVER: the delivery failed or the parcel was returned, and the Staff switch the order to
  collection at the workshop.

The function is patched in place from its current definition, as migration 0014 did; upgrade refuses when a line it expects
is not found exactly once. No data is touched. Rollback: `alembic downgrade 0033` (refused by the patch check if the
function was changed again in between; orders already moved by the new transitions keep their status).

Revision ID: 0034
Revises: 0033
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

PATCHES = [
    ("WHEN 'AWAITING_FINAL_PAYMENT' THEN NEW.order_status IN ('READY_TO_DELIVER')",
     "WHEN 'AWAITING_FINAL_PAYMENT' THEN NEW.order_status IN ('READY_TO_DELIVER','CANCELLED')"),
    ("WHEN 'READY_TO_DELIVER'       THEN NEW.order_status IN ('DELIVERING','COMPLETED')",
     "WHEN 'READY_TO_DELIVER'       THEN NEW.order_status IN ('DELIVERING','COMPLETED','CANCELLED')"),
    ("WHEN 'DELIVERING'             THEN NEW.order_status IN ('COMPLETED')",
     "WHEN 'DELIVERING'             THEN NEW.order_status IN ('COMPLETED','READY_TO_DELIVER','CANCELLED')"),
]


def _patch_guard(conn, pairs: list[tuple[str, str]]) -> None:
    body = conn.exec_driver_sql("SELECT pg_get_functiondef('fn_order_state_guard()'::regprocedure)").scalar_one()
    for old, new in pairs:
        if body.count(old) != 1:
            raise RuntimeError(f"fn_order_state_guard: expected the text {old!r} exactly once, found {body.count(old)}")
        body = body.replace(old, new)
    conn.exec_driver_sql(body.replace("%", "%%"))


def upgrade() -> None:
    _patch_guard(op.get_bind(), PATCHES)


def downgrade() -> None:
    _patch_guard(op.get_bind(), [(new, old) for old, new in PATCHES])
