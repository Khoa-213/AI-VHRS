"""SMS port (Phase 5e, FR-53 OTP).

SMS_MODE=mock (default): nothing leaves the server. The message is kept in `MockSms.outbox` (tests read the code there) and the
log gets the masked number only, never the text, so a code never lands in a log.

SMS_MODE=speedsms: SpeedSMS.vn (`SpeedSms`), personal account, no business licence needed. Default route sms_type 4 = SpeedSMS's
own Brandname (Verify / Notify). No sandbox: every call sends a REAL, paid SMS. Endpoint, auth and codes were checked against
speedsms.vn/sms-api-service and its NodeJS sample on 2026-11-17; covered by tests with a mocked transport; no real call made yet.

SMS_MODE=esms: eSMS.vn (`EsmsSms`), Brandname "CSKH" messages (SmsType 2, the type used for OTP). Needs ESMS_API_KEY,
ESMS_SECRET_KEY and a Brandname registered with the carriers through eSMS. ESMS_SANDBOX=true (the default) makes eSMS accept and
answer the call without delivering or charging; set it false only on the project owner's say. With a Brandname, the TEXT must match
a template eSMS registered for it (`VERIFY_SMS` / `RESET_SMS` in services/phone_otp.py), otherwise eSMS rejects the message.

VERIFICATION: written from eSMS's published REST API (SendMultipleMessage_V4_post_json, CodeResult "100" = accepted); covered by
tests with a mocked transport only. No call to eSMS (sandbox or live) has been made from this server yet.
"""
from __future__ import annotations

import logging
import uuid
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger("app.sms")


class SmsSender(Protocol):
    mode: str

    def send(self, phone: str, text: str) -> None: ...


def mask(phone: str) -> str:
    return phone[:3] + "****" + phone[-3:] if len(phone) > 6 else "****"


class MockSms:
    mode = "MOCK"
    outbox: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> None:
        self.outbox.append((phone, text))
        log.info("SMS mode=MOCK to=%s (not sent)", mask(phone))


# eSMS answers HTTP 200 with a CodeResult; "100" is the only success. The ones below are the configuration problems worth
# telling apart in the log and the error (from eSMS's code table); anything else is reported as a rejection with its code.
ESMS_OK = "100"
_ESMS_CONFIG_CODES = {"101": "sai ApiKey / SecretKey", "102": "tài khoản eSMS bị khoá", "103": "tài khoản eSMS hết tiền",
                      "104": "Brandname không tồn tại hoặc đã bị huỷ"}


class EsmsSms:
    PATH = "/SendMultipleMessage_V4_post_json/"

    def __init__(self, *, api_key: str, secret_key: str, brandname: str, base_url: str, sandbox: bool, sms_type: int = 2,
                 timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self._api_key, self._secret = api_key, secret_key
        self.brandname, self.base, self.sandbox = brandname, base_url.rstrip("/"), sandbox
        self.sms_type, self.timeout, self._transport = sms_type, timeout, transport
        self.mode = "ESMS_SANDBOX" if sandbox else "ESMS"

    def send(self, phone: str, text: str) -> None:
        request_id = uuid.uuid4().hex                 # eSMS drops a repeated RequestId, so a retried call cannot send twice
        payload = {"ApiKey": self._api_key, "SecretKey": self._secret, "Phone": phone, "Content": text,
                   "Brandname": self.brandname, "SmsType": str(self.sms_type), "IsUnicode": "0",
                   "Sandbox": "1" if self.sandbox else "0", "RequestId": request_id}
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout) as http:
                r = http.post(self.base + self.PATH, json=payload)
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("SMS mode=%s to=%s failed: %s", self.mode, mask(phone), type(exc).__name__)
            raise AppError(502, "SMS_UNAVAILABLE", "Không kết nối được tới nhà cung cấp SMS, vui lòng thử lại.") from exc
        code = str(data.get("CodeResult", "")) if isinstance(data, dict) else ""
        if r.status_code >= 500 or code != ESMS_OK:
            detail = data.get("ErrorMessage") if isinstance(data, dict) else None
            log.warning("SMS mode=%s to=%s rejected: http=%s code=%s %s", self.mode, mask(phone), r.status_code, code or "-",
                        detail or "")
            if code in _ESMS_CONFIG_CODES:
                raise AppError(503, "SMS_NOT_CONFIGURED", "Dịch vụ SMS chưa sẵn sàng, vui lòng thử lại sau.",
                               {"provider_code": code})
            raise AppError(502, "SMS_REJECTED", "Nhà cung cấp SMS từ chối gửi tin, vui lòng thử lại sau.",
                           {"provider_code": code or None})
        log.info("SMS mode=%s to=%s sent id=%s request=%s", self.mode, mask(phone), data.get("SMSID"), request_id)


def intl_phone(phone: str) -> str:
    """0901234567 / +84901234567 -> 84901234567 (the form SpeedSMS's samples use)."""
    p = phone.strip().replace(" ", "").lstrip("+")
    return "84" + p[1:] if p.startswith("0") else p


# SpeedSMS error codes (speedsms.vn/sms-api-service, read 2026-11-17) that mean the account or server setup is wrong.
_SPEEDSMS_CONFIG_CODES = {"007": "IP bị khoá", "008": "tài khoản bị khoá", "009": "tài khoản chưa được gọi API",
                          "300": "tài khoản không đủ tiền"}


class SpeedSms:
    """SpeedSMS (speedsms.vn): POST {base}/sms/send, JSON {to, content, sms_type, sender}, HTTP Basic `<access token>:x`
    (as in SpeedSMS's own NodeJS sample; the token is never put in the URL). Success = status "success" and code "00".
    sms_type: 2 random number, 3 own Brandname (sender = it), 4 SpeedSMS's default Brandname (Verify / Notify), 5 their
    Android app (sender = device id). No sandbox: every accepted call is a real, paid SMS."""
    mode = "SPEEDSMS"

    def __init__(self, *, access_token: str, base_url: str, sms_type: int = 4, sender: str = "", timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._token, self.base, self.sms_type, self.sender = access_token, base_url.rstrip("/"), sms_type, sender
        self.timeout, self._transport = timeout, transport

    def send(self, phone: str, text: str) -> None:
        to = intl_phone(phone)
        payload = {"to": [to], "content": text, "sms_type": self.sms_type, "sender": self.sender}
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout) as http:
                r = http.post(self.base + "/sms/send", json=payload, auth=(self._token, "x"))
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("SMS mode=%s to=%s failed: %s", self.mode, mask(phone), type(exc).__name__)
            raise AppError(502, "SMS_UNAVAILABLE", "Không kết nối được tới nhà cung cấp SMS, vui lòng thử lại.") from exc
        data = data if isinstance(data, dict) else {}
        code, body = str(data.get("code", "")), data.get("data") if isinstance(data.get("data"), dict) else {}
        refused = to in (body.get("invalidPhone") or []) or to in (data.get("invalidPhone") or [])
        if r.status_code in (401, 403):
            code = code or "401"
        if data.get("status") != "success" or code != "00" or refused:
            log.warning("SMS mode=%s to=%s rejected: http=%s code=%s %s", self.mode, mask(phone), r.status_code, code or "-",
                        data.get("message") or ("invalid phone" if refused else ""))
            if code in _SPEEDSMS_CONFIG_CODES or code == "401":
                raise AppError(503, "SMS_NOT_CONFIGURED", "Dịch vụ SMS chưa sẵn sàng, vui lòng thử lại sau.",
                               {"provider_code": code})
            if code == "500" or r.status_code >= 500:
                raise AppError(502, "SMS_UNAVAILABLE", "Nhà cung cấp SMS đang lỗi, vui lòng thử lại.", {"provider_code": code})
            raise AppError(502, "SMS_REJECTED", "Nhà cung cấp SMS từ chối gửi tin, vui lòng thử lại sau.",
                           {"provider_code": code or None})
        log.info("SMS mode=%s to=%s sent tran=%s price=%s", self.mode, mask(phone), body.get("tranId"), body.get("totalPrice"))


_mock = MockSms()


def esms_configured() -> bool:
    s = get_settings()
    return bool(s.esms_api_key and s.esms_secret_key and s.esms_brandname)


def speedsms_configured() -> bool:
    s = get_settings()
    return bool(s.speedsms_access_token) and (s.speedsms_sms_type not in (3, 5) or bool(s.speedsms_sender))


def sms_configured() -> bool:
    mode = get_settings().sms_mode
    return mode == "mock" or (mode == "esms" and esms_configured()) or (mode == "speedsms" and speedsms_configured())


def sms_mode_label() -> str:
    s = get_settings()
    return "ESMS_SANDBOX" if s.sms_mode == "esms" and s.esms_sandbox else s.sms_mode.upper()


def get_sms_sender() -> SmsSender:
    s = get_settings()
    if s.sms_mode == "mock":
        return _mock
    if not sms_configured():
        raise AppError(503, "SMS_NOT_CONFIGURED", "Dịch vụ SMS chưa được cấu hình trên máy chủ.")
    if s.sms_mode == "speedsms":
        return SpeedSms(access_token=s.speedsms_access_token, base_url=s.speedsms_base_url, sms_type=s.speedsms_sms_type,
                        sender=s.speedsms_sender or "", timeout=s.sms_timeout_seconds)
    return EsmsSms(api_key=s.esms_api_key, secret_key=s.esms_secret_key, brandname=s.esms_brandname,
                   base_url=s.esms_base_url, sandbox=s.esms_sandbox, sms_type=s.esms_sms_type,
                   timeout=s.sms_timeout_seconds)
