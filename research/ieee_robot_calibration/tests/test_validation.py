"""Validation tests for the simulation framework. Run: python -m pytest -q tests  (from research/ieee_robot_calibration)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vhrs_calib.calibrate import calibrate  # noqa: E402
from vhrs_calib.compensation import execute  # noqa: E402
from vhrs_calib.kinematics import (JOINT_LOWER, JOINT_UPPER, NOMINAL_ORIGINS, URDF_PATH, KinModel,  # noqa: E402
                                   load_urdf_origins, rpy_matrix)
from vhrs_calib.metrics import handwriting_metrics  # noqa: E402
from vhrs_calib.pipeline import Scene, rng_for  # noqa: E402
from vhrs_calib.truth import TruthConfig, make_truth  # noqa: E402
from vhrs_calib.workspace import (BALL_TOOL_FLANGE, PAPER_CORNERS, PEN_TOOL_FLANGE, CollectConfig, INSPECTION_FLANGE_RPY_DEG,  # noqa: E402
                                  INSPECTION_JOINTS_DEG, Paper, check_repo_scene, collect_socket_data, layout)
from vhrs_calib.evaluation import kabsch  # noqa: E402

REPO = ROOT.parents[1]


@pytest.fixture(scope="module")
def scene():
    return Scene()


def test_nominal_constants_match_vendor_urdf():
    if not URDF_PATH.exists():
        pytest.skip("vendor URDF not present (git-ignored); run robot_agent/scripts/fetch_fr3_model.py")
    o, lo, hi = load_urdf_origins()
    assert np.allclose(o, NOMINAL_ORIGINS) and np.allclose(lo, JOINT_LOWER) and np.allclose(hi, JOINT_UPPER)


def test_scene_constants_match_repo_files():
    s = check_repo_scene()
    assert np.allclose(s["probes"], PAPER_CORNERS)
    assert np.allclose(s["flange_rpy"], INSPECTION_FLANGE_RPY_DEG) and np.allclose(s["joints"], INSPECTION_JOINTS_DEG)


@pytest.mark.parametrize("fname", ["robot_inspection.json", "robot_inspection_20261025.json"])
def test_fk_matches_real_controller_flange(fname):
    """Read-only controller readings: nominal FK (URDF + 100 mm flange) reproduces the controller's own flange pose."""
    d = json.loads((REPO / "robot_agent" / "runs" / fname).read_text())["reads"]
    q = np.radians(d["GetActualJointPosDegree"][1])
    fl = np.array(d["GetActualToolFlangePose"][1])
    p, R = KinModel().fk(q)
    Rc = rpy_matrix(*np.radians(fl[3:]))
    assert np.linalg.norm(p[0] - fl[:3]) < 0.05
    assert np.degrees(np.arccos(np.clip((np.trace(Rc.T @ R[0]) - 1) / 2, -1, 1))) < 0.01


def test_jacobian_matches_finite_differences(scene):
    m, q = scene.nominal_pen, scene.q_seed[None]
    J, p0, _ = m.jacobian(q)
    h = 1e-7
    for j in range(6):
        dq = np.zeros(6)
        dq[j] = h
        p1, _ = m.fk(q + dq)
        assert np.allclose((p1[0] - p0[0]) / h, J[0, :3, j], atol=1e-3)


def test_ik_round_trip(scene):
    rng = np.random.default_rng(0)
    q = scene.q_seed + rng.normal(0, 0.15, (300, 6))
    p, R = scene.nominal_pen.fk(q)
    q2, pe, re, ok = scene.nominal_pen.ik(p, R, scene.q_seed)
    assert ok.mean() > 0.99 and np.max(pe[ok]) < 1e-4


def test_paper_frame_equals_ai_vhrs_build_frame():
    spec = importlib.util.spec_from_file_location("frame", REPO / "BE" / "app" / "services" / "motion" / "frame.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frame"] = mod
    spec.loader.exec_module(mod)
    f = mod.build_frame([{"x": a, "y": b, "z": c} for a, b, c in PAPER_CORNERS])
    p = Paper.from_corners(PAPER_CORNERS)
    assert np.allclose(f.origin, p.origin) and np.allclose(f.x_axis, p.x) and np.allclose(f.y_axis, p.y) and np.allclose(f.normal, p.n)


def test_precompensation_is_exact_with_a_perfect_model(scene):
    """If the calibrated model equals the true robot, pre-compensated execution lands on the desired points."""
    truth = KinModel(origins=NOMINAL_ORIGINS + np.random.default_rng(3).normal(0, 0.5, (6, 6)) * [1, 1, 1, 0.002, 0.002, 0.002]
                     ).with_tool(PEN_TOOL_FLANGE)
    pts = scene.paper.to_base(np.stack([np.linspace(10, 200, 50), np.linspace(10, 280, 50)], 1))
    ex = execute(pts, scene.R_w, scene.nominal_pen, truth, scene.q_seed, precomp_model=truth)
    assert ex.ik_ok.all() and np.max(np.linalg.norm(ex.tip - pts, axis=1)) < 1e-5
    ex0 = execute(pts, scene.R_w, scene.nominal_pen, truth, scene.q_seed, precomp_model=None)
    assert np.max(np.linalg.norm(ex0.tip - pts, axis=1)) > 0.5          # without it the geometric error is visible


def _noise_free():
    return TruthConfig(harmonic_amp_deg=0.0, use_compliance=False), CollectConfig(sigma_seat_mm=0, sigma_q_deg=0, sigma_d_mm=0)


@pytest.mark.parametrize("name", ["S2", "S3"])
def test_noise_free_calibration_recovers_the_geometry(scene, name):
    """With noise-free data and no unmodelled errors the identifiable part of the geometry is recovered (registration-invariant
    TCP error ~ 0), so any error in the experiments comes from noise / unmodelled effects / coverage, not from the solver."""
    tcfg, ccfg = _noise_free()
    tr = make_truth(5, tcfg, BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
    lay = layout(name, scene.paper)
    data, _ = collect_socket_data(np.random.default_rng(1), tr.ball(), lay, 60 // len(lay.centres), scene.R_w, scene.q_seed, ccfg)
    res = calibrate(data, BALL_TOOL_FLANGE, lam=1e-10)
    q = scene.q_seed + np.random.default_rng(2).normal(0, 0.2, (200, 6))
    pt, _ = tr.ball().fk(q)
    pc, _ = res.model.fk(q)
    R, t = kabsch(pc, pt)
    err = np.linalg.norm(pc @ R.T + t - pt, axis=1)
    pn, _ = scene.nominal_ball.fk(q)
    Rn, tn = kabsch(pn, pt)
    err_nom = np.linalg.norm(pn @ Rn.T + tn - pt, axis=1)
    assert err.max() < 0.02 * err_nom.max()


def test_base_gauge_is_unobservable(scene):
    """At a zero-residual point the 6 parameters of the first joint origin (= base frame pose) lie in the null space."""
    from vhrs_calib.calibrate import observability, theta_of
    tcfg, ccfg = _noise_free()
    tr = make_truth(1, tcfg, BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
    data, _ = collect_socket_data(np.random.default_rng(1), tr.ball(), layout("S3", scene.paper), 20, scene.R_w, scene.q_seed, ccfg)
    ob = observability(data, theta_of(tr.arm.origins, tr.ball_tool_flange, BALL_TOOL_FLANGE), BALL_TOOL_FLANGE)
    for j in range(6):
        e = np.zeros(39)
        e[j] = 1.0
        assert np.linalg.norm(ob["null_space"] @ e) > 0.999          # unit vector fully inside the null space
    assert 6 <= ob["n_unidentifiable"] < 39


def test_solver_never_sees_ground_truth(scene):
    tr = make_truth(2, TruthConfig(), BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
    data, hidden = collect_socket_data(np.random.default_rng(0), tr.ball(), layout("S2", scene.paper), 10, scene.R_w,
                                       scene.q_seed, CollectConfig())
    assert set(data) == {"q", "cluster", "pairs", "d", "n_clusters"} and "q_true" in hidden


def test_metrics_zero_and_shift(scene):
    s = [np.stack([np.linspace(20, 120, 101), np.full(101, 50.0)], 1)]
    x = [scene.paper.to_base(s[0])]
    m = handwriting_metrics(s, x, scene.paper)
    assert m["mae"] < 1e-9 and m["chamfer"] < 0.006 and m["hausdorff"] < 0.006 and m["contact_0.3"] == 1.0
    x2 = [scene.paper.to_base(s[0] + [0.0, 1.0], 0.5)]
    m2 = handwriting_metrics(s, x2, scene.paper)
    assert m2["shape_mae"] < 1e-9 and abs(m2["mae"] - 1.0) < 1e-9 and abs(m2["hd95"] - 1.0) < 0.01 and m2["contact_0.3"] == 0.0 and m2["contact_1"] == 1.0


def test_trials_are_reproducible(scene):
    a = make_truth(7, TruthConfig(), BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
    b = make_truth(7, TruthConfig(), BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
    assert np.array_equal(a.delta_origins, b.delta_origins)
    assert np.array_equal(rng_for(7, 1).normal(size=3), rng_for(7, 1).normal(size=3))
