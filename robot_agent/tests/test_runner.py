"""Job runner on the software robots (MOCK / SIM). Nothing here touches a robot.

Every number is a TEST FIXTURE. A passing test proves the software rules (refusals, stop, resume, no re-sending),
not that any physical robot can do the job.
"""
import itertools
import json

import numpy as np
import pytest

from app.services.motion.frame import build_frame
from app.services.motion.plan import MotionConfig
from app.services.motion.validate import Workspace
from app.services.stroke_ai.trajectory import Page, Stroke

from vhrs_agent.gripper import ForceLimits, SimGripper
from vhrs_agent.port import Mode, RobotError, RobotInfo
from vhrs_agent.runner import (ControllerLock, JobRunner, RunRefused, Watchdogs, authorization_token, plan_digest)
from vhrs_agent.sim import MockRobot, SimRobot

CFG = MotionConfig(a_lat_mm_s2=2000.0, a_tan_mm_s2=1000.0, travel_speed_mm_s=100.0, approach_speed_mm_s=10.0,
                   pen_up_clearance_mm=5.0, spring_k_n_per_mm=0.4, max_spring_travel_mm=6.0, f_target_n=1.0, v_max_mm_s=40.0)
WS = Workspace(box_min_mm=(0.0, -300.0, -50.0), box_max_mm=(500.0, 300.0, 200.0))
PROBES = [{"x": 300.0, "y": -105.0, "z": 20.0}, {"x": 300.0, "y": 105.0, "z": 20.0}, {"x": 3.0, "y": -105.0, "z": 20.0}]
LIMITS = ForceLimits(f_min=0.6, f_target=1.0, f_max=1.6, f_hard=4.0)
HASH = "a" * 64
FRAME = build_frame(PROBES)
START = (150.0, 0.0, 60.0)                       # 40 mm above the sheet


def pages(n_strokes=3):
    return [Page("A4", [Stroke([(20, 20 + 15 * i), (80, 20 + 15 * i)]) for i in range(n_strokes)])]


def depth(p):
    rel = np.asarray(p) - FRAME.origin
    return -(float(rel @ FRAME.normal) - float(FRAME.height(rel @ FRAME.x_axis, rel @ FRAME.y_axis)))


def grip(k=0.4, **kw):
    return SimGripper(depth, k, f_hard_n=LIMITS.f_hard, max_travel_mm=CFG.max_spring_travel_mm, **kw)


WATCHDOGS = Watchdogs(stop_settle_s=0.01, stop_window_s=0.02, stop_tolerance_mm=1.0, tracking_tolerance_mm=2.0, tracking_grace_s=0.5)


def runner(tmp_path, robot=None, gripper="default", **kw):
    robot = robot or SimRobot(START, speed_factor=None)
    g = grip() if gripper == "default" else gripper
    if robot.mode == Mode.REAL:
        kw.setdefault("watchdogs", WATCHDOGS)
    return JobRunner(robot, g, run_dir=tmp_path, limits=LIMITS, **kw), robot


def run(r, pg=None, **kw):
    return r.run(job_id=7, pages=pg or pages(), package_hash=HASH, probes=PROBES, cfg=CFG, ws=WS, **kw)


def events(tmp_path):
    out = []
    for f in sorted((tmp_path / "job7").glob("run-*.jsonl")):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    return out


# ---------------------------------------------------------------- happy paths
def test_sim_run_writes_every_stroke_in_band_and_records_everything(tmp_path):
    r, robot = runner(tmp_path)
    res = run(r)
    assert res.state == "DONE" and res.completed_strokes == res.total_strokes == 3
    assert res.force_summary["in_band_pct"] == 100.0 and res.force_summary["f_max"] == pytest.approx(1.0, abs=0.01)
    prog = json.loads((tmp_path / "job7" / "progress.json").read_text())
    assert prog["state"] == "DONE" and prog["completed"] == 3
    kinds = [e["kind"] for e in events(tmp_path)]
    assert kinds[0] == "robot_info" and "run_start" in kinds and kinds[-1] == "run_end"
    assert not (tmp_path / "agent.lock").exists()                       # the controller lock is released
    assert robot.mode == Mode.SIM


def test_dry_run_never_touches_the_paper_and_unlocks_nothing_by_itself(tmp_path):
    forces = []
    r, robot = runner(tmp_path, on_snapshot=lambda s: forces.append(s.force_n))
    res = run(r, dry_run=True)
    assert res.state == "DRY_RUN_DONE"
    assert all((f or 0.0) == 0.0 for f in forces)
    assert not any(c for c in robot.commands if "plunge" in c)
    assert json.loads((tmp_path / "job7" / "progress.json").read_text())["dry_run_ok"] in ("MOCK", "SIM")


# ---------------------------------------------------------------- REAL mode gate (a test double labelled REAL, nothing moves)
class FakeReal(SimRobot):
    mode = Mode.REAL

    def connect(self):
        self._alive = True
        return RobotInfo(Mode.REAL, "TEST DOUBLE posing as REAL (nothing moves)")


def test_real_mode_needs_the_operators_authorization_and_a_dry_run_of_the_same_plan(tmp_path):
    r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None))
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "AUTHORIZATION_REQUIRED" and robot.commands == []
    digest = plan_digest(HASH, PROBES, CFG, WS)
    token = authorization_token(7, digest)
    with pytest.raises(RunRefused) as e:
        run(r, authorization="AUTHORIZE-7-deadbeef")
    assert e.value.code == "AUTHORIZATION_REQUIRED"
    with pytest.raises(RunRefused) as e:
        run(r, authorization=token)                                       # authorised but never rehearsed
    assert e.value.code == "DRY_RUN_REQUIRED" and robot.commands == []
    assert run(r, dry_run=True, authorization=token).state == "DRY_RUN_DONE"
    assert run(r, authorization=token).state == "DONE"
    other = authorization_token(8, digest)                                # a token for another job is worthless
    with pytest.raises(RunRefused) as e:
        r.run(job_id=7, pages=pages(), package_hash=HASH, probes=PROBES, cfg=CFG, ws=WS, authorization=other)
    assert e.value.code == "AUTHORIZATION_REQUIRED"


# ---------------------------------------------------------------- refusals before any motion
def test_nothing_moves_when_validation_fails(tmp_path):
    bad = [Page("A4", [Stroke([(20, 20), (230, 20)])])]                  # outside the sheet
    r, robot = runner(tmp_path)
    with pytest.raises(RunRefused) as e:
        run(r, bad)
    assert e.value.code == "VALIDATION_FAILED" and robot.commands == []


def test_start_pose_below_the_clearance_height_is_refused_not_guessed(tmp_path):
    r, robot = runner(tmp_path, robot=SimRobot((150.0, 0.0, 22.0), speed_factor=None))
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "START_POSE_UNSAFE" and robot.commands == []


@pytest.mark.parametrize("position,code", [((150., 0., 537.), "START_OUTSIDE_WORKSPACE"),
                                          ((150., 0., 22.), "START_POSE_UNSAFE")])
def test_real_preflight_rejects_bad_start_before_authorization_or_motion(tmp_path, position, code):
    r, robot = runner(tmp_path, robot=FakeReal(position, speed_factor=None))
    with pytest.raises(RunRefused) as err:
        r.preflight(job_id=7, pages=pages(), package_hash=HASH, probes=PROBES, cfg=CFG, ws=WS,
                    dry_run=True, authorization=None)
    assert err.value.code == code and robot.commands == [] and robot.stopped == 0


def test_real_preflight_reports_adapter_start_orientation_refusal(tmp_path):
    class MisalignedReal(FakeReal):
        def check_start_ready(self):
            raise RobotError("START_ORIENTATION_MISMATCH", "wrong orientation", {"actual_deg": [-58, 13, -173]})
    r, robot = runner(tmp_path, robot=MisalignedReal(START, speed_factor=None))
    with pytest.raises(RunRefused) as err:
        r.preflight(job_id=7, pages=pages(), package_hash=HASH, probes=PROBES, cfg=CFG, ws=WS,
                    dry_run=True, authorization=None)
    assert err.value.code == "START_ORIENTATION_MISMATCH"
    assert err.value.details == {"actual_deg": [-58, 13, -173]} and robot.commands == []


def test_gripper_must_be_present_calibrated_and_at_rest(tmp_path):
    for g, code in ((grip(calibrated=False), "GRIPPER_UNCALIBRATED"),):
        r, robot = runner(tmp_path, gripper=g)
        with pytest.raises(RunRefused) as e:
            run(r)
        assert e.value.code == code and robot.commands == []
    r, robot = runner(tmp_path, gripper=None)
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "GRIPPER_REQUIRED"
    r, robot = runner(tmp_path, robot=SimRobot((150.0, 0.0, 19.0), speed_factor=None))   # pen resting pressed into the paper
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "GRIPPER_ZERO_DRIFT"


def test_multi_page_jobs_need_a_paper_change_confirmation(tmp_path):
    two = pages(1) + pages(1)
    r, _ = runner(tmp_path)
    with pytest.raises(RunRefused) as e:
        run(r, two)
    assert e.value.code == "PAPER_CHANGE_UNSUPPORTED"
    asked = []
    r, _ = runner(tmp_path / "b", wait_for_paper=lambda p: asked.append(p) or True)
    assert run(r, two).state == "DONE" and asked == [1]
    r, robot = runner(tmp_path / "c", wait_for_paper=lambda p: False)
    assert run(r, two).state == "STOPPED"


def test_only_one_controller_at_a_time(tmp_path):
    r, robot = runner(tmp_path)
    with ControllerLock(tmp_path / "agent.lock"):
        with pytest.raises(RunRefused) as e:
            run(r)
    assert e.value.code == "CONTROLLER_BUSY" and robot.commands == []
    assert run(r).state == "DONE"                                        # and it is free again afterwards


# ---------------------------------------------------------------- stop, faults, recovery
class StopAfter(SimGripper):
    """Asks the runner to stop after N observed points (an operator pressing STOP during a stroke)."""

    def __init__(self, n, holder, **kw):
        super().__init__(depth, 0.4, f_hard_n=4.0, max_travel_mm=6.0, **kw)
        self.n, self.holder, self.count = n, holder, 0

    def observe(self, tcp):
        super().observe(tcp)
        self.count += 1
        if self.count == self.n:
            self.holder["r"].stop("operator pressed STOP")


def test_stop_mid_job_records_the_interrupted_stroke_and_never_restarts_from_zero(tmp_path):
    holder = {}
    g = StopAfter(400, holder)                                              # inside the second stroke
    r, robot = runner(tmp_path, gripper=g)
    holder["r"] = r
    res = run(r)
    assert res.state == "STOPPED" and res.interrupted_stroke is not None and robot.stopped >= 1
    done, cut = res.completed_strokes, res.interrupted_stroke
    assert done == cut and done < 3
    prog = json.loads((tmp_path / "job7" / "progress.json").read_text())
    assert prog["state"] == "STOPPED" and prog["completed"] == done

    r2, robot2 = runner(tmp_path)
    with pytest.raises(RunRefused) as e:
        run(r2)                                                          # no explicit decision: refused
    assert e.value.code == "PARTIAL_JOB_EXISTS" and robot2.commands == []
    with pytest.raises(RunRefused) as e:
        run(r2, resume_from=0)                                           # would overwrite what is already written
    assert e.value.code == "PARTIAL_JOB_EXISTS"
    res2 = run(r2, resume_from=done + 1)                                 # the operator inspected the sheet: skip the cut stroke
    assert res2.state == "DONE" and res2.completed_strokes == 3
    written = [e["stroke"] for e in events(tmp_path) if e["kind"] == "command" and e["move"] == "write"]
    assert written.count(0) == 1                                          # stroke 0 was written once, never again
    assert robot2.commands


def test_over_force_stops_at_once_and_reports_it(tmp_path):
    r, robot = runner(tmp_path, gripper=grip(k=3.0))                     # a far too stiff spring model
    res = run(r)
    assert res.state == "FAULT" and res.fault == "OVER_FORCE" and robot.stopped >= 1
    assert res.completed_strokes == 0 and res.interrupted_stroke == 0


def test_lost_sensor_data_stops_the_job(tmp_path):
    r, robot = runner(tmp_path, gripper=grip(silent_after=800))
    res = run(r)
    assert res.state == "FAULT" and res.fault == "SENSOR_LOST" and robot.stopped >= 1


def test_loss_of_contact_pauses_instead_of_writing_in_the_air(tmp_path):
    tick = itertools.count()
    r, robot = runner(tmp_path, gripper=grip(k=0.01), clock=lambda: next(tick) * 0.001)
    ev = []
    r.on_snapshot = lambda s: (ev.append(s.state), r.stop("operator ends the test") if s.state == "PAUSED" else None)
    res = run(r)
    assert "PAUSED" in ev and res.state in ("STOPPED", "FAULT") and res.completed_strokes == 0


def test_lost_link_marks_the_outcome_unknown_and_nothing_is_resent(tmp_path):
    r, robot = runner(tmp_path, robot=SimRobot(START, speed_factor=None, fail_after_s=0.5))
    res = run(r)
    assert res.state == "UNKNOWN"
    n = len(robot.commands)
    r2, robot2 = runner(tmp_path)
    with pytest.raises(RunRefused) as e:
        run(r2)
    assert e.value.code == "OUTCOME_UNKNOWN" and robot2.commands == [] and len(robot.commands) == n
    with pytest.raises(RunRefused) as e:
        run(r2, confirm_unknown=True)                                    # still has to say where to continue
    assert e.value.code == "PARTIAL_JOB_EXISTS"


def test_mock_robot_exercises_the_flow_instantly(tmp_path):
    r, robot = runner(tmp_path, robot=MockRobot(START))
    r.robot.mode  # MOCK
    assert run(r).state == "DONE"


def test_real_mode_refuses_without_measured_watchdog_thresholds(tmp_path):
    r, robot = runner(tmp_path, robot=FakeReal(START, speed_factor=None), watchdogs=Watchdogs())
    with pytest.raises(RunRefused) as e:
        run(r)
    assert e.value.code == "WATCHDOG_UNCONFIGURED" and robot.commands == []


def test_a_dry_run_never_touches_the_record_of_what_is_on_the_paper(tmp_path):
    r, robot = runner(tmp_path)
    assert run(r).state == "DONE"
    before = json.loads((tmp_path / "job7" / "progress.json").read_text())
    r2, _ = runner(tmp_path)
    assert run(r2, dry_run=True).state == "DRY_RUN_DONE"
    after = json.loads((tmp_path / "job7" / "progress.json").read_text())
    assert after["state"] == "DONE" and after["completed"] == before["completed"] == 3     # still DONE; only "rehearsed" is noted
    assert after["dry_run_ok"] in ("MOCK", "SIM")
    r3, robot3 = runner(tmp_path)
    with pytest.raises(RunRefused) as e:
        run(r3)                                                                       # writing again would overdraw the finished sheet
    assert e.value.code == "JOB_ALREADY_WRITTEN" and robot3.commands == []


def test_a_dry_run_after_a_stopped_job_keeps_the_interrupted_stroke_on_record(tmp_path):
    holder = {}
    g = StopAfter(400, holder)
    r, robot = runner(tmp_path, gripper=g)
    holder["r"] = r
    assert run(r).state == "STOPPED"
    before = json.loads((tmp_path / "job7" / "progress.json").read_text())
    r2, _ = runner(tmp_path)
    assert run(r2, dry_run=True).state == "DRY_RUN_DONE"
    after = json.loads((tmp_path / "job7" / "progress.json").read_text())
    assert after["state"] == "STOPPED" and after["completed"] == before["completed"] and after["interrupted"] == before["interrupted"]


@pytest.mark.parametrize("dry_run", [True, False])
def test_rejected_robot_command_ends_in_fault_and_never_approves_dry_run(tmp_path, dry_run):
    class RejectingRobot(SimRobot):
        def execute(self, *args, **kwargs):
            self.commands.append("rejected")
            raise RobotError("SDK_ERROR", "ServoCart trả mã lỗi 14; lỗi controller: [1, 28]", {"code": 14})

    r, robot = runner(tmp_path, robot=RejectingRobot(START, speed_factor=None))
    res = run(r, dry_run=dry_run)
    assert res.state == r.snap.state == "FAULT" and res.fault == "SDK_ERROR"
    assert res.completed_strokes == 0 and robot.commands == ["rejected"] and robot.stopped >= 1
    assert "[1, 28]" in r.snap.message
    assert not (tmp_path / "agent.lock").exists()
    ev = events(tmp_path)
    assert any(e["kind"] == "robot_error" and e["details"] == {"code": 14} for e in ev)
    assert ev[-1]["kind"] == "run_end" and ev[-1]["state"] == "FAULT"
    progress = tmp_path / "job7" / "progress.json"
    if dry_run:
        assert not progress.exists()  # failed rehearsal must not certify any mode
    else:
        assert json.loads(progress.read_text())["state"] == "FAULT"
