"""GHN (Giao Hàng Nhanh) adapter: fee and delivery estimate, create / cancel a waybill, label link, status callbacks.

Auth: headers `Token` and `ShopId`. Hosts: staging `https://dev-online-gateway.ghn.vn/shiip/public-api`, production
`https://online-gateway.ghn.vn/shiip/public-api`.

Addresses use GHN's two-level model (province -> ward, `is_new_to_address: true`) and are sent by NAME, exactly as the catalogue
(`integrations/locations.py`) spells them. The fee and the delivery estimate come from ONE call, `shipping-order/preview` (a dry-run
of Create Order), so the quote is priced on the very request that later creates the waybill. The parcels here are always far below
20 kg, so the service is "hàng nhẹ" (`service_type_id` 2); 5 is used only if a parcel ever reaches 20 kg.

The workshop pays GHN (`payment_type_id` 1 = shop pays); the customer already paid us the fee. No cash on delivery.

Callbacks: GHN does not sign them. The callback address carries a shared secret (`?key=...`, CARRIER_WEBHOOK_SECRET) or the same
secret travels in a custom header (`X-Webhook-Secret`) configured in the Developer Portal (Webhook configuration). GHN retries
5xx/408/429 and gives up on any other 4xx; it may repeat a callback, and the waybill state machine ignores repeats and older states.

VERIFICATION: preview, create (with `client_order_code` idempotency), cancel and the A5 label token were run against GHN's staging
API on 2026-10-26 with this shop (see PROJECT_STATUS.md). The callback and the status vocabulary follow GHN's published pages; no
real GHN callback has reached this server yet.
"""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain.carrier_rules import Parcel, ServiceQuote, TrackingEvent, Waybill
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback

SECRET_HEADER = "x-webhook-secret"
HEAVY_FROM_GRAMS = 20_000
SERVICE_NAME = {2: "Giao hàng nhẹ (dưới 20 kg)", 5: "Giao hàng nặng (từ 20 kg)"}
_ADDRESS_PROBLEMS = ("ward not found", "province not found", "phone")             # GHN says what is wrong in `message`


def _iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def service_type_for(parcel: Parcel) -> int:
    return 5 if parcel.weight_g >= HEAVY_FROM_GRAMS else 2


class GhnCarrier:
    name = "GHN"

    def __init__(self, *, token: str, shop_id: str | int, base_url: str, mode: str, webhook_secret: str | None,
                 transport: httpx.BaseTransport | None = None):
        self._token, self.shop_id, self.base = token, int(shop_id), base_url.rstrip("/")
        self.mode, self._secret, self._transport = mode, webhook_secret, transport

    # ---- HTTP ---------------------------------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"Token": self._token, "ShopId": str(self.shop_id), "Content-Type": "application/json"}

    def _call(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.post(self.base + path, headers=self._headers(), json=payload)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(502, "CARRIER_UNAVAILABLE", "Không kết nối được tới GHN.") from exc
        if r.status_code in (401, 403):
            raise AppError(503, "CARRIER_NOT_CONFIGURED", "GHN không chấp nhận thông tin xác thực của cửa hàng.")
        if r.status_code >= 500:
            raise AppError(502, "CARRIER_UNAVAILABLE", "GHN đang lỗi, vui lòng thử lại.")
        if not isinstance(data, dict) or data.get("code") != 200:
            self._reject(data if isinstance(data, dict) else {})
        return data.get("data")

    @staticmethod
    def _reject(data: Mapping[str, Any]) -> None:
        message = str(data.get("message") or "")[:300]
        if data.get("code_message") == "PHONE_INVALID" or any(p in message.lower() for p in _ADDRESS_PROBLEMS):
            raise AppError(422, "INVALID_ADDRESS", "GHN không nhận địa chỉ hoặc số điện thoại người nhận này.", {"message": message})
        raise AppError(502, "CARRIER_REJECTED", "GHN từ chối yêu cầu.", {"message": message})

    # ---- the request GHN prices and ships from -----------------------------------------------------------------------------
    @staticmethod
    def _names(to: Mapping[str, Any]) -> tuple[str, str]:
        province, ward = str(to.get("province_name") or "").strip(), str(to.get("ward_name") or "").strip()
        if not province or not ward:
            raise AppError(422, "INVALID_ADDRESS", "Địa chỉ cần tên tỉnh/thành và phường/xã (chọn lại địa chỉ theo danh mục).")
        return province, ward

    def _body(self, *, parcel: Parcel, to: Mapping[str, Any], service_type: int, note: str | None = None) -> dict[str, Any]:
        province, ward = self._names(to)
        street = str(to.get("street") or "").strip()
        item = {"name": "Sản phẩm chữ viết tay", "quantity": 1, "weight": parcel.weight_g, "length": parcel.length_cm,
                "width": parcel.width_cm, "height": parcel.height_cm}
        return {
            "payment_type_id": 1, "required_note": "KHONGCHOXEMHANG", "note": (note or "")[:500],
            "to_name": str(to.get("receiver") or ""), "to_phone": str(to.get("phone") or ""),
            "to_address": ", ".join(p for p in (street, ward, province) if p), "to_ward_name": ward, "to_province_name": province,
            "is_new_to_address": True, "cod_amount": 0, "insurance_value": parcel.value, "order_value": parcel.value,
            "service_type_id": service_type, "content": "Sản phẩm chữ viết tay", "weight": parcel.weight_g,
            "length": parcel.length_cm, "width": parcel.width_cm, "height": parcel.height_cm, "items": [item]}

    # ---- fee and estimate ----------------------------------------------------------------------------------------------
    def quote(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str) -> list[ServiceQuote]:
        service_type = service_type_for(parcel)
        data = self._call("/v2/shipping-order/preview", self._body(parcel=parcel, to=to, service_type=service_type)) or {}
        total = data.get("total_fee")
        if total is None:
            raise AppError(502, "CARRIER_REJECTED", "GHN không trả phí vận chuyển.")
        return [ServiceQuote(carrier="GHN", service_code=str(service_type), service_name=SERVICE_NAME[service_type],
                             fee=cr.round_up_100(int(total)), eta=_iso(data.get("expected_delivery_time")), mode=self.mode)]

    # ---- waybill -------------------------------------------------------------------------------------------------------
    def create(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str, service_code: str, note: str | None,
               reference: str | None = None) -> Waybill:
        try:
            service_type = int(service_code)
        except ValueError as exc:
            raise AppError(422, "SERVICE_NOT_AVAILABLE", "Mã dịch vụ GHN không hợp lệ.") from exc
        if service_type not in SERVICE_NAME:
            raise AppError(422, "SERVICE_NOT_AVAILABLE", "Mã dịch vụ GHN không hợp lệ.")
        body = self._body(parcel=parcel, to=to, service_type=service_type, note=note)
        # GHN answers a repeated client_order_code with the waybill it already made, so a retry never ships twice.
        body["client_order_code"] = (reference or order_code)[:50]
        data = self._call("/v2/shipping-order/create", body) or {}
        code = data.get("order_code")
        if not code:
            raise AppError(502, "CARRIER_REJECTED", "GHN không trả mã vận đơn.")
        fee = data.get("total_fee")
        return Waybill(code=str(code), fee=int(fee) if fee is not None else None, eta=_iso(data.get("expected_delivery_time")),
                       raw=data)

    def cancel(self, waybill_code: str, reason: str | None = None) -> None:
        data = self._call("/v2/switch-status/cancel", {"order_codes": [waybill_code], "reason_code": "GHN-CANCEL-OTHER",
                                                       "reason": (reason or "")[:200]})
        entry = next((r for r in data or [] if isinstance(r, dict) and r.get("order_code") == waybill_code), None)
        if entry is None or entry.get("result") is not True:
            raise AppError(409, "CARRIER_CANCEL_REFUSED", "GHN không cho huỷ vận đơn này (có thể hãng đã lấy hàng).",
                           {"message": str((entry or {}).get("message", ""))[:200]})

    def label(self, *, waybill_code: str, context: Mapping[str, Any]) -> bytes | None:
        return None                                   # GHN's A5 label is a web page, opened through label_link

    def label_link(self, waybill_code: str) -> str | None:
        """A fresh address of GHN's printable A5 label (the token GHN issues is short-lived, so it is asked for each time)."""
        token = (self._call("/v2/a5/gen-token", {"order_codes": [waybill_code]}) or {}).get("token")
        if not token:
            return None
        return f"{self.base.split('/shiip/')[0]}/a5/public-api/printA5?token={token}"

    # ---- callbacks -----------------------------------------------------------------------------------------------------------
    def _authentic(self, query: Mapping[str, str], headers: Mapping[str, str]) -> bool:
        if not self._secret:
            return False
        given = str(query.get("key") or {k.lower(): v for k, v in headers.items()}.get(SECRET_HEADER) or "")
        return hmac.compare_digest(given, self._secret)

    def parse_webhook(self, *, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> TrackingEvent:
        if not self._authentic(query, headers):
            raise InvalidSignature()
        try:
            data = json.loads(body)
            code = str(data["OrderCode"])
        except (ValueError, KeyError, TypeError) as exc:
            raise MalformedCallback() from exc
        kind = str(data.get("Type", "switch_status"))
        raw = str(data.get("Status", ""))
        status = cr.map_ghn_status(raw) if kind == "switch_status" else None        # other types: create, weight, COD, fee...
        return TrackingEvent(waybill_code=code, raw_status=raw, status=status, occurred_at=_iso(data.get("Time")),
                             reason=data.get("Reason") or None, raw=data)
