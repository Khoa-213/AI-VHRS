"""Audit 2026-11-27, package G1 (docs/audit/05_ISSUES_AND_RECOMMENDATIONS.md): robot safety on the backend side.

TP-01  a job that ends behind the robot's back (incident, robot taken out of service) also stops the robot, and "written" is refused
       while a run is still open
TP-02  an open red alert, or a robot out of service, holds every command that moves the arm
TP-03  a bare RESUME (no job_id) obeys the paused job's rules; a Manager may halt but not resume
TP-06  an agent key stops working when its technician's account is locked
TP-07  the agent may still close its own run after the job left its live states
TP-09  probe points turned the wrong way are reported (the writing would be a mirror image)

Real database and triggers. The agent is simulated by the test; no robot is involved.
"""
import numpy as np

from app.services.motion.frame import build_frame
from app.services.motion.plan import MotionConfig
from app.services.motion.validate import Workspace, validate
from app.services.stroke_ai.trajectory import Page, Stroke
from tests.conftest import agent_h
from tests.test_api_orders import API, _sql
from tests.test_api_robot_link import A, fresh_hub, key_for, sync  # noqa: F401
from tests.test_api_robot_ops import open_run, raise_alert
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL, T, _err, _post, _ready, _running, _status
from tests.test_api_workshop import _user, cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"
RED = "TRACKING_ERROR"          # a level-4 code of the catalogue (tests/test_api_robot_ops.py)


def _cmd(client, who, jid, kind, **params):
    return client.post(f"{T}/robot-commands", headers=who[0], json={"kind": kind, "job_id": jid, "params": params})


def _kinds(payload):
    return [c["kind"] for c in payload["commands"]]


# ---------------------------------------------------------------------------------------------- TP-02
def test_an_open_red_alert_holds_every_motion_command_until_a_manager_closes_it(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    red = raise_alert(client, tech, robot, RED, job_id=jid).json()
    assert red["level"] == 4

    for kind, params in (("RUN", {"mode": "SIM"}), ("RESUME", {}), ("ALIGN_START", {"mode": "SIM"})):
        r = _cmd(client, tech, jid, kind, **params)
        assert r.status_code == 409 and _err(r) == "RED_ALERT_OPEN", (kind, r.text)
        assert r.json()["error"]["details"]["alert_id"] == red["id"]
    r, _ = open_run(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "RED_ALERT_OPEN"
    for kind in ("PAUSE", "STOP"):                                               # halting is never held back
        assert _cmd(client, tech, jid, kind).status_code == 201, kind
    refused, _ = open_run(client, tech, jid, refused_reason="RED_ALERT_OPEN")    # the agent may still record that it refused
    assert refused.status_code == 201 and refused.json()["result"] == "REFUSED"

    assert client.post(f"{M}/alerts/{red['id']}/resolve", headers=mgr, json={"note": "Đã kiểm tra robot, an toàn"}).status_code == 200
    sync(client, ah)
    assert _cmd(client, tech, jid, "RUN", mode="SIM").status_code == 201
    r, _ = open_run(client, tech, jid)
    assert r.status_code == 201, r.text


def test_a_robot_out_of_service_takes_no_motion_command(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    assert client.patch(f"{M}/robots/{robot}", headers=mgr, json={"status": "BROKEN"}).status_code == 200
    r = _cmd(client, tech, jid, "RUN", mode="SIM")
    assert r.status_code == 409 and _err(r) == "ROBOT_UNAVAILABLE"
    r, _ = open_run(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "ROBOT_UNAVAILABLE"
    assert _cmd(client, tech, jid, "STOP").status_code == 201


# ---------------------------------------------------------------------------------------------- TP-03
def test_a_bare_resume_obeys_the_paused_jobs_rules_and_a_manager_cannot_resume(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    _post(client, tech, jid, "events", {"event_type": "ESTOP"}, status=201)
    _post(client, tech, jid, "calibration", CAL, status=201)                     # recalibrated while paused: the simulation is stale
    bare = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "RESUME", "robot_id": robot})
    assert bare.status_code == 409 and _err(bare) == "SIMULATION_STALE", bare.text

    r = client.post(f"{M}/robots/{robot}/robot-commands", headers=mgr, json={"kind": "RESUME"})
    assert r.status_code == 403 and _err(r) == "FORBIDDEN"
    for kind in ("PAUSE", "STOP"):
        assert client.post(f"{M}/robots/{robot}/robot-commands", headers=mgr, json={"kind": kind}).status_code == 201

    _post(client, tech, jid, "simulation", {"passed": True}, status=200)
    sync(client, ah)
    ok = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "RESUME", "robot_id": robot})
    assert ok.status_code == 201, ok.text


# ---------------------------------------------------------------------------------------------- TP-01 / TP-07
def test_written_is_refused_while_a_run_is_still_open(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _sql("update robots set is_simulated = true where id=:r returning 1", r=robot)       # a simulated robot: its finished run is the copy (L1)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    no = _post(client, tech, jid, "finish")
    assert no.status_code == 409 and _err(no) == "RUN_OPEN" and no.json()["error"]["details"]["open_run_id"] == run
    assert _status(jid) == "WRITING"
    assert client.patch(f"{T}/runs/{run}", headers=agent_h(run=run),
                        json={"result": "DONE", "completed_strokes": 10, "total_strokes": 10}).status_code == 200
    _post(client, tech, jid, "finish", status=200)
    assert _status(jid) == "WRITTEN"


def test_an_incident_during_a_run_stops_the_robot_and_the_agent_can_still_close_its_run(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    queued = _cmd(client, tech, jid, "PREFLIGHT", mode="SIM").json()["id"]        # still waiting for the agent

    _post(client, tech, jid, "incidents", {"type": "ROBOT", "description": "Bút lệch khỏi giấy"}, status=201)
    assert _status(jid) == "FAILED"
    assert _kinds(sync(client, ah)) == ["STOP"]                                   # the arm is told to stop; the stale command is not sent
    row = client.get(f"{T}/robot-commands/{queued}", headers=tech[0]).json()
    assert row["status"] == "EXPIRED" and row["error_code"] == "JOB_ENDED"
    stop = _sql("select params->>'system' from robot_commands where job_id=:j and kind='STOP'", j=jid)
    assert stop == "true"

    # TP-07: the job is no longer live, yet the agent may close the run it still holds (and only that)
    closed = client.patch(f"{T}/runs/{run}", headers=ah, json={"result": "STOPPED", "completed_strokes": 3, "total_strokes": 10})
    assert closed.status_code == 200 and closed.json()["result"] == "STOPPED", closed.text
    gone = client.get(f"{T}/jobs/{jid}/package", headers=ah)
    assert gone.status_code == 401 and _err(gone) == "AGENT_HAS_NO_ACTIVE_JOB"    # nothing is open any more: no standing left


def test_an_incident_with_nothing_moving_queues_no_stop(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    _post(client, tech, jid, "incidents", {"type": "ROBOT", "description": "Kẹp giấy lỏng"}, status=201)
    assert _kinds(sync(client, ah)) == []


def test_taking_a_robot_out_of_service_stops_what_is_running_on_it(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    r, _ = open_run(client, tech, jid)
    assert r.status_code == 201
    assert client.patch(f"{M}/robots/{robot}", headers=mgr, json={"status": "MAINTENANCE"}).status_code == 200
    assert _kinds(sync(client, ah)) == ["STOP"]


# ---------------------------------------------------------------------------------------------- TP-06
def test_an_agent_key_stops_working_when_its_technician_is_locked(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    assert client.get(f"{T}/jobs/{jid}", headers=ah).status_code == 200
    _sql("update accounts set status='LOCKED' where id=:i returning 1", i=tech[1])
    try:
        r = client.get(f"{T}/jobs/{jid}", headers=ah)
        assert r.status_code == 401 and _err(r) == "AGENT_ACCOUNT_INACTIVE", r.text
    finally:
        _sql("update accounts set status='ACTIVE' where id=:i returning 1", i=tech[1])


# ---------------------------------------------------------------------------------------------- TP-09
def _probes(swap=False):
    # a sheet read from above by someone facing +Y: top-left, top-right (to +X), bottom-left (towards -Y)
    p0, p1, p2 = {"x": 300.0, "y": 100.0, "z": 20.0}, {"x": 510.0, "y": 100.0, "z": 20.0}, {"x": 300.0, "y": -197.0, "z": 20.0}
    return [p0, p2, p1] if swap else [p0, p1, p2]


def test_probe_points_turned_the_wrong_way_are_flagged_as_mirrored():
    good, bad = build_frame(_probes()), build_frame(_probes(swap=True))
    assert good.mirrored is False and bad.mirrored is True
    assert good.to_dict()["mirrored"] is False and bad.to_dict()["mirrored"] is True
    # the letter L (bar down, foot to the right) keeps its hand on the good frame and loses it on the swapped one
    L = np.array([[10.0, 10.0], [10.0, 40.0], [30.0, 40.0]])

    def turn(frame):                                        # > 0: the foot is on the reader's right, seen from above
        a, b, c = frame.to_base(L)[:, :2]
        bar, foot = b - a, c - b
        return float(bar[0] * foot[1] - bar[1] * foot[0])
    assert turn(good) > 0 > turn(bad)


def test_the_server_validation_warns_about_mirrored_probes_without_failing():
    cfg = MotionConfig(a_lat_mm_s2=2000.0, a_tan_mm_s2=1000.0, travel_speed_mm_s=100.0, approach_speed_mm_s=10.0,
                       pen_up_clearance_mm=5.0, spring_k_n_per_mm=0.4, max_spring_travel_mm=6.0, f_target_n=1.0, v_max_mm_s=40.0)
    ws = Workspace(box_min_mm=(0.0, -400.0, -50.0), box_max_mm=(560.0, 400.0, 200.0))
    pages = [Page("A4", [Stroke([(20.0, 20.0), (60.0, 20.0)])])]
    ok, _ = validate(pages, _probes(), cfg, ws)
    flipped, _ = validate(pages, _probes(swap=True), cfg, ws)
    assert "PROBE_ORDER_MIRRORED" not in {w.code for w in ok.warnings}
    assert "PROBE_ORDER_MIRRORED" in {w.code for w in flipped.warnings}
    assert flipped.stats["frame"]["mirrored"] is True
