"""Alerts, run reporting and the watchdogs that look at what the robot REALLY does. Software robots and a fake backend only.

A passing test shows the software raises the right alert and tells the operator the right thing; it does not show that a
physical robot stops or that a person presses the emergency stop in time.
"""
import itertools
import time

import numpy as np
import pytest

from vhrs_agent.bridge import BridgeError
from vhrs_agent.ops import FALLBACK, OpsReporter
from vhrs_agent.port import Mode, RobotInfo
from vhrs_agent.runner import RunRefused
from vhrs_agent.sim import SimRobot
from test_runner import (CFG, HASH, LIMITS, PROBES, START, WATCHDOGS, WS, FakeReal, StopAfter, grip, pages, run, runner)


class FakeBridge:
    """What the backend would record. `catalog` plays the part of alert_catalog (level and wording decided there)."""

    def __init__(self, fail_open=False, fail_alert=False):
        self.runs, self.closed, self.alerts, self.beats, self.events = [], [], [], [], []
        self.fail_open, self.fail_alert = fail_open, fail_alert

    def open_run(self, job_id, **kw):
        if self.fail_open:
            raise BridgeError(503, "DOWN", "backend down")
        self.runs.append((job_id, kw))
        return {"id": len(self.runs)}

    def close_run(self, run_id, **kw):
        self.closed.append((run_id, kw))
        return {}

    def alert(self, robot_id, code, **kw):
        if self.fail_alert:
            raise BridgeError(503, "DOWN", "backend down")
        self.alerts.append((robot_id, code, kw))
        return {"id": len(self.alerts), "level": FALLBACK[code]["level"] + (0 if code != "OVER_FORCE" else 0),
                "title_vi": "từ máy chủ: " + FALLBACK[code]["title_vi"], "action_vi": FALLBACK[code]["action_vi"],
                "estop_advised": FALLBACK[code]["level"] == 4}

    def heartbeat(self, robot_id, **kw):
        self.beats.append((robot_id, kw))
        return {}

    def event(self, job_id, kind, **kw):
        self.events.append((job_id, kind, kw))
        return {}


def with_ops(tmp_path, robot=None, gripper="default", bridge=None, **kw):
    bridge = bridge or FakeBridge()
    r, rb = runner(tmp_path, robot=robot, gripper=gripper, bridge=bridge, ops=OpsReporter(bridge, robot_id=5, heartbeat_every_s=0.01), **kw)
    return r, rb, bridge


def codes(b):
    return [c for _, c, _ in b.alerts]


# ---------------------------------------------------------------- run reporting
def test_a_run_is_opened_before_motion_closed_after_and_the_heartbeat_runs(tmp_path):
    r, robot, b = with_ops(tmp_path)
    res = run(r)
    assert res.state == "DONE"
    (job, opened), = b.runs
    assert job == 7 and opened["mode"] == "SIM" and opened["dry_run"] is False and opened["authorized"] is False
    assert opened["total_strokes"] == 3 and opened["robot_info"]["mode"] == "SIM" and opened["agent_version"]
    (key, closed), = b.closed
    assert key == opened["run_id"] and closed["result"] == "DONE" and closed["completed_strokes"] == 3
    assert closed["summary"]["in_band_pct"] == 100.0 and closed["summary"]["duration_s"] >= 0
    assert b.beats and b.beats[0][0] == 5 and b.beats[0][1]["mode"] == "SIM"
    n = len(b.beats)
    time.sleep(0.05)
    assert len(b.beats) == n                                              # the heartbeat stops with the run


def test_a_start_pose_refusal_closes_the_opened_run_as_refused_and_raises_a_level_2_alert(tmp_path):
    r, robot, b = with_ops(tmp_path, robot=SimRobot((150.0, 0.0, 22.0), speed_factor=None))
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "START_POSE_UNSAFE" and robot.commands == []
    (key, closed), = b.closed
    assert closed["result"] == "REFUSED" and "START_POSE_UNSAFE" in closed["summary"]["reason"]
    assert codes(b) == ["PREFLIGHT_REFUSED"] and r.snap.level == 2 and r.snap.state == "REFUSED"


def test_preflight_refusal_reaches_the_backend(tmp_path):
    from app.services.stroke_ai.trajectory import Page, Stroke
    bad = [Page("A4", [Stroke([(20, 20), (230, 20)])])]
    r, robot, b = with_ops(tmp_path)
    with pytest.raises(RunRefused):
        run(r, bad)
    assert codes(b) == ["PREFLIGHT_REFUSED"] and b.runs[0][1]["refused_reason"].startswith("VALIDATION_FAILED")
    assert r.snap.alerts[0]["level"] == 2 and r.snap.level == 2 and robot.commands == []


def test_real_mode_does_not_start_if_the_backend_cannot_record_the_run(tmp_path):
    from vhrs_agent.runner import authorization_token, plan_digest
    r, robot, b = with_ops(tmp_path, robot=FakeReal(START, speed_factor=None), bridge=FakeBridge(fail_open=True))
    token = authorization_token(7, plan_digest(HASH, PROBES, CFG, WS))
    with pytest.raises(RunRefused) as e:
        run(r, dry_run=True, authorization=token)
    assert e.value.code == "BACKEND_UNREACHABLE" and robot.commands == []


def test_real_run_is_announced_to_the_backend_as_authorized(tmp_path):
    from vhrs_agent.runner import authorization_token, plan_digest
    r, robot, b = with_ops(tmp_path, robot=FakeReal(START, speed_factor=None))
    token = authorization_token(7, plan_digest(HASH, PROBES, CFG, WS))
    assert run(r, dry_run=True, authorization=token).state == "DRY_RUN_DONE"
    assert run(r, authorization=token).state == "DONE"
    dry, real = b.runs[0][1], b.runs[1][1]
    assert dry["mode"] == real["mode"] == "REAL" and dry["dry_run"] is True and real["dry_run"] is False
    assert dry["authorized"] is True and real["authorized"] is True and real["plan_digest"] == plan_digest(HASH, PROBES, CFG, WS)


def test_sim_continues_offline_when_the_backend_is_down(tmp_path):
    r, robot, b = with_ops(tmp_path, bridge=FakeBridge(fail_open=True, fail_alert=True))
    assert run(r).state == "DONE"                                         # SIM/MOCK do not depend on the network


# ---------------------------------------------------------------- alerts raised by faults
def test_over_force_raises_the_backends_alert_and_shows_its_wording(tmp_path):
    r, robot, b = with_ops(tmp_path, gripper=grip(k=3.0))
    res = run(r)
    assert res.fault == "OVER_FORCE" and "OVER_FORCE" in codes(b)
    a = next(a for a in r.snap.alerts if a["code"] == "OVER_FORCE")
    assert a["level"] == 3 and a["title_vi"].startswith("từ máy chủ") and a["source"] == "backend"
    assert b.closed[-1][1]["result"] == "FAULT" and b.closed[-1][1]["summary"]["fault"] == "OVER_FORCE"


def test_a_red_alert_is_still_shown_locally_when_the_network_is_down(tmp_path):
    r, robot, b = with_ops(tmp_path, gripper=grip(k=3.0), bridge=FakeBridge(fail_alert=True))
    run(r)
    a = next(a for a in r.snap.alerts if a["code"] == "OVER_FORCE")
    assert a["source"] == "local" and a["level"] == 3 and "kiểm tra" in a["action_vi"].lower()
    r2 = type(r.ops)(None, robot_id=None).alert("STOP_NOT_EFFECTIVE", job_id=None, run_id=None)
    assert r2["level"] == 4 and r2["estop_advised"] is True and "E-STOP" in r2["action_vi"]


def test_lost_link_during_motion_is_red_and_the_outcome_unknown_is_orange(tmp_path):
    r, robot, b = with_ops(tmp_path, robot=SimRobot(START, speed_factor=None, fail_after_s=0.5))
    res = run(r)
    assert res.state == "UNKNOWN" and {"LINK_LOST_MOVING", "RUN_OUTCOME_UNKNOWN"} <= set(codes(b))
    assert r.snap.level == 4
    assert b.closed[-1][1]["result"] == "UNKNOWN"


def test_operator_stop_mid_stroke_reports_the_interrupted_stroke(tmp_path):
    holder = {}
    g = StopAfter(400, holder)
    r, robot, b = with_ops(tmp_path, gripper=g)
    holder["r"] = r
    res = run(r)
    assert res.state == "STOPPED" and "STROKE_INTERRUPTED" in codes(b)
    assert b.closed[-1][1]["result"] == "STOPPED" and r.snap.level == 3


# ---------------------------------------------------------------- watchdogs that look at the real robot
class Runaway(SimRobot):
    """Ignores the stop command: after stop() the tip keeps drifting 5 mm per look. A test double for the dangerous case."""

    def stop(self):
        super().stop()
        self._runaway = True

    def read_tcp(self):
        if getattr(self, "_runaway", False):
            self._pos = self._pos + np.array([5.0, 0.0, 0.0])
        return self._pos.copy()


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while not cond() and time.time() < end:
        time.sleep(0.02)
    return cond()


def test_a_robot_that_keeps_moving_after_the_stop_command_raises_the_red_alert(tmp_path):
    r, robot, b = with_ops(tmp_path, robot=Runaway(START, speed_factor=None), watchdogs=WATCHDOGS)
    r.stop("operator pressed STOP")                                       # a stop outside a run is enough to start the check
    assert wait_for(lambda: "STOP_NOT_EFFECTIVE" in codes(b))
    a = next(a for a in r.snap.alerts if a["code"] == "STOP_NOT_EFFECTIVE")
    assert a["level"] == 4 and a["estop_advised"] and r.snap.state == "DANGER" and r.snap.level == 4


def test_a_robot_that_stands_still_after_the_stop_command_raises_nothing(tmp_path):
    r, robot, b = with_ops(tmp_path, robot=SimRobot(START, speed_factor=None), watchdogs=WATCHDOGS)
    r.stop("operator pressed STOP")
    time.sleep(0.15)
    assert "STOP_NOT_EFFECTIVE" not in codes(b) and r.snap.level == 1


class Drifting(SimRobot):
    """The real pen position is 20 mm away from where it was told to be."""

    def read_tcp(self):
        return self._pos + np.array([0.0, 0.0, 20.0])


def test_a_pen_that_is_not_where_it_was_told_to_be_stops_the_job_with_a_red_alert(tmp_path):
    tick = itertools.count()
    r, robot, b = with_ops(tmp_path, robot=Drifting(START, speed_factor=None), clock=lambda: next(tick) * 0.01)
    r.watchdogs = WATCHDOGS
    res = run(r)
    assert res.state == "FAULT" and res.fault == "TRACKING_ERROR" and "TRACKING_ERROR" in codes(b)
    assert r.snap.level == 4 and robot.stopped >= 1


class Unhealthy(SimRobot):
    """The link is fine but the controller reports an error (or an emergency stop) once motion has started."""

    def heartbeat(self):
        return not getattr(self, "_started", False) and super().heartbeat()

    def execute(self, points_mm, speeds_mm_s, ctl, on_tcp):
        self._started = True
        super().execute(points_mm, speeds_mm_s, ctl, on_tcp)


def test_a_controller_error_during_motion_is_a_red_alert(tmp_path):
    tick = itertools.count()
    r, robot, b = with_ops(tmp_path, robot=Unhealthy(START, speed_factor=None), clock=lambda: next(tick) * 0.5)
    r.watchdogs = WATCHDOGS
    res = run(r)
    assert res.fault == "CONTROLLER_SAFETY_FAULT" and "CONTROLLER_SAFETY_FAULT" in codes(b) and r.snap.level == 4


# ---------------------------------------------------------------- the offline wording
def test_every_red_sentence_tells_the_operator_to_press_the_estop():
    reds = [c for c, v in FALLBACK.items() if v["level"] == 4]
    assert set(reds) == {"STOP_NOT_EFFECTIVE", "LINK_LOST_MOVING", "TRACKING_ERROR", "CONTROLLER_SAFETY_FAULT", "OVER_FORCE_STILL"}
    assert all("E-STOP" in FALLBACK[c]["action_vi"] for c in reds)
    assert not any("E-STOP" in v["action_vi"] for v in FALLBACK.values() if v["level"] < 4)
