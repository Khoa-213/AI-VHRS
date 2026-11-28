"""Audit 2026-11-27, D08 (owner chose the full version): ways out for an order stuck after production (migration 0034).

* the delivery failed: the Staff in charge switch the order to collection at the workshop
* a Manager closes an order that will not complete, with a reason and the amount to give back
* the background job reminds the customer of the balance and tells the Managers about orders that wait too long
"""
from decimal import Decimal

from app.services import background_jobs
from tests.conftest import auth
from tests.test_api_delivery_final import ADDRESS, O, W, _final, _final_stage, _money, _pickup, _put, _rows
from tests.test_api_orders import API, _sql
from tests.test_api_photos_acceptance import _ost
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_shipments import _create, _event, _ready, carriers_on  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"


def _notes(account_id: int, order_id: int) -> list[str]:
    from sqlalchemy import text
    from app.db.session import get_engine
    with get_engine().connect() as c:
        return [r[0] for r in c.execute(text("select title from notifications where account_id=:a and order_id=:o and "
                                             "channel='IN_APP' order by id"), {"a": account_id, "o": order_id})]


def _back_date(oid: int, status: str, days: int) -> None:
    _sql("update status_histories set created_at = now() - make_interval(days => :d) where order_id=:o and to_status=:s returning 1",
         d=days, o=oid, s=status)


# ---------------------------------------------------------------------------------------------- failed delivery -> collection
def test_a_failed_delivery_can_become_a_collection_at_the_workshop(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    ship = _create(client, staff, oid)
    url = f"{W}/orders/{oid}/shipment/to-pickup"
    _event(client, staff, ship["id"], "PICKED_UP")
    early = client.post(url, headers=staff[0], json={"reason": "Khách muốn tự đến lấy"})
    assert early.status_code == 409 and _err(early) == "SHIPMENT_NOT_FAILED"            # the parcel is still on its way
    _event(client, staff, ship["id"], "FAILED", reason="Khách không nghe máy")
    assert _ost(oid) == "DELIVERING"

    assert client.post(url, headers=staff[0], json={"reason": "x"}).status_code == 422
    other = _user(client, "STAFF")
    assert client.post(url, headers=other[0], json={"reason": "Không phải đơn của tôi"}).status_code == 404
    assert client.post(url, headers=mgr, json={"reason": "Quản lý chuyển giúp"}).status_code == 403   # a Staff write, as the others

    r = client.post(url, headers=staff[0], json={"reason": "Hãng báo giao 3 lần không được, khách hẹn tự đến lấy"})
    assert r.status_code == 200 and r.json()["order_status"] == "READY_TO_DELIVER", r.text
    assert _sql("select delivery_method::text from orders where id=:o", o=oid) == "PICKUP"
    customer_id = _sql("select customer_id from orders where id=:o", o=oid)
    assert any("nhận hàng tại xưởng" in n for n in _notes(customer_id, oid))
    assert _sql("select count(*) from audit_logs where action='DELIVERY_TO_PICKUP' and entity_id=:o", o=oid) == 1

    wrong = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0999999999"})
    assert wrong.status_code == 422 and _err(wrong) == "PICKUP_PHONE_MISMATCH"          # still checked against the receiver's phone
    done = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": ADDRESS["phone"]})
    assert done.status_code == 200 and _ost(oid) == "COMPLETED", done.text


# ---------------------------------------------------------------------------------------------- a Manager closes it
def test_a_manager_closes_an_order_whose_balance_is_never_paid_and_gives_back_what_they_decide(
        client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    total, deposit = _money(oid)
    _put(client, cust, oid, _pickup())
    opened = _final(client, cust, oid).json()                               # a payment link is open when the order is closed
    url = f"{M}/orders/{oid}/close"
    # what the Manager's screen reads first: it may be closed, and this much could be given back
    assert client.get(f"{url}-preview", headers=staff[0]).status_code == 403
    pre = client.get(f"{url}-preview", headers=mgr).json()
    assert pre["allowed"] is True and pre["error_code"] is None and Decimal(pre["refundable"]) == deposit
    assert pre["order_status"] == "AWAITING_FINAL_PAYMENT"
    assert client.post(url, headers=staff[0], json={"reason": "Staff muốn đóng đơn này"}).status_code == 403
    assert client.post(url, headers=mgr, json={"reason": "ngắn"}).status_code == 422
    too_much = client.post(url, headers=mgr, json={"reason": "Khách không trả phần còn lại", "refund_amount": int(deposit) + 1})
    assert too_much.status_code == 422 and _err(too_much) == "REFUND_AMOUNT_INVALID"
    assert Decimal(too_much.json()["error"]["details"]["refundable"]) == deposit

    half = int(deposit) // 2
    r = client.post(url, headers=mgr, json={"reason": "Khách không trả phần còn lại sau nhiều lần nhắc", "refund_amount": half})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["order_status"] == "CANCELLED" and Decimal(out["refundable_before"]) == deposit and Decimal(out["refund_amount"]) == half
    assert _ost(oid) == "CANCELLED" and _sql("select production_status::text from orders where id=:o", o=oid) == "FINISHED"
    assert all(p["s"] == "CANCELLED" for p in _rows(oid) if p["t"] in ("FINAL", "SHIPPING"))           # the open link is dead
    late = client.post(f"{API}/payments/{opened['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert late.status_code == 200 and late.json()["result"] == "IGNORED" and _ost(oid) == "CANCELLED"   # it does not reopen the order
    assert _sql("select gateway_payload->>'needs_refund' from payments where id=:p", p=opened["payments"][0]["id"]) == "true"   # and is flagged
    refund = [p for p in _rows(oid, "REFUND")]
    assert len(refund) == 1 and Decimal(refund[0]["a"]) == half and refund[0]["s"] == "PENDING"
    listed = client.get(f"{W}/refunds", headers=staff[0]).json()["refunds"]
    assert any(x["order_id"] == oid for x in listed)                                                 # the Staff see it to pay out
    assert _sql("select count(*) from audit_logs where action='ORDER_CLOSE' and entity_id=:o", o=oid) == 1
    again = client.post(url, headers=mgr, json={"reason": "Bấm lần nữa cho chắc chắn"})
    assert again.status_code == 409 and _err(again) == "ORDER_CLOSE_UNSUPPORTED"
    after = client.get(f"{url}-preview", headers=mgr).json()                  # closed: nothing more to do, the rest is still owed back
    assert after["allowed"] is False and after["error_code"] == "ORDER_CLOSE_UNSUPPORTED"
    assert Decimal(after["refundable"]) == deposit - half


def test_closing_is_only_for_orders_stuck_after_production_and_never_while_a_parcel_travels(
        client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    from tests.test_api_payments import _paid
    paid, _, _ = _paid(client, cust, staff[0], wcat)                        # CONFIRMED: the refund policy of BR-14 applies instead
    r = client.post(f"{M}/orders/{paid}/close", headers=mgr, json={"reason": "Đơn này mới cọc xong"})
    assert r.status_code == 409 and _err(r) == "ORDER_CLOSE_UNSUPPORTED"
    assert client.post(f"{M}/orders/999999999/close", headers=mgr, json={"reason": "Đơn không tồn tại"}).status_code == 404

    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    ship = _create(client, staff, oid)
    _event(client, staff, ship["id"], "PICKED_UP")
    moving = client.post(f"{M}/orders/{oid}/close", headers=mgr, json={"reason": "Muốn đóng khi hàng đang đi"})
    assert moving.status_code == 409 and _err(moving) == "SHIPMENT_IN_TRANSIT"
    pre = client.get(f"{M}/orders/{oid}/close-preview", headers=mgr).json()
    assert pre["allowed"] is False and pre["error_code"] == "SHIPMENT_IN_TRANSIT" and pre["message"]
    assert client.get(f"{M}/orders/999999999/close-preview", headers=mgr).status_code == 404
    _event(client, staff, ship["id"], "RETURNED", reason="Sai địa chỉ")
    ok = client.post(f"{M}/orders/{oid}/close", headers=mgr, json={"reason": "Hàng hoàn, khách không liên lạc được", "refund_amount": 0})
    assert ok.status_code == 200 and ok.json()["refund_id"] is None and _ost(oid) == "CANCELLED"


# ---------------------------------------------------------------------------------------------- the background job
def test_the_job_reminds_the_customer_then_tells_the_managers_once_each(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    customer_id = _sql("select customer_id from orders where id=:o", o=oid)
    manager_id = client.get(f"{API}/me", headers=mgr).json()["id"]
    run = lambda: background_jobs.run_all(only=["stuck_orders"], order_ids=[oid])["results"]["stuck_orders"]   # noqa: E731

    assert run() == {"balance_reminded": 0, "balance_overdue": 0, "pickup_overdue": 0}      # it has only just started waiting
    _back_date(oid, "AWAITING_FINAL_PAYMENT", 4)
    assert run()["balance_reminded"] == 1 and any("Nhắc thanh toán" in n for n in _notes(customer_id, oid))
    assert run() == {"balance_reminded": 0, "balance_overdue": 0, "pickup_overdue": 0}      # once
    _back_date(oid, "AWAITING_FINAL_PAYMENT", 8)
    assert run()["balance_overdue"] == 1 and any("chờ thanh toán cuối quá lâu" in n for n in _notes(manager_id, oid))
    assert run()["balance_overdue"] == 0

    # paid for collection, then never collected
    _put(client, cust, oid, _pickup())
    pay = _final(client, cust, oid).json()
    assert client.post(f"{API}/payments/{pay['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    assert _ost(oid) == "READY_TO_DELIVER" and run()["pickup_overdue"] == 0
    _back_date(oid, "READY_TO_DELIVER", 9)
    assert run()["pickup_overdue"] == 1 and any("chưa được nhận tại xưởng" in n for n in _notes(manager_id, oid))
    assert run()["pickup_overdue"] == 0


def test_the_new_transitions_are_the_only_ones_the_database_gained():
    """The guard still refuses what it refused before; only the three exits of migration 0034 were added."""
    body = _sql("select pg_get_functiondef('fn_order_state_guard()'::regprocedure)")
    assert "WHEN 'AWAITING_FINAL_PAYMENT' THEN NEW.order_status IN ('READY_TO_DELIVER','CANCELLED')" in body
    assert "WHEN 'READY_TO_DELIVER'       THEN NEW.order_status IN ('DELIVERING','COMPLETED','CANCELLED')" in body
    assert "WHEN 'DELIVERING'             THEN NEW.order_status IN ('COMPLETED','READY_TO_DELIVER','CANCELLED')" in body
    assert "WHEN 'CONFIRMED'              THEN NEW.order_status IN ('AWAITING_ACCEPTANCE','CANCELLED')" in body
    assert "WHEN 'AWAITING_ACCEPTANCE'    THEN NEW.order_status IN ('AWAITING_FINAL_PAYMENT','CONFIRMED')" in body
