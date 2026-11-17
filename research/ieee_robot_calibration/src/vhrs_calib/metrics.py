"""Handwriting accuracy metrics in the TRUE paper frame (Module F). All distances in mm.

Given the desired pen-down path w_i = (u_i, v_i) on the sheet and the simulated true pen-tip positions x_i (base frame), with
(u'_i, v'_i, h_i) = coordinates of x_i in the true paper frame:

  e_i      = || (u'_i, v'_i) - (u_i, v_i) ||             in-plane (paper-space) point error, matched by index
  h_i                                                 signed height of the tip above the sheet (normal error)
  MAE, RMSE, P95, max of e_i
  Chamfer  = 0.5 (mean_a d(a, B) + mean_b d(b, A))     A = desired, B = executed, query points every 0.1 mm, reference polylines
           densified to 0.01 mm (discretisation error <= 0.005 mm)
  HD95     = 95th percentile of {d(a,B)} U {d(b,A)};  Hausdorff = max of the same set
  (Chamfer/HD95/Hausdorff use the same definitions as AI-VHRS Service G, BE/app/services/quality_eval.py, but on vector paths
   instead of photographed ink.)
  shape MAE / shape P95 = e_i after the best 2-D rigid fit (rotation + translation, no scale) of the executed points onto the
           desired ones: the distortion of the letter shapes with the sheet-registration offset removed
  contact ratio(p) = fraction of points with h_i < p, where p is the commanded press depth (spring pre-compression). A point with
   h_i >= p would leave the pen tip above the paper (no ink). This is a geometric proxy, NOT a simulation of ink deposition.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from vhrs_calib.workspace import Paper


def densify(poly: np.ndarray, step: float = 0.1) -> np.ndarray:
    poly = np.asarray(poly, float)
    if len(poly) < 2:
        return poly
    out = [poly[:1]]
    for a, b in zip(poly[:-1], poly[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        t = np.linspace(0, 1, n + 1)[1:, None]
        out.append(a + (b - a) * t)
    return np.concatenate(out)


def handwriting_metrics(desired_strokes: list[np.ndarray], executed_strokes: list[np.ndarray], paper: Paper,
                        press_depths=(0.3, 1.0)) -> dict:
    des, exe, hs = [], [], []
    A, B = [], []
    for d, x in zip(desired_strokes, executed_strokes):
        uvh = paper.to_paper(x)
        des.append(d)
        exe.append(uvh[:, :2])
        hs.append(uvh[:, 2])
        A.append((densify(d, 0.1), densify(d, 0.01)))
        B.append((densify(uvh[:, :2], 0.1), densify(uvh[:, :2], 0.01)))
    des, exe, h = np.concatenate(des), np.concatenate(exe), np.concatenate(hs)
    e = np.linalg.norm(exe - des, axis=1)
    Aq, Af = np.concatenate([a[0] for a in A]), np.concatenate([a[1] for a in A])
    Bq, Bf = np.concatenate([b[0] for b in B]), np.concatenate([b[1] for b in B])
    dAB, _ = cKDTree(Bf).query(Aq)
    dBA, _ = cKDTree(Af).query(Bq)
    allv = np.concatenate([dAB, dBA])
    ca, cb = exe.mean(0), des.mean(0)
    U, _, Vt = np.linalg.svd((exe - ca).T @ (des - cb))
    R = Vt.T @ np.diag([1.0, np.sign(np.linalg.det(Vt.T @ U.T))]) @ U.T
    es = np.linalg.norm((exe - ca) @ R.T + cb - des, axis=1)
    out = {"n_points": int(len(e)), "shape_mae": float(es.mean()), "shape_p95": float(np.percentile(es, 95)), "mae": float(e.mean()), "rmse": float(np.sqrt(np.mean(e ** 2))),
           "p95": float(np.percentile(e, 95)), "max": float(e.max()),
           "chamfer": float(0.5 * (dAB.mean() + dBA.mean())), "hd95": float(np.percentile(allv, 95)), "hausdorff": float(allv.max()),
           "h_mean": float(h.mean()), "h_std": float(h.std()), "h_absmax": float(np.abs(h).max())}
    for p in press_depths:
        out[f"contact_{p:g}"] = float(np.mean(h < p))
    return out
