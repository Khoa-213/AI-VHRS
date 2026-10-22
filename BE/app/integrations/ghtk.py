"""GHTK (Giao Hàng Tiết Kiệm) adapter: fee, create / cancel an order, label, status callbacks.

Auth: headers `Token` (created at /web/thong-tin-shop/cau-hinh-api of the customer site) and `X-Client-Source` (the shop /
partner code). Hosts: staging `https://services-staging.ghtklab.com`, production `https://services.giaohangtietkiem.vn`.
GHTK addresses are NAMES (province, district), not codes: the order address must carry `province_name`, `district_name`
(and `ward_name`) when a GHTK service is chosen.

GHTK's callback carries no signature: the callback address holds a shared secret (`?hash=...`, CARRIER_WEBHOOK_SECRET) and GHTK
treats only HTTP 200 as delivered (it repeats once otherwise). Registering the callback address is done with GHTK.

VERIFICATION STATUS: the auth headers, hosts, the order-create body (`products` + `order`), the callback fields (`label_id`,
`partner_id`, `status_id`, `action_time`, `reason`) and the status ids follow GHTK's published documentation (api.ghtk.vn). The
fee, cancel and label endpoints and the response field names are from the author's knowledge of the same API and were not
confirmed. tests/test_carriers_real.py proves self-consistency only. The first sandbox run must confirm every path below.
"""
from __future__ import annotations

import hmac
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain.carrier_rules import Parcel, ServiceQuote, TrackingEvent, Waybill
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback

TRANSPORTS = {"ROAD": ("road", "Đường bộ"), "FLY": ("fly", "Đường bay")}


def _iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class GhtkCarrier:
    name = "GHTK"

    def __init__(self, *, token: str, client_source: str, base_url: str, mode: str, webhook_secret: str | None,
                 transport: httpx.BaseTransport | None = None):
        self._token, self._source, self.base, self.mode = token, client_source, base_url.rstrip("/"), mode
        self._secret, self._transport = webhook_secret, transport

    # ---- HTTP ---------------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None,
              raw: bool = False) -> Any:
        headers = {"Token": self._token, "X-Client-Source": self._source}
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.request(method, self.base + path, headers=headers, params=params, json=body)
            if raw and r.status_code == 200:
                return r.content
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(502, "CARRIER_UNAVAILABLE", "Không kết nối được tới GHTK.") from exc
        if r.status_code >= 500:
            raise AppError(502, "CARRIER_UNAVAILABLE", "GHTK đang lỗi, vui lòng thử lại.")
        if not isinstance(data, dict) or not data.get("success"):
            raise AppError(502, "CARRIER_REJECTED", "GHTK từ chối yêu cầu.",
                           {"message": str(data.get("message", ""))[:200] if isinstance(data, dict) else ""})
        return data

    @staticmethod
    def _names(to: Mapping[str, Any]) -> tuple[str, str]:
        province, district = str(to.get("province_name") or "").strip(), str(to.get("district_name") or "").strip()
        if not province or not district:
            raise AppError(422, "ADDRESS_NAMES_REQUIRED", "GHTK cần tên tỉnh/thành và quận/huyện trong địa chỉ giao hàng.")
        return province, district

    def _pickup(self) -> dict[str, Any]:
        s = get_settings()
        if not (s.workshop_province and s.workshop_district and s.workshop_address and s.workshop_phone):
            raise AppError(503, "CARRIER_NOT_CONFIGURED", "Chưa cấu hình địa chỉ lấy hàng của xưởng (WORKSHOP_*).")
        return {"pick_name": s.workshop_name, "pick_address": s.workshop_address, "pick_province": s.workshop_province,
                "pick_district": s.workshop_district, "pick_ward": s.workshop_ward or "", "pick_tel": s.workshop_phone}

    # ---- fee ------------------------------------------------------------------------------------------------------------
    def quote(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str) -> list[ServiceQuote]:
        province, district = self._names(to)
        pick = self._pickup()
        out: list[ServiceQuote] = []
        for code, (transport, name) in TRANSPORTS.items():
            try:
                data = self._call("GET", "/services/shipment/fee", params={
                    "pick_province": pick["pick_province"], "pick_district": pick["pick_district"], "province": province,
                    "district": district, "address": str(to.get("street") or ""), "weight": parcel.weight_g,
                    "value": parcel.value, "transport": transport})
            except AppError as exc:
                if exc.code == "CARRIER_REJECTED":
                    continue                                              # this transport is not offered for this route
                raise
            fee = (data.get("fee") or {})
            if fee.get("delivery") is False:
                continue
            out.append(ServiceQuote(carrier="GHTK", service_code=code, service_name=name,
                                    fee=cr.round_up_100(int(fee.get("fee", 0))), eta=None, mode=self.mode))
        return out

    # ---- waybill -------------------------------------------------------------------------------------------------------
    def create(self, *, parcel: Parcel, to: Mapping[str, Any], order_code: str, service_code: str, note: str | None) -> Waybill:
        province, district = self._names(to)
        if service_code not in TRANSPORTS:
            raise AppError(422, "SERVICE_NOT_AVAILABLE", "Dịch vụ GHTK không tồn tại.")
        data = self._call("POST", "/services/shipment/order", body={
            "products": [{"name": "Sản phẩm viết tay", "weight": round(parcel.weight_g / 1000, 3), "quantity": 1}],
            "order": {"id": order_code, **self._pickup(), "name": to.get("receiver"), "tel": to.get("phone"),
                      "address": to.get("street"), "province": province, "district": district,
                      "ward": to.get("ward_name") or "", "is_freeship": 1, "pick_money": 0, "value": parcel.value,
                      "transport": TRANSPORTS[service_code][0], "note": note or ""}})
        order = data.get("order") or {}
        code = order.get("label")
        if not code:
            raise AppError(502, "CARRIER_REJECTED", "GHTK không trả mã vận đơn.")
        fee = order.get("fee")
        return Waybill(code=str(code), fee=int(fee) if fee is not None else None,
                       eta=_iso(order.get("estimated_deliver_time")), raw=order)

    def cancel(self, waybill_code: str) -> None:
        self._call("POST", f"/services/shipment/cancel/{urllib.parse.quote(waybill_code, safe='')}")

    def label(self, *, waybill_code: str, context: Mapping[str, Any]) -> bytes | None:
        content = self._call("GET", f"/services/label/{urllib.parse.quote(waybill_code, safe='')}", raw=True)
        return content if isinstance(content, (bytes, bytearray)) else None

    # ---- callbacks -----------------------------------------------------------------------------------------------------------
    def parse_webhook(self, *, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> TrackingEvent:
        if not self._secret or not hmac.compare_digest(str(query.get("hash", "")), self._secret):
            raise InvalidSignature()
        try:
            if body.lstrip().startswith(b"{"):
                data = json.loads(body)
            else:
                data = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode("utf-8")).items()}
            code, status_id = str(data["label_id"]), data["status_id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MalformedCallback() from exc
        if not isinstance(data, dict):
            raise MalformedCallback()
        return TrackingEvent(waybill_code=code, raw_status=str(status_id), status=cr.map_ghtk_status(status_id),
                             occurred_at=_iso(data.get("action_time")), reason=data.get("reason") or None, raw=data)
