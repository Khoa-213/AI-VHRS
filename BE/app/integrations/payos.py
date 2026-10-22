"""payOS adapter: a VietQR bank transfer into the workshop owner's own bank account (Phase 4c-2d).

Flow: we POST a signed payment request and payOS answers with `checkoutUrl` (its hosted page with the QR) and `qrCode` (the
VietQR string, to draw the code ourselves). The amount and the transfer content are fixed inside the QR and tied to our
`orderCode`. When the money lands, payOS POSTs a signed webhook to us. The order is only updated from that webhook, or from
`query` as the fallback for a late or lost one.

Whether the customer's banking app lets them edit the amount or the content is up to that app, so nothing relies on it: the
webhook is accepted only when its signature is valid and the amount equals what the payment asks for (see PaymentService).

Signing (checksum key, HMAC-SHA256 hex):
  * create request: `amount=..&cancelUrl=..&description=..&orderCode=..&returnUrl=..` (fixed key order);
  * webhook: every field of `data`, sorted by key, as `key=value` joined by `&` (None -> empty).

VERIFICATION STATUS: endpoints, headers, field names and both signature recipes were read from payOS's official Python SDK
(`payos` 1.1.0). payOS has no sandbox, so none of it has run against payOS yet (tests/test_payos.py proves self-consistency
only). The first real run must confirm: the create response (`code` "00", `checkoutUrl`, `qrCode`), the webhook signature, the
`description` length limit (the SDK documents none; payOS has historically allowed 25 characters), and that payOS accepts a
returnUrl/cancelUrl that already carries a query string.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.core.errors import AppError
from app.integrations.payment_gateway import GatewayResult, InvalidSignature, MalformedCallback, PaymentLink

log = logging.getLogger(__name__)

MODE = "LIVE"                      # payOS has no test environment: every payment moves real money
DESCRIPTION_MAX = 25
FINAL_FAILED = {"CANCELLED", "EXPIRED", "FAILED"}
IN_PROGRESS = {"PENDING", "PROCESSING", "UNDERPAID"}


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _query_string(data: Mapping[str, Any]) -> str:
    return "&".join(f"{k}={_text(data[k])}" for k in sorted(data))


def _with_query(url: str, **extra: Any) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(query=urlencode([*parse_qsl(parts.query), *extra.items()])))


class PayosGateway:
    name = "PAYOS"
    mode = MODE

    def __init__(self, *, client_id: str, api_key: str, checksum_key: str, base_url: str,
                 transport: httpx.BaseTransport | None = None):
        self.client_id, self._api_key, self._checksum = client_id, api_key, checksum_key
        self.base_url, self._transport = base_url.rstrip("/"), transport

    # ---- signing -------------------------------------------------------------------------------------------------
    def _hmac(self, raw: str) -> str:
        return hmac.new(self._checksum.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def sign_request(self, *, amount: int, cancel_url: str, description: str, order_code: int, return_url: str) -> str:
        return self._hmac(f"amount={amount}&cancelUrl={cancel_url}&description={description}"
                          f"&orderCode={order_code}&returnUrl={return_url}")

    def sign_data(self, data: Mapping[str, Any]) -> str:
        return self._hmac(_query_string(data))

    def new_txn_id(self) -> str:
        """payOS's orderCode: an integer, unique per attempt, within JavaScript's safe range (16 digits at most)."""
        return str(int(time.time()) * 1_000_000 + secrets.randbelow(1_000_000))   # seconds x 10^6: ~1.8e15, one in a million per second to clash

    # ---- HTTP ----------------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        headers = {"x-client-id": self.client_id, "x-api-key": self._api_key}
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.request(method, self.base_url + path, headers=headers, **kw)
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("payOS %s %s failed: %s: %s", method, path, type(exc).__name__, exc)
            raise AppError(502, "GATEWAY_UNAVAILABLE", "Không kết nối được tới payOS, vui lòng thử lại.") from exc
        if not isinstance(body, dict):
            raise AppError(502, "GATEWAY_UNAVAILABLE", "payOS trả về dữ liệu không hợp lệ.")
        return body

    # ---- pay -----------------------------------------------------------------------------------------------------
    def create_payment(self, *, txn_ref: str, amount: int, order_info: str, client_ip: str | None, return_url: str,
                       ipn_url: str | None, expire_minutes: int) -> PaymentLink:
        if amount <= 0:
            raise AppError(422, "INVALID_AMOUNT", "Số tiền thanh toán phải lớn hơn 0.")
        order_code = int(txn_ref)
        description = (order_info.split()[-1] if order_info.split() else "VHRS")[:DESCRIPTION_MAX]   # the order code: short, ascii
        cancel_url = _with_query(return_url, cancelled=1)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
        body = {"orderCode": order_code, "amount": amount, "description": description, "returnUrl": return_url,
                "cancelUrl": cancel_url, "expiredAt": int(expires_at.timestamp()),
                "items": [{"name": description, "quantity": 1, "price": amount}],
                "signature": self.sign_request(amount=amount, cancel_url=cancel_url, description=description,
                                               order_code=order_code, return_url=return_url)}
        out = self._call("POST", "/v2/payment-requests", json=body)
        data = out.get("data") if isinstance(out.get("data"), dict) else None
        if out.get("code") != "00" or not data or not data.get("checkoutUrl"):
            raise AppError(502, "GATEWAY_REJECTED", "payOS từ chối tạo giao dịch.",
                           {"code": out.get("code"), "message": str(out.get("desc", ""))[:200]})
        meta = {"payment_link_id": data.get("paymentLinkId"), "qr_code": data.get("qrCode"), "bin": data.get("bin"),
                "account_number": data.get("accountNumber"), "account_name": data.get("accountName"),
                "description": description}
        return PaymentLink(url=str(data["checkoutUrl"]), expires_at=expires_at, meta=meta)

    # ---- webhook -------------------------------------------------------------------------------------------------
    def verify_webhook(self, body: Mapping[str, Any]) -> bool:
        data, given = body.get("data"), str(body.get("signature") or "").strip().lower()
        return isinstance(data, dict) and bool(given) and hmac.compare_digest(self.sign_data(data), given)

    def parse_webhook(self, body: Mapping[str, Any]) -> GatewayResult:
        if not self.verify_webhook(body):
            raise InvalidSignature()
        data = body["data"]
        try:
            order_code, amount = int(data["orderCode"]), int(data["amount"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedCallback() from exc
        # payOS reports a transfer that arrived: code "00" on both the envelope and the data means it went through.
        paid = str(body.get("code")) == "00" and str(data.get("code")) == "00"
        return GatewayResult(txn_ref=str(order_code), amount=amount, success=paid, final=True, raw=dict(body))

    # ---- query: ask payOS what happened to a link (fallback for a late or lost webhook) --------------------------------
    def query(self, *, txn_ref: str, meta: Mapping[str, Any], client_ip: str | None) -> GatewayResult | None:
        out = self._call("GET", f"/v2/payment-requests/{int(txn_ref)}")
        data = out.get("data") if isinstance(out.get("data"), dict) else None
        if out.get("code") != "00" or not data:
            return None
        status = str(data.get("status", "")).upper()
        try:
            if status == "PAID":
                return GatewayResult(txn_ref=txn_ref, amount=int(data.get("amountPaid") or data.get("amount")), success=True,
                                     raw=data)
            amount = int(data.get("amount") or 0)
        except (ValueError, TypeError):
            return None
        if status in FINAL_FAILED:
            return GatewayResult(txn_ref=txn_ref, amount=amount, success=False, raw=data)
        return GatewayResult(txn_ref=txn_ref, amount=amount, success=False, final=False, raw=data)

    # ---- housekeeping ----------------------------------------------------------------------------------------------
    def cancel(self, txn_ref: str, reason: str = "Khách đổi cổng hoặc hết hạn") -> None:
        """Close an open link at payOS (best effort: a link that cannot be cancelled simply expires)."""
        try:
            self._call("POST", f"/v2/payment-requests/{int(txn_ref)}/cancel", json={"cancellationReason": reason})
        except AppError:
            pass

    def confirm_webhook(self, webhook_url: str) -> dict[str, Any]:
        """Register the address payOS calls with payments (payOS first calls it with a test message)."""
        return self._call("POST", "/confirm-webhook", json={"webhookUrl": webhook_url})
