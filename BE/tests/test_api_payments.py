"""Phase 3, customer side: approving the quotation, the (MOCK) deposit, the signed idempotent webhook, cancelling.

Runs on the real database with the in-memory storage double. The Pricing Engine, PDF renderer, AI sketch
pipelines, HMAC check and the DB triggers are real; no real money moves (the only gateway is the MOCK adapter).
"""
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.integrations.payment_gateway import MockGateway, webhook_body
from app.main import app
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import (W, _accepted, _err, _order_status, _sent, _user, cust, manager,  # noqa: F401
                                     policy, staff, store, wcat)

GW = MockGateway()


# ---- helpers ----------------------------------------------------------------------------------------
def _quoted(client, cust, staff_h, wcat, **kw):
    """Order with a SENT quotation and the privacy policy accepted: the customer can now approve."""
    oid, q = _sent(client, cust, staff_h, wcat, **kw)
    r = client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    assert r.status_code == 200 and r.json()["order_status"] == "QUOTED", r.text
    return oid, q


def _approved(client, cust, staff_h, wcat, deposit_pct=None, **kw):
    oid, q = _quoted(client, cust, staff_h, wcat, **kw)
    body = {} if deposit_pct is None else {"deposit_pct": deposit_pct}
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json=body)
    assert r.status_code == 200, r.text
    return oid, q, r.json()


def _deposit(client, cust, oid, gateway="VNPAY"):
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": gateway})
    assert r.status_code == 201, r.text
    return r.json()


def _signed(txn_id, code, amount, result="SUCCESS"):
    body = webhook_body(txn_id=txn_id, order_code=code, amount=amount, result=result, paid_at=None)
    return body, GW.sign(body)


def _hook(client, gateway, body, sig):
    headers = {"X-Signature": sig} if sig is not None else {}
    return client.post(f"{API}/webhooks/payments/{gateway}", content=body, headers=headers)


def _code(oid):
    return _sql("select code from orders where id=:o", o=oid)


def _paid(client, cust, staff_h, wcat, **kw):
    oid, q, _ = _approved(client, cust, staff_h, wcat, **kw)
    p = _deposit(client, cust, oid)
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200 and r.json()["order_status"] == "CONFIRMED", r.text
    return oid, q, p


# ---- approving the quotation ------------------------------------------------------------------------
def test_approve_defaults_to_the_minimum_deposit_and_records_everything(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat, text_="Chúc mừng năm mới", qty=2)
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert r.status_code == 200, r.text
    d = r.json()
    total = Decimal(str(q["final_total"]))
    assert d["order_status"] == "AWAITING_DEPOSIT" and Decimal(d["total_amount"]) == total
    assert Decimal(d["deposit_pct"]) == Decimal(str(q["min_deposit_pct"]))
    assert Decimal(d["deposit_amount"]) == Decimal(str(q["options"][0]["min_deposit"]))
    assert _sql("select status::text from quotations where id=:q", q=q["id"]) == "APPROVED"
    assert _sql("select chosen_option from quotations where id=:q", q=q["id"]) == 1
    assert _sql("select customer_responded_at is not null from quotations where id=:q", q=q["id"])
    assert _sql("select count(*) from audit_logs where action='QUOTATION_APPROVE' and entity_id=:q", q=q["id"]) == 1
    assert _sql("""select count(*) from status_histories where order_id=:o and from_status='QUOTED'
                   and to_status='AWAITING_DEPOSIT' and actor_id is not null""", o=oid) == 1
    shown = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert shown["total_amount"] == d["total_amount"] and shown["deposit_amount"] == d["deposit_amount"]


def test_approve_with_a_higher_deposit_and_validation(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    mn = Decimal(str(q["min_deposit_pct"]))
    too_low = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"deposit_pct": float(mn) - 1})
    assert too_low.status_code == 422 and _err(too_low) == "INVALID_DEPOSIT"
    assert too_low.json()["error"]["details"]["min_deposit_pct"]
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"deposit_pct": 100.5}).status_code == 422
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"deposit_pct": 0}).status_code == 422
    assert _order_status(oid) == "QUOTED"                                          # nothing changed by the failures
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"deposit_pct": 100})
    d = r.json()
    assert r.status_code == 200 and Decimal(d["deposit_amount"]) == Decimal(d["total_amount"])


def test_approve_twice_and_wrong_actor(client, cust, staff, manager, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    other = auth(client, "CUSTOMER")
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=other, json={}).status_code == 404
    for h in (staff[0], manager[0], auth(client, "ADMIN"), auth(client, "TECHNICAL_STAFF")):
        assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=h, json={}).status_code == 403
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers={}, json={}).status_code == 401
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    again = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert again.status_code == 409 and _err(again) == "QUOTATION_NOT_OPEN"


def test_cannot_approve_before_privacy_or_an_expired_quote(client, cust, staff, wcat):
    oid, q = _sent(client, cust, staff[0], wcat)                                  # AWAITING_PRIVACY
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert r.status_code == 409 and _err(r) == "QUOTATION_NOT_OPEN"
    client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    _sql("""update quotations set sent_at = now() - interval '9 days', valid_until = now() - interval '2 days'
            where id=:q returning 1""", q=q["id"])
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert r.status_code == 409
    assert _order_status(oid) == "CANCELLED" and _sql("select status::text from quotations where id=:q", q=q["id"]) == "EXPIRED"


def test_multi_option_quote_requires_a_choice_and_applies_the_materials(client, cust, staff, wcat):
    sh = staff[0]
    oid = _accepted(client, cust, sh, wcat, suggest=True)
    v = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"paper_size": "A5"}).json()["version"]
    client.post(f"{W}/orders/{oid}/sketches/{v}/finalize", headers=sh)
    opts = [{"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]},
            {"paper_type_id": wcat["paper"], "pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": opts, "complexity": "MEDIUM"}).json()
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 200
    client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert r.status_code == 422 and _err(r) == "OPTION_REQUIRED"
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"option": 3})
    assert r.status_code == 422 and _err(r) == "INVALID_OPTION"
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"option": 2})
    d = r.json()
    assert r.status_code == 200, r.text
    assert d["pen_type_id"] == wcat["fountain"] and d["ink_color_id"] == wcat["fountain_ink"]
    assert d["workshop_suggest_materials"] is False
    assert Decimal(d["total_amount"]) == Decimal(str(q["options"][1]["total"]))
    assert _sql("select chosen_option from quotations where id=:q", q=q["id"]) == 2


# ---- starting the deposit ----------------------------------------------------------------------------
def test_deposit_needs_an_approved_quote_and_belongs_to_the_owner(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={})
    assert r.status_code == 409 and _err(r) == "DEPOSIT_NOT_EXPECTED"
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    other = auth(client, "CUSTOMER")
    assert client.post(f"{API}/orders/{oid}/payments/deposit", headers=other, json={}).status_code == 404
    assert client.get(f"{API}/orders/{oid}/payments", headers=other).status_code == 404
    assert client.post(f"{API}/orders/{oid}/payments/deposit", headers=staff[0], json={}).status_code == 403
    assert client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "PAYPAL"}).status_code == 422


def test_start_deposit_creates_a_mock_pending_payment_and_is_reusable(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    assert p["status"] == "PENDING" and p["type"] == "DEPOSIT" and p["mode"] == "MOCK"
    assert Decimal(p["amount"]) == Decimal(order["deposit_amount"]) and Decimal(p["deposit_pct"]) == Decimal(order["deposit_pct"])
    assert p["gateway_txn_id"].startswith("MOCK-VNPAY-") and p["checkout_path"].endswith(f"/payments/{p['id']}/mock-checkout")
    assert _deposit(client, cust, oid)["id"] == p["id"]                          # same intent: same open transaction
    p2 = _deposit(client, cust, oid, "MOMO")                                      # other gateway: old one is cancelled
    assert p2["id"] != p["id"] and p2["gateway"] == "MOMO"
    listed = {x["id"]: x["status"] for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()}
    assert listed == {p["id"]: "CANCELLED", p2["id"]: "PENDING"}
    assert _sql("select count(*) from audit_logs where action='PAYMENT_START' and entity_id=any(:i)", i=[p["id"], p2["id"]]) == 2


# ---- paying (mock gateway -> signed webhook) ---------------------------------------------------------
def test_successful_deposit_confirms_the_order_and_queues_production(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    assert _order_status(oid) == "CONFIRMED"
    assert _sql("select production_status::text from orders where id=:o", o=oid) == "PENDING_SCHEDULE"
    assert _sql("select confirmed_at is not null from orders where id=:o", o=oid)
    pay = client.get(f"{API}/orders/{oid}/payments", headers=cust).json()[0]
    assert pay["status"] == "SUCCESS" and pay["paid_at"] and pay["checkout_path"] is None and pay["mode"] == "MOCK"
    assert _sql("select gateway_payload->>'mode' from payments where id=:p", p=p["id"]) == "MOCK"
    assert _sql("select gateway_payload->'webhook'->>'result' from payments where id=:p", p=p["id"]) == "SUCCESS"
    assert _sql("""select count(*) from status_histories where order_id=:o and state_type='ORDER'
                   and from_status='AWAITING_DEPOSIT' and to_status='CONFIRMED' and actor_id is null""", o=oid) == 1
    assert _sql("""select count(*) from status_histories where order_id=:o and state_type='PRODUCTION'
                   and to_status='PENDING_SCHEDULE'""", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='PAYMENT_SUCCESS' and entity_id=:p", p=p["id"]) == 1
    # already paid: no second deposit
    again = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={})
    assert again.status_code == 409 and _err(again) == "DEPOSIT_NOT_EXPECTED"


def test_repeating_the_same_webhook_changes_nothing(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    body, sig = _signed(p["gateway_txn_id"], _code(oid), int(Decimal(p["amount"])))
    r1, r2 = _hook(client, "VNPAY", body, sig), _hook(client, "VNPAY", body, sig)
    for r in (r1, r2):
        assert r.status_code == 200 and r.json() == {"result": "ALREADY_PROCESSED", "status": "SUCCESS",
                                                     "order_status": None, "needs_refund": None}
    assert _sql("select count(*) from payments where order_id=:o and status='SUCCESS'", o=oid) == 1
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
    redo = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "FAILED"})
    assert redo.json()["result"] == "ALREADY_PROCESSED" and _sql("select status::text from payments where id=:p", p=p["id"]) == "SUCCESS"


def test_failed_payment_keeps_the_order_waiting_and_can_be_retried(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "FAILED"})
    assert r.status_code == 200 and r.json()["status"] == "FAILED"
    assert _order_status(oid) == "AWAITING_DEPOSIT"
    p2 = _deposit(client, cust, oid)                                              # a failed attempt is not reused
    assert p2["id"] != p["id"] and p2["status"] == "PENDING"
    assert client.post(f"{API}/payments/{p2['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    assert _order_status(oid) == "CONFIRMED"
    assert [x["status"] for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()] == ["FAILED", "SUCCESS"]


def test_webhook_signature_and_content_are_verified(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    amount, code, txn = int(Decimal(p["amount"])), _code(oid), p["gateway_txn_id"]
    body, sig = _signed(txn, code, amount)
    for bad in (None, "", "0" * 64, sig[:-1] + ("0" if sig[-1] != "0" else "1")):
        r = _hook(client, "VNPAY", body, bad)
        assert r.status_code == 401 and _err(r) == "INVALID_SIGNATURE"
    assert _hook(client, "VNPAY", body + b" ", sig).status_code == 401               # body changed after signing
    wrong_amt = _signed(txn, code, amount - 100)                                      # validly signed, wrong amount
    r = _hook(client, "VNPAY", *wrong_amt)
    assert r.status_code == 422 and _err(r) == "PAYMENT_MISMATCH"
    r = _hook(client, "VNPAY", *_signed(txn, "VHRS-OTHER", amount))
    assert r.status_code == 422 and _err(r) == "PAYMENT_MISMATCH"
    assert _hook(client, "VNPAY", *_signed("MOCK-VNPAY-unknown", code, amount)).status_code == 404
    assert _hook(client, "MOMO", body, sig).status_code == 404                        # txn belongs to VNPAY
    assert _hook(client, "PAYPAL", body, sig).status_code == 422
    bad_json = b"not json"
    assert _hook(client, "VNPAY", bad_json, GW.sign(bad_json)).status_code == 422
    odd = json.dumps({"txn_id": txn, "order_code": code, "amount": amount, "result": "REFUNDED"}).encode()
    assert _hook(client, "VNPAY", odd, GW.sign(odd)).status_code == 422
    assert _order_status(oid) == "AWAITING_DEPOSIT"                                  # nothing above changed the order
    assert _sql("select status::text from payments where id=:p", p=p["id"]) == "PENDING"
    assert _sql("select count(*) from audit_logs where action='PAYMENT_MISMATCH' and entity_id=:p", p=p["id"]) == 2
    ok = _hook(client, "VNPAY", body, sig)                                            # the genuine one still works
    assert ok.status_code == 200 and ok.json()["order_status"] == "CONFIRMED"


def test_concurrent_identical_webhooks_confirm_the_order_exactly_once(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    body, sig = _signed(p["gateway_txn_id"], _code(oid), int(Decimal(p["amount"])))

    def fire(_):
        with TestClient(app) as c:
            return _hook(c, "VNPAY", body, sig).json()["result"]

    with ThreadPoolExecutor(4) as pool:
        results = sorted(pool.map(fire, range(4)))
    assert results == ["ALREADY_PROCESSED"] * 3 + ["PROCESSED"]
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
    assert _sql("select count(*) from payments where order_id=:o and status='SUCCESS'", o=oid) == 1


def test_mock_checkout_is_for_the_owner_only(client, cust, staff, manager, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    url = f"{API}/payments/{p['id']}/mock-checkout"
    assert client.post(url, headers=auth(client, "CUSTOMER"), json={"result": "SUCCESS"}).status_code == 404
    assert client.post(url, headers=manager[0], json={"result": "SUCCESS"}).status_code == 403
    assert client.post(url, headers={}, json={"result": "SUCCESS"}).status_code == 401
    assert client.post(url, headers=cust, json={"result": "MAYBE"}).status_code == 422
    assert client.post(f"{API}/payments/999999999/mock-checkout", headers=cust, json={}).status_code == 404
    assert _order_status(oid) == "AWAITING_DEPOSIT"


def test_real_gateway_payments_are_not_mock_checkable(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    _sql("update payments set gateway_payload = '{}'::jsonb where id=:p returning 1", p=p["id"])    # not tagged MOCK
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 409 and _err(r) == "NOT_A_MOCK_PAYMENT"


# ---- cancelling and late money -----------------------------------------------------------------------
def test_customer_can_decline_a_quoted_order(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Giá cao quá"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED"
    assert _sql("select status::text from quotations where id=:q", q=q["id"]) == "CANCELLED"
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 409


def test_cancelling_while_waiting_for_the_deposit_closes_the_open_payment(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Đổi ý"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED"
    assert _sql("select status::text from payments where id=:p", p=p["id"]) == "CANCELLED"
    late = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert late.status_code == 200 and late.json()["result"] == "IGNORED"            # cancelled intent: no state change
    assert _order_status(oid) == "CANCELLED"
    assert _sql("select count(*) from payments where order_id=:o and status='SUCCESS'", o=oid) == 0


def test_money_arriving_for_a_closed_order_is_kept_and_flagged_for_refund(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    _sql("update orders set order_status='CANCELLED', cancel_reason='huỷ bởi xưởng' where id=:o returning 1", o=oid)
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200 and r.json()["needs_refund"] is True and r.json()["order_status"] == "CANCELLED"
    assert _order_status(oid) == "CANCELLED"
    pay = client.get(f"{API}/orders/{oid}/payments", headers=cust).json()[0]
    assert pay["status"] == "SUCCESS" and pay["needs_refund"] is True
    assert _sql("select count(*) from audit_logs where action='PAYMENT_ORPHAN' and entity_id=:p", p=p["id"]) == 1


def test_cancelling_after_the_deposit_is_not_available_online(client, cust, staff, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "x"})
    assert r.status_code == 409 and _err(r) == "ORDER_CANCEL_UNSUPPORTED"            # refund policy comes with Phase 4


# ---- workshop read access ----------------------------------------------------------------------------
def test_workshop_sees_payments_and_jobs_with_record_level_access(client, cust, staff, manager, wcat):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    rows = client.get(f"{W}/orders/{oid}/payments", headers=staff[0])
    assert rows.status_code == 200 and rows.json()[0]["id"] == p["id"] and rows.json()[0]["mode"] == "MOCK"
    assert client.get(f"{W}/orders/{oid}/payments", headers=manager[0]).status_code == 200
    assert client.get(f"{W}/orders/{oid}/payments", headers=_user(client, "STAFF")[0]).status_code == 404   # other staff
    assert client.get(f"{W}/orders/{oid}/payments", headers=cust).status_code == 403
    assert client.get(f"{W}/orders/{oid}/jobs", headers=staff[0]).json() == []
    assert client.get(f"{W}/orders/{oid}/jobs", headers=_user(client, "STAFF")[0]).status_code == 404


def test_the_webhook_needs_no_login_but_is_not_open(client):
    assert client.post(f"{API}/webhooks/payments/VNPAY", content=b"{}").status_code == 401   # unsigned -> refused, not 403/404
