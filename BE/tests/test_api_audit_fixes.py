"""Fixes from the 2026-10-22 backend audit (F-01 .. F-04, F-09): every one of them is a RACE between two requests, so each test
holds a second transaction open (or runs two requests together) to put the code in the situation that used to go wrong.

* F-01 a technician could be booked on two overlapping jobs (two robots, same slot, concurrent requests);
* F-02 a customer cancel racing the deposit confirmation cancelled a PAID order without any refund flag;
* F-03 webhook vs customer action on the same order deadlocked (lock order inverted) and one of them got a 500;
* F-04 cancelling an order left its payOS QR payable;
* F-09 the same "read before the lock" mistake in start-deposit and quotation approval.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import get_engine
from app.main import app
from app.repositories.ops import PaymentRepository
from app.repositories.orders import OrderRepository
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _code, _deposit, _hook, _quoted, _signed
from tests.test_api_payos import HOOK, _hit, payos  # noqa: F401
from tests.test_api_payos import _start as _payos_start
from tests.test_api_scheduling import M, _at, _robot, mgr, robot, tech  # noqa: F401
from tests.test_api_scheduling import _sched
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401


def _hold(sql_steps: list[tuple[str, dict]], locked: threading.Event, seconds: float = 2.5) -> threading.Thread:
    """Another transaction that takes the order lock, changes things, and commits only after `seconds` (like a slow webhook)."""
    def run():
        with get_engine().connect() as c:
            for sql, params in sql_steps:
                c.execute(text(sql), params)
            locked.set()
            time.sleep(seconds)
            c.commit()
    t = threading.Thread(target=run)
    t.start()
    return t


def _confirm_steps(oid: int, pid: int) -> list[tuple[str, dict]]:
    return [("select id from orders where id=:o for update", {"o": oid}),
            ("update payments set status='SUCCESS', paid_at=now() where id=:p", {"p": pid}),
            ("update orders set order_status='CONFIRMED', production_status='PENDING_SCHEDULE' where id=:o", {"o": oid})]


def _in_thread(fn) -> tuple[threading.Thread, dict]:
    out: dict = {}

    def run():
        out["r"] = fn()
    t = threading.Thread(target=run)
    return t, out


# ---- F-01: one technician, two robots, the same slot ---------------------------------------------------------------------
def test_concurrent_requests_cannot_book_one_technician_twice(client, cust, staff, mgr, wcat, tech):
    token = mgr["Authorization"]
    for i in range(3):
        o1, o2 = _approved(client, cust, staff[0], wcat)[0], _approved(client, cust, staff[0], wcat)[0]
        # (_approved only reaches AWAITING_DEPOSIT; pay both deposits through the mock gateway)
        for oid in (o1, o2):
            p = _deposit(client, cust, oid)
            assert client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
        r1, r2, start = _robot(), _robot(), _at(2 + i, 9)

        def go(args):
            oid, rid = args
            with TestClient(app) as c:
                r = c.post(f"{M}/orders/{oid}/schedule", headers={"Authorization": token},
                           json={"robot_id": rid, "technician_id": tech[1], "slot_start": start.isoformat()})
                return r.status_code, (r.json().get("error") or {}).get("details")

        with ThreadPoolExecutor(2) as pool:
            got = sorted(pool.map(go, [(o1, r1), (o2, r2)]), key=lambda x: x[0])
        assert [g[0] for g in got] == [201, 409], got                          # exactly one wins
        assert got[1][1] == {"resource": "technician"}                          # and the loser is told why, not given a 500
        assert _sql("select count(*) from production_jobs where technician_id=:t and slot_start=:s and status='SCHEDULED'",
                    t=tech[1], s=start) == 1
        for r in (r1, r2):
            _sql("update robots set status='MAINTENANCE' where id=:r returning 1", r=r)


def test_the_database_itself_refuses_overlapping_jobs_of_one_technician(client, cust, staff, mgr, wcat, robot, tech):
    from tests.test_api_payments import _paid
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    assert _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).status_code == 201
    other_order = _approved(client, cust, staff[0], wcat)[0]
    with pytest.raises(IntegrityError) as exc:
        with get_engine().begin() as c:                                       # a different robot, the same technician and slot
            c.execute(text("""insert into production_jobs (order_id,sketch_id,robot_id,technician_id,scheduled_by,status,
                              slot_start,slot_end,estimated_duration_min)
                              select :oo,sketch_id,:r2,technician_id,scheduled_by,'SCHEDULED',slot_start,slot_end,
                                     estimated_duration_min from production_jobs where order_id=:o"""),
                      {"oo": other_order, "r2": _robot(), "o": oid})
    assert "ex_job_technician_overlap" in str(exc.value)


# ---- F-02: cancel racing the deposit confirmation --------------------------------------------------------------------------
def test_cancel_cannot_overwrite_a_deposit_that_is_being_confirmed(client, cust, staff, wcat):
    oid, q, ap = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid, "VNPAY")
    locked = threading.Event()
    holder = _hold(_confirm_steps(oid, p["id"]), locked)
    locked.wait()

    def cancel():
        with TestClient(app) as c:
            return c.post(f"{API}/orders/{oid}/cancel", headers={"Authorization": cust["Authorization"]}, json={"reason": "Đổi ý"})

    t, out = _in_thread(cancel)
    t.start(); t.join(); holder.join()
    r = out["r"]
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_CANCEL_UNSUPPORTED", r.text
    assert _sql("select order_status::text from orders where id=:o", o=oid) == "CONFIRMED"
    assert _sql("select status::text from payments where id=:p", p=p["id"]) == "SUCCESS"
    assert _sql("select count(*) from audit_logs where action='ORDER_CANCEL' and entity_id=:o", o=oid) == 0


# ---- F-09: the same stale read in start-deposit and quotation approval ---------------------------------------------------------
def test_starting_a_deposit_sees_an_order_cancelled_meanwhile(client, cust, staff, wcat):
    oid, q, ap = _approved(client, cust, staff[0], wcat)
    locked = threading.Event()
    holder = _hold([("select id from orders where id=:o for update", {"o": oid}),
                    ("update orders set order_status='CANCELLED', cancel_reason='test' where id=:o", {"o": oid})], locked)
    locked.wait()

    def start():
        with TestClient(app) as c:
            return c.post(f"{API}/orders/{oid}/payments/deposit", headers={"Authorization": cust["Authorization"]},
                          json={"gateway": "VNPAY"})

    t, out = _in_thread(start)
    t.start(); t.join(); holder.join()
    assert out["r"].status_code == 409 and out["r"].json()["error"]["code"] == "DEPOSIT_NOT_EXPECTED", out["r"].text
    assert _sql("select count(*) from payments where order_id=:o", o=oid) == 0      # no payment link for a cancelled order


def test_approving_a_quotation_sees_an_order_cancelled_meanwhile(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    locked = threading.Event()
    holder = _hold([("select id from orders where id=:o for update", {"o": oid}),
                    ("update orders set order_status='CANCELLED', cancel_reason='test' where id=:o", {"o": oid})], locked)
    locked.wait()

    def approve():
        with TestClient(app) as c:
            return c.post(f"{API}/orders/{oid}/quotation/approve", headers={"Authorization": cust["Authorization"]}, json={})

    t, out = _in_thread(approve)
    t.start(); t.join(); holder.join()
    assert out["r"].status_code == 409, out["r"].text
    assert _sql("select order_status::text from orders where id=:o", o=oid) == "CANCELLED"
    assert _sql("select deposit_amount is null from orders where id=:o", o=oid) is True


# ---- F-04: cancelling closes the payOS QR ---------------------------------------------------------------------------------------
def test_cancelling_closes_the_payos_link_and_late_money_is_flagged(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _payos_start(client, cust, oid)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Đổi ý"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED"
    assert payos.cancelled == [int(p["gateway_txn_id"])]                       # the QR is dead at payOS too
    assert _sql("select status::text from payments where id=:p", p=p["id"]) == "CANCELLED"
    late = _hit(client, payos.webhook(p["gateway_txn_id"], order["deposit_amount"]))
    assert late["result"] == "IGNORED"                                          # money that still arrives is kept for a refund
    assert [x["needs_refund"] for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()] == [True]


# ---- F-03: the webhook takes the order lock before the payment lock -----------------------------------------------------------------
def test_a_webhook_locks_the_order_before_the_payment(client, cust, staff, wcat, monkeypatch):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid, "VNPAY")
    events = []
    real_order_get, real_by_txn = OrderRepository.get, PaymentRepository.by_txn

    def order_get(self, order_id, *, lock=False):
        if lock:
            events.append("order")
        return real_order_get(self, order_id, lock=lock)

    def by_txn(self, gateway, txn_id, *, lock=False):
        if lock:
            events.append("payment")
        return real_by_txn(self, gateway, txn_id, lock=lock)

    monkeypatch.setattr(OrderRepository, "get", order_get)
    monkeypatch.setattr(PaymentRepository, "by_txn", by_txn)
    body, sig = _signed(p["gateway_txn_id"], _code(oid), int(order["deposit_amount"]))
    assert _hook(client, "VNPAY", body, sig).status_code == 200
    assert events and events[0] == "order" and "payment" in events and events.index("order") < events.index("payment"), events


def test_customer_actions_racing_the_webhook_never_fail_with_a_500(client, cust, staff, wcat):
    for _ in range(4):
        oid, q, order = _approved(client, cust, staff[0], wcat)
        p = _deposit(client, cust, oid, "VNPAY")
        body, sig = _signed(p["gateway_txn_id"], _code(oid), int(order["deposit_amount"]))
        token = cust["Authorization"]

        def webhook(_):
            with TestClient(app) as c:
                return c.post(f"{API}/webhooks/payments/VNPAY", content=body, headers={"X-Signature": sig}).status_code

        def cancel(_):
            with TestClient(app, raise_server_exceptions=False) as c:
                return c.post(f"{API}/orders/{oid}/cancel", headers={"Authorization": token}, json={"reason": "x"}).status_code

        with ThreadPoolExecutor(2) as pool:
            codes = list(pool.map(lambda f: f(0), [webhook, cancel]))
        assert 500 not in codes, codes
        status = _sql("select order_status::text from orders where id=:o", o=oid)
        paid = _sql("select status::text from payments where id=:p", p=p["id"]) == "SUCCESS"
        assert not (status == "CANCELLED" and paid and _sql(
            "select coalesce(gateway_payload->>'needs_refund','no') from payments where id=:p", p=p["id"]) == "no")
