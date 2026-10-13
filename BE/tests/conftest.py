"""Tests run against the real (Supabase) database. Only rows whose email starts with
'pytest_' are created and they are removed afterwards."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import get_engine
from app.integrations.mailer import ConsoleMailer
from app.main import app

PASSWORD = "Passw0rd!x"
ROLE_ID = {"CUSTOMER": 1, "STAFF": 2, "TECHNICAL_STAFF": 3, "MANAGER": 4, "ADMIN": 5}
_TEST_IDS = "(select id from accounts where email like 'pytest\\_%@example.com')"


def _cleanup() -> None:
    with get_engine().begin() as c:
        c.execute(text(f"delete from audit_logs where actor_id in {_TEST_IDS} "
                       f"or (entity_type = 'account' and entity_id in {_TEST_IDS})"))
        c.execute(text(f"update accounts set created_by = null where created_by in {_TEST_IDS}"))
        c.execute(text("delete from accounts where email like 'pytest\\_%@example.com'"))


@pytest.fixture(scope="session", autouse=True)
def _db_clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    from app.core.ratelimit import limiter
    limiter.reset()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def make_account(role: str = "CUSTOMER", password: str = PASSWORD) -> str:
    email = f"pytest_{uuid.uuid4().hex[:10]}@example.com"
    with get_engine().begin() as c:
        c.execute(text("insert into accounts (role_id, email, password_hash, full_name) values (:r,:e,:h,:n)"),
                  {"r": ROLE_ID[role], "e": email, "h": hash_password(password), "n": f"Test {role}"})
    return email


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth(client: TestClient, role: str) -> dict[str, str]:
    email = make_account(role)
    return {"Authorization": f"Bearer {login(client, email)['access_token']}"}


@pytest.fixture
def mailbox():
    ConsoleMailer.outbox.clear()
    return ConsoleMailer.outbox
