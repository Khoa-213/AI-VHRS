"""Joint-level simulation with the vendor's FR3 V6 URDF solved by PyBullet, and the web API that serves it to the 3D viewer.

Needs PyBullet (the `.simenv` environment) and the model files (`scripts/fetch_fr3_model.py`); skipped otherwise.
The tool length and the sheet position are TEST FIXTURES, not measurements of the workshop's robot.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("pybullet")
from vhrs_agent.kinematics import DEFAULT_URDF, FR3Kinematics, READY_POSE_DEG      # noqa: E402

if not DEFAULT_URDF.exists():                                                        # pragma: no cover
    pytest.skip("FR3 model not fetched (scripts/fetch_fr3_model.py)", allow_module_level=True)

from app.services.motion.frame import build_frame                                    # noqa: E402
from app.services.stroke_ai.trajectory import Page, Stroke                          # noqa: E402
from vhrs_agent.cli import DEMO_CFG, DEMO_LIMITS, DEMO_PROBES, DEMO_START, DEMO_WS    # noqa: E402
from vhrs_agent.gripper import SimGripper                                           # noqa: E402
from vhrs_agent.runner import JobRunner, RunRefused                                  # noqa: E402
from vhrs_agent.sim_pybullet import PyBulletSimRobot                                 # noqa: E402
from vhrs_agent.viewer import ViewerHub, create_app                                  # noqa: E402

TOOL = 250.0


@pytest.fixture(scope="module")
def kin():
    k = FR3Kinematics(tool_offset_mm=TOOL, table_z_mm=19.0)
    yield k
    k.close()


def test_the_joint_limits_come_from_the_vendors_urdf(kin):
    got = [(round(a), round(b)) for a, b in kin.limits_deg]
    assert got == [(-175, 175), (-265, 85), (-162, 162), (-265, 85), (-175, 175), (-175, 175)]


@pytest.mark.parametrize("tcp", [[-300, 0, 20], [-300, -105, 20], [-250, 105, 25], [-400, 0, 80], [-460, 60, 20]])
def test_inverse_kinematics_hits_the_target_with_the_pen_pointing_down(kin, tcp):
    r = kin.ik(tcp)
    assert r.joints_deg is not None and r.error_mm < 0.01 and r.tilt_deg < 0.1
    pos, axis = kin.fk(r.joints_deg)
    assert np.linalg.norm(pos - np.array(tcp)) < 0.01 and axis[2] < -0.9999
    assert kin.margin_to_limits_deg(r.joints_deg) > 5.0


def test_points_the_arm_cannot_reach_are_refused_not_approximated(kin):
    assert kin.ik([-100, 0, 20]).joints_deg is None            # too close to the base
    assert kin.ik([-760, 0, 20]).joints_deg is None            # beyond the reach
    assert kin.ik([0, 0, 600]).joints_deg is None


def test_a_straight_line_is_solved_on_one_branch_and_a_tight_jump_limit_flags_it(kin):
    pts = np.array([[-300.0, -60.0 + 5.0 * i, 20.0] for i in range(25)])
    problems, joints = kin.check_path(pts)
    assert problems == [] and not np.isnan(joints).any()
    assert float(np.max(np.abs(np.diff(joints, axis=0)))) < 5.0                 # continuous: no branch jump
    problems, _ = kin.check_path(pts, max_jump_deg=0.01)
    assert problems and "jump" in problems[0]


def test_long_pen_up_moves_are_checked_along_the_way(kin):
    assert len(kin.densify(np.array([[-300.0, 0, 50], [-300.0, 100, 50]]))) == 21


def test_a_tool_too_short_for_the_flange_pokes_into_the_table(kin):
    short = FR3Kinematics(tool_offset_mm=100.0, table_z_mm=19.0)
    problems, _ = short.check_path(np.array([[-300.0, 0.0, 17.5]]))
    assert any("table" in p for p in problems)
    short.close()


def test_the_controller_comparison_helper_reports_the_difference(kin):
    q = READY_POSE_DEG
    pos, _ = kin.fk(q)
    ok = kin.verify_against_controller(q, pos + np.array([0.5, 0, 0]))
    assert ok["within_tolerance"] and ok["error_mm"] == 0.5
    bad = kin.verify_against_controller(q, pos + np.array([40.0, 0, 0]))
    assert not bad["within_tolerance"]


# ---------------------------------------------------------------- the simulated robot in a real run
def _plan_pages():
    return [Page("A5", [Stroke([(20, 20), (80, 20)]), Stroke([(20, 40), (80, 60)])])]


def _runner(tmp_path, kin, **kw):
    frame = build_frame(DEMO_PROBES)

    def depth(p):
        rel = np.asarray(p) - frame.origin
        return -(float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis)))

    robot = PyBulletSimRobot(kin, DEMO_START, speed_factor=None)
    runner = JobRunner(robot, SimGripper(depth, 0.4, DEMO_LIMITS.f_hard, DEMO_CFG.max_spring_travel_mm), run_dir=tmp_path,
                       limits=DEMO_LIMITS, **kw)
    return runner, robot


def test_a_run_with_the_joint_model_reports_joint_angles_that_follow_the_pen(tmp_path, kin):
    seen = []
    runner, robot = _runner(tmp_path, kin, on_snapshot=lambda s: seen.append((s.tcp, s.joints_deg)) if s.tcp and s.joints_deg else None)
    res = runner.run(job_id=3, pages=_plan_pages(), package_hash="d" * 64, probes=DEMO_PROBES, cfg=DEMO_CFG, ws=DEMO_WS)
    assert res.state == "DONE" and seen
    tcp, joints = seen[len(seen) // 2]
    pos, _ = kin.fk(joints)
    assert np.linalg.norm(pos - np.array(tcp)) < 2.0                           # the arm in the picture is where the pen is (<= IK step)
    assert robot.read_joints() is not None and runner.info.model.startswith("SIMULATED FR3 V6")


def test_joint_level_reach_check_runs_in_the_preflight(tmp_path, kin):
    far = [{"x": -520.0, "y": -74.0, "z": 20.0}, {"x": -520.0, "y": 74.0, "z": 20.0}, {"x": -730.0, "y": -74.0, "z": 20.0}]
    runner, robot = _runner(tmp_path, kin)
    with pytest.raises(RunRefused) as e:
        runner.run(job_id=3, pages=_plan_pages(), package_hash="e" * 64, probes=far, cfg=DEMO_CFG,
                   ws=type(DEMO_WS)(box_min_mm=(-900.0, -400.0, -50.0), box_max_mm=(0.0, 400.0, 200.0), max_reach_mm=900.0))
    assert e.value.code == "NOT_REACHABLE" and robot.commands == []            # nothing moved
    assert e.value.details and all(d.startswith("point ") for d in e.value.details)     # which sampled points and why


# ---------------------------------------------------------------- the web API for the 3D viewer
def test_the_viewer_serves_the_model_the_joints_and_refuses_odd_mesh_names(tmp_path, kin):
    runner, robot = _runner(tmp_path, kin)
    hub = ViewerHub()
    frame = build_frame(DEMO_PROBES)
    hub.attach(runner, _plan_pages(), frame, DEMO_LIMITS, DEMO_CFG.press_mm, DEMO_CFG.pen_up_clearance_mm, job_id=3, tool_mm=TOOL)
    c = TestClient(create_app(hub))
    m = c.get("/api/model").json()
    assert m["available"] is True and [j["name"] for j in m["joints"]] == ["j1", "j2", "j3", "j4", "j5", "j6"] and m["tool_mm"] == TOOL
    assert c.get("/fr3/fairino3_v6.urdf").status_code == 200
    assert c.get("/fr3/meshes/fairino3_v6/base_link.STL").status_code == 200
    for bad in ("..%2Ffairino3_v6.urdf", "x.txt", "..", "base_link.STL%00.png"):
        assert c.get(f"/fr3/meshes/fairino3_v6/{bad}").status_code in (404, 422)
    assert c.get("/vendor/three/build/three.module.js").status_code == 200
    hub.set_snapshot(type(hub.snapshot)(state="WRITING", mode="SIM", joints_deg=[1.0, 2, 3, 4, 5, 6], tcp=[-300.0, 0.0, 20.0]))
    j = c.get("/api/joints").json()
    assert j["joints_deg"] == [1.0, 2, 3, 4, 5, 6] and j["mode"] == "SIM" and j["tcp_mm"] == [-300.0, 0.0, 20.0]
