"""Socket-constrained kinematic calibration (MUKCa objective, Franzese et al., Commun. Eng. 5:138, 2026) for K >= 2 sockets.

Objective (MUKCa Eq. 5, generalised from 2 sockets to K sockets and any set of known socket distances):

  J(theta) = (1/N) sum_k sum_{i in k} || f_theta(q_i) - mu_k(theta) ||^2              consistency  (sample-weighted trace of cov.)
           + sum_{(k,l) in D} ( || mu_k(theta) - mu_l(theta) || - d_kl )^2           distortion   (known socket distances)
           + lambda || theta - theta_nom ||^2                                         regularisation (Occam / gauge fixing)

f_theta = predicted ball centre, mu_k = mean prediction of socket k, theta = 36 joint-origin deviations (6 joints x [dx dy dz in mm,
droll dpitch dyaw in mrad]) + 3 ball-offset deviations (mm). In (mm, mrad) units lambda = 1e-4 equals MUKCa's lambda = 1e-4 in
(m, rad) units. Solved as nonlinear least squares (scipy, Levenberg-Marquardt / TRF with a finite-difference Jacobian) instead of
Ipopt + CasADi: same objective, different solver (documented in METHODOLOGY.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from vhrs_calib.kinematics import NOMINAL_ORIGINS, KinModel

N_PARAM = 39
PARAM_NAMES = [f"j{j + 1}.{c}" for j in range(6) for c in ("x", "y", "z", "roll", "pitch", "yaw")] + ["ball.x", "ball.y", "ball.z"]


def unpack(theta: np.ndarray, nominal_ball_flange: np.ndarray) -> KinModel:
    d = theta[:36].reshape(6, 6).copy()
    d[:, 3:] *= 1e-3                                              # mrad -> rad
    m = KinModel(origins=NOMINAL_ORIGINS + d, name="calibrated")
    return m.with_tool(nominal_ball_flange + theta[36:39])


def residuals(theta, data, nominal_ball_flange, lam, include_reg=True):
    m = unpack(theta, nominal_ball_flange)
    P, _ = m.fk(data["q"])
    cl = data["cluster"]
    n = len(cl)
    mus = np.array([P[cl == k].mean(axis=0) for k in range(data["n_clusters"])])
    r_cons = (P - mus[cl]).ravel() / np.sqrt(n)
    r_dist = np.array([np.linalg.norm(mus[k] - mus[l]) for k, l in data["pairs"]]) - data["d"]
    parts = [r_cons, r_dist]
    if include_reg:
        parts.append(np.sqrt(lam) * theta)
    return np.concatenate(parts)


@dataclass
class CalibResult:
    theta: np.ndarray
    model: KinModel
    success: bool
    status: int
    nfev: int
    cost_initial: float
    cost_final: float
    consistency_rms_mm: float          # sqrt of the consistency term (MUKCa "inconsistency")
    distortion_mm: np.ndarray          # signed distance errors at the solution
    singular_values: np.ndarray        # of the data Jacobian at the solution (diagnostic only; for identifiability use
    message: str                       # observability(), which evaluates a zero-residual problem)


def calibrate(data: dict, nominal_ball_flange: np.ndarray, lam: float = 1e-4) -> CalibResult:
    x0 = np.zeros(N_PARAM)
    r0 = residuals(x0, data, nominal_ball_flange, lam)
    sol = least_squares(residuals, x0, args=(data, nominal_ball_flange, lam), method="lm", x_scale=1.0,
                        xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=4000)
    th = sol.x
    r_data = residuals(th, data, nominal_ball_flange, lam, include_reg=False)
    n_cons = 3 * len(data["cluster"])
    cons = float(np.sqrt(np.sum(r_data[:n_cons] ** 2)))
    s = np.linalg.svd(data_jacobian(th, data, nominal_ball_flange), compute_uv=False)
    return CalibResult(theta=th, model=unpack(th, nominal_ball_flange), success=bool(sol.success), status=int(sol.status),
                       nfev=int(sol.nfev), cost_initial=float(0.5 * r0 @ r0), cost_final=float(sol.cost),
                       consistency_rms_mm=cons, distortion_mm=r_data[n_cons:], singular_values=s,
                       message=str(sol.message))


def data_jacobian(theta, data, nominal_ball_flange, h: float = 1e-6) -> np.ndarray:
    """Central-difference Jacobian of the data residuals (consistency + distortion) w.r.t. the 39 parameters."""
    cols = []
    for j in range(N_PARAM):
        e = np.zeros(N_PARAM)
        e[j] = h
        cols.append((residuals(theta + e, data, nominal_ball_flange, 0.0, False)
                     - residuals(theta - e, data, nominal_ball_flange, 0.0, False)) / (2 * h))
    return np.stack(cols, axis=1)


def null_directions(J: np.ndarray, rank_tol: float = 1e-6) -> np.ndarray:
    """Right-singular vectors spanning the (numerically) unobservable parameter subspace."""
    _, s, Vt = np.linalg.svd(J, full_matrices=True)
    r = int(np.sum(s > rank_tol * s[0]))
    return Vt[r:]


def theta_of(origins: np.ndarray, ball_flange: np.ndarray, nominal_ball_flange: np.ndarray) -> np.ndarray:
    """Parameter vector (mm, mrad) of a model given by absolute origins and ball offset."""
    d = (origins - NOMINAL_ORIGINS).copy()
    d[:, 3:] *= 1e3
    return np.concatenate([d.ravel(), ball_flange - nominal_ball_flange])


def observability(data_noise_free: dict, theta_true: np.ndarray, nominal_ball_flange: np.ndarray, rank_tol: float = 1e-6) -> dict:
    """Identifiability at a ZERO-RESIDUAL point: noise-free socket data generated by a robot that lies inside the model class
    (no unmodelled errors), Jacobian evaluated at that robot's own parameters. There the gauge directions (rigid base motion)
    give exactly zero columns, so the numerical rank is the number of identifiable parameter combinations.
    Parameters are scaled to mm and mrad (1 mrad ~ 1 mm at 1 m), the usual choice for mixed units."""
    J = data_jacobian(theta_true, data_noise_free, nominal_ball_flange)
    U, s, Vt = np.linalg.svd(J, full_matrices=True)
    r = int(np.sum(s > rank_tol * s[0]))
    return {"singular_values": s, "rank": r, "n_unidentifiable": N_PARAM - r, "cond": float(s[0] / s[r - 1]),
            "null_space": Vt[r:], "sigma_min_identifiable": float(s[r - 1])}
