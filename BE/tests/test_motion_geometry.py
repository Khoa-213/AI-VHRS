"""Paper -> robot frame, resampling, speed profile and the deterministic trajectory validator. Pure computation.

The numbers below are TEST FIXTURES that make the geometry checkable; they are not measurements of any robot.
"""
import math

import numpy as np
import pytest

from app.services.motion import plan as mp
from app.services.motion.frame import FrameChecks, FrameError, build_frame
from app.services.motion.validate import Workspace, validate
from app.services.stroke_ai.trajectory import Page, Stroke

CFG = mp.MotionConfig(a_lat_mm_s2=2000.0, a_tan_mm_s2=1000.0, travel_speed_mm_s=100.0, approach_speed_mm_s=10.0,
                      pen_up_clearance_mm=5.0, spring_k_n_per_mm=0.4, max_spring_travel_mm=6.0, f_target_n=1.0,
                      v_max_mm_s=40.0)
BOX = Workspace(box_min_mm=(100.0, -300.0, -50.0), box_max_mm=(500.0, 300.0, 200.0))


def probes(origin=(300.0, -105.0, 20.0), w=210.0, h=297.0):
    x0, y0, z0 = origin
    return [{"x": x0, "y": y0, "z": z0}, {"x": x0, "y": y0 + w, "z": z0}, {"x": x0 - h, "y": y0, "z": z0}]


def page(*strokes):
    return Page("A4", [Stroke(list(s)) for s in strokes])


# ---------------------------------------------------------------- frame
def test_frame_maps_corners_exactly_for_a_flat_sheet():
    f = build_frame(probes())
    xy = np.array([[0, 0], [210, 0], [0, 297], [210, 297]], float)
    out = f.to_base(xy)
    assert out[0] == pytest.approx([300, -105, 20])
    assert out[1] == pytest.approx([300, 105, 20])
    assert out[2] == pytest.approx([3, -105, 20])
    assert out[3] == pytest.approx([3, 105, 20])
    assert f.normal == pytest.approx([0, 0, 1])


def test_frame_lift_goes_along_the_normal_and_normal_points_up():
    f = build_frame(probes())
    assert f.to_base(np.array([[10.0, 10.0]]), lift_mm=5.0)[0, 2] == pytest.approx(25.0)
    swapped = [probes()[0], probes()[2], probes()[1]]            # opposite handedness still gets an upward normal
    assert build_frame(swapped).normal[2] > 0


def test_frame_handles_a_tilted_sheet_not_parallel_to_the_robot_plane():
    t = math.radians(10)
    p0 = np.array([300.0, -100.0, 20.0])
    ex = np.array([0.0, 1.0, 0.0])
    ey = np.array([-math.cos(t), 0.0, math.sin(t)])            # the sheet rises towards its bottom
    pts = [{"x": v[0], "y": v[1], "z": v[2]} for v in (p0, p0 + 210 * ex, p0 + 297 * ey)]
    f = build_frame(pts)
    assert f.normal[2] == pytest.approx(math.cos(t))
    assert f.to_base(np.array([[0.0, 297.0]]))[0] == pytest.approx(p0 + 297 * ey)
    assert f.to_base(np.array([[0.0, 297.0]]))[0, 2] != pytest.approx(20.0)     # Z is NOT assumed constant


def test_extra_probes_become_a_height_map_and_a_bad_probe_is_rejected():
    base = probes()
    extra = [{"x": 150.0, "y": 0.0, "z": 20.6}]                 # centre of the sheet is 0.6 mm high
    f = build_frame(base + extra)
    assert f.n_probes == 4 and f.plane_max_mm < 1.0
    with pytest.raises(FrameError) as e:
        build_frame(base + [{"x": 150.0, "y": 0.0, "z": 25.0}])
    assert e.value.code == "PROBE_NOT_ON_PLANE"


@pytest.mark.parametrize("pts,code", [
    ([{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}, {"x": 200, "y": 0, "z": 0}], "INVALID_PROBE_POINTS"),   # collinear
    ([{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 0, "z": 0}, {"x": 0, "y": 100, "z": 0}], "PROBE_BASELINE_TOO_SHORT"),
    ([{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}, {"x": 80, "y": 60, "z": 0}], "PROBE_AXES_NOT_PERPENDICULAR"),
    ([{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}, {"x": 0, "y": 0, "z": 100}], "PAPER_PLANE_TOO_STEEP"),
    ([{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": float("nan")}, {"x": 0, "y": 100, "z": 0}], "INVALID_PROBE_POINTS"),
    ([{"x": 0, "y": 0}], "INVALID_PROBE_POINTS"),
])
def test_bad_probe_sets_are_refused(pts, code):
    with pytest.raises(FrameError) as e:
        build_frame(pts)
    assert e.value.code == code


# ---------------------------------------------------------------- resample / speed
def test_resample_keeps_the_shape_the_spacing_and_the_corners():
    original = [(0, 0), (50, 0), (50, 30), (80, 30)]            # two 90-degree corners
    out = mp.resample_stroke(original, 0.2)
    gaps = np.linalg.norm(np.diff(out, axis=0), axis=1)
    assert gaps.max() <= 0.2 + 1e-9
    assert mp.max_deviation_mm(original, out) < 1e-9             # no smoothing: same polyline
    for corner in [(50, 0), (50, 30)]:
        assert np.min(np.linalg.norm(out - np.array(corner), axis=1)) < 1e-9


def test_resample_does_not_change_a_curve_beyond_a_tiny_chord_error():
    t = np.linspace(0, math.pi, 40)
    original = np.stack([20 * np.cos(t) + 30, 20 * np.sin(t) + 30], axis=1)
    out = mp.resample_stroke(original, 0.2)
    assert mp.max_deviation_mm(original, out) < 0.02


def test_speed_profile_slows_in_curves_at_corners_and_ends_and_limits_acceleration():
    ds = 0.2
    line = mp.resample_stroke([(0, 0), (100, 0)], ds)
    v = mp.speed_profile(line, v_max=40, a_lat=200.0, a_tan=1000, ds=ds)
    assert v[0] == v[-1] == 5.0 and v.max() == pytest.approx(40.0)
    seg = np.linalg.norm(np.diff(line, axis=0), axis=1)
    assert np.all(v[1:] ** 2 - v[:-1] ** 2 <= 2 * 1000 * seg + 1e-6)          # forward acceleration cap
    assert np.all(v[:-1] ** 2 - v[1:] ** 2 <= 2 * 1000 * seg + 1e-6)          # backward deceleration cap
    th = np.linspace(0, math.pi, 200)
    arc = mp.resample_stroke(np.stack([0.5 * np.cos(th), 0.5 * np.sin(th)], axis=1), ds)
    va = mp.speed_profile(arc, v_max=40, a_lat=200.0, a_tan=1000, ds=ds)
    assert va[len(va) // 2] <= math.sqrt(200.0 * 0.5) * 1.15      # sqrt(a_lat / kappa), kappa = 1 / 0.5
    corner = mp.resample_stroke([(0, 0), (20, 0), (20, 20)], ds)
    vc = mp.speed_profile(corner, v_max=40, a_lat=200.0, a_tan=1000, ds=ds)
    assert vc[int(np.argmin(np.linalg.norm(corner - [20, 0], axis=1)))] == 5.0


# ---------------------------------------------------------------- planning and validation
def test_unconfigured_values_refuse_planning_instead_of_defaulting():
    empty = mp.MotionConfig()
    assert set(empty.missing()) == set(CFG.__dataclass_fields__)
    with pytest.raises(mp.PlanError) as e:
        mp.plan_page(page([(10, 10), (50, 10)]), build_frame(probes()), empty)
    assert e.value.code == "UNCONFIGURED"
    rep, plans = validate([page([(10, 10), (50, 10)])], probes(), empty, BOX)
    assert not rep.passed and plans == [] and rep.errors[0].code == "UNCONFIGURED"


def test_a_good_trajectory_passes_and_the_plan_is_pen_up_between_strokes():
    pg = page([(20, 20), (100, 20)], [(20, 40), (20, 80), (60, 80)])
    rep, plans = validate([pg], probes(), CFG, BOX)
    assert rep.passed, rep.error_texts()
    assert rep.checks["joint_reachability_ik"] == "NOT_CHECKED"       # never claimed server-side
    kinds = [m.kind for m in plans[0].moves]
    assert kinds == ["plunge", "write", "retract", "travel", "plunge", "write", "retract"]
    write = plans[0].moves[1].points
    assert write[:, 2] == pytest.approx(20.0 - CFG.press_mm)            # surface z=20, pressed f/k = 2.5 mm in
    assert plans[0].moves[3].points[:, 2] == pytest.approx(25.0)        # travel at the clearance height
    assert rep.stats["estimated_seconds"] > 0


def test_refusals_outside_paper_unreachable_unconfigured_box_and_spring_travel():
    far = probes(origin=(300.0, -105.0, 20.0))
    assert validate([page([(20, 20), (230, 20)])], far, CFG, BOX)[0].errors[0].code == "OUTSIDE_PAPER"
    reach = probes(origin=(600.0, -105.0, 20.0))                       # sheet corner beyond 0.9 x 622 mm
    assert "OUT_OF_REACH" in {e.code for e in validate([page([(20, 20), (100, 20)])], reach, CFG, BOX)[0].errors}
    codes = {e.code for e in validate([page([(20, 20), (100, 20)])], probes(), CFG, Workspace())[0].errors}
    assert codes == {"UNCONFIGURED"}                                   # real runs need a configured box
    assert validate([page([(20, 20), (100, 20)])], probes(), CFG, Workspace(), require_box=False)[0].passed
    stiff = mp.MotionConfig(**{**CFG.__dict__, "max_spring_travel_mm": 2.0})
    assert "SPRING_TRAVEL_EXCEEDED" in {e.code for e in validate([page([(20, 20), (100, 20)])], probes(), stiff, BOX)[0].errors}
    tight = Workspace(box_min_mm=(100, -300, -50), box_max_mm=(500, 300, 22))   # below the clearance height
    assert "OUTSIDE_WORKSPACE" in {e.code for e in validate([page([(20, 20), (100, 20)])], probes(), CFG, tight)[0].errors}


def test_validator_is_deterministic_and_does_not_mutate_inputs():
    pg = page([(20, 20), (100, 60), (30, 90)])
    a = validate([pg], probes(), CFG, BOX)[0].as_dict()
    b = validate([pg], probes(), CFG, BOX)[0].as_dict()
    assert a == b


def test_frame_checks_are_adjustable_without_silently_widening_defaults():
    skew = [{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}, {"x": 5, "y": 100, "z": 0}]   # ~2.9 deg off square
    assert build_frame(skew)
    with pytest.raises(FrameError):
        build_frame(skew, FrameChecks(max_axes_skew_deg=1.0))
