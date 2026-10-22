"""Carrier port (GHN / GHTK): quote services, create and cancel a waybill, get the label, read the carrier's callbacks.

Behind it, `CARRIER_MODE` picks the adapter:

* `mock` (default): simulated carriers (`MockCarrier`); their callbacks are signed with a key derived from JWT_SECRET and carry
  mode="MOCK". Nothing leaves the server.
* `sandbox` / `live`: the real adapters in `ghn.py` and `ghtk.py`, talking to the carriers' test or production APIs.

Whether a carrier's API is used at all is the DB setting `system_settings.integrations_enabled.<CARRIER>`; while it is false the
carrier is offered with one option priced from the fallback fee table (FR-21: "phí dự phòng khi API lỗi").
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain.carrier_rules import Parcel, ServiceQuote, TrackingEvent, Waybill
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback
from app.models.ops import ShipmentStatus

SIGNATURE_HEADER = "X-Signature"
_LABEL = b"vhrs-carrier-webhook/v1"
CARRIERS = ("GHN", "GHTK")
MODE_LABEL = {"mock": "MOCK", "sandbox": "SANDBOX", "live": "LIVE"}


class CarrierAdapter(Protocol):
    name: str
    mode: str

    def quote(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str) -> list[ServiceQuote]: ...
    def create(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str, service_code: str,
               note: str | None) -> Waybill: ...
    def cancel(self, waybill_code: str) -> None: ...
    def label(self, *, waybill_code: str, context: Mapping[str, Any]) -> bytes | None: ...
    def parse_webhook(self, *, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> TrackingEvent: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------------- the MOCK carrier
class MockCarrier:
    mode = "MOCK"

    def __init__(self, name: str, fee_table: Mapping[str, Any] | None):
        self.name, self._fees = name, dict(fee_table or {})

    @staticmethod
    def _key() -> bytes:
        return hmac.new(get_settings().jwt_secret.encode(), _LABEL, hashlib.sha256).digest()

    def sign(self, body: bytes) -> str:
        return hmac.new(self._key(), body, hashlib.sha256).hexdigest()

    def _verify(self, body: bytes, signature: str | None) -> bool:
        return bool(signature) and hmac.compare_digest(self.sign(body), signature.strip().lower())

    def quote(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str) -> list[ServiceQuote]:
        base = self._fees.get(parcel.package_type)
        if base is None:
            raise AppError(503, "SHIPPING_FEE_UNAVAILABLE", "Chưa cấu hình phí vận chuyển cho loại gói này.")
        return cr.mock_services(self.name, Decimal(str(base)), _now())

    def create(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str, service_code: str,
               note: str | None) -> Waybill:
        known = {code for code, *_ in cr.MOCK_SERVICES[self.name]} | {"STANDARD"}
        if service_code not in known:
            raise AppError(422, "SERVICE_NOT_AVAILABLE", "Dịch vụ vận chuyển không tồn tại.")
        return Waybill(code=f"MOCK-{self.name}-{uuid.uuid4().hex[:12].upper()}", fee=None, raw={"mode": "MOCK"})

    def cancel(self, waybill_code: str) -> None:
        return None

    def label(self, *, waybill_code: str, context: Mapping[str, Any]) -> bytes | None:
        from app.services.shipment_label import render_label
        return render_label(waybill_code=waybill_code, carrier=self.name, service_name=str(context.get("service_name", "")),
                            order_code=str(context.get("order_code", "")), receiver=str(context.get("receiver", "")),
                            phone=str(context.get("phone", "")), address_line=str(context.get("address_line", "")),
                            weight_g=int(context.get("weight_g", 0)), mock=True)

    # callbacks: {"waybill_code", "status": <shipment_status>, "event_time", "reason"} signed in X-Signature
    def webhook_body(self, waybill_code: str, status: ShipmentStatus, reason: str | None = None) -> bytes:
        return json.dumps({"waybill_code": waybill_code, "status": status.value, "event_time": _now().isoformat(),
                           "reason": reason}, sort_keys=True, separators=(",", ":")).encode()

    def parse_webhook(self, *, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> TrackingEvent:
        if not self._verify(body, headers.get(SIGNATURE_HEADER) or headers.get(SIGNATURE_HEADER.lower())):
            raise InvalidSignature()
        try:
            data = json.loads(body)
            code, status = str(data["waybill_code"]), ShipmentStatus(data["status"])
        except (ValueError, KeyError, TypeError) as exc:
            raise MalformedCallback() from exc
        return TrackingEvent(waybill_code=code, raw_status=status.value, status=status, reason=data.get("reason"), raw=data)


# ---------------------------------------------------------------------------------------------------- registry
_overrides: dict[str, CarrierAdapter] = {}
_flag_override: dict[str, bool] | None = None


def use_adapters(adapters: Mapping[str, CarrierAdapter] | None) -> None:
    """Tests only: stand-in adapters for the real modes (None clears)."""
    _overrides.clear()
    _overrides.update(adapters or {})


def use_flags(flags: Mapping[str, bool] | None) -> None:
    """Tests only: decide which carriers' APIs count as enabled without touching the database (None = read the setting)."""
    global _flag_override
    _flag_override = dict(flags) if flags is not None else None


def mode_label() -> str:
    return MODE_LABEL[get_settings().carrier_mode]


def api_enabled(carrier: str, flags: Any) -> bool:
    """`system_settings.integrations_enabled[carrier]`: false = the carrier's API is not to be used, fallback fees only."""
    if _flag_override is not None:
        return bool(_flag_override.get(carrier, False))
    return bool(flags.get(carrier)) if isinstance(flags, dict) else False


def get_adapter(carrier: str, *, fee_table: Mapping[str, Any] | None = None, strict: bool = True) -> CarrierAdapter | None:
    carrier = str(getattr(carrier, "value", carrier)).upper()
    s = get_settings()
    if s.carrier_mode == "mock":
        return MockCarrier(carrier, fee_table)
    if carrier in _overrides:
        return _overrides[carrier]
    mode = MODE_LABEL[s.carrier_mode]
    if carrier == "GHN" and s.ghn_token and s.ghn_shop_id and s.ghn_from_district_id and s.ghn_from_ward_code:
        from app.integrations.ghn import GhnCarrier
        return GhnCarrier(token=s.ghn_token, shop_id=s.ghn_shop_id, base_url=s.ghn_base_url,
                          from_district_id=s.ghn_from_district_id, from_ward_code=s.ghn_from_ward_code, mode=mode,
                          webhook_secret=s.carrier_webhook_secret)
    if carrier == "GHTK" and s.ghtk_token and s.ghtk_client_source:
        from app.integrations.ghtk import GhtkCarrier
        return GhtkCarrier(token=s.ghtk_token, client_source=s.ghtk_client_source, base_url=s.ghtk_base_url, mode=mode,
                           webhook_secret=s.carrier_webhook_secret)
    if strict:
        raise AppError(503, "CARRIER_NOT_CONFIGURED", f"Hãng vận chuyển {carrier} chưa được cấu hình trên máy chủ.")
    return None
