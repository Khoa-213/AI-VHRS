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


_TEST_ORDERS = f"(select id from orders where customer_id in {_TEST_IDS})"


def _cleanup() -> None:
    with get_engine().begin() as c:
        # audit rows about test orders / their quotations / sketches (written by the system or by staff)
        c.execute(text(f"""delete from audit_logs where
            (entity_type = 'order' and entity_id in {_TEST_ORDERS})
            or (entity_type = 'quotation' and entity_id in (select id from quotations where order_id in {_TEST_ORDERS}))
            or (entity_type = 'sketch' and entity_id in (select id from sketches where order_id in {_TEST_ORDERS}))"""))
        # orders (cascade: inputs, sketches, quotations, messages, status_histories) before accounts;
        # test catalog rows after the orders
        c.execute(text(f"delete from orders where customer_id in {_TEST_IDS}"))
        c.execute(text("delete from paper_pen_compats where paper_type_id in "
                       "(select id from paper_types where code like 'pytest\_%')"))
        c.execute(text("delete from ink_colors where pen_type_id in (select id from pen_types where code like 'pytest\_%')"))
        c.execute(text("delete from pen_types where code like 'pytest\_%'"))
        c.execute(text("delete from paper_types where code like 'pytest\_%'"))
        c.execute(text("delete from templates where code like 'pytest\_%'"))
        c.execute(text(f"delete from audit_logs where actor_id in {_TEST_IDS} "
                       f"or (entity_type = 'account' and entity_id in {_TEST_IDS})"))
        c.execute(text(f"update accounts set created_by = null where created_by in {_TEST_IDS}"))
        c.execute(text("delete from accounts where email like 'pytest\\_%@example.com'"))


@pytest.fixture(scope="session", autouse=True)
def _db_clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="session", autouse=True)
def _all_order_types_open(_db_clean):
    """The seed restricts customers to OT-1/OT-3 (LI-10); tests exercise every type, so the restriction is
    lifted while the suite runs and put back afterwards."""
    with get_engine().begin() as c:
        row = c.execute(text("select value::text, description from system_settings where key='order_types_enabled'")).first()
        c.execute(text("delete from system_settings where key='order_types_enabled'"))
    yield
    if row:
        with get_engine().begin() as c:
            c.execute(text("insert into system_settings (key, value, description) values "
                           "('order_types_enabled', cast(:v as jsonb), :d) on conflict (key) do nothing"),
                      {"v": row[0], "d": row[1]})


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
