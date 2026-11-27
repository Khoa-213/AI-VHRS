"""Audit 2026-11-27, batch 3 (docs/audit/09_APPROVAL_AND_IMPLEMENTATION_PLAN.md): ways out and responsibility.

D04  an ACCEPTED order can be withdrawn: by the customer, and by the Staff in charge with a reason
D05  an account that still holds orders / jobs / robots is not locked or re-roled until they are reassigned (or forced, with a reason)
(D06, the robot run behind "written", is covered next to the tests it changes: tests/test_api_technician.py and tests/test_api_robot_ops.py.)
"""
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_robot_link import fresh_hub, session_key  # noqa: F401
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_technician import T, _job
from tests.test_api_workshop import (_accepted, _err, _order_status, _quoted, _sent, _user, cust, manager, policy, staff, store,  # noqa: F401
                                     wcat)

W = f"{API}/workshop"
ADMIN = f"{API}/admin"


def _notes(account_id: int, order_id: int) -> list[str]:
    from sqlalchemy import text
    from app.db.session import get_engine
    with get_engine().connect() as c:
        return [r[0] for r in c.execute(text("select type::text || ':' || title from notifications where account_id=:a and order_id=:o "
                                             "and channel='IN_APP' order by id"), {"a": account_id, "o": order_id})]


# ---------------------------------------------------------------------------------------------- D04
def test_the_customer_can_withdraw_an_accepted_order_and_the_staff_are_told(client, cust, staff, wcat):
    oid, _ = _quoted(client, cust, staff[0], wcat)                     # ACCEPTED with a quotation DRAFT in the Staff's hands
    assert _order_status(oid) == "ACCEPTED"
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Tôi đổi ý, không cần nữa"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED", r.text
    assert _sql("select count(*) from quotations where order_id=:o and status in ('DRAFT','PENDING_APPROVAL','SENT')", o=oid) == 0
    assert any("đã huỷ" in n for n in _notes(staff[1], oid))            # the Staff who were preparing it


def test_the_customer_can_withdraw_right_after_asking_for_changes(client, cust, staff, wcat):
    oid, _ = _sent(client, cust, staff[0], wcat)
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    r = client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust, json={"note": "Chữ to hơn giúp tôi"})
    assert r.status_code == 200 and _order_status(oid) == "ACCEPTED", r.text
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Chờ lâu quá"})
    assert r.status_code == 200 and _order_status(oid) == "CANCELLED", r.text


def test_the_staff_in_charge_can_close_an_accepted_order_with_a_reason(client, cust, staff, manager, wcat):
    oid, _ = _quoted(client, cust, staff[0], wcat)
    url = f"{W}/orders/{oid}/cancel"
    assert client.post(url, headers=staff[0], json={"reason": "x"}).status_code == 422                  # a real reason is required
    other = _user(client, "STAFF")
    assert client.post(url, headers=other[0], json={"reason": "Không phải đơn của tôi"}).status_code == 404   # not in charge
    assert client.post(url, headers=manager[0], json={"reason": "Quản lý muốn huỷ"}).status_code == 403    # Staff only, as every write
    assert client.post(url, headers=cust, json={"reason": "Khách gọi nhầm"}).status_code == 403

    r = client.post(url, headers=staff[0], json={"reason": "Hết loại giấy khách chọn, không nhập thêm được"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED", r.text
    assert _sql("select cancel_reason from orders where id=:o", o=oid).startswith("Hết loại giấy")
    assert _sql("select count(*) from quotations where order_id=:o and status in ('DRAFT','PENDING_APPROVAL','SENT')", o=oid) == 0
    assert _sql("select count(*) from audit_logs where action='ORDER_CANCEL' and entity_id=:o", o=oid) == 1
    customer_id = _sql("select customer_id from orders where id=:o", o=oid)
    assert any("đã huỷ" in n for n in _notes(customer_id, oid))
    again = client.post(url, headers=staff[0], json={"reason": "Bấm lần nữa cho chắc"})
    assert again.status_code == 409 and _err(again) == "ORDER_CANCEL_UNSUPPORTED"


def test_the_workshop_cancel_is_only_for_accepted_orders(client, cust, staff, wcat):
    oid, _ = _sent(client, cust, staff[0], wcat)                        # the quotation is with the customer now
    r = client.post(f"{W}/orders/{oid}/cancel", headers=staff[0], json={"reason": "Muốn rút lại báo giá"})
    assert r.status_code == 409 and _err(r) == "ORDER_CANCEL_UNSUPPORTED" and r.json()["error"]["details"]["order_status"] != "ACCEPTED"


# ---------------------------------------------------------------------------------------------- D05
def test_a_staff_holding_orders_is_not_locked_until_they_are_reassigned(client, cust, staff, manager, wcat):
    admin = auth(client, "ADMIN")
    oid = _accepted(client, cust, staff[0], wcat)
    url = f"{ADMIN}/accounts/{staff[1]}"
    r = client.patch(url, headers=admin, json={"status": "LOCKED", "reason": "Nghỉ việc"})
    assert r.status_code == 409 and _err(r) == "ACCOUNT_HAS_OPEN_WORK" and r.json()["error"]["details"] == {"orders": [oid]}, r.text
    r = client.patch(url, headers=admin, json={"role": "TECHNICAL_STAFF"})
    assert r.status_code == 409 and _err(r) == "ACCOUNT_HAS_OPEN_WORK"                                  # a role change strands them too
    assert client.get(f"{API}/me", headers=staff[0]).status_code == 200                                 # nothing was changed

    other = _user(client, "STAFF")
    assert client.put(f"{API}/manager/orders/{oid}/assignment", headers=manager[0], json={"staff_id": other[1]}).status_code == 200
    r = client.patch(url, headers=admin, json={"status": "LOCKED", "reason": "Nghỉ việc"})
    assert r.status_code == 200 and r.json()["status"] == "LOCKED", r.text
    assert client.get(f"{API}/me", headers=staff[0]).status_code == 401


def test_an_emergency_lock_needs_force_and_a_reason_and_records_what_was_left(client, cust, staff, wcat):
    admin = auth(client, "ADMIN")
    oid = _accepted(client, cust, staff[0], wcat)
    url = f"{ADMIN}/accounts/{staff[1]}"
    r = client.patch(url, headers=admin, json={"status": "LOCKED", "force": True})
    assert r.status_code == 422 and _err(r) == "REASON_REQUIRED"
    r = client.patch(url, headers=admin, json={"status": "LOCKED", "force": True, "reason": "Nghi lộ mật khẩu"})
    assert r.status_code == 200 and r.json()["status"] == "LOCKED", r.text
    left = _sql("select new_value->'forced_with_open_work'->'orders' from audit_logs where action='ACCOUNT_LOCK' and entity_id=:a "
                "order by id desc limit 1", a=staff[1])
    assert left == [oid]                                                # the Manager can see what to reassign


def test_a_technician_holding_jobs_or_robots_is_not_locked_and_a_forced_lock_ends_their_workstation_keys(
        client, cust, staff, mgr, wcat, robot, tech):
    admin = auth(client, "ADMIN")
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    key = session_key(client, tech, robot, "app-instance-1")["key"]
    assert client.get(f"{T}/jobs/{jid}", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    url = f"{ADMIN}/accounts/{tech[1]}"
    r = client.patch(url, headers=admin, json={"status": "DISABLED", "reason": "Chuyển bộ phận"})
    assert r.status_code == 409 and _err(r) == "ACCOUNT_HAS_OPEN_WORK" and r.json()["error"]["details"]["jobs"] == [jid], r.text

    r = client.patch(url, headers=admin, json={"status": "DISABLED", "force": True, "reason": "Sự cố an toàn, khoá ngay"})
    assert r.status_code == 200, r.text
    assert _sql("select count(*) from robot_agents where account_id=:a and revoked_at is null", a=tech[1]) == 0
    gone = client.get(f"{T}/jobs/{jid}", headers={"Authorization": f"Bearer {key}"})
    assert gone.status_code == 401                                      # the app's key died with the account


def test_an_account_with_nothing_in_hand_is_locked_as_before(client):
    admin = auth(client, "ADMIN")
    idle = _user(client, "STAFF")
    r = client.patch(f"{ADMIN}/accounts/{idle[1]}", headers=admin, json={"status": "LOCKED"})
    assert r.status_code == 200 and r.json()["status"] == "LOCKED"
    r = client.patch(f"{ADMIN}/accounts/{idle[1]}", headers=admin, json={"status": "ACTIVE"})
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"                                      # unlocking is never held back
