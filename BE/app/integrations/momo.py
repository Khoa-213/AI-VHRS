"""MoMo (captureWallet one-time payment + IPN + query) adapter. Test or production, depending on the configured endpoint/keys.

Flow: we POST a signed create request and MoMo answers with a `payUrl`; the customer is sent there (wallet app or QR);
MoMo POSTs the result to our `ipnUrl` (JSON, signed) and redirects the browser to `redirectUrl` (display only). The order is
only updated from the IPN, or from `query` as the fallback for a late/lost IPN.

Signing: HMAC-SHA256 with the secret key over `key=value` pairs joined by `&`. The create request uses the fixed key order
accessKey, amount, extraData, ipnUrl, orderId, orderInfo, partnerCode, redirectUrl, requestId, requestType (MoMo's docs).
The IPN is checked over accessKey, amount, extraData, message, orderId, orderInfo, orderType, partnerCode, payType, requestId,
responseTime, resultCode, transId (alphabetical).

VERIFICATION STATUS: the create-request signature and key order are taken from MoMo's public documentation; the IPN field
list, the query endpoint and the pending result codes follow the same documentation as the author knows it. None of it has
been run against MoMo's test environment yet (tests/test_gateways_real.py proves self-consistency only). The first real run
must confirm: the create response (`resultCode` 0 and `payUrl`), the IPN signature check, and the answer to the IPN
(MoMo documents HTTP 204 within 15 s; one page of its docs says 200: this code answers 204).
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import httpx

from app.core.errors import AppError
from app.integrations.payment_gateway import GatewayResult, InvalidSignature, MalformedCallback, PaymentLink

CREATE_PATH = "/v2/gateway/api/create"
QUERY_PATH = "/v2/gateway/api/query"
REQUEST_TYPE = "captureWallet"
PENDING_CODES = {1000, 7000, 7002, 9000}          # initiated / being processed / waiting for the user / authorized
NOT_FOUND_CODE = 42
IPN_FIELDS = ("accessKey", "amount", "extraData", "message", "orderId", "orderInfo", "orderType", "partnerCode",
              "payType", "requestId", "responseTime", "resultCode", "transId")


def _raw(pairs: list[tuple[str, Any]]) -> str:
    return "&".join(f"{k}={'' if v is None else v}" for k, v in pairs)


class MomoGateway:
    name = "MOMO"

    def __init__(self, *, partner_code: str, access_key: str, secret_key: str, endpoint: str, mode: str,
                 transport: httpx.BaseTransport | None = None):
        self.partner_code, self.access_key, self._secret = partner_code, access_key, secret_key
        self.endpoint, self.mode, self._transport = endpoint.rstrip("/"), mode, transport

    # ---- signing -------------------------------------------------------------------------------------------------
    def sign(self, raw: str) -> str:
        return hmac.new(self._secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def new_txn_id(self) -> str:
        return "VHRS" + uuid.uuid4().hex[:20].upper()          # MoMo's orderId: unique per attempt

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.post(self.endpoint + path, json=body)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(502, "GATEWAY_UNAVAILABLE", "Không kết nối được tới MoMo, vui lòng thử lại.") from exc
        if not isinstance(data, dict):
            raise AppError(502, "GATEWAY_UNAVAILABLE", "MoMo trả về dữ liệu không hợp lệ.")
        return data

    # ---- pay -----------------------------------------------------------------------------------------------------
    def create_payment(self, *, txn_ref: str, amount: int, order_info: str, client_ip: str | None, return_url: str,
                       ipn_url: str | None, expire_minutes: int) -> PaymentLink:
        if amount <= 0:
            raise AppError(422, "INVALID_AMOUNT", "Số tiền thanh toán phải lớn hơn 0.")
        if not ipn_url:
            raise AppError(503, "GATEWAY_NOT_CONFIGURED", "Chưa cấu hình PUBLIC_BASE_URL để MoMo gọi lại kết quả (IPN).")
        request_id, extra = uuid.uuid4().hex, ""
        raw = _raw([("accessKey", self.access_key), ("amount", amount), ("extraData", extra), ("ipnUrl", ipn_url),
                    ("orderId", txn_ref), ("orderInfo", order_info), ("partnerCode", self.partner_code),
                    ("redirectUrl", return_url), ("requestId", request_id), ("requestType", REQUEST_TYPE)])
        data = self._post(CREATE_PATH, {
            "partnerCode": self.partner_code, "partnerName": "Xuong Net Viet", "storeId": "VHRS", "requestId": request_id,
            "amount": amount, "orderId": txn_ref, "orderInfo": order_info, "redirectUrl": return_url, "ipnUrl": ipn_url,
            "lang": "vi", "requestType": REQUEST_TYPE, "autoCapture": True, "extraData": extra,
            "signature": self.sign(raw)})
        if data.get("resultCode") != 0 or not data.get("payUrl"):
            raise AppError(502, "GATEWAY_REJECTED", "MoMo từ chối tạo giao dịch.",
                           {"resultCode": data.get("resultCode"), "message": str(data.get("message", ""))[:200]})
        return PaymentLink(url=str(data["payUrl"]), expires_at=datetime.now(timezone.utc) + timedelta(minutes=expire_minutes))

    # ---- IPN -------------------------------------------------------------------------------------------------------
    def verify_ipn(self, body: Mapping[str, Any]) -> bool:
        given = str(body.get("signature") or "").strip().lower()
        raw = _raw([(k, self.access_key if k == "accessKey" else body.get(k, "")) for k in IPN_FIELDS])
        return bool(given) and hmac.compare_digest(self.sign(raw), given)

    def parse_ipn(self, body: Mapping[str, Any]) -> GatewayResult:
        if not self.verify_ipn(body):
            raise InvalidSignature()
        if str(body.get("partnerCode")) != self.partner_code:
            raise InvalidSignature()
        try:
            code, amount, txn_ref = int(body["resultCode"]), int(body["amount"]), str(body["orderId"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedCallback() from exc
        return GatewayResult(txn_ref=txn_ref, amount=amount, success=code == 0, final=code not in PENDING_CODES,
                             raw=dict(body))

    # ---- query: ask MoMo what happened to a transaction (fallback for a late or lost IPN) --------------------------------
    def query(self, *, txn_ref: str, meta: Mapping[str, Any], client_ip: str | None) -> GatewayResult | None:
        request_id = uuid.uuid4().hex
        raw = _raw([("accessKey", self.access_key), ("orderId", txn_ref), ("partnerCode", self.partner_code),
                    ("requestId", request_id)])
        data = self._post(QUERY_PATH, {"partnerCode": self.partner_code, "requestId": request_id, "orderId": txn_ref,
                                       "lang": "vi", "signature": self.sign(raw)})
        try:
            code = int(data["resultCode"])
        except (KeyError, ValueError, TypeError):
            return None
        if code == NOT_FOUND_CODE:
            return None
        try:
            amount = int(data.get("amount", 0))
        except (ValueError, TypeError):
            return None
        return GatewayResult(txn_ref=txn_ref, amount=amount, success=code == 0, final=code not in PENDING_CODES, raw=data)
