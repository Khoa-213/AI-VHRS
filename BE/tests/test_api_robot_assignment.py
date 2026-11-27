"""Fixed robot assignment (migration 0032, owner decision 2026-11-26).

The Manager gives each robot to ONE technician; a job is scheduled for a technician (robot optional, and when given it must be
theirs); the technician picks one of their robots before preparing. The technician's robot strip counts their robots, how many
are connected and how many are working, and shows nobody else's robots. Real database; nothing here talks to a robot.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import get_engine
from tests.test_api_orders import API, _sql, issue_paper
from tests.test_api_payments import _paid
from tests.test_api_scheduling import M, _at, _give, _iso, _robot, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, manager, policy, staff, store, wcat  # noqa: F401

T = f"{API}/technician"


def _assign(client, mgr, robot_id, tech_id):
    return client.put(f"{M}/robots/{robot_id}/technician", headers=mgr, json={"technician_id": tech_id})


def _plain(client, mgr, oid, tech_id, start):
    """Schedule WITHOUT a robot: the technician picks it later."""
    return client.post(f"{M}/orders/{oid}/schedule", headers=mgr, json={"technician_id": tech_id, "slot_start": _iso(start)})


# ---- Manager: give / move / take back a robot ------------------------------------------------------------------------
def test_the_manager_gives_a_robot_to_one_technician(client, cust, staff, mgr, wcat, robot, tech):
    other = _user(client, "TECHNICAL_STAFF")
    r = _assign(client, mgr, robot, tech[1])
    assert r.status_code == 200 and r.json()["technician_id"] == tech[1] and r.json()["technician_name"]
    assert _assign(client, mgr, robot, tech[1]).status_code == 200                     # the same again changes nothing
    assert _sql("select count(*) from audit_logs where action='ROBOT_ASSIGN' and entity_id=:r", r=robot) == 1
    listed = next(x for x in client.get(f"{M}/robots", headers=mgr).json() if x["id"] == robot)
    assert listed["technician_id"] == tech[1]
    techs = {t["id"]: t for t in client.get(f"{M}/technicians", headers=mgr).json()}
    assert [x["id"] for x in techs[tech[1]]["robots"]] == [robot] and techs[other[1]]["robots"] == []

    # refused: unknown robot, an account that is not an active technician, a non-Manager
    assert _assign(client, mgr, 999999999, tech[1]).status_code == 404
    for who in (_user(client, "STAFF")[1], 999999999):
        r = _assign(client, mgr, robot, who)
        assert r.status_code == 422 and _err(r) == "INVALID_TECHNICIAN"
    assert client.put(f"{M}/robots/{robot}/technician", headers=tech[0], json={"technician_id": tech[1]}).status_code == 403

    # a robot with a job of its current technician on it cannot be moved or taken back
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    job = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()
    for r in (_assign(client, mgr, robot, other[1]), client.delete(f"{M}/robots/{robot}/technician", headers=mgr)):
        assert r.status_code == 409 and _err(r) == "ROBOT_HAS_ACTIVE_JOBS" and r.json()["error"]["details"]["job_ids"] == [job["id"]]
    client.post(f"{M}/jobs/{job['id']}/unschedule", headers=mgr, json={"reason": "Đổi người phụ trách"})
    r = _assign(client, mgr, robot, other[1])
    assert r.status_code == 200 and r.json()["technician_id"] == other[1]
    r = client.delete(f"{M}/robots/{robot}/technician", headers=mgr)
    assert r.status_code == 200 and r.json()["technician_id"] is None
    assert _sql("select count(*) from technician_robots where robot_id=:r", r=robot) == 0
    assert _sql("select count(*) from audit_logs where action='ROBOT_UNASSIGN' and entity_id=:r", r=robot) == 1


# ---- Manager: schedule for a technician ------------------------------------------------------------------------------
def test_a_job_is_scheduled_for_a_technician_who_has_a_suitable_robot(client, cust, staff, mgr, wcat, robot, tech):
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    r = _plain(client, mgr, oid, tech[1], _at(1, 9))
    assert r.status_code == 422 and _err(r) == "TECHNICIAN_HAS_NO_ROBOT"           # no robot given to them yet
    fountain = _robot("FOUNTAIN")
    _give(fountain, tech[1])
    r = _plain(client, mgr, oid, tech[1], _at(1, 9))
    assert r.status_code == 422 and _err(r) == "TECHNICIAN_HAS_NO_ROBOT"           # theirs does not fit the gel pen (BR-18)
    other = _user(client, "TECHNICAL_STAFF")[1]
    _give(robot, other)
    r = client.post(f"{M}/orders/{oid}/schedule", headers=mgr,
                    json={"robot_id": robot, "technician_id": tech[1], "slot_start": _iso(_at(1, 9))})
    assert r.status_code == 422 and _err(r) == "ROBOT_NOT_ASSIGNED"               # somebody else's robot
    assert _sql("select count(*) from production_jobs where order_id=:o", o=oid) == 0

    _give(robot, tech[1])
    r = _plain(client, mgr, oid, tech[1], _at(1, 9))
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["robot_id"] is None and job["robot_code"] == "" and job["technician_id"] == tech[1]
    assert _sql("select robot_id from production_jobs where id=:j", j=job["id"]) is None

    # the suggestion names the technician with one of THEIR robots
    oid2, _, _ = _paid(client, cust, staff[0], wcat)
    s = client.get(f"{M}/orders/{oid2}/schedule-suggestion", headers=mgr).json()["suggestions"]
    assert all(_sql("select technician_id from technician_robots where robot_id=:r", r=x["robot_id"]) == x["technician_id"]
               for x in s)
    _sql("update robots set status='MAINTENANCE' where id=:r returning 1", r=fountain)

    # the database: only a SCHEDULED or CANCELLED job may have no robot
    with pytest.raises(IntegrityError) as exc:
        with get_engine().begin() as c:
            c.execute(text("update production_jobs set status='PREPARING' where id=:j"), {"j": job["id"]})
    assert "chk_job_robot_before_prepare" in str(exc.value)


# ---- Technician: my robots, pick a robot ---------------------------------------------------------------------------
def test_the_technician_sees_only_their_robots_with_connected_and_working_counts(client, mgr, robot, tech):
    mine2, theirs = _robot(), _robot()
    other = _user(client, "TECHNICAL_STAFF")
    _give(robot, tech[1])
    _give(mine2, tech[1])
    _give(theirs, other[1])
    d = client.get(f"{T}/robots", headers=tech[0]).json()
    assert d["total"] == 2 and d["online"] == 0 and d["active"] == 0
    assert sorted(x["robot_id"] for x in d["robots"]) == sorted([robot, mine2])
    row = next(x for x in d["robots"] if x["robot_id"] == robot)
    assert row["connection_state"] == "UNKNOWN" and row["technician_id"] == tech[1] and row["robot_status"] == "AVAILABLE"
    assert row["active"] is False and row["enabled_modes"] == [] and row["state"] == "OFFLINE"

    # the workstation of one robot reports in: 1 of 2 connected
    assert client.put(f"{T}/robots/{robot}/heartbeat", headers=tech[0], json={"mode": "SIM"}).status_code == 200
    d = client.get(f"{T}/robots", headers=tech[0]).json()
    assert d["online"] == 1 and next(x for x in d["robots"] if x["robot_id"] == robot)["connection_state"] == "ONLINE"
    assert {x["robot_id"] for x in client.get(f"{T}/robot-status", headers=tech[0]).json()} >= {robot, mine2}

    # somebody else's robot stays hidden: not listed, not readable, no heartbeat
    assert [x["robot_id"] for x in client.get(f"{T}/robots", headers=other[0]).json()["robots"]] == [theirs]
    assert client.get(f"{T}/robots/{theirs}/live", headers=tech[0]).status_code == 404
    assert client.put(f"{T}/robots/{theirs}/heartbeat", headers=tech[0], json={"mode": "SIM"}).status_code == 404
    assert client.get(f"{T}/robots", headers=mgr).status_code == 403
    _sql("update robots set status='MAINTENANCE' where id in (:a,:b) returning 1", a=mine2, b=theirs)


def test_the_technician_picks_one_of_their_robots_before_preparing(client, cust, staff, mgr, wcat, robot, tech):
    spare, broken, foreign = _robot(), _robot(status="MAINTENANCE"), _robot()
    for r in (robot, spare, broken):
        _give(r, tech[1])
    _give(foreign, _user(client, "TECHNICAL_STAFF")[1])
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    job = _plain(client, mgr, oid, tech[1], _at(1, 9)).json()
    jid = job["id"]
    pick = lambda rid, h=tech[0]: client.put(f"{T}/jobs/{jid}/robot", headers=h, json={"robot_id": rid})  # noqa: E731

    # prepare needs a robot; so does a robot command
    _sql("update production_jobs set downloaded_at=now() where id=:j returning 1", j=jid)
    r = client.post(f"{T}/jobs/{jid}/prepare", headers=tech[0])
    assert r.status_code == 409 and _err(r) == "ROBOT_NOT_SELECTED"
    r = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "LOAD", "job_id": jid, "params": {}})
    assert r.status_code == 409 and _err(r) == "ROBOT_NOT_SELECTED"

    for rid, status, code in ((foreign, 404, "ROBOT_NOT_FOUND"), (999999999, 404, "ROBOT_NOT_FOUND"),
                              (broken, 409, "ROBOT_UNAVAILABLE")):
        r = pick(rid)
        assert r.status_code == status and _err(r) == code, r.text
    assert client.put(f"{T}/jobs/{jid}/robot", headers=_user(client, "TECHNICAL_STAFF")[0],
                      json={"robot_id": robot}).status_code == 404                  # not their job
    r = pick(robot)
    assert r.status_code == 200 and r.json()["robot_id"] == robot and r.json()["robot_code"]
    assert pick(robot).status_code == 200                                         # the same robot again: nothing changes
    assert pick(spare).json()["robot_id"] == spare                                # changed while still SCHEDULED
    assert _sql("select count(*) from audit_logs where action='JOB_ROBOT_CHOOSE' and entity_id=:j", j=jid) == 2

    # a robot already booked in that slot (a job scheduled on it before it was given to me) is refused by the database
    other_tech = _user(client, "TECHNICAL_STAFF")[1]
    oid2, _, _ = _paid(client, cust, staff[0], wcat)
    _give(robot, other_tech)
    legacy = _sched(client, mgr, oid2, robot, other_tech, _at(1, 9)).json()
    _give(robot, tech[1])
    r = pick(robot)
    assert r.status_code == 409 and _err(r) == "SLOT_CONFLICT", r.text
    client.post(f"{M}/jobs/{legacy['id']}/unschedule", headers=mgr, json={"reason": "x"})

    # once preparing, the robot is fixed
    issue_paper(client, tech[0], jid)
    assert client.post(f"{T}/jobs/{jid}/prepare", headers=tech[0]).status_code == 200
    r = pick(robot)
    assert r.status_code == 409 and _err(r) == "JOB_STATE_CONFLICT"
    _sql("update robots set status='MAINTENANCE' where id in (:a,:b) returning 1", a=spare, b=foreign)


def test_rescheduling_to_another_technician_drops_a_robot_that_is_not_theirs(client, cust, staff, mgr, wcat, robot, tech):
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    job = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()
    assert job["robot_id"] == robot
    other = _user(client, "TECHNICAL_STAFF")[1]
    spare = _robot()
    _give(spare, other)
    r = client.post(f"{M}/jobs/{job['id']}/reschedule", headers=mgr, json={"technician_id": other, "reason": "Đổi ca"})
    assert r.status_code == 200, r.text
    assert r.json()["technician_id"] == other and r.json()["robot_id"] is None    # the new technician picks their own
    keep = client.post(f"{M}/jobs/{r.json()['id']}/reschedule", headers=mgr, json={"slot_start": _iso(_at(2, 9)), "reason": "Giờ"})
    assert keep.status_code == 200 and keep.json()["robot_id"] is None
    _sql("update robots set status='MAINTENANCE' where id=:r returning 1", r=spare)


# ---- the REAL switch is set at the workstation only; the backend just shows it (owner 2026-11-26) --------------------
def test_the_real_switch_reported_by_the_agent_is_shown_and_cannot_be_set_through_the_backend(client, mgr, robot, tech):
    from app.services.robot_link import hub
    from tests.test_api_robot_link import key_for
    hub.reset()
    try:
        _give(robot, tech[1])
        _, ah = key_for(client, mgr, robot)
        switch = {"job_id": 12, "expires_at": 1_900_000_000.0, "enabled_by": "desktop:Ky Thuat", "waive_dry_run": False}
        r = client.post(f"{API}/agent/sync", headers=ah,
                        json={"status": {"mode": "SIM", "enabled_modes": ["SIM", "REAL"], "real_enabled": switch}})
        assert r.status_code == 200, r.text
        row = next(x for x in client.get(f"{T}/robots", headers=tech[0]).json()["robots"] if x["robot_id"] == robot)
        assert row["real_enabled"] == switch and row["enabled_modes"] == ["SIM", "REAL"]
        for kind in ("REAL_ENABLE", "REAL_DISABLE"):                      # no command can switch REAL on (or off) remotely
            r = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": kind, "robot_id": robot})
            assert r.status_code == 422, r.text
        client.post(f"{API}/agent/sync", headers=ah, json={"status": {"mode": "SIM", "real_enabled": None}})
        row = next(x for x in client.get(f"{T}/robots", headers=tech[0]).json()["robots"] if x["robot_id"] == robot)
        assert row["real_enabled"] is None
    finally:
        hub.reset()
