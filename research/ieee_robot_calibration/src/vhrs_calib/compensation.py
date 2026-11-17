"""Closed-controller execution model, paper-frame probing and trajectory pre-compensation (Module D).

Closed controller: the FR3 controller accepts Cartesian targets and solves its OWN inverse kinematics with its NOMINAL model
(the URDF + 100 mm flange; verified against two controller readings). We cannot change that model. The pen then lands where the
TRUE robot puts it for those joint angles:

    q_c = IK_nom(x_cmd, R_cmd)          (controller, nominal model)
    x_tip = FK_true(q_c)                (physics)

Pre-compensation with a calibrated model C: find the joints that C says reach the desired point, and send the controller the
pose its nominal model associates with those joints:

    q* = IK_C(x_des, R_des),  (x_cmd, R_cmd) = FK_nom(q*)   =>   IK_nom(x_cmd, R_cmd) = q*  =>  x_tip = FK_true(q*) ~ x_des

Paper registration (all methods except A): the operator touches P0, P1, P2 with the pen tip; the joint readings at contact are
mapped through the model in use (nominal or calibrated) and the AI-VHRS 3-probe frame construction is applied. This absorbs any
rigid base/gauge offset and the constant part of the pen-tip offset error.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vhrs_calib.kinematics import KinModel
from vhrs_calib.workspace import PAPER_CORNERS, Paper, writing_rotation


@dataclass
class ProbeConfig:
    sigma_inplane_mm: float = 0.10     # operator's visual alignment of the pen tip on a paper corner
    sigma_normal_mm: float = 0.02      # "touch lightly" height repeatability
    sigma_q_deg: float = 0.001


def probe_paper(rng, truth_pen: KinModel, true_paper: Paper, q_seed: np.ndarray, cfg: ProbeConfig) -> np.ndarray:
    """Joint readings (3, 6) recorded while the TRUE pen tip touches the three corners (with operator error)."""
    c = PAPER_CORNERS.copy()
    noise = (rng.normal(0, cfg.sigma_inplane_mm, (3, 1)) * true_paper.x + rng.normal(0, cfg.sigma_inplane_mm, (3, 1)) * true_paper.y
             + rng.normal(0, cfg.sigma_normal_mm, (3, 1)) * true_paper.n)
    q, pe, re, ok = truth_pen.ik(c + noise, writing_rotation(true_paper.n), q_seed)
    assert ok.all(), "probe IK failed"
    return q + rng.normal(0, np.radians(cfg.sigma_q_deg), q.shape)


def frame_from_probes(model_pen: KinModel, q_probe: np.ndarray) -> Paper:
    p, _ = model_pen.fk(q_probe)
    return Paper.from_corners(p)


@dataclass
class Execution:
    tip: np.ndarray            # (N, 3) true pen-tip positions (base frame)
    q_cmd: np.ndarray
    ik_ok: np.ndarray          # (N,) all IK stages converged and stayed on the seed branch
    max_joint_step_deg: float


def execute(points_model: np.ndarray, R_model: np.ndarray, nominal_pen: KinModel, truth_pen: KinModel, q_seed: np.ndarray,
            precomp_model: KinModel | None = None) -> Execution:
    """Send a model-space pen-tip path to the simulated closed controller and return where the true pen goes."""
    ok = np.ones(len(points_model), bool)
    if precomp_model is None:
        x_cmd, R_cmd = points_model, np.broadcast_to(R_model, (len(points_model), 3, 3))
    else:
        q_star, _, _, ok1 = precomp_model.ik(points_model, R_model, q_seed)
        ok &= ok1
        x_cmd, R_cmd = nominal_pen.fk(q_star)
    q_c, _, _, ok2 = nominal_pen.ik(x_cmd, R_cmd, q_seed)                  # the controller's own IK (nominal model)
    ok &= ok2 & nominal_pen.within_limits(q_c, 0.0)
    tip, _ = truth_pen.fk(q_c)
    step = np.degrees(np.max(np.abs(np.diff(q_c, axis=0)))) if len(q_c) > 1 else 0.0
    return Execution(tip=tip, q_cmd=q_c, ik_ok=ok, max_joint_step_deg=float(step))


def resample_stroke(pts: np.ndarray, step_mm: float = 1.0) -> np.ndarray:
    pts = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] < 1e-9:
        return pts[:1]
    n = max(2, int(np.ceil(s[-1] / step_mm)) + 1)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])], 1)
