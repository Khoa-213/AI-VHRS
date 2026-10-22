"""Payment gateway port (VNPay / MoMo).

Two kinds of adapter sit behind it:

* the MOCK gateway (default, `PAYMENT_MODE=mock`): simulated payments, a signed webhook that the "checkout" button replays.
  Everything it produces carries mode="MOCK" so a simulated payment is never reported as a real one.
* the REAL gateways (`integrations/vnpay.py`, `integrations/momo.py`), used when `PAYMENT_MODE` is `sandbox` (the gateways' test
  environments, test money) or `live` (production, REAL money). They create a payment link, verify the gateway's own
  signature on its IPN callback and can ask the gateway for the state of a transaction.

`real_adapter(gateway)` is the one place that decides which kind a payment uses.
"""
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol

from app.core.config import get_settings
from app.core.errors import AppError

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


# ---------------------------------------------------------------------------------------------------- real gateways
MODE_LABEL = {"mock": "MOCK", "sandbox": "SANDBOX", "live": "LIVE"}


class InvalidSignature(Exception):
    """The callback does not carry a valid signature from the gateway (or the gateway is not configured to check one)."""


class MalformedCallback(Exception):
    """The callback is signed but its content cannot be understood."""


@dataclass(frozen=True)
class PaymentLink:
    url: str
    expires_at: datetime
    meta: dict[str, Any] = field(default_factory=dict)      # gateway-specific values to keep with the payment


@dataclass(frozen=True)
class GatewayResult:
    """What a gateway says about one transaction (IPN or query). `final=False` = still in progress, nothing to settle yet."""
    txn_ref: str
    amount: int                  # VND
    success: bool
    final: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


class RealGateway(Protocol):
    name: str
    mode: str                    # "SANDBOX" | "LIVE"

    def new_txn_id(self) -> str: ...
    def create_payment(self, *, txn_ref: str, amount: int, order_info: str, client_ip: str | None, return_url: str,
                       ipn_url: str | None, expire_minutes: int) -> PaymentLink: ...
    def query(self, *, txn_ref: str, meta: Mapping[str, Any], client_ip: str | None) -> GatewayResult | None: ...


_overrides: dict[str, RealGateway] = {}


def use_adapters(adapters: Mapping[str, RealGateway] | None) -> None:
    """Tests only: put stand-in real adapters in place of the configured ones (None clears them)."""
    _overrides.clear()
    _overrides.update(adapters or {})


def mode_label() -> str:
    return MODE_LABEL[get_settings().payment_mode]


def real_adapter(gateway: Any, *, strict: bool = True) -> RealGateway | None:
    """The real adapter for `gateway`, or None while payments are simulated (PAYMENT_MODE=mock).

    With `strict`, a real mode with missing credentials is an error (503) so no payment can start half-configured; the IPN
    endpoints ask with strict=False and simply cannot verify anything then."""
    s = get_settings()
    if s.payment_mode == "mock":
        return None
    name = str(getattr(gateway, "value", gateway)).upper()
    if name in _overrides:
        return _overrides[name]
    mode = MODE_LABEL[s.payment_mode]
    if name == "VNPAY" and s.vnpay_tmn_code and s.vnpay_hash_secret:
        from app.integrations.vnpay import VnpayGateway
        return VnpayGateway(tmn_code=s.vnpay_tmn_code, hash_secret=s.vnpay_hash_secret, pay_url=s.vnpay_pay_url,
                            api_url=s.vnpay_api_url, mode=mode)
    if name == "MOMO" and s.momo_partner_code and s.momo_access_key and s.momo_secret_key:
        from app.integrations.momo import MomoGateway
        return MomoGateway(partner_code=s.momo_partner_code, access_key=s.momo_access_key,
                           secret_key=s.momo_secret_key, endpoint=s.momo_endpoint, mode=mode)
    if strict:
        raise AppError(503, "GATEWAY_NOT_CONFIGURED", f"Cổng thanh toán {name} chưa được cấu hình trên máy chủ.")
    return None


def ipn_url(gateway: str) -> str | None:
    base = (get_settings().public_base_url or "").rstrip("/")
    return f"{base}/api/v1/webhooks/payments/{gateway.lower()}/ipn" if base else None


def gateway_status() -> list[dict[str, Any]]:
    """Which gateways the customer may pick right now (for the checkout screen)."""
    mode = mode_label()
    out = []
    for name in ("VNPAY", "MOMO"):
        try:
            enabled = True if mode == "MOCK" else real_adapter(name) is not None
        except AppError:
            enabled = False
        out.append({"gateway": name, "mode": mode, "enabled": enabled})
    return out
