"""SIM robot with a real joint model: the vendor's FR3 V6 URDF solved with PyBullet (see kinematics.py).

It follows the planned pen-tip path like SimRobot, and for every ~1 mm it solves the inverse kinematics so the 3D viewer can draw the
whole arm, and so reach, joint limits (with margin), solution branch, singularities and table clearance are checked at joint level.
It is still a SIMULATION: it models the vendor's kinematics, not the controller's firmware, the arm's dynamics or its real accuracy,
and it is always labelled SIM. The real controller's own inverse kinematics remains the authority in REAL mode.
"""
from __future__ import annotations

import numpy as np

from vhrs_agent.kinematics import READY_POSE_DEG, FR3Kinematics
from vhrs_agent.port import Control, RobotInfo, TcpCallback
from vhrs_agent.sim import SimRobot

IK_STEP_MM = 1.0


class PyBulletSimRobot(SimRobot):
    def __init__(self, kin: FR3Kinematics, start_mm=(-350.0, 0.0, 80.0), speed_factor: float | None = 1.0,
                 fail_after_s: float | None = None, yaw_deg: float = 0.0):
        super().__init__(start_mm, 559.8, speed_factor, fail_after_s)
        self.kin, self.yaw = kin, yaw_deg
        self._joints: np.ndarray | None = None
        self._ik_at: np.ndarray | None = None

    def connect(self) -> RobotInfo:
        info = super().connect()
        r = self.kin.ik(self._pos, None, self.yaw)
        self._joints = r.joints_deg if r.joints_deg is not None else READY_POSE_DEG.copy()
        self._ik_at = self._pos.copy()
        return RobotInfo(info.mode, "SIMULATED FR3 V6 (vendor URDF kinematics, PyBullet)",
                         note="vhrs simulator with a joint model: checks reach, limits, branch, singularity, table clearance; "
                              "it is not the controller")

    def read_joints(self) -> list[float] | None:
        return None if self._joints is None else [round(float(v), 3) for v in self._joints]

    def check_reachable(self, points_mm: np.ndarray) -> list[str]:
        problems, _ = self.kin.check_path(np.asarray(points_mm, dtype=np.float64), yaw_deg=self.yaw, seed_deg=self._joints)
        return problems

    def execute(self, points_mm: np.ndarray, speeds_mm_s: np.ndarray, ctl: Control, on_tcp: TcpCallback) -> None:
        def track(p: np.ndarray, t: float) -> None:
            if self._ik_at is None or float(np.linalg.norm(p - self._ik_at)) >= IK_STEP_MM:
                r = self.kin.ik(p, self._joints, self.yaw)
                if r.joints_deg is None:
                    ctl.request_stop(f"IK không có nghiệm tại {np.round(p, 1).tolist()} (sai số {r.error_mm:.2f} mm)")
                else:
                    self._joints, self._ik_at = r.joints_deg, np.array(p, dtype=np.float64)
            on_tcp(p, t)

        super().execute(points_mm, speeds_mm_s, ctl, track)
