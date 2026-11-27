"""Firebase phone sign-in as the proof of a phone number (2026-11-27, integrations/firebase_auth.py). Real database; Google
is never called: the tokens are signed with a key made here and the verifier is given its certificate."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import text

from app.core.errors import AppError
from app.db.session import get_engine
from app.integrations.firebase_auth import CertVerifier, get_firebase_verifier
from app.main import app
from tests.conftest import PASSWORD, login, make_account

API = "/api/v1"
PROJECT, KID = "proj-test", "kid-1"


def _key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "securetoken.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT = _key_and_cert()
OTHER_KEY, _ = _key_and_cert()


def _token(phone: str | None = "+84901234567", *, key=KEY, kid: str = KID, age: int = 5, provider: str = "phone", **over) -> str:
    now = int(time.time())
    claims = {"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": "uid-" + uuid.uuid4().hex[:8],
              "iat": now - age, "exp": now + 3600, "auth_time": now - age,
              "firebase": {"sign_in_provider": provider, "identities": {"phone": [phone]}}}
    if phone is not None:
        claims["phone_number"] = phone
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def _verifier(**kw) -> CertVerifier:
    return CertVerifier(project_id=PROJECT, fetch=lambda: ({KID: CERT}, 3600.0), max_age=600, **kw)


@pytest.fixture
def firebase():
    app.dependency_overrides[get_firebase_verifier] = lambda: _verifier()   # a bare _verifier(**kw) would read as query params
    yield
    app.dependency_overrides.pop(get_firebase_verifier, None)


def _phone() -> str:
    return "09" + f"{uuid.uuid4().int % 10 ** 8:08d}"


def _sql(q: str, **p):
    with get_engine().begin() as c:
        return c.execute(text(q), p).scalar()


def _err(r) -> str:
    return r.json()["error"]["code"]


def _customer(client, phone: str | None, verified: bool = False) -> tuple[str, dict]:
    email = make_account("CUSTOMER")
    if phone:
        _sql("update accounts set phone=:p, phone_verified_at=:v where email=:e returning 1", p=phone, e=email,
             v=datetime.now(timezone.utc) if verified else None)
    return email, {"Authorization": f"Bearer {login(client, email, PASSWORD)['access_token']}"}


# ---- the verifier ----------------------------------------------------------------------------------------------------
def test_a_fresh_phone_sign_in_of_our_project_is_accepted():
    proof = _verifier().verify_phone(_token("+84853643832"))
    assert proof.phone == "+84853643832" and proof.uid.startswith("uid-") and time.time() - proof.auth_time < 60


@pytest.mark.parametrize("make, code", [
    (lambda: _token(key=OTHER_KEY), "FIREBASE_TOKEN_INVALID"),                              # not signed by Google's key
    (lambda: _token(kid="unknown"), "FIREBASE_TOKEN_INVALID"),
    (lambda: _token(aud="another-project"), "FIREBASE_TOKEN_INVALID"),
    (lambda: _token(iss="https://securetoken.google.com/another-project"), "FIREBASE_TOKEN_INVALID"),
    (lambda: _token(exp=int(time.time()) - 120), "FIREBASE_TOKEN_INVALID"),
    (lambda: _token(provider="password"), "FIREBASE_TOKEN_INVALID"),                        # signed in, but not by phone
    (lambda: _token(None), "FIREBASE_TOKEN_INVALID"),                                       # no phone number in it
    (lambda: _token(sub=""), "FIREBASE_TOKEN_INVALID"),
    (lambda: _token(age=601), "FIREBASE_TOKEN_EXPIRED"),                                    # the SMS sign-in is too old
    (lambda: jwt.encode({"aud": PROJECT}, "secret", algorithm="HS256", headers={"kid": KID}), "FIREBASE_TOKEN_INVALID"),
    (lambda: "not-a-token-at-all-not-a-token", "FIREBASE_TOKEN_INVALID"),
])
def test_other_tokens_are_refused(make, code):
    with pytest.raises(AppError) as err:
        _verifier().verify_phone(make())
    assert err.value.status == 401 and err.value.code == code


def test_not_configured_and_google_unreachable():
    import httpx
    with pytest.raises(AppError) as err:
        CertVerifier(fetch=lambda: ({KID: CERT}, 60.0)).verify_phone(_token())      # FIREBASE_PROJECT_ID is not set in tests
    assert err.value.status == 503 and err.value.code == "FIREBASE_NOT_CONFIGURED"

    def down():
        raise httpx.ConnectError("down")
    with pytest.raises(AppError) as err:
        CertVerifier(project_id=PROJECT, fetch=down).verify_phone(_token())
    assert err.value.status == 503 and err.value.code == "FIREBASE_UNAVAILABLE"


def test_certificates_are_fetched_once_and_again_for_an_unknown_key():
    calls = []

    def fetch():
        calls.append(1)
        return {KID: CERT}, 3600.0
    v = CertVerifier(project_id=PROJECT, fetch=fetch, max_age=600)
    v.verify_phone(_token())
    v.verify_phone(_token())
    assert len(calls) == 1
    with pytest.raises(AppError):
        v.verify_phone(_token(kid="rotated"))                                       # Google rotated: look again, once
    assert len(calls) == 2


# ---- verify the profile's number ---------------------------------------------------------------------------------------
def test_profile_phone_is_verified_by_a_firebase_sign_in_with_that_number(client, firebase):
    phone = _phone()
    email, h = _customer(client, phone)
    url = f"{API}/me/phone/verify-firebase"
    other = client.post(url, headers=h, json={"id_token": _token("+84" + _phone()[1:])})
    assert other.status_code == 400 and _err(other) == "PHONE_MISMATCH"
    assert client.post(url, headers=h, json={"id_token": _token("+84" + phone[1:], key=OTHER_KEY)}).status_code == 401
    assert client.post(url, json={"id_token": _token("+84" + phone[1:])}).status_code == 401          # needs a login
    ok = client.post(url, headers=h, json={"id_token": _token("+84" + phone[1:])})
    assert ok.status_code == 200, ok.text
    assert ok.json()["phone_verified"] is True and ok.json()["phone"] == phone
    again = client.post(url, headers=h, json={"id_token": _token("+84" + phone[1:])})
    assert again.status_code == 409 and _err(again) == "PHONE_ALREADY_VERIFIED"
    assert _sql("select new_value->>'via' from audit_logs where action='PHONE_VERIFY' and entity_id="
                "(select id from accounts where email=:e)", e=email) == "FIREBASE"
    # an account without a number, and a number another account verified
    _, h2 = _customer(client, None)
    assert _err(client.post(url, headers=h2, json={"id_token": _token()})) == "PHONE_MISSING"
    _, h3 = _customer(client, phone)
    assert _err(client.post(url, headers=h3, json={"id_token": _token("+84" + phone[1:])})) == "PHONE_TAKEN"


# ---- forgotten password --------------------------------------------------------------------------------------------------
def test_password_is_reset_with_a_firebase_sign_in_of_the_verified_number(client, firebase, mailbox):
    phone = _phone()
    email, h = _customer(client, phone, verified=True)
    url = f"{API}/auth/password-reset/confirm"
    token = _token("+84" + phone[1:])
    assert client.post(url, json={"firebase_id_token": token, "new_password": "short"}).status_code == 422
    assert client.post(url, json={"firebase_id_token": token, "code": "123456", "new_password": "Brandn3wPass"}).status_code == 422
    assert client.post(url, json={"firebase_id_token": token, "phone": phone, "new_password": "Brandn3wPass"}).status_code == 422
    stranger = client.post(url, json={"firebase_id_token": _token("+84" + _phone()[1:]), "new_password": "Brandn3wPass"})
    assert stranger.status_code == 400 and _err(stranger) == "PHONE_NOT_VERIFIED"
    old = client.post(url, json={"firebase_id_token": _token("+84" + phone[1:], age=700), "new_password": "Brandn3wPass"})
    assert old.status_code == 401 and _err(old) == "FIREBASE_TOKEN_EXPIRED"

    mailbox.clear()
    ok = client.post(url, json={"firebase_id_token": token, "new_password": "Brandn3wPass"})
    assert ok.status_code == 204, ok.text
    assert client.get(f"{API}/me", headers=h).status_code == 401                    # every device signed out
    login(client, email, "Brandn3wPass")
    assert [m[0] for m in mailbox] == [email] and "đã được đổi" in mailbox[0][1]
    again = client.post(url, json={"firebase_id_token": token, "new_password": "Another1234"})
    assert again.status_code == 401 and _err(again) == "FIREBASE_TOKEN_INVALID"     # the token works once
    login(client, email, "Brandn3wPass")
    assert _sql("select new_value->>'via' from audit_logs where action='PASSWORD_RESET_PHONE' and entity_id="
                "(select id from accounts where email=:e)", e=email) == "FIREBASE"


def test_an_unverified_or_disabled_account_is_not_recovered(client, firebase):
    url = f"{API}/auth/password-reset/confirm"
    phone = _phone()
    _customer(client, phone)                                                         # number typed, never verified
    r = client.post(url, json={"firebase_id_token": _token("+84" + phone[1:]), "new_password": "Brandn3wPass"})
    assert r.status_code == 400 and _err(r) == "PHONE_NOT_VERIFIED"
    phone2 = _phone()
    email2, _ = _customer(client, phone2, verified=True)
    _sql("update accounts set status='DISABLED' where email=:e returning 1", e=email2)
    r = client.post(url, json={"firebase_id_token": _token("+84" + phone2[1:]), "new_password": "Brandn3wPass"})
    assert r.status_code == 400 and _err(r) == "PHONE_NOT_VERIFIED"


def test_firebase_is_listed_with_the_integrations_and_answers_503_when_not_configured(client):
    from tests.conftest import auth
    names = {i["name"]: i for i in client.get(f"{API}/admin/integrations", headers=auth(client, "ADMIN")).json()}
    assert names["FIREBASE_PHONE"]["configured"] is False
    _, h = _customer(client, _phone())
    r = client.post(f"{API}/me/phone/verify-firebase", headers=h, json={"id_token": _token()})
    assert r.status_code == 503 and _err(r) == "FIREBASE_NOT_CONFIGURED"
