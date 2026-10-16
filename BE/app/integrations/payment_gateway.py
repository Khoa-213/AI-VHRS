"""Payment gateway port (VNPay / MoMo). Only the MOCK adapter exists until sandbox accounts are available.

The mock behaves like a real gateway from the system's point of view: it issues a transaction id, and the
result reaches the system only through a signed webhook (HMAC-SHA256 over the raw body). Everything it
produces carries mode="MOCK" so a simulated payment is never reported as a real one.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Protocol

from app.core.config import get_settings

SIGNATURE_HEADER = "X-Signature"
_LABEL = b"vhrs-payment-webhook/v1"


class GatewayAdapter(Protocol):
    mode: str

    def new_txn_id(self, gateway: str) -> str: ...
    def checkout_path(self, payment_id: int) -> str: ...
    def sign(self, body: bytes) -> str: ...
    def verify(self, body: bytes, signature: str | None) -> bool: ...


class MockGateway:
    mode = "MOCK"

    @staticmethod
    def _key() -> bytes:
        # Derived from JWT_SECRET so the mock needs no extra secret; real gateways bring their own keys.
        return hmac.new(get_settings().jwt_secret.encode(), _LABEL, hashlib.sha256).digest()

    def new_txn_id(self, gateway: str) -> str:
        return f"MOCK-{gateway}-{uuid.uuid4().hex[:20]}"

    def checkout_path(self, payment_id: int) -> str:
        return f"/api/v1/payments/{payment_id}/mock-checkout"

    def sign(self, body: bytes) -> str:
        return hmac.new(self._key(), body, hashlib.sha256).hexdigest()

    def verify(self, body: bytes, signature: str | None) -> bool:
        return bool(signature) and hmac.compare_digest(self.sign(body), signature.strip().lower())


def webhook_body(*, txn_id: str, order_code: str, amount: int, result: str, paid_at: datetime | None) -> bytes:
    """Canonical JSON the (mock) gateway posts to /webhooks/payments/{gateway}."""
    return json.dumps({"txn_id": txn_id, "order_code": order_code, "amount": amount, "result": result,
                       "paid_at": paid_at.isoformat() if paid_at else None},
                      sort_keys=True, separators=(",", ":")).encode()


_adapter: GatewayAdapter = MockGateway()


def get_gateway() -> GatewayAdapter:
    return _adapter
