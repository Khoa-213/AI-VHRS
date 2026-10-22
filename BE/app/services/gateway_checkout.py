"""Opening a gateway transaction for payment rows (deposit, or final = FINAL + SHIPPING paid together).

In PAYMENT_MODE=mock nothing leaves the server: the rows carry a mock transaction id and the customer's "checkout" button
replays a signed webhook. In sandbox/live the real adapter creates a payment link; it is stored with the rows (so the same
intent reuses it until it expires) and the customer is sent there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings
from app.integrations import payment_gateway as gw
from app.models.ops import Payment, PaymentGateway, PaymentStatus
from app.models.order import Order


def begin(gateway: PaymentGateway) -> tuple[str, str]:
    """(transaction reference, mode label) for a new payment on `gateway`."""
    adapter = gw.real_adapter(gateway)
    if adapter is None:
        mock = gw.get_gateway()
        return mock.new_txn_id(gateway.value), mock.mode
    return adapter.new_txn_id(), adapter.mode


def group_ref(row: Payment) -> str:
    return (row.gateway_txn_id or "").split(":")[0]


def attach(rows: list[Payment], gateway: PaymentGateway, order: Order, *, total: Decimal, ip: str | None) -> None:
    """Create the payment link for the transaction that settles `rows` (no-op while payments are simulated)."""
    adapter = gw.real_adapter(gateway)
    if adapter is None or not rows:
        return
    s = get_settings()
    link = adapter.create_payment(
        txn_ref=group_ref(rows[0]), amount=int(total), order_info=f"Thanh toan don {order.code}", client_ip=ip,
        return_url=return_url(s.payment_return_url, order), ipn_url=gw.ipn_url(gateway.value), expire_minutes=s.payment_expire_minutes)
    for row in rows:
        row.gateway_payload = {**(row.gateway_payload or {}), "pay_url": link.url,
                               "pay_url_expires_at": link.expires_at.isoformat(),
                               "gateway_meta": {**link.meta, "transfer_amount": int(total)}}


def return_url(base: str, order: Order) -> str:
    """The page the customer lands on after paying, with the order id added so the web app knows which order to show."""
    parts = urlsplit(base)
    query = urlencode([*parse_qsl(parts.query), ("order_id", order.id)])
    return urlunsplit(parts._replace(query=query))


def close(row: Payment) -> None:
    """Best effort: close a payment link that is being replaced, so the customer cannot still pay the old one. Only payOS needs
    it (a bank transfer cannot be refused once the QR is scanned); the card gateways' links just expire."""
    if row.gateway != PaymentGateway.PAYOS or (row.gateway_payload or {}).get("mode") == "MOCK":
        return
    adapter = gw.real_adapter(row.gateway, strict=False)
    if adapter is not None:
        adapter.cancel(group_ref(row))


def usable(row: Payment) -> bool:
    """A pending payment may be handed to the customer again: always for a mock, until its link expires for a real one."""
    if row.status != PaymentStatus.PENDING:
        return False
    payload = row.gateway_payload or {}
    if payload.get("mode") == "MOCK":
        return True
    try:
        return bool(payload.get("pay_url")) and datetime.fromisoformat(payload["pay_url_expires_at"]) > datetime.now(timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
