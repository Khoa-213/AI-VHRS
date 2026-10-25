"""Server-side re-validation of the simulation result (Service F): the server does not take the workstation's word.

Real database (like test_api_technician.py). The calibration numbers are TEST FIXTURES, not measurements of any robot.
"""
import json
from types import SimpleNamespace

from app.core.config import get_settings
from tests.test_api_orders import _sql
from tests.test_api_technician import CAL, _err, _job, _post, T
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401

MOTION = {"a_lat_mm_s2": 2000.0, "a_tan_mm_s2": 1000.0, "travel_speed_mm_s": 100.0, "approach_speed_mm_s": 10.0,
          "pen_up_clearance_mm": 5.0, "spring_k_n_per_mm": 0.4, "max_spring_travel_mm": 6.0}
BIG_BOX = {"box_min_mm": [-100, -100, -50], "box_max_mm": [600, 600, 200]}


def _report(jid):
    return json.loads(_sql("select simulation_report::text from production_jobs where id=:j", j=jid))


def _cal(**over):
    block = {"schema": "vhrs-motion/1", "motion": MOTION, "workspace": BIG_BOX}
    block.update(over)
    return {**CAL, "frame_transform": block}


def _prepared(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _post(client, tech, jid, "prepare", status=200)
    return jid


def test_server_overrules_a_client_that_says_the_simulation_passed(client, cust, staff, mgr, wcat, robot, tech):
    jid = _prepared(client, cust, staff, mgr, wcat, robot, tech)
    tight = {"box_min_mm": [0, 0, 0], "box_max_mm": [5, 5, 5]}             # the sheet cannot fit
    _post(client, tech, jid, "calibration", _cal(workspace=tight), status=201)
    r = _post(client, tech, jid, "simulation", {"passed": True}, status=200).json()
    assert r["simulation_passed"] is False
    rep = _report(jid)
    assert rep["server_validation"]["status"] == "FAIL"
    assert any("OUTSIDE_WORKSPACE" in e or "OUT_OF_REACH" in e for e in rep["errors"])
    assert _err(_post(client, tech, jid, "start", status=409)) == "SIMULATION_FAILED"


def test_server_validation_passes_a_consistent_calibration(client, cust, staff, mgr, wcat, robot, tech):
    jid = _prepared(client, cust, staff, mgr, wcat, robot, tech)
    _post(client, tech, jid, "calibration", _cal(), status=201)
    r = _post(client, tech, jid, "simulation", {"passed": True}, status=200).json()
    sv = _report(jid)["server_validation"]
    assert sv["status"] == "PASS", sv
    assert sv["checks"]["joint_reachability_ik"] == "NOT_CHECKED"          # honest about what the server cannot see
    assert r["simulation_passed"] is True
    _post(client, tech, jid, "start", status=200)


def test_missing_measured_values_fail_the_server_validation(client, cust, staff, mgr, wcat, robot, tech):
    jid = _prepared(client, cust, staff, mgr, wcat, robot, tech)
    _post(client, tech, jid, "calibration", _cal(motion={"a_lat_mm_s2": 2000.0}), status=201)
    r = _post(client, tech, jid, "simulation", {"passed": True}, status=200).json()
    assert r["simulation_passed"] is False
    assert any("UNCONFIGURED" in e for e in _report(jid)["errors"])


def test_legacy_calibration_without_the_block_still_works_unless_required(client, cust, staff, mgr, wcat, robot, tech,
                                                                          monkeypatch):
    jid = _prepared(client, cust, staff, mgr, wcat, robot, tech)
    _post(client, tech, jid, "calibration", CAL, status=201)
    real = get_settings()
    import app.services.technician as svc
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(motion_validation_required=True))
    r = _post(client, tech, jid, "simulation", {"passed": True}, status=200).json()
    assert r["simulation_passed"] is False
    assert any("MOTION_BLOCK_MISSING" in e for e in _report(jid)["errors"])
    monkeypatch.setattr(svc, "get_settings", lambda: real)
    r = _post(client, tech, jid, "simulation", {"passed": True}, status=200).json()
    assert r["simulation_passed"] is True and _report(jid)["server_validation"] == {"status": "NOT_RUN"}
