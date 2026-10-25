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
            (entity_type = 'payment' and entity_id in (select id from payments where order_id in {_TEST_ORDERS}))
            or (entity_type = 'production_job' and entity_id in (select id from production_jobs where order_id in {_TEST_ORDERS}))
            or (entity_type = 'order' and entity_id in {_TEST_ORDERS})
            or (entity_type = 'quotation' and entity_id in (select id from quotations where order_id in {_TEST_ORDERS}))
            or (entity_type = 'sketch' and entity_id in (select id from sketches where order_id in {_TEST_ORDERS}))
            or (entity_type = 'shipment' and entity_id in (select id from shipments where order_id in {_TEST_ORDERS}))
            or (entity_type = 'incident' and entity_id in (select id from incidents where reported_by in {_TEST_IDS}
                 or robot_id in (select id from robots where code like 'pytest\\_%')))"""))
        # orders (cascade: inputs, sketches, quotations, messages, status_histories) before accounts;
        # test catalog rows after the orders
        # payments / production jobs do not cascade from orders; jobs must go before the test robots
        c.execute(text(f"delete from shipments where order_id in {_TEST_ORDERS}"))   # no cascade from orders
        c.execute(text(f"delete from payments where order_id in {_TEST_ORDERS}"))
        # product_photos.job_id does not cascade, so photos go before their jobs
        c.execute(text(f"delete from quality_evaluations where created_by in {_TEST_IDS} or order_id in {_TEST_ORDERS}"))   # before the photos
        c.execute(text(f"delete from product_photos where order_id in {_TEST_ORDERS}"))
        # robot_alerts / robot_runs (migration 0008) reference jobs, robots and accounts without cascade; alerts go first
        _jobs_of_tests = (f"(select id from production_jobs where order_id in {_TEST_ORDERS} "
                          "or robot_id in (select id from robots where code like 'pytest\\_%'))")
        c.execute(text(f"delete from robot_alerts where job_id in {_jobs_of_tests} or acknowledged_by in {_TEST_IDS} "
                       f"or resolved_by in {_TEST_IDS} or robot_id in (select id from robots where code like 'pytest\\_%')"))
        c.execute(text(f"delete from robot_runs where job_id in {_jobs_of_tests} or created_by in {_TEST_IDS} "
                       f"or authorized_by in {_TEST_IDS} or robot_id in (select id from robots where code like 'pytest\\_%')"))
        c.execute(text(f"delete from robot_commands where created_by in {_TEST_IDS} or job_id in {_jobs_of_tests} "
                       "or robot_id in (select id from robots where code like 'pytest\_%')"))
        c.execute(text(f"delete from robot_agents where created_by in {_TEST_IDS} "
                       "or robot_id in (select id from robots where code like 'pytest\_%')"))
        c.execute(text(f"delete from audit_logs where entity_type = 'alert_catalog' and actor_id in {_TEST_IDS}"))
        c.execute(text(f"update alert_catalog set updated_by = null where updated_by in {_TEST_IDS}"))
        c.execute(text(f"delete from production_jobs where order_id in {_TEST_ORDERS}"))
        c.execute(text(f"delete from orders where customer_id in {_TEST_IDS}"))
        c.execute(text("delete from production_jobs where robot_id in (select id from robots where code like 'pytest\\_%')"))
        # incidents reference robots and accounts without cascade (job_events/calibrations went with their jobs)
        c.execute(text(f"delete from incidents where reported_by in {_TEST_IDS} "
                       "or robot_id in (select id from robots where code like 'pytest\\_%')"))
        c.execute(text("delete from robots where code like 'pytest\\_%'"))
        c.execute(text(f"delete from handwriting_styles where owner_id in {_TEST_IDS}"))
        # a test may have saved a new PricingConfig version: drop those and re-activate the last real one
        c.execute(text(f"delete from pricing_configs where created_by in {_TEST_IDS}"))
        c.execute(text("update pricing_configs set is_active = true where version = (select max(version) from pricing_configs) "
                       "and not exists (select 1 from pricing_configs where is_active)"))
        # The test catalog is publicly visible while the suite runs, so a REAL customer may have ordered one of its
        # items. Never delete those (FK violation would abort the whole cleanup): switch them off and rename them so
        # they are no longer treated as test data. Their order stays untouched.
        c.execute(text("update pen_types set code='orphan_'||code, is_active=false where code like 'pytest\\_%' "
                       "and id in (select pen_type_id from orders where pen_type_id is not null)"))
        c.execute(text("update paper_types set code='orphan_'||code, is_active=false where code like 'pytest\\_%' "
                       "and id in (select paper_type_id from orders where paper_type_id is not null)"))
        c.execute(text("update templates set code='orphan_'||left(code, 30), is_active=false where code like 'pytest\\_%' "
                       "and id in (select template_id from order_inputs where template_id is not null)"))
        c.execute(text("delete from paper_pen_compats where paper_type_id in "
                       "(select id from paper_types where code like 'pytest\\_%')"))
        c.execute(text("delete from ink_colors where pen_type_id in (select id from pen_types where code like 'pytest\\_%')"))
        c.execute(text("delete from pen_types where code like 'pytest\\_%'"))
        c.execute(text("delete from paper_types where code like 'pytest\\_%'"))
        c.execute(text("delete from templates where code like 'pytest\\_%'"))
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
    # Always put the restriction back. If the row was already missing when this run began (an earlier run was
    # interrupted), restore the project default instead of leaving customers able to order OT-2.
    value, desc = (row[0], row[1]) if row else ('["OT1_COPY_RESTORE", "OT3_TEMPLATE"]', "LI-10: loại đơn đang nhận.")
    with get_engine().begin() as c:
        c.execute(text("insert into system_settings (key, value, description) values "
                       "('order_types_enabled', cast(:v as jsonb), :d) on conflict (key) do nothing"), {"v": value, "d": desc})


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    from app.core.ratelimit import limiter
    limiter.reset()
    yield


@pytest.fixture(autouse=True)
def _no_real_provider_credentials(monkeypatch):
    """The tests must never reach a real payment gateway or carrier. `BE/.env` may hold real keys (payOS, VNPay sandbox...): without
    this, a test that expects "not configured" would call the real API (a payOS test once created a real payment link), and the
    gateway-list tests would depend on whoever runs them. Tests that need a provider switch it on explicitly or use test doubles."""
    from app.core.config import get_settings
    s = get_settings()
    for name in ("payos_client_id", "payos_api_key", "payos_checksum_key", "vnpay_tmn_code", "vnpay_hash_secret",
                 "momo_partner_code", "momo_access_key", "momo_secret_key", "ghn_token", "ghn_shop_id", "ghtk_token",
                 "ghtk_client_source", "carrier_webhook_secret"):
        monkeypatch.setattr(s, name, None)
    # e-mail: never reach a real SMTP server (alerts go to every active Manager, and the database holds real people)
    for name in ("smtp_host", "smtp_user", "smtp_password", "smtp_from"):
        monkeypatch.setattr(s, name, None)
    from app.integrations.mailer import ConsoleMailer
    ConsoleMailer.outbox.clear()


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
