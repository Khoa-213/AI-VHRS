"""Audit 2026-11-27, batch 2 (docs/audit/05_ISSUES_AND_RECOMMENDATIONS.md): doors that were open by default, and reliability.

D01 / PP-01  a payment that moves no real money is refused unless the deployment allows test payments
AI-11        a picture is refused by its header before any pixel is decoded
AI-05        replaying an assistant turn is limited to the caller's own conversations
AR-02        webhooks do their database work off the event loop; a stuck row lock is given up on (409 RESOURCE_BUSY)
AR-05        every failure answers with the error envelope, unknown routes and unexpected errors included
(AI-10, the order types, is in tests/test_api_orders.py next to the test it replaces.)
"""
import inspect
import struct
import zlib

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.v1 import payments as payments_api, shipments as shipments_api
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_engine
from app.main import app
from app.services import handwriting_image, image_guard
from app.services.stroke_ai import recovery, recovery_v2
from tests.conftest import auth
from tests.test_api_orders import API, _new, _sql
from tests.test_api_payments import _approved, _code, _deposit, _hook, _signed
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401


def _err(r):
    return r.json()["error"]["code"]


# ---------------------------------------------------------------------------------------------- D01 / PP-01
def test_test_payments_are_refused_where_real_orders_are_taken(client, cust, staff, wcat, monkeypatch):
    oid, _, order = _approved(client, cust, staff[0], wcat)
    pay = _deposit(client, cust, oid)                                    # a mock payment opened while test payments were allowed
    assert pay["mode"] == "MOCK"

    monkeypatch.setattr(get_settings(), "allow_test_payments", False)   # what a deployment that takes real orders runs with
    listed = {g["gateway"]: g for g in client.get(f"{API}/payments/gateways", headers=cust).json()}
    assert listed["VNPAY"]["enabled"] is False and listed["MOMO"]["enabled"] is False       # not even offered
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "MOMO"})
    assert r.status_code == 403 and _err(r) == "TEST_PAYMENTS_DISABLED", r.text
    r = client.post(f"{API}/payments/{pay['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 403 and _err(r) == "TEST_PAYMENTS_DISABLED"                    # the "I paid" button is shut
    body, sig = _signed(pay["gateway_txn_id"], _code(oid), int(float(order["deposit_amount"])))
    r = _hook(client, "VNPAY", body, sig)
    assert r.status_code == 403 and _err(r) == "TEST_PAYMENTS_DISABLED"                    # and so is the mock webhook behind it
    assert _sql("select order_status::text from orders where id=:i", i=oid) == "AWAITING_DEPOSIT"   # nothing was confirmed

    monkeypatch.setattr(get_settings(), "allow_test_payments", True)    # a demo / test environment
    r = client.post(f"{API}/payments/{pay['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200, r.text
    assert _sql("select order_status::text from orders where id=:i", i=oid) == "CONFIRMED"


def test_test_payments_are_off_unless_the_deployment_says_so():
    from app.core.config import Settings
    assert Settings.model_fields["allow_test_payments"].default is False


# ---------------------------------------------------------------------------------------------- AI-11
def _png_header(width: int, height: int) -> bytes:
    """A syntactically valid PNG that DECLARES width x height and carries almost no data (what a decompression bomb looks like)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


def test_an_enormous_picture_is_refused_by_its_header_before_anything_is_decoded(monkeypatch):
    bomb = _png_header(30_000, 30_000)                                   # 900 megapixels in a few dozen bytes
    assert image_guard.declared_size(bomb) == (30_000, 30_000)
    decoded = []
    monkeypatch.setattr(cv2, "imdecode", lambda *a, **k: decoded.append(1))
    for call in (lambda: handwriting_image.analyze_image(bomb),
                 lambda: recovery.recover_page(bomb, paper_size="A4"),
                 lambda: recovery_v2.recover_page(bomb, paper_size="A4")):
        with pytest.raises(AppError) as e:
            call()
        assert e.value.status == 422 and e.value.code == "IMAGE_TOO_LARGE" and e.value.details["max_pixels"] == image_guard.MAX_PIXELS
    assert decoded == []                                                 # the decoder was never reached


def test_an_ordinary_picture_still_decodes_and_garbage_is_still_just_not_a_picture():
    ok, buf = cv2.imencode(".png", np.full((120, 200), 240, np.uint8))
    assert ok
    img = image_guard.decode(buf.tobytes(), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape == (120, 200)
    assert image_guard.declared_size(b"not a picture") is None
    assert image_guard.decode(b"not a picture", cv2.IMREAD_GRAYSCALE) is None      # the callers answer INVALID_IMAGE as before


# ---------------------------------------------------------------------------------------------- AI-05
def test_replaying_an_assistant_turn_is_limited_to_the_callers_own_conversations(client, cust):
    oid = _new(client, cust)["id"]
    owner = _sql("select customer_id from orders where id=:i", i=oid)
    sid = _sql("""insert into ai_sessions (order_id, customer_id, consented_at, flags) values (:o, :c, now(), '[]'::jsonb)
                  returning id""", o=oid, c=owner)
    _sql("""insert into ai_messages (session_id, role, content, client_ref) values (:s, 'USER', 'thư riêng của tôi', 'ref-audit-1')
            returning id""", s=sid)
    _sql("insert into ai_messages (session_id, role, content) values (:s, 'ASSISTANT', 'đã ghi nhận') returning id", s=sid)
    body = {"text": "x", "client_ref": "ref-audit-1"}

    mine = client.post(f"{API}/orders/{oid}/assistant/messages", headers=cust, json=body)
    assert mine.status_code == 200 and mine.json()["user"]["content"] == "thư riêng của tôi"       # the owner's retry is replayed

    stranger = auth(client, "CUSTOMER")
    r = client.post(f"{API}/orders/{oid}/assistant/messages", headers=stranger, json=body)
    assert r.status_code == 404 and "thư riêng" not in r.text, r.text                               # somebody else gets nothing
    r = client.post(f"{API}/orders/{oid}/assistant/messages/stream", headers=stranger, json=body)
    assert r.status_code == 404 and "thư riêng" not in r.text


# ---------------------------------------------------------------------------------------------- AR-02
def test_webhooks_run_their_database_work_in_the_thread_pool_not_on_the_event_loop():
    for handler in (payments_api.payos_webhook, payments_api.payment_webhook, payments_api.momo_ipn, payments_api.vnpay_ipn,
                    shipments_api.carrier_webhook):
        assert not inspect.iscoroutinefunction(handler), handler.__name__


def test_webhooks_still_refuse_a_body_that_is_not_what_the_gateway_sends(client):
    for path, body in ((f"{API}/webhooks/payments/payos", b"not json"), (f"{API}/webhooks/payments/payos", b"[1, 2]"),
                       (f"{API}/webhooks/payments/momo/ipn", b"\xff\xfe"), (f"{API}/webhooks/payments/momo/ipn", b'"text"')):
        r = client.post(path, content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 422 and _err(r) == "INVALID_WEBHOOK", (path, body, r.text)


def test_every_pooled_connection_gives_up_on_a_stuck_lock():
    assert get_settings().db_lock_timeout_ms == 20000
    with get_engine().connect() as c:
        assert c.execute(text("show lock_timeout")).scalar() == "20s"


@pytest.fixture
def failing_routes():
    class _Orig(Exception):
        sqlstate = "55P03"

    def stuck():
        raise OperationalError("select 1 for update", {}, _Orig("canceling statement due to lock timeout"))

    def broken():
        raise RuntimeError("secret detail that must not reach the client")
    app.add_api_route("/api/v1/_audit/stuck", stuck, methods=["GET"])
    app.add_api_route("/api/v1/_audit/broken", broken, methods=["GET"])
    yield
    app.router.routes[:] = [r for r in app.router.routes if "/_audit/" not in getattr(r, "path", "")]


def test_a_lock_that_times_out_is_a_retryable_conflict_not_a_server_error(failing_routes):
    r = TestClient(app).get(f"{API}/_audit/stuck")
    assert r.status_code == 409 and _err(r) == "RESOURCE_BUSY" and r.headers["Retry-After"] == "5"


# ---------------------------------------------------------------------------------------------- AR-05
def test_an_unknown_route_or_method_answers_with_the_error_envelope(client):
    r = client.get(f"{API}/no-such-route")
    assert r.status_code == 404 and _err(r) == "NOT_FOUND" and r.json()["detail"] == "Not Found"   # the old key is kept beside it
    r = client.post(f"{API}/health")
    assert r.status_code == 405 and _err(r) == "METHOD_NOT_ALLOWED"


def test_an_unexpected_error_answers_with_the_envelope_inside_cors_and_leaks_nothing(failing_routes, caplog):
    origin = get_settings().cors_origins[0]
    with caplog.at_level("ERROR", logger="app"):
        r = TestClient(app, raise_server_exceptions=False).get(f"{API}/_audit/broken", headers={"Origin": origin})
    assert r.status_code == 500 and r.json() == {"error": {"code": "INTERNAL_ERROR", "message": "Lỗi hệ thống.", "details": None}}
    assert r.headers.get("access-control-allow-origin") == origin      # the web app sees a failure, not a "CORS error"
    assert "secret detail" not in r.text
    assert any("unhandled error: GET /api/v1/_audit/broken" in rec.getMessage() and rec.exc_info for rec in caplog.records)


# ---------------------------------------------------------------------------------------------- AR-08 (found while fixing AR-02)
def _account_id(client) -> int:
    from tests.conftest import make_account
    return _sql("select id from accounts where email=:e", e=make_account("CUSTOMER"))


def test_notifications_wait_for_the_real_commit_not_for_a_savepoint(client, monkeypatch):
    """SQLAlchemy fires `after_commit` for a released SAVEPOINT too. A request that notifies two people used to dispatch the first
    notification when the second one's SAVEPOINT was released: before anything was committed, from a second connection that could
    not see the row yet (push and e-mail silently dropped), and while still holding the order's lock (a pool deadlock)."""
    from app.db.session import _factory
    from app.services import notifications
    sent = []
    monkeypatch.setattr(notifications, "dispatch", lambda ids: sent.append(list(ids)))
    a, b = _account_id(client), _account_id(client)
    with _factory()() as s:
        notifications.notify(s, account_id=a, order_id=None, msg_code="FINAL_PAID", code="VHRS-AUDIT")
        notifications.notify(s, account_id=b, order_id=None, msg_code="FINAL_PAID", code="VHRS-AUDIT")
        with s.begin_nested():                                   # any later SAVEPOINT of the same request (audit, snapshot...)
            s.execute(text("select 1"))
        assert sent == []                                        # nothing leaves before the commit
        s.commit()
    assert len(sent) == 1 and len(sent[0]) >= 2                  # both, once, after the commit


def test_a_rolled_back_request_dispatches_no_notification(client, monkeypatch):
    from app.db.session import _factory
    from app.services import notifications
    sent = []
    monkeypatch.setattr(notifications, "dispatch", lambda ids: sent.append(list(ids)))
    a = _account_id(client)
    with _factory()() as s:
        notifications.notify(s, account_id=a, order_id=None, msg_code="FINAL_PAID", code="VHRS-AUDIT")
        with s.begin_nested():
            s.execute(text("select 1"))
        s.rollback()
    assert sent == []


def test_live_events_wait_for_the_real_commit_not_for_a_savepoint(monkeypatch):
    from app.db.session import _factory
    from app.services import notification_stream as ns
    pushed = []
    monkeypatch.setattr(ns.broker, "publish", lambda account_id, item: pushed.append(account_id))
    with _factory()() as s:
        ns.publish_after_commit(s, {11, 12}, "message", {"id": 1})
        with s.begin_nested():
            s.execute(text("select 1"))
        assert pushed == []
        s.commit()
    assert sorted(pushed) == [11, 12]


def test_the_old_catalog_file_is_deleted_after_the_real_commit_only():
    from app.db.session import _factory
    from app.services.manager_catalog import ManagerCatalogService
    for finish, expected in (("commit", ["deleted"]), ("rollback", [])):
        calls = []
        with _factory()() as s:
            svc = ManagerCatalogService(s, None)
            svc._after_commit(lambda: calls.append("deleted"))
            with s.begin_nested():
                s.execute(text("select 1"))
            assert calls == []                                   # a released SAVEPOINT is not a commit
            getattr(s, finish)()
            s.execute(text("select 1"))
            s.commit()                                           # a second commit on the same session does not repeat it
        assert calls == expected, finish
