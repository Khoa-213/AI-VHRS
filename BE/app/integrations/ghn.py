"""GHN (Giao Hàng Nhanh) adapter: services, fee, lead time, create / cancel an order, label, status callbacks.

Auth: headers `Token` and `ShopId`. Hosts: staging `https://dev-online-gateway.ghn.vn/shiip/public-api`, production
`https://online-gateway.ghn.vn/shiip/public-api`. Addresses use GHN's own location ids: our order address keeps them in
`district_code` (district id) and `ward_code` (ward code).

The workshop pays GHN (`payment_type_id` 1 = shop pays); the customer already paid us the fee. No cash on delivery.

GHN does not sign its callbacks by default: the callback address carries a shared secret (`?key=...`, CARRIER_WEBHOOK_SECRET)
and the callback is registered with GHN support per client (they ask for the address, the environment and the auth you want).
GHN may repeat a callback; the waybill state machine ignores repeats and older states.

VERIFICATION STATUS: services, fee, lead time and the status vocabulary follow GHN's published documentation as found by the
author (developer.ghn.vn); the create, cancel, label and callback field names are from the author's knowledge of the same API
and the site could not be read while this was written. tests/test_carriers_real.py proves the request shapes and mappings are
self-consistent, NOT that GHN accepts them. The first sandbox run must confirm every endpoint path and field below.
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


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class GhnCarrier:
    name = "GHN"

    def __init__(self, *, token: str, shop_id: str | int, base_url: str, from_district_id: int, from_ward_code: str,
                 mode: str, webhook_secret: str | None, transport: httpx.BaseTransport | None = None):
        self._token, self.shop_id, self.base = token, int(shop_id), base_url.rstrip("/")
        self.from_district, self.from_ward, self.mode = int(from_district_id), str(from_ward_code), mode
        self._secret, self._transport = webhook_secret, transport

    # ---- HTTP ---------------------------------------------------------------------------------------------------
    def _call(self, path: str, payload: dict[str, Any], *, absolute: str | None = None, method: str = "POST") -> Any:
        headers = {"Token": self._token, "ShopId": str(self.shop_id), "Content-Type": "application/json"}
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.request(method, absolute or self.base + path, headers=headers,
                                 json=payload if method == "POST" else None, params=None if method == "POST" else payload)
            if absolute and r.status_code == 200 and "json" not in r.headers.get("content-type", ""):
                return r.content                                           # a file (the label)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(502, "CARRIER_UNAVAILABLE", "Không kết nối được tới GHN.") from exc
        if r.status_code >= 500:
            raise AppError(502, "CARRIER_UNAVAILABLE", "GHN đang lỗi, vui lòng thử lại.")
        if not isinstance(data, dict) or data.get("code") != 200:
            raise AppError(502, "CARRIER_REJECTED", "GHN từ chối yêu cầu.",
                           {"message": str((data or {}).get("message", ""))[:200] if isinstance(data, dict) else ""})
        return data.get("data")

    @staticmethod
    def _to(to: Mapping[str, Any]) -> tuple[int, str]:
        try:
            return int(to["district_code"]), str(to["ward_code"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AppError(422, "INVALID_ADDRESS", "Địa chỉ cần mã quận/huyện và phường/xã của GHN.") from exc

    # ---- services, fee, lead time ----------------------------------------------------------------------------------
    def quote(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str) -> list[ServiceQuote]:
        district, ward = self._to(to)
        services = self._call("/v2/shipping-order/available-services",
                              {"shop_id": self.shop_id, "from_district": self.from_district, "to_district": district}) or []
        out: list[ServiceQuote] = []
        for svc in services:
            sid = svc.get("service_id")
            if sid is None:
                continue
            common = {"from_district_id": self.from_district, "from_ward_code": self.from_ward, "to_district_id": district,
                      "to_ward_code": ward, "service_id": int(sid)}
            try:
                fee = self._call("/v2/shipping-order/fee", {**common, "weight": parcel.weight_g, "length": parcel.length_cm,
                                                            "width": parcel.width_cm, "height": parcel.height_cm,
                                                            "insurance_value": parcel.value})
            except AppError as exc:
                if exc.code == "CARRIER_REJECTED":
                    continue                                              # this service cannot carry the parcel: leave it out
                raise
            try:
                eta = _ts((self._call("/v2/shipping-order/leadtime", common) or {}).get("leadtime"))
            except AppError:
                eta = None                                                # the estimate is a convenience
            out.append(ServiceQuote(carrier="GHN", service_code=str(sid),
                                    service_name=str(svc.get("short_name") or f"GHN {sid}"),
                                    fee=cr.round_up_100(int((fee or {}).get("total", 0))), eta=eta, mode=self.mode))
        return out

    # ---- waybill -------------------------------------------------------------------------------------------------------
    def create(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str, service_code: str, note: str | None) -> Waybill:
        district, ward = self._to(to)
        try:
            service_id = int(service_code)
        except ValueError as exc:
            raise AppError(422, "SERVICE_NOT_AVAILABLE", "Mã dịch vụ GHN không hợp lệ.") from exc
        data = self._call("/v2/shipping-order/create", {
            "payment_type_id": 1, "required_note": "KHONGCHOXEMHANG", "note": note or "", "client_order_code": order_code,
            "to_name": to.get("receiver"), "to_phone": to.get("phone"), "to_address": to.get("street"),
            "to_ward_code": ward, "to_district_id": district, "cod_amount": 0, "content": f"Chữ viết tay - đơn {order_code}",
            "weight": parcel.weight_g, "length": parcel.length_cm, "width": parcel.width_cm, "height": parcel.height_cm,
            "insurance_value": parcel.value, "service_id": service_id,
            "items": [{"name": "Sản phẩm viết tay", "quantity": 1, "weight": parcel.weight_g}]}) or {}
        code = data.get("order_code")
        if not code:
            raise AppError(502, "CARRIER_REJECTED", "GHN không trả mã vận đơn.")
        fee = data.get("total_fee")
        return Waybill(code=str(code), fee=int(fee) if fee is not None else None, eta=_iso(data.get("expected_delivery_time")),
                       raw=data)

    def cancel(self, waybill_code: str) -> None:
        self._call("/v2/switch-status/cancel", {"order_codes": [waybill_code]})

    def label(self, *, waybill_code: str, context: Mapping[str, Any]) -> bytes | None:
        token = (self._call("/v2/a5/gen-token", {"order_codes": [waybill_code]}) or {}).get("token")
        if not token:
            return None
        host = self.base.split("/shiip/")[0]
        content = self._call("", {"token": token}, absolute=f"{host}/a5/public-api/printA5", method="GET")
        return content if isinstance(content, (bytes, bytearray)) else None

    # ---- callbacks -----------------------------------------------------------------------------------------------------------
    def parse_webhook(self, *, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> TrackingEvent:
        if not self._secret or not hmac.compare_digest(str(query.get("key", "")), self._secret):
            raise InvalidSignature()
        try:
            data = json.loads(body)
            code = str(data["OrderCode"])
        except (ValueError, KeyError, TypeError) as exc:
            raise MalformedCallback() from exc
        if not isinstance(data, dict):
            raise MalformedCallback()
        kind = str(data.get("Type", "switch_status"))
        raw = str(data.get("Status", ""))
        status = cr.map_ghn_status(raw) if kind == "switch_status" else None        # other types: weight, COD, fee changes
        return TrackingEvent(waybill_code=code, raw_status=raw, status=status, occurred_at=_iso(data.get("Time")),
                             reason=data.get("Reason") or None, raw=data)
