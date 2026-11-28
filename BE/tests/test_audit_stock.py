"""Stock ledger audit, 2026-11-28 (docs/audit/09_APPROVAL_AND_IMPLEMENTATION_PLAN.md, section 10), K1.

Paper a job took came back only at "Writing done". A job that failed or was cancelled kept it for ever.
* cancelled before Prepare (unschedule, reschedule, order cancelled): nothing was used, everything goes back by itself;
* ended half-way (incident, cancelled after Prepare): the technician or a Manager settles once, with the spoiled sheets.

Real database and triggers.
"""
from app.domain import notification_messages as nm
from tests.test_api_orders import API, _sql, issue_paper
from tests.test_api_scheduling import _at, mgr, robot, tech  # noqa: F401
from tests.test_api_technician import T, _err, _job, _post, _ready, _running
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"
W = f"{API}/workshop"


def _shelf(wcat):
    return _sql("select stock_qty from paper_types where id=:i", i=wcat["paper"])


def _stock(client, tech, jid):
    return client.get(f"{T}/jobs/{jid}/stock", headers=tech[0]).json()


def _taken(client, cust, staff, mgr, wcat, robot, tech, spare=0):
    """A scheduled job that has taken its paper (plus `spare`) but was not prepared yet."""
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    issue_paper(client, tech[0], jid, spare=spare)
    return oid, jid


def _settles(jid):
    return _sql("select new_value from audit_logs where action='STOCK_SETTLE' and entity_id=:j order by id desc limit 1", j=jid)


# ---------------------------------------------------------------------------------------------- cancelled before Prepare
def test_unscheduling_a_job_gives_its_paper_back(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _taken(client, cust, staff, mgr, wcat, robot, tech, spare=2)
    held = _stock(client, tech, jid)["paper_held"]
    assert held == 3 and _shelf(wcat) == 97
    assert client.post(f"{M}/jobs/{jid}/unschedule", headers=mgr, json={"reason": "Đổi kế hoạch sản xuất tuần này"}).status_code == 200
    st = _stock(client, tech, jid)
    assert _shelf(wcat) == 100 and st["paper_held"] == 0 and st["settled"] is True and st["can_settle"] is False
    assert _settles(jid) == {"held": 3, "waste": 0, "returned": 3, "automatic": True}
    assert _sql("select count(*) from stock_movements where job_id=:j and kind='RETURN' and quantity=3", j=jid) == 1


def test_rescheduling_moves_the_paper_back_and_the_new_job_takes_its_own(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _taken(client, cust, staff, mgr, wcat, robot, tech)
    assert _shelf(wcat) == 99
    r = client.post(f"{M}/jobs/{jid}/reschedule", headers=mgr, json={"slot_start": _at(3, 9).isoformat(), "reason": "Dời sang ngày khác"})
    assert r.status_code == 200, r.text
    new = r.json()["id"]
    assert new != jid and _shelf(wcat) == 100 and _stock(client, tech, jid)["paper_held"] == 0
    assert client.get(f"{T}/jobs/{new}/package", headers=tech[0]).status_code == 200
    assert _err(_post(client, tech, new, "prepare")) == "STOCK_NOT_ISSUED"          # the new job starts from nothing
    issue_paper(client, tech[0], new)
    assert _shelf(wcat) == 99 and _post(client, tech, new, "prepare").status_code == 200


def test_cancelling_the_order_returns_the_paper_of_a_job_not_yet_prepared(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _taken(client, cust, staff, mgr, wcat, robot, tech)
    assert _shelf(wcat) == 99
    r = client.post(f"{W}/orders/{oid}/cancel", headers=staff[0], json={"reason": "Xưởng không làm kịp đơn này"})
    assert r.status_code == 200, r.text
    assert _sql("select status::text from production_jobs where id=:j", j=jid) == "CANCELLED"
    assert _shelf(wcat) == 100 and _settles(jid)["automatic"] is True


# ---------------------------------------------------------------------------------------------- ended half-way
def test_a_failed_job_keeps_its_paper_until_somebody_counts_the_spoiled_sheets(client, cust, staff, mgr, wcat, robot, tech):
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    issue_paper(client, tech[0], jid, spare=3)                                      # 1 needed + 3 spare
    assert _shelf(wcat) == 96
    alive = client.post(f"{T}/jobs/{jid}/stock/settle", headers=tech[0], json={"waste": 0})
    assert alive.status_code == 409 and _err(alive) == "STOCK_SETTLE_NOT_ALLOWED"    # a running job returns at "Writing done"
    assert _post(client, tech, jid, "incidents", {"type": "ROBOT", "description": "Cánh tay dừng giữa chừng"}).status_code == 201
    st = _stock(client, tech, jid)
    assert st["paper_held"] == 4 and st["can_settle"] is True and st["settled"] is False and _shelf(wcat) == 96
    d = client.get(f"{M}/jobs/{jid}", headers=mgr).json()
    assert d["status"] == "FAILED" and d["paper_held"] == 4 and d["can_settle_stock"] is True

    url = f"{T}/jobs/{jid}/stock/settle"
    too_many = client.post(url, headers=tech[0], json={"waste": 5})
    assert too_many.status_code == 422 and _err(too_many) == "WASTE_OUT_OF_RANGE" and too_many.json()["error"]["details"] == {"held": 4}
    other = client.post(url, headers=staff[0], json={"waste": 1})
    assert other.status_code == 403                                                  # the job's technician (or a Manager), nobody else
    r = client.post(url, headers=tech[0], json={"waste": 1})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["paper_held"] == 1 and out["settled"] is True and out["can_settle"] is False   # the spoiled sheet stays written off
    assert _shelf(wcat) == 99 and _settles(jid) == {"held": 4, "waste": 1, "returned": 3, "automatic": False}
    again = client.post(url, headers=tech[0], json={"waste": 0})
    assert again.status_code == 409 and _err(again) == "STOCK_ALREADY_SETTLED" and _shelf(wcat) == 99
    assert client.get(f"{M}/jobs/{jid}", headers=mgr).json()["can_settle_stock"] is False


def test_a_manager_settles_a_job_and_all_of_it_may_be_spoiled(client, cust, staff, mgr, wcat, robot, tech):
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech)
    assert _post(client, tech, jid, "incidents", {"type": "OTHER", "description": "Giấy bị ướt khi chuẩn bị"}).status_code == 201
    url = f"{M}/jobs/{jid}/stock/settle"
    assert client.post(url, headers=tech[0], json={"waste": 0}).status_code == 403
    assert client.post(f"{M}/jobs/999999999/stock/settle", headers=mgr, json={"waste": 0}).status_code == 404
    r = client.post(url, headers=mgr, json={"waste": 1})
    assert r.status_code == 200 and r.json() == {"job_id": jid, "held": 1, "waste": 1, "returned": 0}, r.text
    assert _shelf(wcat) == 99                                                        # nothing came back: the one sheet was spoiled
    assert _err(client.post(url, headers=mgr, json={"waste": 0})) == "STOCK_ALREADY_SETTLED"


def test_a_finished_job_has_nothing_to_settle(client, cust, staff, mgr, wcat, robot, tech):
    from tests.test_api_technician import _robot_wrote
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _robot_wrote(client, tech, jid)
    assert _post(client, tech, jid, "finish").status_code == 200
    st = _stock(client, tech, jid)
    assert st["can_settle"] is False
    r = client.post(f"{T}/jobs/{jid}/stock/settle", headers=tech[0], json={"waste": 0})
    assert r.status_code == 409 and _err(r) == "STOCK_SETTLE_NOT_ALLOWED"


# ---------------------------------------------------------------------------------------------- which page a notification opens
def test_workshop_payment_notifications_say_what_they_are_about():
    """The web opens the refunds desk only for REFUND_DUE. An overdue balance is about the order (the Manager closes it there);
    before, both carried no code and the web sent every workshop PAYMENT notification to the refunds desk."""
    refund = nm.render("REFUND_TO_PROCESS", {"code": "VHRS-1", "amount": "50000"})
    overdue = nm.render("FINAL_PAYMENT_OVERDUE", {"code": "VHRS-1", "days": 9})
    pickup = nm.render("PICKUP_OVERDUE", {"code": "VHRS-1", "days": 9})
    assert (refund.type, refund.msg_code) == ("PAYMENT", "REFUND_DUE")
    assert (overdue.type, overdue.msg_code) == ("PAYMENT", "PAY_LATE")
    assert pickup.msg_code == "PICK_LATE"
    assert all(len(m.msg_code) <= 10 for m in (refund, overdue, pickup))             # notifications.msg_code is VARCHAR(10)
