"""E1 evaluation: positioning accuracy of a kinematic model on an independent test set of TRUE robot configurations.

A model calibrated from socket constraints is defined only up to a rigid motion of its base (no socket position is known in the
base frame; this gauge freedom is pinned by the regulariser, not by data). Raw absolute errors would therefore mix the model
error with an arbitrary gauge choice. The primary metric is the registration-invariant error: the predicted TCP positions are
rigidly aligned (Kabsch, 6 DOF, no scale) to the true positions before measuring. In the writing application the same rigid
registration is performed physically by probing the paper corners, see compensation.py. Raw errors are reported as well.
"""
from __future__ import annotations

import numpy as np

from vhrs_calib.kinematics import KinModel
from vhrs_calib.workspace import PAPER_H_MM, PAPER_W_MM, Paper, sample_orientations


def kabsch(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """R, t minimising sum ||R a_i + t - b_i||^2."""
    ca, cb = A.mean(0), B.mean(0)
    H = (A - ca).T @ (B - cb)
    U, _, Vt = np.linalg.svd(H)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ D @ U.T
    return R, cb - R @ ca


def make_test_set(rng, truth_tool: KinModel, paper: Paper, R_w: np.ndarray, q_seed: np.ndarray, n: int = 500,
                  height_range=(0.0, 60.0), cone_deg: float = 20.0, spin_deg: float = 45.0, margin_deg: float = 5.0):
    """Independent test configurations: TCP uniformly over the sheet (u, v) and 0-60 mm above it, tool tilted up to 20 deg.
    Generated with the TRUE robot (so the true TCP is known exactly)."""
    qs = []
    while sum(len(x) for x in qs) < n:
        m = n
        uv = np.stack([rng.uniform(0, PAPER_W_MM, m), rng.uniform(0, PAPER_H_MM, m)], 1)
        p = paper.to_base(uv, rng.uniform(*height_range, m))
        Rs = sample_orientations(rng, m, R_w, cone_deg, spin_deg)
        q, pe, re, ok = truth_tool.ik(p, Rs, q_seed)
        ok &= truth_tool.within_limits(q, np.radians(margin_deg))
        qs.append(q[ok])
    q = np.concatenate(qs)[:n]
    return q


def position_errors(model: KinModel, truth_tool: KinModel, q_true: np.ndarray, sigma_q_rad: float, rng) -> dict:
    p_true, _ = truth_tool.fk(q_true)
    q_meas = q_true + rng.normal(0, sigma_q_rad, q_true.shape)
    p_pred, _ = model.fk(q_meas)
    raw = np.linalg.norm(p_pred - p_true, axis=1)
    R, t = kabsch(p_pred, p_true)
    aligned = np.linalg.norm(p_pred @ R.T + t - p_true, axis=1)
    return {"aligned": aligned, "raw": raw}


def summarize(e: np.ndarray) -> dict:
    return {"mean": float(np.mean(e)), "rmse": float(np.sqrt(np.mean(e ** 2))), "median": float(np.median(e)),
            "p95": float(np.percentile(e, 95)), "max": float(np.max(e))}
