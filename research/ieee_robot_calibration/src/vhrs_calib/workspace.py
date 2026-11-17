"""Scene of the AI-VHRS workcell in the robot base frame (mm): paper sheet, writing orientation, socket layouts, data collection.

Scene numbers taken from the repository (real values recorded by the operator, not invented):
  * paper corners P0, P1, P2 = `robot_agent/calibration.json` "probe_points" (A4 portrait, re-measured 2026-10-31 with Tool2);
  * pen-tip offset 179.62 mm from the flange (Tool2, same file); its direction is ASSUMED to be the flange z axis;
  * writing orientation = the flange orientation read from the controller at a pen-down pose (runs/robot_inspection.json),
    rotated minimally so the tool axis is exactly normal to the sheet.
Everything about the calibration sockets is a DESIGN ASSUMPTION of this study (no socket tool exists yet).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from vhrs_calib.kinematics import REPO_ROOT, KinModel, rpy_matrix

PAPER_CORNERS = np.array([[-124.184, 518.909, 10.076],      # P0 top-left (paper origin)
                          [84.853, 516.534, 8.211],         # P1 top-right (+x of paper)
                          [-127.45, 220.28, 5.273]])        # P2 bottom-left (+y of paper)
PEN_TOOL_FLANGE = np.array([0.0, 0.0, 179.62])
BALL_TOOL_FLANGE = np.array([0.0, 0.0, 179.62])               # assumed: a ball-tipped rod in the same holder as the pen
INSPECTION_FLANGE_RPY_DEG = np.array([-177.74880981445312, -1.2372442483901978, -30.762834548950195])
INSPECTION_JOINTS_DEG = np.array([-88.58004760742188, -64.54521942138672, 66.76315307617188, -93.46580505371094,
                                  -92.24555969238281, 32.134246826171875])
PAPER_W_MM, PAPER_H_MM = 210.0, 297.0


def check_repo_scene() -> dict:
    """Re-read the repo files the constants come from (tests call this to make sure they were copied correctly)."""
    cal = json.loads((REPO_ROOT / "robot_agent" / "calibration.json").read_text(encoding="utf8"))
    ins = json.loads((REPO_ROOT / "robot_agent" / "runs" / "robot_inspection.json").read_text(encoding="utf8"))
    probes = np.array([[p["x"], p["y"], p["z"]] for p in cal["probe_points"]])
    return {"probes": probes, "flange_rpy": np.array(ins["reads"]["GetActualToolFlangePose"][1][3:]),
            "joints": np.array(ins["reads"]["GetActualJointPosDegree"][1])}


@dataclass
class Paper:
    origin: np.ndarray
    x: np.ndarray
    y: np.ndarray
    n: np.ndarray            # unit normal towards the tool (up)

    @staticmethod
    def from_corners(c: np.ndarray) -> "Paper":
        """Same construction as AI-VHRS BE/app/services/motion/frame.py build_frame (3 probes): Gram-Schmidt on P1-P0, P2-P0."""
        x = (c[1] - c[0]) / np.linalg.norm(c[1] - c[0])
        y = c[2] - c[0] - np.dot(c[2] - c[0], x) * x
        y /= np.linalg.norm(y)
        n = np.cross(x, y)
        if n[2] < 0:
            n = -n
        return Paper(c[0].copy(), x, y, n)

    def to_base(self, uv: np.ndarray, h: float | np.ndarray = 0.0) -> np.ndarray:
        uv = np.atleast_2d(uv)
        return self.origin + np.outer(uv[:, 0], self.x) + np.outer(uv[:, 1], self.y) + np.outer(np.broadcast_to(h, len(uv)), self.n)

    def to_paper(self, p: np.ndarray) -> np.ndarray:
        """(N,3) base -> (N,3) [u, v, height above the sheet]."""
        d = np.atleast_2d(p) - self.origin
        return np.stack([d @ self.x, d @ self.y, d @ self.n], axis=1)


def rot_about(axis: np.ndarray, ang: float) -> np.ndarray:
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def writing_rotation(normal: np.ndarray) -> np.ndarray:
    """Flange orientation for writing: the real pen-down flange orientation, minimally rotated so that its z axis = -normal."""
    R = rpy_matrix(*np.radians(INSPECTION_FLANGE_RPY_DEG))
    z, t = R[:, 2], -np.asarray(normal, float)
    ax = np.cross(z, t)
    s = np.linalg.norm(ax)
    if s < 1e-12:
        return R
    return rot_about(ax, np.arctan2(s, float(np.dot(z, t)))) @ R


def writing_seed(model: KinModel, paper: Paper) -> np.ndarray:
    """Joint seed for the writing posture: the inspection joints, re-solved for the sheet centre (elbow-up branch)."""
    q0 = np.radians(INSPECTION_JOINTS_DEG)
    p = paper.to_base(np.array([[PAPER_W_MM / 2, PAPER_H_MM / 2]]), 0.0)
    q, pe, re, ok = model.ik(p, writing_rotation(paper.n), q0)
    assert ok[0], "writing seed IK failed"
    return q[0]


# ---------------------------------------------------------------------------------------------------- socket layouts
@dataclass
class SocketLayout:
    name: str
    centres: np.ndarray                      # (K, 3) TRUE ball-centre positions when seated (mm)
    pairs: list = field(default_factory=list)   # [(k, l)] pairs whose distance is known (same rigid tool)

    def true_distances(self) -> np.ndarray:
        return np.array([np.linalg.norm(self.centres[k] - self.centres[l]) for k, l in self.pairs])


def layout(name: str, paper: Paper, spacing_mm: float = 150.0, height_mm: float = 12.0,
           centre_uv: tuple = (PAPER_W_MM / 2, PAPER_H_MM / 2)) -> SocketLayout:
    """Socket layouts on the writing table, `height_mm` = ball centre above the sheet plane.
      S2      two sockets `spacing` apart along the sheet's x axis (MUKCa's tool)
      S3      three sockets on an equilateral triangle with side `spacing` (the extension studied here), 3 known distances
      S3L     three collinear sockets (spacing/2 apart): same count, no 2-D spread (ablation)
      S2x2    the MUKCa two-socket tool placed twice (along x, then along y), 4 sockets, 2 known distances
    """
    cu, cv = centre_uv
    d = spacing_mm
    if name == "S2":
        uv, pairs = [(cu - d / 2, cv), (cu + d / 2, cv)], [(0, 1)]
    elif name == "S3":
        r = d / np.sqrt(3.0)
        uv = [(cu + r * np.cos(a), cv + r * np.sin(a)) for a in np.radians([90.0, 210.0, 330.0])]
        pairs = [(0, 1), (1, 2), (0, 2)]
    elif name == "S3L":
        uv, pairs = [(cu - d / 2, cv), (cu, cv), (cu + d / 2, cv)], [(0, 1), (1, 2), (0, 2)]
    elif name == "S2x2":
        # placement A along x (75 mm towards the sheet top), placement B along y (centred 75 mm towards the bottom)
        uv = [(cu - d / 2, cv - 75.0), (cu + d / 2, cv - 75.0), (cu, cv + 75.0 - d / 2), (cu, cv + 75.0 + d / 2)]
        pairs = [(0, 1), (2, 3)]
    else:
        raise ValueError(name)
    c = paper.to_base(np.array(uv, float), height_mm)
    return SocketLayout(name, c, pairs)


# ---------------------------------------------------------------------------------------------------- data collection
@dataclass
class CollectConfig:
    cone_deg: float = 30.0        # max tilt of the tool axis from the sheet normal while the ball sits in a socket
    spin_deg: float = 60.0        # max rotation about the tool axis around the writing yaw
    sigma_seat_mm: float = 0.02   # ball/socket seating repeatability
    sigma_q_deg: float = 0.001    # joint-encoder noise (quantisation of a 17-bit encoder is ~0.0008 deg rms)
    sigma_d_mm: float = 0.02      # caliper uncertainty of a socket distance
    margin_deg: float = 5.0       # joint-limit margin


def sample_orientations(rng, n: int, R_w: np.ndarray, cone_deg: float, spin_deg: float) -> np.ndarray:
    th = np.radians(cone_deg) * np.sqrt(rng.uniform(0, 1, n))          # uniform over the cone's spherical cap (small angles)
    ph = rng.uniform(-np.pi, np.pi, n)
    ps = np.radians(spin_deg) * rng.uniform(-1, 1, n)
    out = np.empty((n, 3, 3))
    for i in range(n):
        Rs = np.array([[np.cos(ps[i]), -np.sin(ps[i]), 0], [np.sin(ps[i]), np.cos(ps[i]), 0], [0, 0, 1]])
        out[i] = rot_about([np.cos(ph[i]), np.sin(ph[i]), 0.0], th[i]) @ R_w @ Rs
    return out


def collect_socket_data(rng, truth_ball: KinModel, lay: SocketLayout, n_per_socket, R_w: np.ndarray, q_seed: np.ndarray,
                        cfg: CollectConfig) -> dict:
    """Simulate kinesthetic data collection: for every socket, `n_per_socket` arm configurations of the TRUE robot whose TRUE
    ball centre sits in the socket (plus seating noise), recorded as noisy joint readings. Infeasible draws (IK failure, joint
    limit margin) are re-drawn and counted. Returns only what a real user would have: joint readings, cluster ids, measured
    distances. Returns (data for the solver, hidden simulation diagnostics)."""
    counts = n_per_socket if np.ndim(n_per_socket) else [int(n_per_socket)] * len(lay.centres)
    qs, ids, rejected = [], [], 0
    for k, c in enumerate(lay.centres):
        got = 0
        tries = 0
        while got < counts[k]:
            tries += 1
            if tries > 50:
                raise RuntimeError(f"socket {k}: cannot find feasible configurations")
            m = counts[k] - got
            Rs = sample_orientations(rng, 2 * m, R_w, cfg.cone_deg, cfg.spin_deg)
            tgt = c + rng.normal(0, cfg.sigma_seat_mm, (2 * m, 3))
            q, pe, re, ok = truth_ball.ik(tgt, Rs, q_seed)
            ok &= truth_ball.within_limits(q, np.radians(cfg.margin_deg))
            ok &= np.max(np.abs(q - q_seed), axis=1) < np.radians(150)       # same branch as the writing posture
            rejected += int((~ok).sum())
            take = np.flatnonzero(ok)[:m]
            qs.append(q[take])
            ids.extend([k] * len(take))
            got += len(take)
    q_true = np.concatenate(qs)
    q_meas = q_true + rng.normal(0, np.radians(cfg.sigma_q_deg), q_true.shape)
    d_meas = lay.true_distances() + rng.normal(0, cfg.sigma_d_mm, len(lay.pairs))
    data = {"q": q_meas, "cluster": np.array(ids), "pairs": list(lay.pairs), "d": d_meas, "n_clusters": len(lay.centres)}
    hidden = {"q_true": q_true, "rejected": rejected}      # simulation-side diagnostics, never passed to the solver
    return data, hidden
