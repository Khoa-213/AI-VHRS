"""Batched serial-chain kinematics of the FAIRINO FR3 V6 in the URDF parameterisation used by MUKCa.

Every joint i has a fixed origin transform (x, y, z in mm; roll, pitch, yaw in rad, URDF convention R = Rz(y) Ry(p) Rx(r))
followed by a rotation q_i about its local z axis. A rigid tool offset t (mm, in the last link frame) gives the tool-centre
point (TCP). This is exactly the parameterisation of a URDF <joint><origin .../></joint>, so a calibrated parameter set can be
written back into a URDF without conversion (the reason MUKCa chose it).

Units: mm and rad inside this module. Pure numpy; PyBullet is used only as an independent cross-check (tests/scripts).

Nominal values come from the vendor URDF `robot_agent/vendor/fr3/fairino3_v6.urdf` (FAIR-INNOVATION/frcobot_ros2). They are
embedded here (they are 36 numbers, not the mesh files) and `load_urdf_origins` re-reads the URDF so tests can confirm they match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
URDF_PATH = REPO_ROOT / "robot_agent" / "vendor" / "fr3" / "fairino3_v6.urdf"

# joint origins from the vendor URDF: x, y, z [mm], roll, pitch, yaw [rad]
NOMINAL_ORIGINS = np.array([
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 140.0, 1.5708, 0.0, 0.0],
    [-280.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [-240.01, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 102.0, 1.5708, 0.0, 0.0],
    [0.0, 0.0, 102.0, -1.5708, 0.0, 0.0],
])
# joint limits from the same URDF [rad]
JOINT_LOWER = np.array([-3.0543, -4.6251, -2.8274, -4.6251, -3.0543, -3.0543])
JOINT_UPPER = np.array([3.0543, 1.4835, 2.8274, 1.4835, 3.0543, 3.0543])
# Controller flange = URDF wrist3 frame + 100 mm along its z axis (found by comparing URDF FK with two read-only controller
# readings of GetActualJointPosDegree / GetActualToolFlangePose, see scripts/validate_urdf_vs_controller.py).
FLANGE_OFFSET_MM = 100.0
# URDF link masses [kg] (vendor URDF <inertial>), used only by the optional gravity-compliance term of the ground truth
LINK_MASS_KG = np.array([2.24, 4.94, 2.29, 1.56, 1.56, 0.36])


def rpy_matrix(r: np.ndarray, p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """URDF fixed-axis roll-pitch-yaw, R = Rz(y) Ry(p) Rx(r). Broadcasts over leading dims; returns (..., 3, 3)."""
    r, p, y = np.broadcast_arrays(np.asarray(r, float), np.asarray(p, float), np.asarray(y, float))
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    out = np.empty(r.shape + (3, 3))
    out[..., 0, 0] = cy * cp
    out[..., 0, 1] = cy * sp * sr - sy * cr
    out[..., 0, 2] = cy * sp * cr + sy * sr
    out[..., 1, 0] = sy * cp
    out[..., 1, 1] = sy * sp * sr + cy * cr
    out[..., 1, 2] = sy * sp * cr - cy * sr
    out[..., 2, 0] = -sp
    out[..., 2, 1] = cp * sr
    out[..., 2, 2] = cp * cr
    return out


def matrix_to_rpy(R: np.ndarray) -> np.ndarray:
    pitch = -np.arcsin(np.clip(R[..., 2, 0], -1.0, 1.0))
    roll = np.arctan2(R[..., 2, 1], R[..., 2, 2])
    yaw = np.arctan2(R[..., 1, 0], R[..., 0, 0])
    return np.stack([roll, pitch, yaw], axis=-1)


def origin_transform(row: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = rpy_matrix(row[3], row[4], row[5])
    T[:3, 3] = row[:3]
    return T


def load_urdf_origins(path: Path = URDF_PATH) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Re-read joint origins (mm, rad) and limits from the vendor URDF (for verification only)."""
    text = path.read_text(encoding="utf8")
    rows, lo, hi = [], [], []
    for m in re.finditer(r'<joint\s+name="(j\d)"\s+type="revolute">(.*?)</joint>', text, re.S):
        body = m.group(2)
        o = re.search(r'<origin\s+xyz="([^"]+)"\s+rpy="([^"]+)"', body)
        a = re.search(r'<axis\s+xyz="([^"]+)"', body)
        lim = re.search(r'<limit\s+lower="([^"]+)"\s+upper="([^"]+)"', body)
        assert a is not None and [float(v) for v in a.group(1).split()] == [0.0, 0.0, 1.0], "all FR3 joints rotate about local z"
        xyz = [float(v) * 1000.0 for v in o.group(1).split()]
        rpy = [float(v) for v in o.group(2).split()]
        rows.append(xyz + rpy)
        lo.append(float(lim.group(1)))
        hi.append(float(lim.group(2)))
    return np.array(rows), np.array(lo), np.array(hi)


@dataclass
class KinModel:
    """A kinematic model: 6 joint origins + tool offset. `joint_error` (optional, ground truth only) maps commanded/encoder joint
    angles (N, 6) to the extra link-side rotation (N, 6) that the model does not know about (unmodelled non-geometric errors)."""
    origins: np.ndarray = field(default_factory=lambda: NOMINAL_ORIGINS.copy())
    tool: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, FLANGE_OFFSET_MM]))
    joint_error: object | None = None
    name: str = "nominal"

    def copy(self, **kw) -> "KinModel":
        d = dict(origins=self.origins.copy(), tool=self.tool.copy(), joint_error=self.joint_error, name=self.name)
        d.update(kw)
        return KinModel(**d)

    def with_tool(self, tool_flange_mm: np.ndarray) -> "KinModel":
        """Same arm, tool given relative to the controller FLANGE frame (the wrist3 frame shifted 100 mm along z)."""
        return self.copy(tool=np.asarray(tool_flange_mm, float) + np.array([0.0, 0.0, FLANGE_OFFSET_MM]))

    # ------------------------------------------------------------------ forward kinematics
    def chain(self, q: np.ndarray):
        """Batched FK. q: (N, 6) rad. Returns tip (N,3), R (N,3,3), joint axes (N,6,3), joint origins (N,6,3)."""
        q = np.atleast_2d(np.asarray(q, float))
        if self.joint_error is not None:
            q = q + self.joint_error(q)
        n = q.shape[0]
        T = np.broadcast_to(np.eye(4), (n, 4, 4)).copy()
        axes = np.empty((n, 6, 3))
        orgs = np.empty((n, 6, 3))
        for i in range(6):
            T = T @ origin_transform(self.origins[i])
            axes[:, i] = T[:, :3, 2]
            orgs[:, i] = T[:, :3, 3]
            c, s = np.cos(q[:, i]), np.sin(q[:, i])
            Rz = np.zeros((n, 4, 4))
            Rz[:, 0, 0], Rz[:, 0, 1], Rz[:, 1, 0], Rz[:, 1, 1] = c, -s, s, c
            Rz[:, 2, 2] = Rz[:, 3, 3] = 1.0
            T = T @ Rz
        R = T[:, :3, :3]
        tip = T[:, :3, 3] + R @ self.tool
        return tip, R, axes, orgs

    def fk(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        tip, R, _, _ = self.chain(q)
        return tip, R

    def jacobian(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Geometric Jacobian at the TCP: (N, 6, 6) with rows [v (mm/rad); w (rad/rad)]. Ignores joint_error's derivative
        (it is a tiny correction; the IK iterates on the true FK residual, so convergence is unaffected)."""
        tip, R, axes, orgs = self.chain(q)
        Jv = np.cross(axes, tip[:, None, :] - orgs)            # (N, 6, 3)
        J = np.concatenate([Jv, axes], axis=2).transpose(0, 2, 1)
        return J, tip, R

    # ------------------------------------------------------------------ inverse kinematics (batched, damped least squares)
    def ik(self, p_target: np.ndarray, R_target: np.ndarray, q_seed: np.ndarray, *, iters: int = 100,
           tol_mm: float = 1e-6, tol_rad: float = 1e-9, damping: float = 1e-4, rot_scale: float = 500.0):
        """Full-pose IK for N targets at once. Returns q (N,6), position error (N,) mm, orientation error (N,) rad, converged (N,).
        `rot_scale` (mm/rad) weights orientation against position in the damped step; all targets start from `q_seed`
        (one seed (6,) or one per target (N,6)), so a whole stroke stays on the seed's solution branch."""
        p_target = np.atleast_2d(np.asarray(p_target, float))
        n = p_target.shape[0]
        R_target = np.broadcast_to(R_target, (n, 3, 3))
        q = np.broadcast_to(np.asarray(q_seed, float), (n, 6)).copy()
        active = np.ones(n, bool)
        for _ in range(iters):
            J, tip, R = self.jacobian(q[active])
            ep = p_target[active] - tip
            er = 0.5 * sum(np.cross(R[:, :, k], R_target[active][:, :, k]) for k in range(3))
            e = np.concatenate([ep, rot_scale * er], axis=1)
            Js = J.copy()
            Js[:, 3:, :] *= rot_scale
            A = Js @ Js.transpose(0, 2, 1) + damping * np.eye(6)
            dq = np.einsum("nji,nj->ni", Js, np.linalg.solve(A, e[..., None])[..., 0])
            dq = np.clip(dq, -0.2, 0.2)
            idx = np.flatnonzero(active)
            q[idx] += dq
            done = (np.linalg.norm(ep, axis=1) < tol_mm) & (np.linalg.norm(er, axis=1) < tol_rad)
            active[idx[done]] = False
            if not active.any():
                break
        tip, R = self.fk(q)
        perr = np.linalg.norm(p_target - tip, axis=1)
        rerr = np.linalg.norm(0.5 * sum(np.cross(R[:, :, k], R_target[:, :, k]) for k in range(3)), axis=1)
        conv = (perr < 1e-4) & (rerr < 1e-7)
        return q, perr, rerr, conv

    def within_limits(self, q: np.ndarray, margin_rad: float = np.radians(5.0)) -> np.ndarray:
        q = np.atleast_2d(q)
        return np.all((q > JOINT_LOWER + margin_rad) & (q < JOINT_UPPER - margin_rad), axis=1)


def gravity_torques(model: KinModel, q: np.ndarray, payload_kg: float = 0.6) -> np.ndarray:
    """Static gravity torque (N*m) on each joint, base z up, with each link's mass lumped at the midpoint of its two joint origins
    (an APPROXIMATION: the vendor URDF's centre-of-mass entries are not trusted, see METHODOLOGY.md) and the payload at the TCP."""
    tip, R, axes, orgs = model.chain(q)
    g = np.array([0.0, 0.0, -9.81])
    pts = np.concatenate([orgs, tip[:, None, :]], axis=1)          # (N, 7, 3) mm
    com = 0.5 * (pts[:, :-1] + pts[:, 1:]) / 1000.0                  # link i between joint i and joint i+1 (last: wrist to tip)
    masses = LINK_MASS_KG.copy()
    tau = np.zeros((q.shape[0], 6))
    for j in range(6):
        oj = orgs[:, j] / 1000.0
        mom = np.zeros((q.shape[0], 3))
        for k in range(j, 6):
            mom += np.cross(com[:, k] - oj, masses[k] * g)
        mom += np.cross(tip / 1000.0 - oj, payload_kg * g)
        tau[:, j] = np.einsum("ni,ni->n", mom, axes[:, j])
    return tau
