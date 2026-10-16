"""Phase 3, production scheduling: queue, suggestion, schedule, conflicts (BR-18), reschedule, failure re-queue.

Real database, real calendar maths and DB triggers. Each test gets its own 'pytest_' robot and technician, so the
workshop's real robot and technicians are never touched. Nothing here talks to a robot.
"""
import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import scheduling_rules as sr
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid
from tests.test_api_workshop import (W, _accepted, _err, _order_status, _ot3, _user, cust, manager, policy,  # noqa: F401
                                     staff, store, wcat)

M = f"{API}/manager"
CAL = sr.WorkCalendar.from_setting(_sql("select value from system_settings where key='working_hours'"))


def _at(days: int = 1, hour: int = 9, minute: int = 0) -> datetime:
    """A moment inside working hours, `days` ahead (rolled forward to the next open day when closed)."""
    local = (datetime.now(CAL.tz) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return CAL.next_open(local)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _robot(category=None, status="AVAILABLE") -> int:
    cats = "null" if category is None else f"array['{category}']::pen_category[]"
    return _sql(f"""insert into robots (code,station,status,supported_pen_categories)
                    values (:c,'Ban test',cast(:s as robot_status),{cats}) returning id""",
                c="pytest_" + uuid.uuid4().hex[:8], s=status)


@pytest.fixture
def robot():
    return _robot()


@pytest.fixture
def tech(client):
    return _user(client, "TECHNICAL_STAFF")


@pytest.fixture
def mgr(client):
    return _user(client, "MANAGER")[0]


def _sched(client, mgr, oid, robot_id, tech_id, start, **kw):
    return client.post(f"{M}/orders/{oid}/schedule", headers=mgr,
                       json={"robot_id": robot_id, "technician_id": tech_id, "slot_start": _iso(start), **kw})


def _prod(oid):
    return _sql("select production_status::text from orders where id=:o", o=oid)


def _minutes(oid) -> int:
    sec = _sql("select estimated_writing_sec from sketches where order_id=:o and is_final", o=oid)
    qty = _sql("select quantity from orders where id=:o", o=oid)
    return sr.job_minutes(sec, qty)


# ---- access -----------------------------------------------------------------------------------------
def test_scheduling_is_manager_only(client, cust):
    calls = [("get", "/manager/orders/1/schedule-suggestion", None),
             ("post", "/manager/orders/1/schedule", {"robot_id": 1, "technician_id": 1, "slot_start": "2030-01-01T09:00:00+07:00"}),
             ("post", "/manager/jobs/1/reschedule", {"reason": "x"}), ("post", "/manager/jobs/1/unschedule", {"reason": "x"}),
             ("get", "/manager/jobs/1", None)]
    for role in ("CUSTOMER", "STAFF", "TECHNICAL_STAFF", "ADMIN", None):
        h = auth(client, role) if role else {}
        for method, path, body in calls:
            r = client.request(method.upper(), f"{API}{path}", headers=h, json=body)
            assert r.status_code == (403 if role else 401), (role, path)


# ---- queue, suggestion, validation (no state change) --------------------------------------------------
def test_queue_suggestion_and_schedule_validation(client, cust, staff, mgr, wcat, robot, tech):
    oid, q, p = _paid(client, cust, staff[0], wcat, text_="Chúc mừng năm mới", qty=2)
    code = _sql("select code from orders where id=:o", o=oid)
    # unpaid orders are not in the queue
    unpaid = _accepted(client, cust, staff[0], wcat)

    rows, page = [], 1
    while True:
        d = client.get(f"{M}/schedule/queue", headers=mgr, params={"page": page, "page_size": 100}).json()
        rows += d["items"]
        if len(rows) >= d["total"] or not d["items"]:
            break
        page += 1
    mine = [r for r in rows if r["order_id"] == oid]
    assert len(mine) == 1 and mine[0]["code"] == code and mine[0]["production_status"] == "PENDING_SCHEDULE"
    assert mine[0]["duration_min"] == _minutes(oid) and mine[0]["quantity"] == 2
    assert unpaid not in [r["order_id"] for r in rows]

    # robot suitability (BR-18): a fountain-pen-only robot does not fit a gel-pen order
    fountain_only = _robot("FOUNTAIN")
    _robot(status="BROKEN")
    r = client.get(f"{M}/orders/{oid}/schedule-suggestion", headers=mgr)
    assert r.status_code == 200, r.text
    s = r.json()
    ids = [x["robot_id"] for x in s["suggestions"]]
    assert s["duration_min"] == _minutes(oid) and s["quantity"] == 2 and s["writing_sec_per_copy"] > 0
    assert robot in ids and fountain_only not in ids and 1 <= len(ids) <= 5
    starts = [x["slot_start"] for x in s["suggestions"]]
    assert starts == sorted(starts)
    technicians = {t["id"] for t in client.get(f"{M}/technicians", headers=mgr).json()}
    now = datetime.now(timezone.utc)
    for x in s["suggestions"]:
        start, end = datetime.fromisoformat(x["slot_start"]), datetime.fromisoformat(x["slot_end"])
        assert CAL.next_open(start) == start and end > start and start > now                  # working time, in the future
        assert end == CAL.add_working_minutes(start, s["duration_min"])
        assert x["technician_id"] in technicians and isinstance(x["eta_risk"], bool)
        assert x["robot_id"] != fountain_only
    assert s["stock_warnings"] == [] or all(isinstance(w, str) for w in s["stock_warnings"])
    _sql("update paper_types set stock_qty=0 where id=:i returning 1", i=wcat["paper"])
    warn = client.get(f"{M}/orders/{oid}/schedule-suggestion", headers=mgr).json()["stock_warnings"]
    assert any("Giấy" in w for w in warn)
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])

    # validation: every one of these leaves the order untouched
    ok = _at(1, 9)
    cases = [
        (_sched(client, mgr, oid, robot, tech[1], _at(-3, 9)), 422, "SLOT_IN_PAST"),
        (_sched(client, mgr, oid, robot, tech[1], _at(1, 9).replace(hour=21)), 422, "OUTSIDE_WORKING_HOURS"),
        (client.post(f"{M}/orders/{oid}/schedule", headers=mgr, json={"robot_id": robot, "technician_id": tech[1],
                                                                       "slot_start": "2031-01-05T09:00:00"}), 422, "INVALID_SLOT"),
        (_sched(client, mgr, oid, 999999999, tech[1], ok), 404, "ROBOT_NOT_FOUND"),
        (_sched(client, mgr, oid, _robot(status="MAINTENANCE"), tech[1], ok), 409, "ROBOT_UNAVAILABLE"),
        (_sched(client, mgr, oid, fountain_only, tech[1], ok), 422, "ROBOT_NOT_SUITABLE"),
        (_sched(client, mgr, oid, robot, _user(client, "STAFF")[1], ok), 422, "INVALID_TECHNICIAN"),
        (_sched(client, mgr, oid, robot, 999999999, ok), 422, "INVALID_TECHNICIAN"),
        (_sched(client, mgr, unpaid, robot, tech[1], ok), 409, "NOT_SCHEDULABLE"),
        (_sched(client, mgr, 999999999, robot, tech[1], ok), 404, "ORDER_NOT_FOUND"),
        (client.get(f"{M}/orders/{unpaid}/schedule-suggestion", headers=mgr), 409, "NOT_SCHEDULABLE"),
    ]
    for r, status, code_ in cases:
        assert r.status_code == status and _err(r) == code_, (code_, r.text)
    assert _prod(oid) == "PENDING_SCHEDULE" and _sql("select count(*) from production_jobs where order_id=:o", o=oid) == 0


# ---- scheduling and conflicts -----------------------------------------------------------------------
def test_schedule_creates_the_job_and_blocks_overlaps(client, cust, staff, mgr, wcat, robot, tech):
    oid, q, p = _paid(client, cust, staff[0], wcat, text_="Kính gửi quý khách")
    start = _at(1, 9)
    r = _sched(client, mgr, oid, robot, tech[1], start, note="Ưu tiên khách quen")
    assert r.status_code == 201, r.text
    job = r.json()
    minutes = _minutes(oid)
    assert job["status"] == "SCHEDULED" and job["is_rewrite"] is False and job["estimated_duration_min"] == minutes
    assert datetime.fromisoformat(job["slot_start"]) == start
    assert datetime.fromisoformat(job["slot_end"]) == CAL.add_working_minutes(start, minutes)
    assert job["order_code"] and job["robot_code"].startswith("pytest_") and job["technician_name"]
    assert job["package_hash"] == _sql("select content_hash from sketches where order_id=:o and is_final", o=oid)
    assert _prod(oid) == "SCHEDULED" and _order_status(oid) == "CONFIRMED"
    assert _sql("select eta is not null from orders where id=:o", o=oid)                      # ETA set when there was none
    assert _sql("""select count(*) from status_histories where order_id=:o and state_type='PRODUCTION'
                   and from_status='PENDING_SCHEDULE' and to_status='SCHEDULED' and actor_id is not null""", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='JOB_SCHEDULE' and entity_id=:j", j=job["id"]) == 1

    assert client.get(f"{M}/jobs/{job['id']}", headers=mgr).json()["id"] == job["id"]
    listed = client.get(f"{M}/jobs", headers=mgr, params={"robot_id": robot}).json()
    assert [j["id"] for j in listed["items"]] == [job["id"]] and listed["total"] == 1
    assert client.get(f"{M}/jobs", headers=mgr, params={"technician_id": tech[1], "status": "SCHEDULED"}).json()["total"] == 1
    assert client.get(f"{M}/jobs", headers=mgr, params={"technician_id": tech[1], "status": "DONE"}).json()["total"] == 0
    day = client.get(f"{M}/jobs", headers=mgr, params={"robot_id": robot, "from": _iso(start - timedelta(hours=1)),
                                                       "to": _iso(start + timedelta(hours=1))}).json()
    assert day["total"] == 1
    assert client.get(f"{M}/jobs", headers=mgr, params={"robot_id": robot, "from": _iso(start + timedelta(days=30))}).json()["total"] == 0
    assert next(t for t in client.get(f"{M}/technicians", headers=mgr).json() if t["id"] == tech[1])["active_jobs"] == 1
    mine = client.get(f"{W}/orders/{oid}/jobs", headers=staff[0]).json()                        # Staff may look, not change
    assert [j["id"] for j in mine] == [job["id"]]
    again = _sched(client, mgr, oid, robot, tech[1], _at(3, 9))
    assert again.status_code == 409 and _err(again) == "NOT_SCHEDULABLE"

    # BR-18: one job per robot at a time; a technician cannot be in two places either
    oid2, _, _ = _paid(client, cust, staff[0], wcat, text_="Xin chào")
    clash = _sched(client, mgr, oid2, robot, _user(client, "TECHNICAL_STAFF")[1], start + timedelta(minutes=5))
    assert clash.status_code == 409 and _err(clash) == "SLOT_CONFLICT" and clash.json()["error"]["details"] == {"resource": "robot"}
    clash = _sched(client, mgr, oid2, _robot(), tech[1], start + timedelta(minutes=5))
    assert clash.status_code == 409 and _err(clash) == "SLOT_CONFLICT" and clash.json()["error"]["details"] == {"resource": "technician"}
    assert _prod(oid2) == "PENDING_SCHEDULE"
    end = datetime.fromisoformat(job["slot_end"])
    suggestion = client.get(f"{M}/orders/{oid2}/schedule-suggestion", headers=mgr).json()["suggestions"]
    taken = (start, end)
    assert all(not (x["robot_id"] == robot and sr.overlaps((datetime.fromisoformat(x["slot_start"]),
                                                            datetime.fromisoformat(x["slot_end"])), taken))
               for x in suggestion)                                                  # never suggests an occupied slot
    if CAL.next_open(end) == end:                                                              # back-to-back is allowed
        nxt = _sched(client, mgr, oid2, robot, tech[1], end)
        assert nxt.status_code == 201 and datetime.fromisoformat(nxt.json()["slot_start"]) == end


def test_db_exclusion_constraint_is_the_backstop(client, cust, staff, mgr, wcat, robot, tech):
    """Even if two requests raced past the service check, the database refuses an overlapping robot slot."""
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    start = _at(1, 9)
    assert _sched(client, mgr, oid, robot, tech[1], start).status_code == 201
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db.session import get_engine
    other_tech, other_order = _user(client, "TECHNICAL_STAFF")[1], _ot3(client, cust, wcat, submit=False)
    with pytest.raises(IntegrityError) as exc:
        with get_engine().begin() as c:
            c.execute(text("""insert into production_jobs (order_id,sketch_id,robot_id,technician_id,scheduled_by,status,
                              slot_start,slot_end,estimated_duration_min)
                              select :oo,sketch_id,robot_id,:t,scheduled_by,'SCHEDULED',slot_start,slot_end,
                                     estimated_duration_min from production_jobs where order_id=:o"""),
                      {"oo": other_order, "t": other_tech, "o": oid})
    assert "ex_job_robot_overlap" in str(exc.value)


# ---- changing the plan ------------------------------------------------------------------------------
def test_reschedule_and_unschedule(client, cust, staff, mgr, wcat, robot, tech):
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    job = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()
    robot2, tech2 = _robot(), _user(client, "TECHNICAL_STAFF")[1]

    assert client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr, json={"robot_id": robot2}).status_code == 422   # reason required
    r = client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr,
                    json={"robot_id": robot2, "technician_id": tech2, "slot_start": _iso(_at(2, 10)), "reason": "Kỹ thuật viên nghỉ"})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] != job["id"] and new["robot_id"] == robot2 and new["technician_id"] == tech2 and new["status"] == "SCHEDULED"
    assert datetime.fromisoformat(new["slot_start"]) == _at(2, 10)
    assert _sql("select status::text from production_jobs where id=:j", j=job["id"]) == "CANCELLED"
    assert _prod(oid) == "SCHEDULED"
    assert _sql("select count(*) from production_jobs where order_id=:o and status='SCHEDULED'", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='JOB_RESCHEDULE' and entity_id=:j", j=new["id"]) == 1
    assert next(t for t in client.get(f"{M}/technicians", headers=mgr).json() if t["id"] == tech[1])["active_jobs"] == 0   # freed

    again = client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr, json={"reason": "x"})                             # old job is gone
    assert again.status_code == 409 and _err(again) == "JOB_ALREADY_STARTED"
    keep = client.post(f"{M}/jobs/{new['id']}/reschedule", headers=mgr, json={"reason": "Chỉ đổi giờ", "slot_start": _iso(_at(3, 9))})
    assert keep.status_code == 200 and keep.json()["robot_id"] == robot2 and keep.json()["technician_id"] == tech2   # omitted = unchanged
    cur = keep.json()

    assert client.post(f"{M}/jobs/{cur['id']}/unschedule", headers=mgr, json={"reason": ""}).status_code == 422
    r = client.post(f"{M}/jobs/{cur['id']}/unschedule", headers=mgr, json={"reason": "Chờ vật tư"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert _prod(oid) == "PENDING_SCHEDULE" and _order_status(oid) == "CONFIRMED"
    assert client.post(f"{M}/jobs/{cur['id']}/unschedule", headers=mgr, json={"reason": "x"}).status_code == 409
    final = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert final.status_code == 201 and _prod(oid) == "SCHEDULED"

    # once the technician has started preparing, the Manager can no longer move it
    _sql("update production_jobs set status='PREPARING' where id=:j returning 1", j=final.json()["id"])
    _sql("update orders set production_status='PREPARING' where id=:o returning 1", o=oid)
    for path in ("reschedule", "unschedule"):
        r = client.post(f"{M}/jobs/{final.json()['id']}/{path}", headers=mgr, json={"reason": "x"})
        assert r.status_code == 409 and _err(r) == "JOB_ALREADY_STARTED"


def test_failed_production_can_be_scheduled_again(client, cust, staff, mgr, wcat, robot, tech):
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    first = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()
    # the technician phase will do this; here the legal transitions are applied directly to the database
    _sql("update orders set production_status='PREPARING' where id=:o returning 1", o=oid)
    _sql("update orders set production_status='FAILED' where id=:o returning 1", o=oid)
    _sql("update production_jobs set status='FAILED' where id=:j returning 1", j=first["id"])

    queue = client.get(f"{M}/schedule/queue", headers=mgr, params={"page_size": 100}).json()["items"]
    assert [r["production_status"] for r in queue if r["order_id"] == oid] == ["FAILED"]
    assert client.get(f"{M}/orders/{oid}/schedule-suggestion", headers=mgr).status_code == 200
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9), note="Xếp lại sau khi robot lỗi")           # same slot is free again
    assert r.status_code == 201, r.text
    assert r.json()["id"] != first["id"] and r.json()["is_rewrite"] is False
    assert _prod(oid) == "SCHEDULED"
    assert [j["status"] for j in client.get(f"{M}/jobs", headers=mgr, params={"robot_id": robot}).json()["items"]] == ["FAILED", "SCHEDULED"]
    assert _sql("""select count(*) from status_histories where order_id=:o and state_type='PRODUCTION'
                   and from_status='FAILED' and to_status='PENDING_SCHEDULE'""", o=oid) == 1
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='SCHEDULED'", o=oid) == 2


def test_robot_out_of_service_lists_the_jobs_to_move(client, cust, staff, mgr, wcat, robot, tech):
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    job = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()
    r = client.patch(f"{M}/robots/{robot}", headers=mgr, json={"status": "BROKEN"})
    assert r.status_code == 200 and r.json()["affected_job_ids"] == [job["id"]]
    spare = _robot()
    moved = client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr, json={"robot_id": spare, "reason": "Robot hỏng"})
    assert moved.status_code == 200 and moved.json()["robot_id"] == spare
    assert client.patch(f"{M}/robots/{robot}", headers=mgr, json={"status": "MAINTENANCE"}).json()["affected_job_ids"] == []
    oid2, _, _ = _paid(client, cust, staff[0], wcat)
    r = _sched(client, mgr, oid2, robot, tech[1], _at(5, 9))
    assert r.status_code == 409 and _err(r) == "ROBOT_UNAVAILABLE"
