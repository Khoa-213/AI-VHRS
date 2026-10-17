"""Google sign-in. Google itself cannot be called from a test, so:
* the verification rules (audience, issuer, expiry, verified e-mail, Google's refusal) are tested on the REAL
  `TokenInfoVerifier` against a scripted HTTP transport that answers like Google's tokeninfo endpoint;
* the account logic (create / link by e-mail / refuse staff / disabled) runs on the real database with the verifier
  replaced by a stand-in that returns a chosen identity.
"""
import time
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.db.session import get_engine
from app.integrations.google_auth import GoogleIdentity, TokenInfoVerifier, get_google_verifier
from app.main import app
from tests.conftest import make_account
from tests.test_api_orders import API, _sql

CLIENT = "123-abc.apps.googleusercontent.com"
TOKEN = "x" * 40


def _verifier(payload=None, status=200, client_ids=(CLIENT,), error=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if error:
            raise error
        return httpx.Response(status, json=payload or {})
    return TokenInfoVerifier(list(client_ids), httpx.Client(transport=httpx.MockTransport(handler)))


def _good(**over):
    return {"aud": CLIENT, "iss": "https://accounts.google.com", "exp": str(int(time.time()) + 600), "sub": "1001",
            "email": "a@example.org", "email_verified": "true", "name": "An Nguyen", **over}


def _code(call):
    with pytest.raises(Exception) as exc:
        call()
    return exc.value.code, exc.value.status


# ---- the verification rules (real code, scripted Google) ----------------------------------------------
def test_valid_token_yields_the_identity():
    who = _verifier(_good()).verify(TOKEN)
    assert who == GoogleIdentity(sub="1001", email="a@example.org", name="An Nguyen")
    assert _verifier(_good(iss="accounts.google.com")).verify(TOKEN).email == "a@example.org"


@pytest.mark.parametrize("payload,status,code,http", [
    (_good(aud="someone-elses-client"), 200, "GOOGLE_TOKEN_INVALID", 401),         # token minted for another app
    (_good(iss="https://evil.example"), 200, "GOOGLE_TOKEN_INVALID", 401),
    (_good(exp=str(int(time.time()) - 5)), 200, "GOOGLE_TOKEN_INVALID", 401),
    (_good(exp="soon"), 200, "GOOGLE_TOKEN_INVALID", 401),
    ({k: v for k, v in _good().items() if k != "email"}, 200, "GOOGLE_TOKEN_INVALID", 401),
    (_good(email_verified="false"), 200, "GOOGLE_EMAIL_NOT_VERIFIED", 401),
    ({"error": "invalid_token"}, 400, "GOOGLE_TOKEN_INVALID", 401),               # Google refuses the token
])
def test_invalid_tokens_are_refused(payload, status, code, http):
    assert _code(lambda: _verifier(payload, status).verify(TOKEN)) == (code, http)


def test_not_configured_and_google_down():
    assert _code(lambda: _verifier(_good(), client_ids=()).verify(TOKEN)) == ("GOOGLE_NOT_CONFIGURED", 503)
    down = _verifier(error=httpx.ConnectError("boom"))
    assert _code(lambda: down.verify(TOKEN)) == ("GOOGLE_UNAVAILABLE", 503)


def test_without_a_client_id_the_endpoint_answers_503(client):
    app.dependency_overrides.pop(get_google_verifier, None)          # the real verifier, no GOOGLE_CLIENT_ID in this env
    r = client.post(f"{API}/auth/google", json={"id_token": TOKEN})
    from app.core.config import get_settings
    assert r.status_code == (503 if not get_settings().google_client_ids else 401)
    assert client.post(f"{API}/auth/google", json={"id_token": "short"}).status_code == 422


# ---- account logic on the real database ----------------------------------------------------------------
@pytest.fixture
def google(request):
    holder = {}

    class Stub:
        def verify(self, id_token):
            return holder["who"]

    app.dependency_overrides[get_google_verifier] = lambda: Stub()
    yield lambda email, name="Khach Google": holder.__setitem__("who", GoogleIdentity("sub-" + uuid.uuid4().hex[:8], email, name))
    app.dependency_overrides.pop(get_google_verifier, None)


def _post(client):
    return client.post(f"{API}/auth/google", json={"id_token": TOKEN})


def test_first_google_login_creates_a_customer_and_returns_working_tokens(client, google):
    email = f"pytest_{uuid.uuid4().hex[:10]}@example.com"
    google(email, "Lê Thị Mai")
    r = _post(client)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["account"]["role"] == "CUSTOMER" and d["account"]["email"] == email and d["account"]["full_name"] == "Lê Thị Mai"
    h = {"Authorization": f"Bearer {d['access_token']}"}
    assert client.get(f"{API}/me", headers=h).json()["email"] == email                    # a normal session
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": d["refresh_token"]}).status_code == 200
    assert _sql("select count(*) from audit_logs where action='ACCOUNT_REGISTER_GOOGLE' and actor_id=:a", a=d["account"]["id"]) == 1
    assert client.post(f"{API}/orders", headers=h, json={"order_type": "OT3_TEMPLATE", "quantity": 1}).status_code == 201
    # the random password cannot be guessed or used
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!x"}).status_code == 401


def test_second_login_reuses_the_account_and_matches_email_case_insensitively(client, google):
    email = make_account("CUSTOMER")
    google(email.upper(), "Ten Khac")
    r = _post(client)
    assert r.status_code == 200
    assert r.json()["account"]["email"] == email and r.json()["account"]["full_name"] == "Test CUSTOMER"     # profile untouched
    assert _sql("select count(*) from accounts where lower(email)=lower(:e)", e=email) == 1
    again = _post(client)
    assert again.status_code == 200 and again.json()["account"]["id"] == r.json()["account"]["id"]


def test_internal_accounts_cannot_use_google(client, google):
    for role in ("STAFF", "MANAGER", "ADMIN", "TECHNICAL_STAFF"):
        google(make_account(role))
        r = _post(client)
        assert r.status_code == 403 and r.json()["error"]["code"] == "GOOGLE_NOT_ALLOWED", role


def test_disabled_or_locked_accounts_are_refused(client, google):
    email = make_account("CUSTOMER")
    google(email)
    with get_engine().begin() as c:
        c.execute(text("update accounts set status='LOCKED' where email=:e"), {"e": email})
    r = _post(client)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    with get_engine().begin() as c:
        c.execute(text("update accounts set status='ACTIVE', locked_until=now()+interval '10 minutes' where email=:e"), {"e": email})
    r = _post(client)
    assert r.status_code == 423 and r.json()["error"]["code"] == "ACCOUNT_TEMP_LOCKED"


def test_logout_revokes_a_google_session(client, google):
    google(f"pytest_{uuid.uuid4().hex[:10]}@example.com")
    d = _post(client).json()
    h = {"Authorization": f"Bearer {d['access_token']}"}
    assert client.post(f"{API}/auth/logout", headers=h).status_code in (200, 204)
    assert client.get(f"{API}/me", headers=h).status_code == 401
