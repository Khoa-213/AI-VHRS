"""Phase 5e, FR-53 / UC-54: verify the profile's phone number by SMS OTP, then recover the account with it.

SMS_MODE=mock: nothing is sent; `MockSms.outbox` holds (number, text) and the tests read the code from the text. Time-based
rules (60 s between codes, 5 minutes of life) are exercised by moving `created_at` / `expires_at` back in the database
instead of sleeping.
"""
import random
import re

import pytest
from sqlalchemy import text

from app.db.session import get_engine
from app.integrations.sms import MockSms
from app.services.phone_otp import normalize_phone, phone_variants
from tests.conftest import PASSWORD, login, make_account

API = "/api/v1"


@pytest.fixture
def sms():
    MockSms.outbox.clear()
    return MockSms.outbox


def _sql(q: str, **kw):
    with get_engine().begin() as c:
        return c.execute(text(q), kw).scalar()


def _phone() -> str:
    return "09" + "".join(random.choices("0123456789", k=8))


def _customer(client, phone: str | None) -> tuple[str, dict]:
    email = make_account("CUSTOMER")
    h = {"Authorization": f"Bearer {login(client, email, PASSWORD)['access_token']}"}
    if phone:
        assert client.patch(f"{API}/me", headers=h, json={"phone": phone}).status_code == 200
    return email, h


def _code(sms) -> str:
    return re.search(r"\b(\d{6})\b", sms[-1][1]).group(1)


def _err(r) -> str:
    return r.json()["error"]["code"]


def _age_codes(phone: str, seconds: int = 120) -> None:
    """Pretend the codes of this number were sent `seconds` ago (past the resend wait)."""
    _sql("update phone_otps set created_at = created_at - make_interval(secs => :s), "
         "expires_at = expires_at - make_interval(secs => :s) where phone = :p returning 1", s=seconds, p=phone)


def _verified(client, sms, phone: str) -> tuple[str, dict]:
    email, h = _customer(client, phone)
    assert client.post(f"{API}/me/phone/otp", headers=h).status_code == 202
    assert client.post(f"{API}/me/phone/verify", headers=h, json={"code": _code(sms)}).status_code == 200
    return email, h


def test_phone_numbers_are_compared_in_one_form():
    assert normalize_phone("+84901234567") == "0901234567" == normalize_phone(" 0901234567 ")
    assert phone_variants("+84901234567") == ("0901234567", "+84901234567")


def test_a_customer_verifies_the_profile_phone_by_sms(client, sms):
    phone = _phone()
    _, h = _customer(client, "+84" + phone[1:])                 # entered in +84 form, verified and stored as 0xxxxxxxxx
    r = client.post(f"{API}/me/phone/otp", headers=h)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["mode"] == "MOCK" and body["expires_in"] == 300 and body["resend_after"] == 60
    assert body["phone_masked"] == phone[:3] + "****" + phone[-3:]
    assert sms[-1][0] == phone and "ma xac minh" in sms[-1][1]
    stored = _sql("select otp_hash from phone_otps where phone=:p", p=phone)
    assert _code(sms) not in stored and len(stored) == 64          # only the HMAC is kept

    wrong = "000000" if _code(sms) != "000000" else "111111"
    r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": wrong})
    assert r.status_code == 400 and _err(r) == "OTP_INVALID" and r.json()["error"]["details"]["attempts_left"] == 4
    assert client.post(f"{API}/me/phone/verify", headers=h, json={"code": "12ab56"}).status_code == 422

    r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": _code(sms)})
    assert r.status_code == 200, r.text
    assert r.json()["phone_verified"] is True and r.json()["phone"] == phone
    assert _sql("select count(*) from audit_logs where action='PHONE_VERIFY' and entity_id = "
                "(select id from accounts where phone=:p)", p=phone) == 1
    assert _err(client.post(f"{API}/me/phone/otp", headers=h)) == "PHONE_ALREADY_VERIFIED"
    # a code works once
    r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": _code(sms)})
    assert r.status_code == 409 and _err(r) == "PHONE_ALREADY_VERIFIED"
    # a new number has to be verified again
    me = client.patch(f"{API}/me", headers=h, json={"phone": _phone()}).json()
    assert me["phone_verified"] is False


def test_a_profile_without_a_phone_cannot_ask_for_a_code(client, sms):
    _, h = _customer(client, None)
    r = client.post(f"{API}/me/phone/otp", headers=h)
    assert r.status_code == 422 and _err(r) == "PHONE_MISSING" and sms == []


def test_one_number_is_verified_for_one_account_only(client, sms):
    phone = _phone()
    _verified(client, sms, phone)
    _, other = _customer(client, phone)
    r = client.post(f"{API}/me/phone/otp", headers=other)
    assert r.status_code == 409 and _err(r) == "PHONE_TAKEN"
    _, plus84 = _customer(client, "+84" + phone[1:])             # the same number written the other way
    assert _err(client.post(f"{API}/me/phone/otp", headers=plus84)) == "PHONE_TAKEN"


def test_resend_wait_newer_code_and_daily_limit(client, sms):
    phone = _phone()
    _, h = _customer(client, phone)
    assert client.post(f"{API}/me/phone/otp", headers=h).status_code == 202
    first = _code(sms)
    r = client.post(f"{API}/me/phone/otp", headers=h)
    assert r.status_code == 429 and _err(r) == "OTP_RESEND_TOO_SOON" and 1 <= r.json()["error"]["details"]["retry_after"] <= 60
    assert len(sms) == 1

    _age_codes(phone)
    assert client.post(f"{API}/me/phone/otp", headers=h).status_code == 202
    second = _code(sms)
    if first != second:                                           # the older code is closed by the newer one
        r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": first})
        assert r.status_code == 400 and _err(r) == "OTP_INVALID"

    for _ in range(3):                                            # 5 codes per number in 24 hours
        _age_codes(phone)
        assert client.post(f"{API}/me/phone/otp", headers=h).status_code == 202
    _age_codes(phone)
    r = client.post(f"{API}/me/phone/otp", headers=h)
    assert r.status_code == 429 and _err(r) == "OTP_DAILY_LIMIT" and len(sms) == 5
    _age_codes(phone, 86400)                                      # a day later the number may receive codes again
    assert client.post(f"{API}/me/phone/otp", headers=h).status_code == 202


def test_five_wrong_guesses_burn_the_code_and_an_old_code_expires(client, sms):
    phone = _phone()
    _, h = _customer(client, phone)
    client.post(f"{API}/me/phone/otp", headers=h)
    right = _code(sms)
    wrong = "000000" if right != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": wrong})
        assert _err(r) == "OTP_INVALID" and r.json()["error"]["details"]["attempts_left"] == left
    assert _err(client.post(f"{API}/me/phone/verify", headers=h, json={"code": wrong})) == "OTP_TOO_MANY_ATTEMPTS"
    assert _err(client.post(f"{API}/me/phone/verify", headers=h, json={"code": right})) == "OTP_INVALID"
    assert _sql("select attempt_count from phone_otps where phone=:p", p=phone) == 5

    _age_codes(phone)
    client.post(f"{API}/me/phone/otp", headers=h)
    _age_codes(phone, 301)                                        # past the 5 minutes
    r = client.post(f"{API}/me/phone/verify", headers=h, json={"code": _code(sms)})
    assert r.status_code == 400 and _err(r) == "OTP_EXPIRED"
    assert client.get(f"{API}/me", headers=h).json()["phone_verified"] is False


def test_forgotten_password_is_reset_with_the_verified_phone(client, sms, mailbox):
    phone = _phone()
    email, h = _verified(client, sms, phone)
    _age_codes(phone)                                             # past the resend wait of the verification code
    sms.clear()
    # unknown and unverified numbers answer the same, and nothing is sent
    _customer(client, unverified := _phone())
    for p in (_phone(), unverified):
        r = client.post(f"{API}/auth/phone-reset/request", json={"phone": p})
        assert r.status_code == 202
    assert sms == []

    r = client.post(f"{API}/auth/phone-reset/request", json={"phone": "+84" + phone[1:]})
    assert r.status_code == 202 and len(sms) == 1 and sms[0][0] == phone and "dat lai mat khau" in sms[0][1]
    assert client.post(f"{API}/auth/phone-reset/request", json={"phone": phone}).status_code == 202
    assert len(sms) == 1                                          # resend wait: silently nothing, same answer

    url, code = f"{API}/auth/password-reset/confirm", _code(sms)
    wrong = "000000" if code != "000000" else "111111"
    r = client.post(url, json={"phone": phone, "code": wrong, "new_password": "Brandn3wPass"})
    assert r.status_code == 400 and _err(r) == "OTP_INVALID" and r.json()["error"]["details"]["attempts_left"] == 4
    r = client.post(url, json={"phone": _phone(), "code": code, "new_password": "Brandn3wPass"})
    assert r.status_code == 400 and _err(r) == "OTP_INVALID"     # a number nobody verified
    r = client.post(url, json={"phone": phone, "code": code, "new_password": "short"})
    assert r.status_code == 422                                   # weak password: the code is not used up
    assert client.post(url, json={"phone": phone, "email": email, "code": code, "new_password": "Brandn3wPass"}).status_code == 422
    assert client.post(url, json={"token": "x", "new_password": "Brandn3wPass"}).status_code == 422   # no token any more
    assert client.post(f"{API}/auth/phone-reset/verify", json={"phone": phone, "code": code}).status_code in (404, 405)

    mailbox.clear()
    ok = client.post(url, json={"phone": "+84" + phone[1:], "code": code, "new_password": "Brandn3wPass"})
    assert ok.status_code == 204, ok.text
    assert client.get(f"{API}/me", headers=h).status_code == 401  # every device signed out
    login(client, email, "Brandn3wPass")
    assert [m[0] for m in mailbox] == [email] and "đã được đổi" in mailbox[0][1]
    again = client.post(url, json={"phone": phone, "code": code, "new_password": "Another1234"})
    assert again.status_code == 400 and _err(again) == "OTP_INVALID"   # single use
    assert _sql("select count(*) from audit_logs where action='PASSWORD_RESET_PHONE' and entity_id = "
                "(select id from accounts where email=:e)", e=email) == 1


def test_a_disabled_account_cannot_be_recovered_by_phone(client, sms):
    phone = _phone()
    email, _ = _verified(client, sms, phone)
    _age_codes(phone)
    sms.clear()
    _sql("update accounts set status='DISABLED' where email=:e returning 1", e=email)
    assert client.post(f"{API}/auth/phone-reset/request", json={"phone": phone}).status_code == 202
    assert sms == []
    r = client.post(f"{API}/auth/password-reset/confirm", json={"phone": phone, "code": "123456", "new_password": "Brandn3wPass"})
    assert r.status_code == 400 and _err(r) == "OTP_INVALID"


def test_otp_endpoints_need_a_login_and_valid_input(client):
    assert client.post(f"{API}/me/phone/otp").status_code == 401
    assert client.post(f"{API}/me/phone/verify", json={"code": "123456"}).status_code == 401
    assert client.post(f"{API}/auth/phone-reset/request", json={"phone": "12345"}).status_code == 422
    assert client.post(f"{API}/auth/password-reset/confirm",
                       json={"phone": "0901234567", "code": "1234", "new_password": "Brandn3wPass"}).status_code == 422


def test_sms_is_listed_with_the_integrations(client):
    from tests.conftest import auth
    names = {i["name"]: i for i in client.get(f"{API}/admin/integrations", headers=auth(client, "ADMIN")).json()}
    assert names["SMS"]["mode"] == "MOCK" and names["SMS"]["toggleable"] is False


# ---- eSMS adapter (SMS_MODE=esms). Mocked transport only: nothing reaches eSMS. ----------------------------------------------
import json

import httpx

from app.core.errors import AppError
from app.integrations.sms import EsmsSms


def _esms(handler, sandbox: bool = True) -> EsmsSms:
    return EsmsSms(api_key="k", secret_key="s", brandname="AIVHRS", base_url="https://esms.test/json/", sandbox=sandbox,
                   transport=httpx.MockTransport(handler))


def test_esms_sends_a_brandname_otp_and_keeps_the_text_out_of_the_log(caplog):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(200, json={"CodeResult": "100", "SMSID": "abc-1"})

    caplog.set_level("INFO", logger="app.sms")
    sender = _esms(handler)
    sender.send("0901234567", "AI-VHRS: ma xac minh cua ban la 123456")
    url, body = seen[0]
    assert url == "https://esms.test/json/SendMultipleMessage_V4_post_json/"
    assert body["Phone"] == "0901234567" and body["Brandname"] == "AIVHRS" and body["SmsType"] == "2"
    assert body["Sandbox"] == "1" and body["IsUnicode"] == "0" and len(body["RequestId"]) == 32
    assert sender.mode == "ESMS_SANDBOX" and _esms(handler, sandbox=False).mode == "ESMS"
    assert "123456" not in caplog.text and "0901234567" not in caplog.text and "090****567" in caplog.text


@pytest.mark.parametrize("reply, status, code", [
    (httpx.Response(200, json={"CodeResult": "101", "ErrorMessage": "Authorize Failed"}), 503, "SMS_NOT_CONFIGURED"),
    (httpx.Response(200, json={"CodeResult": "103"}), 503, "SMS_NOT_CONFIGURED"),
    (httpx.Response(200, json={"CodeResult": "99"}), 502, "SMS_REJECTED"),
    (httpx.Response(500, text="oops"), 502, "SMS_UNAVAILABLE"),
    (httpx.Response(502, json={"Message": "bad gateway"}), 502, "SMS_REJECTED"),
])
def test_esms_failures_become_clean_errors(reply, status, code):
    with pytest.raises(AppError) as err:
        _esms(lambda req: reply).send("0901234567", "x")
    assert err.value.status == status and err.value.code == code


def test_esms_network_error_is_sms_unavailable():
    def handler(req):
        raise httpx.ConnectTimeout("slow")
    with pytest.raises(AppError) as err:
        _esms(handler).send("0901234567", "x")
    assert err.value.status == 502 and err.value.code == "SMS_UNAVAILABLE"


def test_esms_mode_without_keys_is_not_configured(monkeypatch):
    from app.core.config import get_settings
    from app.integrations.sms import get_sms_sender
    s = get_settings()
    monkeypatch.setattr(s, "sms_mode", "esms")
    monkeypatch.setattr(s, "esms_api_key", None)
    with pytest.raises(AppError) as err:
        get_sms_sender()
    assert err.value.status == 503 and err.value.code == "SMS_NOT_CONFIGURED"
    monkeypatch.setattr(s, "esms_api_key", "k")
    monkeypatch.setattr(s, "esms_secret_key", "s")
    monkeypatch.setattr(s, "esms_brandname", "AIVHRS")
    assert isinstance(get_sms_sender(), EsmsSms)


# ---- SpeedSMS adapter (SMS_MODE=speedsms). Mocked transport only: nothing reaches SpeedSMS. -----------------------------------
import base64

from app.integrations.sms import SpeedSms, intl_phone


def _speedsms(handler, **kw) -> SpeedSms:
    return SpeedSms(access_token="tok", base_url="https://speedsms.test/index.php/", transport=httpx.MockTransport(handler), **kw)


def test_speedsms_posts_json_with_basic_auth_and_keeps_secrets_out_of_url_and_log(caplog):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"status": "success", "code": "00",
                                         "data": {"tranId": 77, "totalSMS": 1, "totalPrice": 500, "invalidPhone": []}})

    caplog.set_level("INFO", logger="app.sms")
    _speedsms(handler).send("0901234567", "AI-VHRS: ma xac minh cua ban la 654321")
    req = seen[0]
    assert str(req.url) == "https://speedsms.test/index.php/sms/send" and "tok" not in str(req.url)
    assert req.headers["authorization"] == "Basic " + base64.b64encode(b"tok:x").decode()
    body = json.loads(req.content)
    assert body == {"to": ["84901234567"], "content": "AI-VHRS: ma xac minh cua ban la 654321", "sms_type": 4, "sender": ""}
    assert "654321" not in caplog.text and "0901234567" not in caplog.text and "tran=77" in caplog.text
    assert intl_phone("+84901234567") == "84901234567" and intl_phone("84901234567") == "84901234567"


@pytest.mark.parametrize("reply, status, code", [
    (httpx.Response(200, json={"status": "error", "code": "300", "message": "balance not enough"}), 503, "SMS_NOT_CONFIGURED"),
    (httpx.Response(200, json={"status": "error", "code": "009", "message": "not allowed"}), 503, "SMS_NOT_CONFIGURED"),
    (httpx.Response(401, json={"status": "error", "message": "unauthorized"}), 503, "SMS_NOT_CONFIGURED"),
    (httpx.Response(200, json={"status": "error", "code": "105", "invalidPhone": ["84901234567"]}), 502, "SMS_REJECTED"),
    (httpx.Response(200, json={"status": "success", "code": "00",
                               "data": {"totalSMS": 0, "invalidPhone": ["84901234567"]}}), 502, "SMS_REJECTED"),
    (httpx.Response(200, json={"status": "error", "code": "500"}), 502, "SMS_UNAVAILABLE"),
    (httpx.Response(503, text="maintenance"), 502, "SMS_UNAVAILABLE"),
])
def test_speedsms_failures_become_clean_errors(reply, status, code):
    with pytest.raises(AppError) as err:
        _speedsms(lambda req: reply).send("0901234567", "x")
    assert err.value.status == status and err.value.code == code


def test_speedsms_mode_needs_a_token_and_a_sender_for_own_brandname(monkeypatch):
    from app.core.config import get_settings
    from app.integrations.sms import get_sms_sender, sms_mode_label
    s = get_settings()
    monkeypatch.setattr(s, "sms_mode", "speedsms")
    monkeypatch.setattr(s, "speedsms_access_token", None)
    with pytest.raises(AppError) as err:
        get_sms_sender()
    assert err.value.code == "SMS_NOT_CONFIGURED"
    monkeypatch.setattr(s, "speedsms_access_token", "tok")
    assert isinstance(get_sms_sender(), SpeedSms) and sms_mode_label() == "SPEEDSMS"
    monkeypatch.setattr(s, "speedsms_sms_type", 3)                  # own Brandname without its name
    monkeypatch.setattr(s, "speedsms_sender", None)
    with pytest.raises(AppError):
        get_sms_sender()
