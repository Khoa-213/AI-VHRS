"""Audit 2026-11-27, package G2 (BE/docs/audit/05_ISSUES_AND_RECOMMENDATIONS.md): robot safety on the agent side.

RB-02  REAL needs the workstation's own hard limits (lowest pen height, largest spring press) and a fourth probe point
RB-03  a watchdog set to an absurd value counts as not configured
RB-05  identify / preflight hold the agent like a run; the "did it really stop?" check finishes before the connection is closed
RB-06  a rehearsal of a new plan is recorded when nothing of the old plan is on the paper
RB-07  an unexpected error inside a controller-planned move stops the arm
TP-09  REAL refuses probe points turned the wrong way (the writing would be a mirror image)

Test doubles only: nothing moves, no hardware, no network.
"""
import threading
import types

import numpy as np
import pytest

from test_runner import (CFG, HASH, PROBES, START, STATION, WATCHDOGS, WS, FakeReal, pages, run, runner)
from test_server_api import auth, make
from vhrs_agent.linear_motion import LinearExecutor
from vhrs_agent.port import Control
from vhrs_agent.runner import ProgressStore, RunRefused, StationLimits, Watchdogs, authorization_token, plan_digest
from vhrs_agent.server import ApiError


def _refusal(r, **kw):
    with pytest.raises(RunRefused) as e:
        run(r, **kw)
    return e.value


def _token(probes=PROBES, cfg=CFG):
    return authorization_token(7, plan_digest(HASH, probes, cfg, WS))


# ---------------------------------------------------------------------------------------------- RB-02
def test_real_refuses_without_the_workstations_own_hard_limits(tmp_path):
    for station in (None, StationLimits(), StationLimits(z_floor_mm=15.0), StationLimits(z_floor_mm=15.0, max_press_mm=0.0)):
        r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None), station=station)
        assert _refusal(r, authorization=_token()).code == "STATION_LIMITS_UNCONFIGURED", station
        assert robot.commands == []


def test_real_needs_a_fourth_probe_point_because_three_always_fit_a_plane(tmp_path):
    r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None))
    with pytest.raises(RunRefused) as e:
        r.run(job_id=7, pages=pages(), package_hash=HASH, probes=PROBES[:3], cfg=CFG, ws=WS, authorization=_token(PROBES[:3]))
    assert e.value.code == "PROBE_CHECK_POINT_REQUIRED" and robot.commands == []
    sim, _ = runner(tmp_path / "sim")                                  # a simulated station may keep three points
    assert sim.run(job_id=7, pages=pages(), package_hash=HASH, probes=PROBES[:3], cfg=CFG, ws=WS).state == "DONE"


def test_real_refuses_a_plan_that_goes_below_the_floor_or_presses_too_hard(tmp_path):
    # every probe mistyped 10 mm too low: the points still fit one plane, so only the workstation's own floor can notice
    low = [{**p, "z": p["z"] - 10.0} for p in PROBES]
    r, robot = runner(tmp_path / "low", robot=FakeReal(START, speed_factor=None))
    with pytest.raises(RunRefused) as e:
        r.run(job_id=7, pages=pages(), package_hash=HASH, probes=low, cfg=CFG, ws=WS, authorization=_token(low))
    assert e.value.code == "BELOW_Z_FLOOR" and e.value.details["z_floor_mm"] == STATION.z_floor_mm and robot.commands == []

    r, robot = runner(tmp_path / "press", robot=FakeReal(START, speed_factor=None), station=StationLimits(z_floor_mm=15.0, max_press_mm=2.0))
    err = _refusal(r, authorization=_token())                           # CFG presses 2.5 mm
    assert err.code == "PRESS_ABOVE_STATION_LIMIT" and robot.commands == []


# ---------------------------------------------------------------------------------------------- TP-09
def test_real_refuses_probe_points_turned_the_wrong_way(tmp_path):
    mirrored = [PROBES[1], PROBES[0], PROBES[3], PROBES[2]]             # top-left and top-right swapped (and the row below)
    r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None))
    with pytest.raises(RunRefused) as e:
        r.run(job_id=7, pages=pages(), package_hash=HASH, probes=mirrored, cfg=CFG, ws=WS, authorization=_token(mirrored))
    assert e.value.code == "PROBE_ORDER_MIRRORED" and robot.commands == []


# ---------------------------------------------------------------------------------------------- RB-03
def test_a_watchdog_set_to_an_absurd_value_is_a_watchdog_switched_off(tmp_path):
    assert WATCHDOGS.configured() and WATCHDOGS.problems() == []
    off = Watchdogs(stop_settle_s=0.3, stop_window_s=0.5, stop_tolerance_mm=1.0, tracking_tolerance_mm=1e9, tracking_grace_s=0.5)
    assert not off.configured() and any("tracking_tolerance_mm" in p for p in off.problems())
    assert not Watchdogs(stop_settle_s=0.3, stop_window_s=3600.0, stop_tolerance_mm=1.0, tracking_tolerance_mm=2.0,
                         tracking_grace_s=0.5).configured()
    r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None), watchdogs=off)
    err = _refusal(r, authorization=_token())
    assert err.code == "WATCHDOG_UNCONFIGURED" and any("tracking_tolerance_mm" in p for p in err.details) and robot.commands == []


# ---------------------------------------------------------------------------------------------- RB-06
def test_a_rehearsal_of_a_new_plan_is_recorded_when_nothing_is_on_the_paper(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.mark_dry_run_ok(7, "old-plan", "REAL", "sig-1")
    store.mark_dry_run_ok(7, "new-plan", "REAL", "sig-2")              # recalibrated: a new plan, rehearsed again
    cur = store.load()
    assert (cur["digest"], cur["dry_run_ok"], cur["execution_signature"], cur["completed"]) == ("new-plan", "REAL", "sig-2", 0)

    store.mark_dry_run_ok(7, "sim-plan", "SIM", None)                  # same rule for a simulator rehearsal of yet another plan
    assert store.load()["digest"] == "sim-plan" and store.load()["dry_run_ok"] == "SIM"


@pytest.mark.parametrize("state,completed", [("STOPPED", 3), ("RUNNING", 0), ("UNKNOWN", 0), ("FAULT", 2), ("DONE", 5)])
def test_a_rehearsal_never_rewrites_the_record_of_ink_on_the_paper(tmp_path, state, completed):
    store = ProgressStore(tmp_path / "progress.json")
    before = {"digest": "old-plan", "job_id": 7, "state": state, "completed": completed, "interrupted": None, "dry_run_ok": "REAL"}
    store.save(before)
    store.mark_dry_run_ok(7, "new-plan", "REAL", "sig-2")
    assert store.load() == before


# ---------------------------------------------------------------------------------------------- RB-05
def test_the_stop_check_finishes_before_the_caller_may_disconnect(tmp_path):
    slow = Watchdogs(stop_settle_s=0.15, stop_window_s=0.15, stop_tolerance_mm=1.0, tracking_tolerance_mm=2.0, tracking_grace_s=0.5)
    r, robot = runner(tmp_path, watchdogs=slow)
    robot.connect()
    seen = []
    real_read = robot.read_tcp
    robot.read_tcp = lambda: (seen.append(threading.current_thread().name), real_read())[1]
    r.stop("operator pressed STOP")
    assert r._verify_thread is not None and r._verify_thread.is_alive()      # still looking at the robot
    r.wait_stop_verified()
    assert not r._verify_thread.is_alive() and len(seen) == 2               # both looks happened while the connection was still ours
    r.wait_stop_verified()                                                   # calling it again, or with nothing to wait for, is harmless
    idle, _ = runner(tmp_path / "idle")
    idle.wait_stop_verified()


def test_preflight_and_identify_hold_the_agent_so_a_run_cannot_start_in_between(tmp_path):
    svc, c, _ = make(tmp_path)
    assert c.post("/api/jobs/12/load", headers=auth()).status_code == 200
    busy_during = []
    real_factory = svc.robot_factory

    def spying(mode):
        busy_during.append(svc._busy)
        return real_factory(mode)
    svc.robot_factory = spying
    assert c.post("/api/jobs/12/preflight", headers=auth(), json={"mode": "sim"}).json()["ok"] is True
    svc.do_identify("sim")
    assert busy_during == [True, True] and svc._busy is False               # held while working, released afterwards

    svc._busy = True                                                        # something else holds the agent
    for call in (lambda: svc.do_identify("sim"), lambda: svc.do_preflight(svc.jobs[12], "sim", "t")):
        with pytest.raises(ApiError) as e:
            call()
        assert e.value.code == "AGENT_BUSY"
    assert svc._busy is True                                                # a refused caller never releases somebody else's hold


# ---------------------------------------------------------------------------------------------- RB-07
def test_an_unexpected_error_inside_a_linear_move_stops_the_arm():
    stops = []

    def broken_pose():
        raise TypeError("a bug, not a robot fault")
    robot = types.SimpleNamespace(cfg=types.SimpleNamespace(speed_cap_mm_s=10.0, linear_max_segment_mm=5.0),
                                  _read_aligned_pose=broken_pose, stop=lambda: stops.append("stop"))
    points = np.array([[300.0, 0.0, 25.0], [302.0, 0.0, 25.0]])
    with pytest.raises(TypeError):
        LinearExecutor(robot).execute(points, np.array([5.0, 5.0]), Control(), lambda p, t: None)
    assert stops == ["stop"]

    def failing_stop():
        stops.append("stop tried")
        raise OSError("the stop channel is down too")
    robot.stop = failing_stop
    with pytest.raises(TypeError):                                           # the original error is not hidden by the failed stop
        LinearExecutor(robot).execute(points, np.array([5.0, 5.0]), Control(), lambda p, t: None)
    assert stops[-1] == "stop tried"
