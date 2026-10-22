"""VNPay (pay + IPN + querydr) adapter. Sandbox or live, depending on the configured URLs and credentials.

Flow: we build a signed payment URL and the customer is sent there; VNPay calls our IPN URL (GET, query string) with the
result, signed with the same secret; the browser is also sent to the return URL, which is display only. The order is only
ever updated from the IPN (or from `query`, the fallback for a late/lost IPN).

Signing (VNPay API 2.1.0): HMAC-SHA512 over the parameters sorted by name, each written `name=urlencoded(value)` and joined
with `&`, empty values left out, `vnp_SecureHash` / `vnp_SecureHashType` excluded. The amount is sent multiplied by 100.

VERIFICATION STATUS: the algorithms below follow VNPay's public integration guide as the author knows it; they have been
checked against the self-consistency tests in tests/test_gateways_real.py but NOT yet against VNPay's sandbox. The first
real run must confirm: the signature accepted by the payment page, the IPN signature check, and the querydr hash.
"""
from __future__ import annotations

import hashlib
import logging
import hmac
import re
import unicodedata
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx

from app.core.errors import AppError
from app.integrations.payment_gateway import GatewayResult, InvalidSignature, MalformedCallback, PaymentLink

log = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")          # VNPay timestamps are GMT+7
VERSION = "2.1.0"
_SECURE_KEYS = ("vnp_SecureHash", "vnp_SecureHashType")
_DATE = "%Y%m%d%H%M%S"


def ascii_text(text: str, limit: int = 100) -> str:
    """vnp_OrderInfo must be plain ASCII without accents or special characters."""
    folded = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    clean = re.sub(r"[^A-Za-z0-9 _.\-]", "", "".join(c for c in folded if not unicodedata.combining(c)))
    return clean.strip()[:limit] or "Thanh toan don hang"


def _encode(value: Any) -> str:
    return urllib.parse.quote_plus(str(value))


def hash_data(params: Mapping[str, Any]) -> str:
    return "&".join(f"{k}={_encode(v)}" for k, v in sorted(params.items())
                    if k not in _SECURE_KEYS and v is not None and str(v) != "")


class VnpayGateway:
    name = "VNPAY"

    def __init__(self, *, tmn_code: str, hash_secret: str, pay_url: str, api_url: str, mode: str,
                 transport: httpx.BaseTransport | None = None):
        self.tmn_code, self._secret, self.pay_url, self.api_url, self.mode = tmn_code, hash_secret, pay_url, api_url, mode
        self._transport = transport

    # ---- signing -----------------------------------------------------------------------------------------------
    def sign(self, params: Mapping[str, Any]) -> str:
        return hmac.new(self._secret.encode(), hash_data(params).encode(), hashlib.sha512).hexdigest()

    def verify(self, params: Mapping[str, Any]) -> bool:
        given = str(params.get("vnp_SecureHash") or "").strip().lower()
        return bool(given) and hmac.compare_digest(self.sign(params), given)

    # ---- pay -----------------------------------------------------------------------------------------------------
    def new_txn_id(self) -> str:
        return "VHRS" + uuid.uuid4().hex[:20].upper()          # letters and digits only, unique per attempt

    def create_payment(self, *, txn_ref: str, amount: int, order_info: str, client_ip: str | None, return_url: str,
                       ipn_url: str | None, expire_minutes: int, now: datetime | None = None) -> PaymentLink:
        if amount <= 0:
            raise AppError(422, "INVALID_AMOUNT", "Số tiền thanh toán phải lớn hơn 0.")
        now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
        expires = now + timedelta(minutes=expire_minutes)
        params = {
            "vnp_Version": VERSION, "vnp_Command": "pay", "vnp_TmnCode": self.tmn_code, "vnp_Amount": str(amount * 100),
            "vnp_CurrCode": "VND", "vnp_TxnRef": txn_ref, "vnp_OrderInfo": ascii_text(order_info), "vnp_OrderType": "other",
            "vnp_Locale": "vn", "vnp_ReturnUrl": return_url, "vnp_IpAddr": client_ip or "127.0.0.1",
            "vnp_CreateDate": now.strftime(_DATE), "vnp_ExpireDate": expires.strftime(_DATE),
        }
        url = f"{self.pay_url}?{hash_data(params)}&vnp_SecureHash={self.sign(params)}"
        return PaymentLink(url=url, expires_at=expires,
                           meta={"vnp_create_date": params["vnp_CreateDate"], "vnp_order_info": params["vnp_OrderInfo"]})

    # ---- IPN -------------------------------------------------------------------------------------------------------
    def parse_ipn(self, params: Mapping[str, str]) -> GatewayResult:
        if not self.verify(params):
            raise InvalidSignature()
        try:
            raw_amount = int(params["vnp_Amount"])
            txn_ref = str(params["vnp_TxnRef"])
        except (KeyError, ValueError) as exc:
            raise MalformedCallback() from exc
        if raw_amount <= 0 or raw_amount % 100:
            raise MalformedCallback()
        ok = params.get("vnp_ResponseCode") == "00" and params.get("vnp_TransactionStatus") == "00"
        return GatewayResult(txn_ref=txn_ref, amount=raw_amount // 100, success=ok, final=True, raw=dict(params))

    @staticmethod
    def ipn_response(code: str, message: str) -> dict[str, str]:
        return {"RspCode": code, "Message": message}

    # ---- querydr: ask VNPay what happened to a transaction (fallback for a late or lost IPN) -------------------------
    def query(self, *, txn_ref: str, meta: Mapping[str, Any], client_ip: str | None) -> GatewayResult | None:
        created = str(meta.get("vnp_create_date") or "")
        if not created:
            return None
        now = datetime.now(VN_TZ)
        info = str(meta.get("vnp_order_info") or "Truy van giao dich")
        body = {"vnp_RequestId": uuid.uuid4().hex[:32], "vnp_Version": VERSION, "vnp_Command": "querydr",
                "vnp_TmnCode": self.tmn_code, "vnp_TxnRef": txn_ref, "vnp_OrderInfo": info,
                "vnp_TransactionDate": created, "vnp_CreateDate": now.strftime(_DATE), "vnp_IpAddr": client_ip or "127.0.0.1"}
        order = ("vnp_RequestId", "vnp_Version", "vnp_Command", "vnp_TmnCode", "vnp_TxnRef", "vnp_TransactionDate",
                 "vnp_CreateDate", "vnp_IpAddr", "vnp_OrderInfo")
        body["vnp_SecureHash"] = hmac.new(self._secret.encode(), "|".join(str(body[k]) for k in order).encode(),
                                          hashlib.sha512).hexdigest()
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.post(self.api_url, json=body)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("VNPay querydr failed for %s: %s: %s", txn_ref, type(exc).__name__, exc)
            raise AppError(502, "GATEWAY_UNAVAILABLE", "Không hỏi được trạng thái giao dịch từ VNPay.") from exc
        # The answer comes straight from VNPay over HTTPS in reply to our own request; its own hash is not re-checked here.
        if r.status_code != 200 or not isinstance(data, dict) or data.get("vnp_ResponseCode") != "00":
            return None                                          # unknown transaction or a query error: nothing to settle
        status = str(data.get("vnp_TransactionStatus", ""))
        try:
            amount = int(data["vnp_Amount"]) // 100
        except (KeyError, ValueError, TypeError):
            return None
        if status == "00":
            return GatewayResult(txn_ref=txn_ref, amount=amount, success=True, raw=data)
        if status == "01":                                       # not completed yet
            return GatewayResult(txn_ref=txn_ref, amount=amount, success=False, final=False, raw=data)
        return GatewayResult(txn_ref=txn_ref, amount=amount, success=False, raw=data)
