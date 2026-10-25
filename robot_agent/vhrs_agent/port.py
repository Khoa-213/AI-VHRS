"""The one interface the job runner uses to move a robot. Three adapters implement it: MOCK, SIM and REAL (Fairino)."""
from __future__ import annotations

import enum
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


class Mode(str, enum.Enum):
    MOCK = "MOCK"        # no kinematics, instant: exercises the software flow only
    SIM = "SIM"          # our own kinematic timing model: NOT the vendor's simulator and NOT a robot
    REAL = "REAL"        # the FAIRINO controller; only after the operator's per-job authorization


class RobotError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


class CommunicationLost(RobotError):
    """The link broke; what the robot did with the last command is unknown. The runner never resends it."""


class StopRequested(Exception):
    """Raised inside a motion when the operator (or a safety rule) asked to stop."""


@dataclass
class RobotInfo:
    mode: Mode
    model: str
    controller_version: str | None = None
    firmware_version: str | None = None
    sdk_version: str | None = None
    ip: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode.value, "model": self.model, "controller_version": self.controller_version,
                "firmware_version": self.firmware_version, "sdk_version": self.sdk_version, "ip": self.ip, "note": self.note}


@dataclass
class Control:
    """Stop / pause flags shared between the operator side (viewer, CLI) and the motion loop."""
    stop: threading.Event = field(default_factory=threading.Event)
    paused: threading.Event = field(default_factory=threading.Event)
    pause_after_stroke: threading.Event = field(default_factory=threading.Event)   # lost link: pause where the pen is already lifted
    reason: str = ""

    def request_stop(self, reason: str) -> None:
        self.reason = self.reason or reason
        self.stop.set()

    def checkpoint(self) -> None:
        """Call between motion steps: raises StopRequested on stop, blocks while paused."""
        while self.paused.is_set() and not self.stop.is_set():
            self.stop.wait(0.05)
        if self.stop.is_set():
            raise StopRequested(self.reason or "stop")


TcpCallback = Callable[[np.ndarray, float], None]      # (xyz mm in the base frame, time s)


class RobotPort(ABC):
    mode: Mode

    @abstractmethod
    def connect(self) -> RobotInfo:
        """Open the link and READ identification. Must not enable the robot and must not move it."""

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def heartbeat(self) -> bool:
        """True while the link is alive and the controller reports no error and no emergency stop."""

    @abstractmethod
    def read_tcp(self) -> np.ndarray:
        """Current pen-tip position in the base frame, mm."""

    def read_joints(self) -> list[float] | None:
        """Joint angles in degrees for the 3D viewer, or None when this robot has no joint model (MOCK, simple SIM)."""
        return None

    def align_to(self, target_mm: np.ndarray, ctl: "Control", box=None) -> dict:
        """Bring the arm from where it is to `target_mm` with the fixed writing orientation (software robots just jump there)."""
        raise NotImplementedError

    def check_start_ready(self) -> None:
        """Read-only adapter-specific start checks; raise RobotError if not ready."""

    def execution_signature(self) -> str | None:
        """Bind a REAL rehearsal to the adapter and its motion settings."""
        return None

    @abstractmethod
    def check_reachable(self, points_mm: np.ndarray) -> list[str]:
        """Joint-level reachability of sampled points WITHOUT moving (inverse kinematics). Returns problems."""

    @abstractmethod
    def execute(self, points_mm: np.ndarray, speeds_mm_s: np.ndarray, ctl: Control, on_tcp: TcpCallback) -> None:
        """Move the pen tip through `points_mm` at the given speeds. Raises StopRequested / CommunicationLost."""

    @abstractmethod
    def stop(self) -> None:
        """Software stop. NOT a replacement for the physical emergency stop."""
