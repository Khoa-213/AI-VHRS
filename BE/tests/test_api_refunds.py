"""Phase 4d-1: cancelling after the deposit and refunds (FR-19, FR-20, UC-21, UC-28; BR-14, BR-16).

Production steps that belong to the technician (PREPARING, WRITING, PAUSED) and ETA postponements are put in place with valid
SQL UPDATEs, as the other Phase 3/4 tests do (AI_PLAYBOOK S07): the subject here is the cancellation and the refund.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _deposit, _paid
from tests.test_api_scheduling import _at, _prod, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import (W, _err, _order_status, _user, cust, manager, policy, staff, store,  # noqa: F401
                                     wcat)

ACCOUNT = {"bank_name": "Vietcombank", "account_number": "0123456789", "account_name": "NGUYEN VAN A"}


def _deposit_amount(oid) -> Decimal:
    return Decimal(_sql("select amount from payments where order_id=:o and type='DEPOSIT' and status='SUCCESS'", o=oid))


def _setup_fee(oid) -> Decimal:
    return Decimal(_sql("""select price_snapshot->'pricing_config'->>'setup_fee' from quotations
                           where order_id=:o and status='APPROVED' order by version desc limit 1""", o=oid))


def _refunds(oid) -> list[dict]:
    from app.db.session import get_engine
    from sqlalchemy import text
    with get_engine().begin() as c:
        rows = c.execute(text("""select id, amount, status::text as status, refund_of_id, gateway_payload
                                 from payments where order_id=:o and type='REFUND' order by id"""), {"o": oid})
        return [dict(r._mapping) for r in rows]


def _preview(client, h, oid, workshop=False):
    url = f"{W}/orders/{oid}/cancel-preview" if workshop else f"{API}/orders/{oid}/cancel-preview"
    r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _cancel(client, cust, oid, **body):
    return client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Khách đổi ý", **body})


def _scheduled(client, cust, staff, wcat, mgr, robot, tech):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    r = _sched(client, mgr, oid, robot, tech[1], _at(2))
    assert r.status_code == 201, r.text
    return oid, r.json()["id"]


def _set_prod(oid, job_id, status, **job_cols):
    extra = "".join(f", {k}={v}" for k, v in job_cols.items())
    _sql(f"update production_jobs set status=cast(:s as job_status){extra} where id=:j returning 1", s=status, j=job_id)
    _sql("update orders set production_status=cast(:s as production_status) where id=:o returning 1", s=status, o=oid)


def _postpone(oid, days):
    """Give the order an ETA (no reason needed the first time), then move it `days` later with a reason (BR-16 trigger)."""
    _sql("update orders set eta = coalesce(eta, current_date + 5) where id=:o returning 1", o=oid)
    _sql("""update orders set eta = eta + cast(:d as int)
            where id=:o and set_config('app.status_reason', 'pytest: robot hỏng', true) is not null returning 1""",
         o=oid, d=days)


# ---- customer: BR-14 / BR-16 -------------------------------------------------------------------------
def test_unpaid_orders_preview_as_free(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    p = _preview(client, cust, oid)
    assert (p["allowed"], p["rule"], Decimal(p["refund_amount"])) == (True, "NO_PAYMENT", 0)


def test_before_scheduling_the_whole_deposit_is_refunded(client, cust, staff, wcat):
    oid, q, pay = _paid(client, cust, staff[0], wcat)
    deposit = _deposit_amount(oid)
    p = _preview(client, cust, oid)
    assert (p["allowed"], p["rule"], Decimal(p["refund_amount"]), Decimal(p["paid"])) == (
        True, "BR14_BEFORE_SCHEDULE", deposit, deposit)
    assert p["account_required"] is False
    r = _cancel(client, cust, oid)
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED", r.text
    assert _prod(oid) == "NOT_STARTED"
    [ref] = _refunds(oid)
    assert (Decimal(ref["amount"]), ref["status"], ref["refund_of_id"]) == (deposit, "PENDING", pay["id"])
    assert ref["gateway_payload"]["rule"] == "BR14_BEFORE_SCHEDULE"
    rows = client.get(f"{API}/orders/{oid}/payments", headers=cust).json()
    refund = next(x for x in rows if x["type"] == "REFUND")
    assert refund["refund"]["kind"] == "CANCELLATION" and refund["refund"]["refund_of_id"] == pay["id"]
    assert _sql("select count(*) from audit_logs where action='ORDER_CANCEL' and entity_id=:o", o=oid) == 1
    again = _cancel(client, cust, oid)
    assert again.status_code == 409 and len(_refunds(oid)) == 1


def test_after_scheduling_the_setup_fee_is_kept_and_the_job_is_cancelled(client, cust, staff, wcat, mgr, robot, tech):
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    cmd = str(uuid.uuid4())
    _sql("""insert into robot_commands (id, robot_id, job_id, kind, created_by, expires_at)
            values (cast(:i as uuid), :r, :j, 'LOAD', :t, now() + interval '5 minutes') returning 1""",
         i=cmd, r=robot, j=job, t=tech[1])
    deposit, setup = _deposit_amount(oid), _setup_fee(oid)
    p = _preview(client, cust, oid)
    assert (p["rule"], Decimal(p["refund_amount"]), Decimal(p["deduction"])) == (
        "BR14_AFTER_SCHEDULE", deposit - min(setup, deposit), min(setup, deposit))
    assert _cancel(client, cust, oid).status_code == 200
    assert _sql("select status::text from production_jobs where id=:j", j=job) == "CANCELLED"
    assert _sql("select status from robot_commands where id=cast(:i as uuid)", i=cmd) == "EXPIRED"
    refunds = _refunds(oid)
    assert [Decimal(r["amount"]) for r in refunds] == ([deposit - setup] if deposit > setup else [])
    # the technician can no longer touch the job
    r = client.post(f"{API}/technician/jobs/{job}/prepare", headers=tech[0])
    assert r.status_code == 409


def test_preparing_still_counts_as_not_written(client, cust, staff, wcat, mgr, robot, tech):
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    _set_prod(oid, job, "PREPARING")
    assert _preview(client, cust, oid)["rule"] == "BR14_AFTER_SCHEDULE"
    assert _cancel(client, cust, oid).status_code == 200
    assert _sql("select status::text from production_jobs where id=:j", j=job) == "CANCELLED"


def test_once_writing_started_only_br16_opens_the_cancel(client, cust, staff, wcat, mgr, robot, tech):
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    _set_prod(oid, job, "PREPARING")
    _set_prod(oid, job, "WRITING", simulation_passed="true", started_at="now()")
    p = _preview(client, cust, oid)
    assert (p["allowed"], p["error_code"]) == (False, "JOB_RUNNING")
    r = _cancel(client, cust, oid)
    assert r.status_code == 409 and _err(r) == "JOB_RUNNING"
    _set_prod(oid, job, "PAUSED")
    r = _cancel(client, cust, oid)
    assert r.status_code == 409 and _err(r) == "CANCEL_AFTER_WRITING_STARTED"
    _postpone(oid, 7)
    assert _preview(client, cust, oid)["error_code"] == "CANCEL_AFTER_WRITING_STARTED"     # exactly 7 days: not yet
    _postpone(oid, 1)
    p = _preview(client, cust, oid)
    assert (p["rule"], p["eta_postponed_days"], Decimal(p["refund_amount"])) == ("BR16_ETA_POSTPONED", 8, _deposit_amount(oid))
    assert _cancel(client, cust, oid).status_code == 200
    assert _sql("select status::text from production_jobs where id=:j", j=job) == "CANCELLED"
    assert Decimal(_refunds(oid)[0]["amount"]) == _deposit_amount(oid)


def test_a_job_that_already_started_writing_blocks_a_cheap_cancel_later(client, cust, staff, wcat, mgr, robot, tech):
    """A rewrite puts the order back in the queue, but the sheet was written once already."""
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    _sql("update production_jobs set started_at = now() where id=:j returning 1", j=job)
    r = _cancel(client, cust, oid)
    assert r.status_code == 409 and _err(r) == "CANCEL_AFTER_WRITING_STARTED"


def test_the_br16_threshold_comes_from_system_settings(client, cust, staff, wcat, mgr, robot, tech):
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    _set_prod(oid, job, "PREPARING")
    _set_prod(oid, job, "WRITING", simulation_passed="true", started_at="now()")
    _set_prod(oid, job, "PAUSED")
    _postpone(oid, 4)
    old = _sql("select value::text from system_settings where key='eta_cancel_threshold_days'")
    try:
        _sql("update system_settings set value='3'::jsonb where key='eta_cancel_threshold_days' returning 1")
        assert _preview(client, cust, oid)["rule"] == "BR16_ETA_POSTPONED"
        assert _cancel(client, cust, oid).status_code == 200            # the trigger reads the same setting (migration 0014)
    finally:
        _sql("update system_settings set value=cast(:v as jsonb) where key='eta_cancel_threshold_days' returning 1", v=old)


def test_a_payos_deposit_needs_an_account_and_the_customer_sees_it_masked(client, cust, staff, wcat):
    oid, q, pay = _paid(client, cust, staff[0], wcat)
    _sql("update payments set gateway='PAYOS' where id=:p returning 1", p=pay["id"])
    assert _preview(client, cust, oid)["account_required"] is True
    r = _cancel(client, cust, oid)
    assert r.status_code == 422 and _err(r) == "REFUND_ACCOUNT_REQUIRED" and _order_status(oid) == "CONFIRMED"
    bad = _cancel(client, cust, oid, refund_account={**ACCOUNT, "account_number": "12ab"})
    assert bad.status_code == 422
    assert _cancel(client, cust, oid, refund_account=ACCOUNT).status_code == 200
    refund = next(x for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json() if x["type"] == "REFUND")
    assert refund["gateway"] == "PAYOS" and refund["refund"]["account"]["account_number"] == "••••••6789"
    listed = client.get(f"{W}/refunds", headers=staff[0]).json()["refunds"]
    assert next(x for x in listed if x["order_id"] == oid)["refund"]["account"]["account_number"] == "0123456789"


# ---- workshop cancel, refund list, confirmation ----------------------------------------------------------
def test_the_workshop_cancels_with_a_full_refund_and_confirms_the_transfer(client, cust, staff, manager, wcat, mgr, robot,
                                                                          tech):
    oid, job = _scheduled(client, cust, staff, wcat, mgr, robot, tech)
    deposit = _deposit_amount(oid)
    other = _user(client, "STAFF")
    assert _preview(client, staff[0], oid, workshop=True)["rule"] == "WORKSHOP_CANCEL"
    assert _preview(client, manager[0], oid, workshop=True)["allowed"] is True
    url = f"{W}/orders/{oid}/cancel"
    assert client.post(url, headers=manager[0], json={"reason": "x"}).status_code == 403
    assert client.post(url, headers=cust, json={"reason": "x"}).status_code == 403
    assert client.post(url, headers=other[0], json={"reason": "x"}).status_code == 404
    assert client.post(url, headers=staff[0], json={"reason": ""}).status_code == 422
    r = client.post(url, headers=staff[0], json={"reason": "Hết loại giấy khách chọn"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED", r.text
    [ref] = _refunds(oid)
    assert Decimal(ref["amount"]) == deposit and ref["gateway_payload"]["rule"] == "WORKSHOP_CANCEL"

    listed = client.get(f"{W}/refunds", headers=staff[0]).json()
    assert any(x["id"] == ref["id"] for x in listed["refunds"])
    assert any(x["id"] == ref["id"] for x in client.get(f"{W}/refunds", headers=manager[0]).json()["refunds"])
    assert not any(x["id"] == ref["id"] for x in client.get(f"{W}/refunds", headers=other[0]).json()["refunds"])

    acc = client.put(f"{API}/orders/{oid}/refunds/{ref['id']}/account", headers=cust, json=ACCOUNT)
    assert acc.status_code == 200 and acc.json()["refund"]["account"]["account_number"] == "••••••6789"
    confirm = f"{W}/refunds/{ref['id']}/confirm"
    assert client.post(confirm, headers=manager[0], json={"reference": "FT123"}).status_code == 403
    assert client.post(confirm, headers=other[0], json={"reference": "FT123"}).status_code == 404
    ok = client.post(confirm, headers=staff[0], json={"reference": "FT26110400123", "note": "chuyển khoản VCB"})
    assert ok.status_code == 200 and ok.json()["status"] == "SUCCESS", ok.text
    assert ok.json()["refund"]["reference"] == "FT26110400123" and ok.json()["refund"]["confirmed_at"]
    assert _sql("select confirmed_by from payments where id=:p", p=ref["id"]) == staff[1]
    twice = client.post(confirm, headers=staff[0], json={"reference": "FT2"})
    assert twice.status_code == 409 and _err(twice) == "REFUND_NOT_PENDING"
    late = client.put(f"{API}/orders/{oid}/refunds/{ref['id']}/account", headers=cust, json=ACCOUNT)
    assert late.status_code == 409
    done = client.get(f"{W}/refunds?status=SUCCESS", headers=staff[0]).json()["refunds"]
    assert any(x["id"] == ref["id"] for x in done)


def test_the_workshop_cannot_cancel_an_unpaid_order_or_someone_elses_refund(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    r = client.post(f"{W}/orders/{oid}/cancel", headers=staff[0], json={"reason": "x"})
    assert r.status_code == 409 and _err(r) == "ORDER_CANCEL_UNSUPPORTED"
    other_cust = _user(client, "CUSTOMER")[0]
    assert client.get(f"{API}/orders/{oid}/cancel-preview", headers=other_cust).status_code == 404
    assert client.put(f"{API}/orders/{oid}/refunds/999999999/account", headers=cust, json=ACCOUNT).status_code == 404
    assert client.post(f"{W}/refunds/999999999/confirm", headers=staff[0], json={"reference": "x"}).status_code == 404


# ---- money flagged needs_refund ----------------------------------------------------------------------
def test_orphan_money_gets_its_own_refund_once(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    _sql("update orders set order_status='CANCELLED', cancel_reason='huỷ bởi xưởng' where id=:o returning 1", o=oid)
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.json()["needs_refund"] is True
    orphans = client.get(f"{W}/refunds", headers=staff[0]).json()["orphans"]
    item = next(x for x in orphans if x["payment_id"] == p["id"])
    assert item["received_amount"] == int(Decimal(p["amount"])) and item["types"] == ["DEPOSIT"]
    url = f"{W}/payments/{p['id']}/refund"
    too_much = client.post(url, headers=staff[0], json={"reason": "tiền về muộn", "amount": item["received_amount"] + 1})
    assert too_much.status_code == 422 and _err(too_much) == "INVALID_REFUND_AMOUNT"
    ok = client.post(url, headers=staff[0], json={"reason": "tiền về muộn"})
    assert ok.status_code == 201 and ok.json()["refund"]["kind"] == "ORPHAN", ok.text
    assert Decimal(ok.json()["amount"]) == Decimal(p["amount"])
    again = client.post(url, headers=staff[0], json={"reason": "lần hai"})
    assert again.status_code == 409 and _err(again) == "REFUND_EXISTS"
    assert not any(x["payment_id"] == p["id"] for x in client.get(f"{W}/refunds", headers=staff[0]).json()["orphans"])
    plain = client.post(f"{W}/payments/{p['id']}/refund", headers=_user(client, "STAFF")[0], json={"reason": "x"})
    assert plain.status_code == 404


def test_only_flagged_payments_can_be_refunded_as_orphans(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    r = client.post(f"{W}/payments/{p['id']}/refund", headers=staff[0], json={"reason": "x"})
    assert r.status_code == 409 and _err(r) == "NOT_REFUNDABLE"


# ---- concurrency -------------------------------------------------------------------------------------
def test_two_cancels_at_once_open_a_single_refund(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    clients = [TestClient(app) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda c: _cancel(c, cust, oid).status_code, clients))
    assert codes == [200, 409] and len(_refunds(oid)) == 1


def test_two_confirmations_at_once_confirm_once(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    assert _cancel(client, cust, oid).status_code == 200
    rid = _refunds(oid)[0]["id"]
    clients = [TestClient(app) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda c: c.post(f"{W}/refunds/{rid}/confirm", headers=staff[0],
                                                 json={"reference": "FT1"}).status_code, clients))
    assert codes == [200, 409]
    assert _sql("select count(*) from audit_logs where action='REFUND_CONFIRM' and entity_id=:p", p=rid) == 1


def test_the_database_refuses_a_second_live_refund_for_the_same_payment(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    assert _cancel(client, cust, oid).status_code == 200
    with pytest.raises(Exception, match="ux_payments_active_refund"):
        _sql("""insert into payments (order_id, type, amount, gateway, status, refund_of_id, gateway_payload)
                values (:o, 'REFUND', 1000, 'VNPAY', 'PENDING', :p, '{"refund_kind": "CANCELLATION"}') returning id""",
             o=oid, p=p["id"])
