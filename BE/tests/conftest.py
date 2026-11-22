"""Tests run against the real (Supabase) database. Only rows whose email starts with
'pytest_' are created and they are removed afterwards."""
import functools
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

# U1: a throw-away signing key for this test session, unless the environment already has one (never a real key in tests)
if not os.environ.get("PRODUCTION_SIGNING_KEY"):
    from app.core.production_signing import generate_private_key
    os.environ["PRODUCTION_SIGNING_KEY"] = generate_private_key()
    os.environ["PRODUCTION_SIGNING_KEY_ID"] = "pytest"

from app.core.security import hash_password  # noqa: E402
from app.db.session import get_engine
from app.integrations.mailer import ConsoleMailer
from app.main import app

PASSWORD = "Passw0rd!x"
ROLE_ID = {"CUSTOMER": 1, "STAFF": 2, "TECHNICAL_STAFF": 3, "MANAGER": 4, "ADMIN": 5}

# T2 (docs/TEST_SPEEDUP_PLAN.md): scripts/run_tests_sharded.py runs shards at the same time. Each shard writes its rows with its
# own prefix 'pytest_<shard>_' and its cleanup removes only that prefix, so shards never delete each other's data. An ordinary
# session (no VHRS_TEST_SHARD) keeps the prefix 'pytest_' and removes every 'pytest_' row, the shards' leftovers included.
SHARD = os.environ.get("VHRS_TEST_SHARD", "").strip()
assert SHARD == "" or SHARD.isalnum(), "VHRS_TEST_SHARD must be letters / digits"
PREFIX = f"pytest_{SHARD}_" if SHARD else "pytest_"
_LIKE = PREFIX.replace("_", "\\_") + "%"          # e.g. pytest\_s1\_%  (SQL LIKE, '_' escaped)
_TEST_IDS = f"(select id from accounts where email like '{_LIKE}@example.com')"


def fresh_email() -> str:
    """A fresh test account e-mail with this session's prefix."""
    return f"{PREFIX}{uuid.uuid4().hex[:10]}@example.com"


def fresh_code(n: int = 8) -> str:
    """A fresh catalog / robot code with this session's prefix."""
    return PREFIX + uuid.uuid4().hex[:n]


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
            or (entity_type = 'production_snapshot' and entity_id in (select id from production_snapshots where order_id in {_TEST_ORDERS}))
            or (entity_type = 'shipment' and entity_id in (select id from shipments where order_id in {_TEST_ORDERS}))
            or (entity_type = 'incident' and entity_id in (select id from incidents where reported_by in {_TEST_IDS}
                 or robot_id in (select id from robots where code like '{_LIKE}')))"""))
        # orders (cascade: inputs, sketches, quotations, messages, status_histories) before accounts;
        # test catalog rows after the orders
        # payments / production jobs do not cascade from orders; jobs must go before the test robots
        c.execute(text(f"delete from shipments where order_id in {_TEST_ORDERS}"))   # no cascade from orders
        # U1 snapshots reference payments, quotations and sketches without cascade; jobs reference them: unlink, then delete
        c.execute(text(f"update production_jobs set snapshot_id = null where order_id in {_TEST_ORDERS} and snapshot_id is not null"))
        c.execute(text(f"delete from production_snapshots where order_id in {_TEST_ORDERS}"))
        c.execute(text(f"delete from sketch_approvals where order_id in {_TEST_ORDERS}"))
        c.execute(text(f"delete from sketch_regions where sketch_id in (select id from sketches where order_id in {_TEST_ORDERS})"))
        c.execute(text(f"delete from payments where order_id in {_TEST_ORDERS}"))
        # product_photos.job_id does not cascade, so photos go before their jobs
        c.execute(text(f"delete from quality_evaluations where created_by in {_TEST_IDS} or order_id in {_TEST_ORDERS}"))   # before the photos
        c.execute(text(f"delete from product_photos where order_id in {_TEST_ORDERS}"))
        # robot_alerts / robot_runs (migration 0008) reference jobs, robots and accounts without cascade; alerts go first
        _jobs_of_tests = (f"(select id from production_jobs where order_id in {_TEST_ORDERS} "
                          f"or robot_id in (select id from robots where code like '{_LIKE}'))")
        c.execute(text(f"delete from robot_alerts where job_id in {_jobs_of_tests} or acknowledged_by in {_TEST_IDS} "
                       f"or resolved_by in {_TEST_IDS} or robot_id in (select id from robots where code like '{_LIKE}')"))
        c.execute(text(f"delete from robot_runs where job_id in {_jobs_of_tests} or created_by in {_TEST_IDS} "
                       f"or authorized_by in {_TEST_IDS} or robot_id in (select id from robots where code like '{_LIKE}')"))
        c.execute(text(f"delete from robot_commands where created_by in {_TEST_IDS} or job_id in {_jobs_of_tests} "
                       f"or robot_id in (select id from robots where code like '{_LIKE}')"))
        c.execute(text(f"delete from robot_agents where created_by in {_TEST_IDS} "
                       f"or robot_id in (select id from robots where code like '{_LIKE}')"))
        c.execute(text(f"delete from audit_logs where entity_type = 'alert_catalog' and actor_id in {_TEST_IDS}"))
        c.execute(text(f"update alert_catalog set updated_by = null where updated_by in {_TEST_IDS}"))
        c.execute(text(f"delete from production_jobs where order_id in {_TEST_ORDERS}"))
        c.execute(text(f"delete from orders where customer_id in {_TEST_IDS}"))
        c.execute(text(f"delete from production_jobs where robot_id in (select id from robots where code like '{_LIKE}')"))
        # incidents reference robots and accounts without cascade (job_events/calibrations went with their jobs)
        c.execute(text(f"delete from incidents where reported_by in {_TEST_IDS} "
                       f"or robot_id in (select id from robots where code like '{_LIKE}')"))
        # U6 material profiles: of test materials / robots, or measured / verified by a test account
        _test_profiles = (f"(select id from material_profiles where robot_id in (select id from robots where code like '{_LIKE}') "
                          f"or paper_type_id in (select id from paper_types where code like '{_LIKE}') "
                          f"or pen_type_id in (select id from pen_types where code like '{_LIKE}') "
                          f"or measured_by in {_TEST_IDS} or verified_by in {_TEST_IDS})")
        c.execute(text(f"update sketches set render_profile_id = null where render_profile_id in {_test_profiles}"))
        c.execute(text(f"delete from material_profiles where id in {_test_profiles}"))
        c.execute(text(f"delete from robots where code like '{_LIKE}'"))
        c.execute(text(f"delete from handwriting_styles where owner_id in {_TEST_IDS}"))
        # a test may have saved a new PricingConfig version: drop those and re-activate the last real one
        c.execute(text(f"delete from pricing_configs where created_by in {_TEST_IDS}"))
        c.execute(text("update pricing_configs set is_active = true where version = (select max(version) from pricing_configs) "
                       "and not exists (select 1 from pricing_configs where is_active)"))
        # The test catalog is publicly visible while the suite runs, so a REAL customer may have ordered one of its
        # items. Never delete those (FK violation would abort the whole cleanup): switch them off and rename them so
        # they are no longer treated as test data. Their order stays untouched.
        c.execute(text(f"update pen_types set code='orphan_'||code, is_active=false where code like '{_LIKE}' "
                       "and id in (select pen_type_id from orders where pen_type_id is not null)"))
        c.execute(text(f"update paper_types set code='orphan_'||code, is_active=false where code like '{_LIKE}' "
                       "and id in (select paper_type_id from orders where paper_type_id is not null)"))
        c.execute(text(f"update templates set code='orphan_'||left(code, 30), is_active=false where code like '{_LIKE}' "
                       "and id in (select template_id from order_inputs where template_id is not null)"))
        c.execute(text("delete from paper_pen_compats where paper_type_id in "
                       f"(select id from paper_types where code like '{_LIKE}')"))
        c.execute(text(f"delete from ink_colors where pen_type_id in (select id from pen_types where code like '{_LIKE}')"))
        c.execute(text(f"delete from pen_types where code like '{_LIKE}'"))
        c.execute(text(f"delete from paper_types where code like '{_LIKE}'"))
        c.execute(text(f"delete from templates where code like '{_LIKE}'"))
        c.execute(text(f"delete from audit_logs where actor_id in {_TEST_IDS} "
                       f"or (entity_type = 'account' and entity_id in {_TEST_IDS})"))
        c.execute(text(f"delete from showcase_posts where posted_by in {_TEST_IDS}"))   # Phase 5c; reviews go with their orders
        c.execute(text(f"update accounts set created_by = null where created_by in {_TEST_IDS}"))
        c.execute(text(f"update system_settings set updated_by = null where updated_by in {_TEST_IDS}"))   # Admin tests write no-op values
        if not SHARD:
            c.execute(text(f"delete from accounts where email like '{_LIKE}@example.com'"))
            return
        # T2 shard: a row of ANOTHER prefix (another shard, maybe still running) can still point at one of our accounts
        # (seen 2026-11-21: another prefix's order assigned to / accepted by our Staff). Never touch that row: keep the
        # account, log who points at it, and let the serial phase's ordinary cleanup (every 'pytest_' row) remove both.
        sp = c.begin_nested()
        try:
            c.execute(text(f"delete from accounts where email like '{_LIKE}@example.com'"))
            sp.commit()
            return
        except IntegrityError:
            sp.rollback()
        kept = []
        for (aid,) in c.execute(text(f"select id from accounts where email like '{_LIKE}@example.com'")).all():
            one = c.begin_nested()
            try:
                c.execute(text("delete from accounts where id = :i"), {"i": aid})
                one.commit()
            except IntegrityError:
                one.rollback()
                kept.append((aid, [tuple(r) for r in c.execute(text(
                    "select o.id, o.code, o.order_status::text, a.email from orders o join accounts a on a.id = o.customer_id "
                    "where :i in (o.assigned_staff_id, o.assigned_by)"), {"i": aid}).all()]))
        log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".test_progress", "cross_shard.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{PREFIX}: kept {kept}\n")


# An ordinary session deletes ALL 'pytest_' rows at its start and end (a shard only its own prefix, see above), so two sessions on the same database destroy each other's
# data mid-test (2026-11-17: 6 U6/U8 tests failed with 422 / 409 / missing ids that way). A session-level Postgres advisory
# lock lets only one session in; a second one stops at once instead of corrupting the first. The lock dies with its
# connection, so a killed run never leaves it behind. Needs a session-mode connection (Supabase session pooler, local DB).
_SUITE_LOCK_KEY = 0x56485253   # "VHRS"


@pytest.fixture(scope="session", autouse=True)
def _db_clean():
    if os.environ.get("VHRS_TEST_RUNNER_LOCK") == "1":     # scripts/run_tests_sharded.py holds the suite lock for its shards
        _cleanup()
        yield
        _cleanup()
        return
    lock = get_engine().connect()
    if not lock.execute(text("select pg_try_advisory_lock(:k)"), {"k": _SUITE_LOCK_KEY}).scalar():
        lock.close()
        pytest.exit("Another pytest session is already running on this database; wait for it to finish "
                    "(two sessions delete each other's pytest_ data).", returncode=3)
    lock.commit()
    try:
        _cleanup()
        yield
        _cleanup()
    finally:
        # 2026-11-19: Supabase closed this connection after ~5 h idle and the unlock raised a teardown ERROR on the last
        # test of an otherwise green run. A dead connection has already released its session lock, so ignore that.
        try:
            lock.execute(text("select pg_advisory_unlock(:k)"), {"k": _SUITE_LOCK_KEY})
        except OperationalError:
            pass
        finally:
            lock.close()


@pytest.fixture(scope="session", autouse=True)
def _all_order_types_open(_db_clean):
    """The seed restricts customers to OT-1/OT-3 (LI-10); tests exercise every type, so the restriction is
    lifted while the suite runs and put back afterwards. Under scripts/run_tests_sharded.py the runner does it once for all
    shards (VHRS_TEST_ORDER_TYPES_OPEN=1), since one shard putting it back would close it under the others."""
    if os.environ.get("VHRS_TEST_ORDER_TYPES_OPEN") == "1":
        yield
        return
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
                 "momo_partner_code", "momo_access_key", "momo_secret_key", "ghn_token", "ghn_shop_id", "carrier_webhook_secret"):
        monkeypatch.setattr(s, name, None)
    # e-mail: never reach a real SMTP server (alerts go to every active Manager, and the database holds real people)
    for name in ("smtp_host", "smtp_user", "smtp_password", "smtp_from"):
        monkeypatch.setattr(s, name, None)
    # U5: never call a real LLM (BE/.env may hold a Gemini / Claude / OpenAI key); assistant tests use scripted providers
    for name in ("anthropic_api_key", "openai_api_key", "gemini_api_key"):
        monkeypatch.setattr(s, name, None)
    from app.integrations.mailer import ConsoleMailer
    ConsoleMailer.outbox.clear()
    # the notification stream would otherwise stay open for 30 minutes (TestClient reads the whole body)
    from app.api.v1 import notifications as notification_api
    monkeypatch.setattr(notification_api, "MAX_STREAM_S", 0.5)
    monkeypatch.setattr(notification_api, "HEARTBEAT_S", 0.2)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@functools.lru_cache
def _password_hash(password: str) -> str:
    """bcrypt once per password per session (a fresh hash per account cost ~110 ms each, docs/TEST_SPEEDUP_PLAN.md)."""
    return hash_password(password)


def make_account(role: str = "CUSTOMER", password: str = PASSWORD) -> str:
    email = fresh_email()
    with get_engine().begin() as c:
        c.execute(text("insert into accounts (role_id, email, password_hash, full_name) values (:r,:e,:h,:n)"),
                  {"r": ROLE_ID[role], "e": email, "h": _password_hash(password), "n": f"Test {role}"})
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
