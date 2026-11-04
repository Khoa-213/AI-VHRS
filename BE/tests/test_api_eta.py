"""Phase 4d-2: ETA (BR-15, BR-16, FR-26, UC-30): estimated at the quotation, first set at the deposit, moved later by the schedule
and the carrier, set by hand by Staff, with its history.

Real database and trigger (`fn_order_state_guard` adds up `eta_postponed_days`, `fn_order_status_history` writes the history).
Moving an ETA earlier by SQL needs the reason GUC, as the application does through `set_actor`.
"""
from datetime import date, datetime, timedelta

from tests.test_api_delivery_final import _final_stage, _put
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _paid
from tests.test_api_scheduling import CAL, M, _at, _iso, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_shipments import _choose, carriers_on  # noqa: F401
from tests.test_api_workshop import W, _err, _user, cust, manager, policy, staff, store, wcat  # noqa: F401


def _eta(oid) -> date | None:
    return _sql("select eta from orders where id=:o", o=oid)


def _set_eta(oid, d: date):
    _sql("""update orders set eta = cast(:d as date)
            where id=:o and set_config('app.status_reason', 'pytest', true) is not null returning 1""", o=oid, d=d.isoformat())


def _today() -> date:
    return datetime.now(CAL.tz).date()


def test_the_quotation_carries_an_estimate_and_the_order_gets_its_eta_at_the_deposit(client, cust, staff, wcat, robot):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    assert q["eta"] is not None and date.fromisoformat(q["eta"]) > _today()       # BR-15 estimate when Staff leaves it empty
    assert _eta(oid) is None                                                        # not before the deposit
    oid2, q2, _ = _paid(client, cust, staff[0], wcat)
    assert _eta(oid2) is not None and _eta(oid2) >= date.fromisoformat(q2["eta"])
    view = client.get(f"{API}/orders/{oid2}/eta", headers=cust).json()
    assert view["postponed_days"] == 0 and view["history"] == []                    # the first ETA is not a postponement
    assert view["can_cancel_full_refund"] is False and view["threshold_days"] == 7


def test_scheduling_past_the_eta_postpones_it_with_a_reason(client, cust, staff, wcat, mgr, robot, tech):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    _set_eta(oid, _today())
    r = _sched(client, mgr, oid, robot, tech[1], _at(4))
    assert r.status_code == 201, r.text
    new = _eta(oid)
    assert new > _today()
    view = client.get(f"{API}/orders/{oid}/eta", headers=cust).json()
    last = view["history"][-1]
    assert last["old_eta"] == _today().isoformat() and last["new_eta"] == new.isoformat()
    assert last["reason"].startswith("Lịch sản xuất") and last["actor_id"] is None             # the customer does not see who
    assert view["postponed_days"] == (new - _today()).days
    staff_view = client.get(f"{W}/orders/{oid}/eta", headers=staff[0]).json()
    assert staff_view["history"][-1]["actor_id"] == mgr_id(client, mgr)


def mgr_id(client, mgr):
    return client.get(f"{API}/me", headers=mgr).json()["id"]


def test_an_earlier_reschedule_never_pulls_the_eta_back(client, cust, staff, wcat, mgr, robot, tech):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    job = _sched(client, mgr, oid, robot, tech[1], _at(6)).json()
    before, days = _eta(oid), _sql("select eta_postponed_days from orders where id=:o", o=oid)
    r = client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr,
                    json={"slot_start": _iso(_at(1, 10)), "reason": "Có khung sớm hơn"})
    assert r.status_code == 200, r.text
    assert _eta(oid) == before and _sql("select eta_postponed_days from orders where id=:o", o=oid) == days


def test_staff_changes_the_eta_by_hand(client, cust, staff, manager, wcat, robot):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    url = f"{W}/orders/{oid}/eta"
    view = client.get(url, headers=staff[0]).json()
    assert view["suggested_eta"] is not None
    assert client.get(url, headers=manager[0]).status_code == 200
    current = _eta(oid)
    later = current + timedelta(days=5)

    other = _user(client, "STAFF")[0]
    assert client.post(url, headers=manager[0], json={"eta": later.isoformat(), "reason": "x"}).status_code == 403
    assert client.post(url, headers=cust, json={"eta": later.isoformat(), "reason": "x"}).status_code == 403
    assert client.post(url, headers=other, json={"eta": later.isoformat(), "reason": "x"}).status_code == 404
    assert client.post(url, headers=staff[0], json={"eta": later.isoformat(), "reason": ""}).status_code == 422
    past = client.post(url, headers=staff[0], json={"eta": (_today() - timedelta(days=1)).isoformat(), "reason": "x"})
    assert past.status_code == 422 and _err(past) == "ETA_IN_PAST"
    same = client.post(url, headers=staff[0], json={"eta": current.isoformat(), "reason": "x"})
    assert same.status_code == 422 and _err(same) == "ETA_UNCHANGED"

    r = client.post(url, headers=staff[0], json={"eta": later.isoformat(), "reason": "Thiếu giấy mỹ thuật"})
    assert r.status_code == 200, r.text
    assert r.json()["eta"] == later.isoformat() and r.json()["postponed_days"] == 5
    assert r.json()["history"][-1]["reason"] == "Thiếu giấy mỹ thuật"
    earlier = client.post(url, headers=staff[0], json={"eta": (later - timedelta(days=2)).isoformat(), "reason": "Có giấy"})
    assert earlier.status_code == 200 and earlier.json()["postponed_days"] == 5                # earlier never subtracts
    r = client.post(url, headers=staff[0], json={"eta": (later + timedelta(days=4)).isoformat(), "reason": "Robot hỏng"})
    assert r.json()["postponed_days"] == 11 and r.json()["can_cancel_full_refund"] is True     # BR-16 opens
    cust_view = client.get(f"{API}/orders/{oid}/eta", headers=cust).json()
    assert cust_view["can_cancel_full_refund"] is True and len(cust_view["history"]) == 3
    assert _sql("select count(*) from audit_logs where entity_type='order' and entity_id=:o and action like 'ETA_%'", o=oid) == 3


def test_eta_is_not_editable_before_the_deposit_or_by_someone_else(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    r = client.post(f"{W}/orders/{oid}/eta", headers=staff[0], json={"eta": (_today() + timedelta(days=9)).isoformat(),
                                                                       "reason": "x"})
    assert r.status_code == 409 and _err(r) == "ETA_NOT_EDITABLE"
    assert client.get(f"{API}/orders/{oid}/eta", headers=_user(client, "CUSTOMER")[0]).status_code == 404
    assert client.get(f"{W}/orders/{oid}/eta", headers=_user(client, "STAFF")[0]).status_code == 404
    view = client.get(f"{API}/orders/{oid}/eta", headers=cust).json()
    assert view["eta"] is None and view["postponed_days"] == 0


def test_a_slower_carrier_service_moves_the_eta(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    _set_eta(oid, _today())
    _put(client, cust, oid, _choose())
    shipping = _sql("select shipping_eta from orders where id=:o", o=oid)
    assert shipping is not None
    expected = max(shipping.astimezone(CAL.tz).date(), _today())
    assert expected > _today() and _eta(oid) == expected                             # the mock carrier delivers in a few days
    last = client.get(f"{API}/orders/{oid}/eta", headers=cust).json()["history"][-1]
    assert last["reason"].startswith("Hãng GHN (EXPRESS)") and last["new_eta"] == expected.isoformat()


def test_the_schedule_config_tells_the_delivery_days(client, mgr):
    cfg = client.get(f"{M}/schedule/config", headers=mgr).json()
    assert cfg["eta_delivery_days"] == 3 and cfg["eta_buffer_days"] >= 0
