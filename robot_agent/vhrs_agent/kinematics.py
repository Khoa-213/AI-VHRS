"""FAIRINO FR3 V6 kinematics from the vendor's own URDF, computed with PyBullet (inverse kinematics, collision, singularity).

Why: the web viewer needs joint angles to draw the arm, and the simulator needs joint-level checks (reach, joint limits with margin,
solution branch, wrist singularity, collision with the table) that the position-only SIM robot cannot do. This is the vendor's MODEL
of the robot, not the robot: the real controller's own inverse kinematics (`GetInverseKin`) stays the authority for REAL mode.

ASSUMPTIONS to be verified on the real robot (`verify_against_controller`):
  * the URDF base frame equals the controller's base frame (same origin, same zero direction of joint 1);
  * the URDF joint limits equal the controller's soft limits (compare with `GetJointSoftLimitDeg`);
  * `tool_offset_mm` is the distance from the URDF frame of link wrist3 to the pen tip along the tool axis. That frame is about 103 mm
    BEHIND the flange face (the wrist3 mesh extends that far past it), so it is flange offset + gripper + pen, not the pen alone. It is a
    measured value, not a guess; if it is too short the flange mesh pokes into the table and the clearance check reports it.
Units at this interface: millimetres and degrees. PyBullet itself works in metres and radians.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_URDF = Path(__file__).resolve().parents[1] / "vendor" / "fr3" / "fairino3_v6.urdf"
JOINT_MARGIN_DEG = 5.0          # SRS S8: stay at least this far from every joint limit
MAX_STEP_JUMP_DEG = 25.0        # between two samples 5 mm apart: more than this means the solver jumped to another branch
IK_TOLERANCE_MM = 0.05
READY_POSE_DEG = np.array([0.0, -100.0, 110.0, -100.0, -90.0, 0.0])   # a natural "pen down in front of the robot" posture (elbow up)
SINGULARITY_RATIO = 0.02        # sigma_min / sigma_max of the Jacobian below this = near a singularity


class KinematicsUnavailable(RuntimeError):
    pass


@dataclass
class IkResult:
    joints_deg: np.ndarray | None
    error_mm: float
    tilt_deg: float


class FR3Kinematics:
    def __init__(self, urdf: Path | None = None, *, tool_offset_mm: float, table_z_mm: float | None = None):
        try:
            import pybullet as p
        except ImportError as exc:                                          # pragma: no cover - environment dependent
            raise KinematicsUnavailable("PyBullet chưa cài (dùng môi trường .simenv, xem robot_agent/README.md).") from exc
        self.p = p
        self.urdf = Path(urdf or DEFAULT_URDF)
        if not self.urdf.exists():
            raise KinematicsUnavailable(f"Chưa có mô hình FR3 ({self.urdf}). Chạy scripts/fetch_fr3_model.py.")
        self.tool_m = float(tool_offset_mm) / 1000.0
        self.cid = p.connect(p.DIRECT)
        local = self.urdf.with_name("local.urdf")                           # absolute mesh paths for PyBullet
        meshes = (self.urdf.parent / "meshes").as_posix()
        local.write_text(self.urdf.read_text(encoding="utf8").replace("package://fairino_description/meshes/fairino3_v6/", meshes + "/"),
                         encoding="utf8")
        self.rid = p.loadURDF(str(local), useFixedBase=True, physicsClientId=self.cid)
        self.n = 6
        infos = [p.getJointInfo(self.rid, i, physicsClientId=self.cid) for i in range(self.n)]
        self.lower = np.array([i[8] for i in infos])
        self.upper = np.array([i[9] for i in infos])
        self.link = self.n - 1
        self.joint_names = [i[1].decode() for i in infos]
        self.table_id: int | None = None
        if table_z_mm is not None:
            self.set_table(table_z_mm)

    # ---------------------------------------------------------------- model
    @property
    def limits_deg(self) -> list[tuple[float, float]]:
        return [(math.degrees(a), math.degrees(b)) for a, b in zip(self.lower, self.upper)]

    def set_table(self, z_mm: float) -> None:
        p = self.p
        if self.table_id is not None:
            p.removeBody(self.table_id, physicsClientId=self.cid)
        half = [1.0, 1.0, 0.01]
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=self.cid)
        self.table_id = p.createMultiBody(0, col, basePosition=[0, 0, z_mm / 1000.0 - half[2]], physicsClientId=self.cid)

    def _set(self, joints_deg: np.ndarray) -> None:
        for i, q in enumerate(np.radians(joints_deg)):
            self.p.resetJointState(self.rid, i, float(q), physicsClientId=self.cid)

    # ---------------------------------------------------------------- forward kinematics
    def fk(self, joints_deg: Any) -> tuple[np.ndarray, np.ndarray]:
        """Pen-tip position (mm) and the unit vector of the tool axis, in the base frame."""
        self._set(np.asarray(joints_deg, dtype=np.float64))
        st = self.p.getLinkState(self.rid, self.link, computeForwardKinematics=True, physicsClientId=self.cid)
        pos, orn = np.array(st[4]), st[5]
        rot = np.array(self.p.getMatrixFromQuaternion(orn)).reshape(3, 3)
        tool_axis = rot[:, 2]
        return (pos + tool_axis * self.tool_m) * 1000.0, tool_axis

    # ---------------------------------------------------------------- inverse kinematics
    def ik(self, tcp_mm: Any, seed_deg: Any | None = None, yaw_deg: float = 0.0) -> IkResult:
        """Joints that put the pen tip at `tcp_mm` with the tool axis pointing straight down (pen perpendicular to a horizontal sheet);
        `yaw_deg` is the rotation of the pen about its own axis (it only matters for the last joint)."""
        p = self.p
        target = np.asarray(tcp_mm, dtype=np.float64)
        orn = p.getQuaternionFromEuler([math.pi, 0.0, math.radians(yaw_deg)])
        link_pos = (target / 1000.0 + np.array([0.0, 0.0, self.tool_m])).tolist()      # tool axis is -Z, so the wrist is above the tip
        seed = np.zeros(self.n) if seed_deg is None else np.asarray(seed_deg, dtype=np.float64)
        rng = (self.upper - self.lower).tolist()
        starts = [seed] if seed_deg is not None else self._starts(target)
        cands: list[IkResult] = []
        for start in starts:
            self._set(start)
            q = np.degrees(self._solve(link_pos, orn, np.radians(start), rng))
            q = self._refine(q, target)                                                # Newton polish: PyBullet's solver stops near 0.05-0.1 mm
            pos, axis = self.fk(q)
            err = float(np.linalg.norm(pos - target))
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(-axis[2])))))
            if np.any(np.radians(q) < self.lower - 1e-6) or np.any(np.radians(q) > self.upper + 1e-6):
                err = max(err, 1e3)
            cands.append(IkResult(q, err, tilt))
            if seed_deg is not None and err < IK_TOLERANCE_MM and tilt < 0.1:
                break                                                                  # continuing a path: keep the neighbouring solution
        good = [c for c in cands if c.error_mm < IK_TOLERANCE_MM and c.tilt_deg < 0.5]
        if good and seed_deg is None:
            def cost(c: IkResult) -> float:                                            # most natural: closest to the ready posture, clear of the table
                clear = self.table_clearance_mm(c.joints_deg)
                return float(np.sum(np.abs(c.joints_deg - READY_POSE_DEG))) + (1e4 if clear is not None and clear < 5.0 else 0.0)
            return min(good, key=cost)
        if good:
            return good[0]
        worst = min(cands, key=lambda c: c.error_mm)
        return IkResult(None, worst.error_mm, worst.tilt_deg)

    def _refine(self, q_deg: np.ndarray, target_mm: np.ndarray, iters: int = 15) -> np.ndarray:
        """Damped Gauss-Newton on 5 constraints (pen-tip position + tool axis straight down); the sixth joint (pen spin) keeps the
        solution closest to where it was, which also keeps a path continuous. Jacobian by finite differences of the URDF kinematics."""
        q = np.clip(q_deg, np.degrees(self.lower), np.degrees(self.upper))
        goal_axis = np.array([0.0, 0.0, -1.0])
        for _ in range(iters):
            pos, axis = self.fk(q)
            e = np.concatenate([target_mm - pos, 100.0 * (goal_axis - axis)[:2]])
            if float(np.linalg.norm(e[:3])) < 1e-4 and float(np.linalg.norm(e[3:])) < 1e-4:
                break
            jac = np.zeros((5, self.n))
            h = 1e-3                                                                   # degrees
            for j in range(self.n):
                qj = q.copy()
                qj[j] += h
                pj, aj = self.fk(qj)
                jac[:3, j] = (pj - pos) / h
                jac[3:, j] = 100.0 * (-(aj - axis)[:2]) / h * -1.0
            lam = 1e-3
            dq = jac.T @ np.linalg.solve(jac @ jac.T + lam * np.eye(5), e)
            q = np.clip(q + np.clip(dq, -20.0, 20.0), np.degrees(self.lower), np.degrees(self.upper))
        return q

    def _solve(self, link_pos: list[float], orn: Any, rest: np.ndarray, rng: list[float]) -> np.ndarray:
        sol = self.p.calculateInverseKinematics(self.rid, self.link, link_pos, orn, lowerLimits=self.lower.tolist(),
                                                upperLimits=self.upper.tolist(), jointRanges=rng, restPoses=rest.tolist(),
                                                maxNumIterations=400, residualThreshold=1e-8, physicsClientId=self.cid)
        return np.array(sol[: self.n])

    def _starts(self, target: np.ndarray) -> list[np.ndarray]:
        """Seeds around the usual \"pen down in front\" postures: the base turned towards the target (the arm's zero points along -X), elbow up,
        wrist either way. The first valid, most natural one wins."""
        a = math.degrees(math.atan2(target[1], target[0])) - 180.0
        a = (a + 180.0) % 360.0 - 180.0
        out = []
        for j1 in (a, a - 10.0, a + 10.0, a - 25.0, a + 25.0):
            for j2, j3, j4 in ((-100, 115, -105), (-80, 90, -100), (-120, 130, -90), (-100, 70, -60), (-90, 140, -130)):
                for j5 in (-90.0, 90.0):
                    out.append(np.array([j1, j2, j3, j4, j5, 0.0]))
        return out

    # ---------------------------------------------------------------- checks
    def margin_to_limits_deg(self, joints_deg: Any) -> float:
        q = np.radians(np.asarray(joints_deg, dtype=np.float64))
        return float(math.degrees(min(np.min(q - self.lower), np.min(self.upper - q))))

    def jacobian_ratio(self, joints_deg: Any) -> float:
        """sigma_min / sigma_max of the 6x6 Jacobian at the wrist point: near 0 means a singularity."""
        q = np.radians(np.asarray(joints_deg, dtype=np.float64)).tolist()
        zero = [0.0] * self.n
        jl, ja = self.p.calculateJacobian(self.rid, self.link, [0, 0, 0], q, zero, zero, physicsClientId=self.cid)
        s = np.linalg.svd(np.vstack([np.array(jl), np.array(ja)]), compute_uv=False)
        return float(s[-1] / s[0]) if s[0] > 0 else 0.0

    def table_clearance_mm(self, joints_deg: Any) -> float | None:
        """Smallest distance (mm) between the arm links and the table; None when no table was set. Negative = penetration."""
        if self.table_id is None:
            return None
        self._set(np.asarray(joints_deg, dtype=np.float64))
        pts = self.p.getClosestPoints(self.rid, self.table_id, distance=0.2, physicsClientId=self.cid)
        d = [c[8] for c in pts if c[3] >= 1]                  # links 1.. ; the base link stands on the table by design
        return min(d) * 1000.0 if d else 200.0

    @staticmethod
    def densify(points_mm: np.ndarray, step_mm: float = 5.0) -> np.ndarray:
        """Insert points so no two neighbours are further apart than `step_mm`: a long pen-up move must be checked along its way,
        not only at its two ends (the arm could pass a limit or a singularity in between)."""
        pts = np.asarray(points_mm, dtype=np.float64)
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            n = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / step_mm)))
            out.extend(a + (b - a) * (k / n) for k in range(1, n + 1))
        return np.array(out)

    def check_path(self, points_mm: np.ndarray, *, yaw_deg: float = 0.0, seed_deg: Any | None = None,
                   margin_deg: float = JOINT_MARGIN_DEG, max_jump_deg: float = MAX_STEP_JUMP_DEG,
                   min_table_clearance_mm: float = 1.0) -> tuple[list[str], np.ndarray]:
        """Joint-level feasibility of sampled points (about 5 mm apart): reach, limit margin, one solution branch, singularity,
        table clearance. Returns (problems, joints (N, 6) with NaN where unsolved)."""
        problems: list[str] = []
        points_mm = self.densify(points_mm)
        joints = np.full((len(points_mm), self.n), np.nan)
        prev = None if seed_deg is None else np.asarray(seed_deg, dtype=np.float64)
        for i, pt in enumerate(points_mm):
            r = self.ik(pt, prev, yaw_deg)
            if r.joints_deg is None and prev is not None:
                r = self.ik(pt, None, yaw_deg)                  # retry with the spread of seeds before calling it unreachable
            if r.joints_deg is None:
                problems.append(f"point {i}: no inverse-kinematics solution (error {r.error_mm:.2f} mm)")
                if len(problems) >= 20:
                    break
                continue
            q = r.joints_deg
            joints[i] = q
            if prev is not None and float(np.max(np.abs(q - prev))) > max_jump_deg:
                problems.append(f"point {i}: a joint jumps {float(np.max(np.abs(q - prev))):.0f} deg between samples (another solution branch)")
            m = self.margin_to_limits_deg(q)
            if m < margin_deg:
                problems.append(f"point {i}: a joint is {m:.1f} deg from its limit (minimum {margin_deg:g})")
            if self.jacobian_ratio(q) < SINGULARITY_RATIO:
                problems.append(f"point {i}: near a wrist or arm singularity")
            c = self.table_clearance_mm(q)
            if c is not None and c < min_table_clearance_mm:
                problems.append(f"point {i}: the arm is {c:.1f} mm from the table")
            prev = q
            if len(problems) >= 20:
                break
        return problems, joints

    def verify_against_controller(self, joints_deg: Any, controller_tcp_mm: Any, tolerance_mm: float = 2.0) -> dict[str, Any]:
        """Hardware validation helper: forward kinematics of the URDF vs the pose the real controller reports for the same joints.
        A big difference means the base frames or the tool offset do not match; do not trust the simulator's numbers until it is small."""
        pos, _ = self.fk(joints_deg)
        err = float(np.linalg.norm(pos - np.asarray(controller_tcp_mm, dtype=np.float64)))
        return {"urdf_tcp_mm": pos.round(2).tolist(), "controller_tcp_mm": list(controller_tcp_mm), "error_mm": round(err, 2),
                "within_tolerance": err <= tolerance_mm}

    def close(self) -> None:
        try:
            self.p.disconnect(physicsClientId=self.cid)
        except Exception:                                       # noqa: BLE001
            pass
