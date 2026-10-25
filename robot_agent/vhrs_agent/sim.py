"""MOCK and SIM robots. Both are software only and always labelled as such (never reported as a real robot).

MockRobot: jumps to every target instantly. SimRobot: walks the path at the planned speeds in (optionally accelerated)
simulated time, so the operator can watch the pen move in the viewer and the safety rules see realistic timing.
SimRobot is OUR timing model: it knows nothing about joints, so it cannot prove an arm can reach a point; the
joint-level check exists only on the real controller.
"""
from __future__ import annotations

import time

import numpy as np

from vhrs_agent.port import Control, Mode, RobotInfo, RobotPort, TcpCallback


class MockRobot(RobotPort):
    mode = Mode.MOCK

    def __init__(self, start_mm=(0.0, 0.0, 100.0), reach_mm: float = 559.8):
        self._pos = np.array(start_mm, dtype=np.float64)
        self._reach, self._alive, self.stopped = reach_mm, False, 0
        self.commands: list[str] = []

    def connect(self) -> RobotInfo:
        self._alive = True
        return RobotInfo(Mode.MOCK, "MOCK (no robot)", note="software mock, nothing moves")

    def disconnect(self) -> None:
        self._alive = False

    def heartbeat(self) -> bool:
        return self._alive

    def read_tcp(self) -> np.ndarray:
        return self._pos.copy()

    def check_reachable(self, points_mm: np.ndarray) -> list[str]:
        r = np.linalg.norm(points_mm, axis=1)
        return [f"point {int(np.argmax(r))} is {float(r.max()):.1f} mm from the base"] if float(r.max()) > self._reach else []

    def execute(self, points_mm: np.ndarray, speeds_mm_s: np.ndarray, ctl: Control, on_tcp: TcpCallback) -> None:
        self.commands.append(f"execute n={len(points_mm)}")
        for i, p in enumerate(points_mm):
            if i % 50 == 0:
                ctl.checkpoint()
            self._pos = np.asarray(p, dtype=np.float64)
            on_tcp(self._pos, 0.0)

    def align_to(self, target_mm: np.ndarray, ctl: Control, box=None) -> dict:
        moved = float(np.linalg.norm(self._pos - np.asarray(target_mm, dtype=np.float64)))
        self._pos = np.asarray(target_mm, dtype=np.float64)
        self.commands.append("align_to")
        return {"moved": moved > 0.3, "distance_mm": moved, "angle_deg": 0.0}

    def stop(self) -> None:
        self.stopped += 1


class SimRobot(MockRobot):
    mode = Mode.SIM

    def __init__(self, start_mm=(0.0, 0.0, 100.0), reach_mm: float = 559.8, speed_factor: float | None = 1.0,
                 fail_after_s: float | None = None):
        """speed_factor: 1.0 = real time, 10 = ten times faster, None = no waiting (tests).
        fail_after_s: simulated time after which the link drops (to rehearse communication loss)."""
        super().__init__(start_mm, reach_mm)
        self.speed_factor, self.fail_after_s, self.sim_time = speed_factor, fail_after_s, 0.0

    def connect(self) -> RobotInfo:
        self._alive = True
        return RobotInfo(Mode.SIM, "SIMULATED FR3 (kinematic timing model)",
                         note="vhrs simulator: verifies timing and path, not joint reachability")

    def _link_ok(self) -> bool:
        return self._alive and not (self.fail_after_s is not None and self.sim_time >= self.fail_after_s)

    def heartbeat(self) -> bool:
        return self._link_ok()

    def execute(self, points_mm: np.ndarray, speeds_mm_s: np.ndarray, ctl: Control, on_tcp: TcpCallback) -> None:
        from vhrs_agent.port import CommunicationLost
        self.commands.append(f"execute n={len(points_mm)}")
        last_tick = time.monotonic()
        for i in range(len(points_mm) - 1):
            ctl.checkpoint()
            if not self._link_ok():
                raise CommunicationLost("LINK_DOWN", "Simulated link lost during a motion; outcome unknown.")
            a, b = np.asarray(points_mm[i], float), np.asarray(points_mm[i + 1], float)
            v = max(0.5 * float(speeds_mm_s[i] + speeds_mm_s[i + 1]), 1e-6)
            dt = float(np.linalg.norm(b - a)) / v
            self.sim_time += dt
            self._pos = b
            on_tcp(b, self.sim_time)
            if self.speed_factor:
                now = time.monotonic()
                wait = dt / self.speed_factor - (now - last_tick)
                if wait > 0.0005:
                    time.sleep(wait)
                last_tick = time.monotonic()
        if len(points_mm) == 1:
            self._pos = np.asarray(points_mm[0], float)
            on_tcp(self._pos, self.sim_time)


class RunawaySimRobot(SimRobot):
    """REHEARSAL ONLY: a simulated robot that ignores the stop command, to show the operator what the red alert looks like.
    It exists so people can practise; no real robot is ever represented by it."""

    def stop(self) -> None:
        super().stop()
        self._runaway = True

    def read_tcp(self) -> np.ndarray:
        if getattr(self, "_runaway", False):
            self._pos = self._pos + np.array([5.0, 0.0, 0.0])
        return self._pos.copy()
