"""Reminders to add / verify the phone number (owner request 2026-11-26, services/phone_reminders.py). Real database.

The suite switches the reminders off (tests/conftest.py); these tests switch them on.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import get_engine
from tests.conftest import PASSWORD, login, make_account

API = "/api/v1"
N = f"{API}/me/notifications"


@pytest.fixture(autouse=True)
def _reminders_on(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "phone_reminders_enabled", True)


def _phone() -> str:
    return "09" + f"{uuid.uuid4().int % 10 ** 8:08d}"


def _sql(q: str, **p):
    with get_engine().begin() as c:
        return c.execute(text(q), p).scalar()


def _bearer(tok: dict) -> dict:
    return {"Authorization": f"Bearer {tok['access_token']}"}


def _mine(client, tok, code: str) -> list[dict]:
    items = client.get(N, headers=_bearer(tok)).json()["items"]
    return [n for n in items if n["msg_code"] == code]


def test_first_sign_in_without_a_phone_asks_for_one_once(client):
    email = make_account("CUSTOMER")
    tok = login(client, email)
    assert tok["reminders"] == ["ADD_PHONE"]
    [n] = _mine(client, tok, "PHONE_ADD")
    assert n["type"] == "SYSTEM" and n["order_id"] is None and "Tài khoản > Hồ sơ" in n["body"]
    assert login(client, email)["reminders"] == []                     # once per account, read or not
    client.post(f"{N}/read-all", headers=_bearer(tok))
    assert login(client, email)["reminders"] == []
    assert _sql("select count(*) from notifications where msg_code='PHONE_ADD' and account_id="
                "(select id from accounts where email=:e)", e=email) == 1   # in-app only, no e-mail row


def test_an_unverified_phone_is_reminded_at_most_weekly_and_not_stacked(client):
    email = make_account("CUSTOMER")
    phone = _phone()
    _sql("update accounts set phone=:p where email=:e returning 1", p=phone, e=email)
    tok = login(client, email)
    assert tok["reminders"] == ["VERIFY_PHONE"]
    [n] = _mine(client, tok, "PHONE_VER")
    assert phone[:3] + "****" + phone[-3:] in n["body"] and phone not in n["body"]     # the number is masked
    assert login(client, email)["reminders"] == []                      # unread: not stacked
    client.post(f"{N}/read-all", headers=_bearer(tok))
    assert login(client, email)["reminders"] == []                      # read, but sent less than 7 days ago
    _sql("update notifications set created_at=:t where msg_code='PHONE_VER' and account_id="
         "(select id from accounts where email=:e) returning 1", t=datetime.now(timezone.utc) - timedelta(days=8), e=email)
    assert login(client, email)["reminders"] == ["VERIFY_PHONE"]


def test_a_verified_phone_gets_no_reminder(client):
    email = make_account("CUSTOMER")
    _sql("update accounts set phone=:p, phone_verified_at=now() where email=:e returning 1", p=_phone(), e=email)
    tok = login(client, email)
    assert tok["reminders"] == [] and _mine(client, tok, "PHONE_VER") == [] and _mine(client, tok, "PHONE_ADD") == []


def test_changing_the_phone_asks_to_verify_the_new_number(client):
    email = make_account("CUSTOMER")
    _sql("update accounts set phone=:p, phone_verified_at=now() where email=:e returning 1", p=_phone(), e=email)
    tok = login(client, email)
    h = _bearer(tok)
    r = client.patch(f"{API}/me", headers=h, json={"phone": _phone()})
    assert r.status_code == 200 and r.json()["phone_verified"] is False
    assert len(_mine(client, tok, "PHONE_VER")) == 1
    client.patch(f"{API}/me", headers=h, json={"phone": _phone()})       # still unread: not stacked
    assert len(_mine(client, tok, "PHONE_VER")) == 1
    client.patch(f"{API}/me", headers=h, json={"full_name": "Không đổi số"})
    assert len(_mine(client, tok, "PHONE_VER")) == 1


def test_refresh_lists_no_reminders(client):
    tok = login(client, make_account("CUSTOMER", PASSWORD))
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200 and r.json()["reminders"] == []


def test_switched_off_creates_nothing(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "phone_reminders_enabled", False)
    tok = login(client, make_account("CUSTOMER"))
    assert tok["reminders"] == [] and _mine(client, tok, "PHONE_ADD") == []
