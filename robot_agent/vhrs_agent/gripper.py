"""Gripper IoT module: serial protocol, force table, safety rules (docs: "Gripper but dang thiet bi IoT", sections 6 and 7).

Hall sensor reading != force. The sensor gives a raw count; force exists only through a calibration table measured on
the team's own gripper (raw -> mN, experiment E1). Without that table the module reports UNCALIBRATED and the runner
refuses to write. Between table points the force is interpolated linearly; outside the measured range it is refused
rather than extrapolated.

Frame (device -> agent, 100 Hz, ASCII):   $F,<seq>,<t_ms>,<raw>,<force_mN>,<flags>*<cs>\n
Event:                                    $E,<NAME>,<arg>*<cs>\n
cs = XOR of every character between '$' and '*', two upper-case hex digits. flags: bit0 touching, bit1 over-force,
bit2 saturated, bit3 uncalibrated.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

FLAG_TOUCH, FLAG_OVERFORCE, FLAG_SATURATED, FLAG_UNCAL = 1, 2, 4, 8
STALE_AFTER_S = 0.100            # docs 5: the agent stops if frames are missing for more than 100 ms


class FrameError(ValueError):
    pass


def checksum(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"


def encode(body: str) -> str:
    return f"${body}*{checksum(body)}\n"


@dataclass(frozen=True)
class Sample:
    seq: int
    t_ms: int
    raw: int
    force_mn: int
    flags: int
    rx_time: float = field(default_factory=time.monotonic)

    @property
    def force_n(self) -> float:
        return self.force_mn / 1000.0

    @property
    def touching(self) -> bool:
        return bool(self.flags & FLAG_TOUCH)


def _split(line: str) -> tuple[str, str]:
    line = line.strip()
    if not line.startswith("$") or "*" not in line:
        raise FrameError("not a frame")
    body, _, cs = line[1:].rpartition("*")
    if checksum(body) != cs.strip().upper():
        raise FrameError("bad checksum")
    return body, cs


def parse_frame(line: str) -> Sample:
    body, _ = _split(line)
    parts = body.split(",")
    if parts[0] != "F" or len(parts) != 6:
        raise FrameError("not a force frame")
    try:
        seq, t_ms, raw, f_mn, flags = (int(x) for x in parts[1:])
    except ValueError as exc:
        raise FrameError("non-numeric field") from exc
    return Sample(seq, t_ms, raw, f_mn, flags)


def parse_event(line: str) -> tuple[str, str]:
    body, _ = _split(line)
    parts = body.split(",", 2)
    if parts[0] != "E" or len(parts) < 2:
        raise FrameError("not an event")
    return parts[1], parts[2] if len(parts) > 2 else ""


class ForceTable:
    """raw -> mN from the team's calibration points. Monotonic in raw, at least 2 points, no extrapolation."""

    def __init__(self, points: list[tuple[float, float]]):
        pts = sorted((float(r), float(f)) for r, f in points)
        if len(pts) < 2:
            raise ValueError("cần ít nhất 2 điểm hiệu chuẩn")
        raws = [p[0] for p in pts]
        if len(set(raws)) != len(raws):
            raise ValueError("raw bị trùng trong bảng hiệu chuẩn")
        self.raw = np.array(raws)
        self.mn = np.array([p[1] for p in pts])

    def force_mn(self, raw: float) -> float | None:
        if raw < self.raw[0] or raw > self.raw[-1]:
            return None
        return float(np.interp(raw, self.raw, self.mn))


@dataclass(frozen=True)
class Fault:
    code: str            # event type to report to the backend: OVER_FORCE | SENSOR_LOST | STROKE_LOST
    reason: str
    stop: bool           # True: stop and lift now. False: pause.


@dataclass(frozen=True)
class ForceLimits:
    """From the pen profile in the database (pen_types): all in N."""
    f_min: float
    f_target: float
    f_max: float
    f_hard: float
    contact_loss_s: float = 0.060        # SRS 3.6: force < 0.3 * F_min for more than 60 ms while writing


class SafetyMonitor:
    def __init__(self, limits: ForceLimits, now: Callable[[], float] = time.monotonic):
        self.limits, self.now = limits, now
        self._low_since: float | None = None
        self.last_seq: int | None = None
        self.dropped = 0

    def reset_contact(self) -> None:
        self._low_since = None

    def evaluate(self, sample: Sample | None, *, writing: bool) -> Fault | None:
        lim = self.limits
        if sample is None or self.now() - sample.rx_time > STALE_AFTER_S:
            return Fault("SENSOR_LOST", "Mất dữ liệu gripper quá 100 ms", True)
        if self.last_seq is not None and sample.seq != self.last_seq:
            self.dropped += max(0, (sample.seq - self.last_seq - 1) & 0xFFFFFFFF)
        self.last_seq = sample.seq
        if sample.flags & FLAG_UNCAL:
            return Fault("SENSOR_LOST", "Gripper báo chưa hiệu chuẩn", True)
        if sample.flags & FLAG_SATURATED:
            return Fault("OVER_FORCE", "Cảm biến Hall bão hoà: hành trình lò xo vượt cho phép", True)
        if sample.flags & FLAG_OVERFORCE or sample.force_n > lim.f_hard:
            return Fault("OVER_FORCE", f"Lực {sample.force_n:.2f} N vượt F_hard {lim.f_hard:.2f} N", True)
        if writing:
            if sample.force_n < 0.3 * lim.f_min:
                t = self.now()
                self._low_since = self._low_since if self._low_since is not None else t
                if t - self._low_since > lim.contact_loss_s:
                    return Fault("STROKE_LOST", "Mất tiếp xúc bút-giấy khi đang viết", False)
            else:
                self._low_since = None
        return None


class GripperPort:
    """Reads the device. Subclasses: SerialGripper (hardware), SimGripper (model)."""

    def latest(self) -> Sample | None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SimGripper(GripperPort):
    """Spring model: force = k * compression, compression = how far the commanded tip is below the paper surface.
    This is a MODEL fed by the planned path, not a measurement."""

    def __init__(self, depth_mm: Callable[[np.ndarray], float], k_n_per_mm: float, f_hard_n: float,
                 max_travel_mm: float, calibrated: bool = True, silent_after: int | None = None):
        self.depth_mm, self.k, self.f_hard, self.travel = depth_mm, k_n_per_mm, f_hard_n, max_travel_mm
        self.calibrated, self.silent_after = calibrated, silent_after
        self._seq, self._last = 0, None

    def observe(self, tcp_mm: np.ndarray) -> None:
        self._seq += 1
        if self.silent_after is not None and self._seq > self.silent_after:
            return                                              # rehearse a lost sensor
        comp = max(0.0, float(self.depth_mm(tcp_mm)))
        f = self.k * min(comp, self.travel)
        flags = (FLAG_TOUCH if comp > 0.0 else 0) | (FLAG_OVERFORCE if f > self.f_hard else 0) \
            | (FLAG_SATURATED if comp >= self.travel else 0) | (0 if self.calibrated else FLAG_UNCAL)
        self._last = Sample(self._seq, self._seq * 10, int(comp * 1000), int(round(f * 1000)), flags)

    def latest(self) -> Sample | None:
        if self.silent_after is not None and self._seq > self.silent_after:
            return None                                         # the sensor went quiet
        return self._last


class SerialGripper(GripperPort):  # pragma: no cover - needs the real device
    """USB-CDC reader thread. Needs pyserial and the physical module; not exercised by the automated tests."""

    def __init__(self, port: str, baud: int = 115200):
        import serial                                               # lazy: only real hardware needs it
        self._ser = serial.Serial(port, baud, timeout=0.05)
        self._last: Sample | None = None
        self._events: list[tuple[str, str]] = []
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while self._run:
            raw = self._ser.readline().decode("ascii", "ignore")
            if not raw:
                continue
            try:
                self._last = parse_frame(raw)
            except FrameError:
                try:
                    self._events.append(parse_event(raw))
                except FrameError:
                    pass                                            # corrupt line: ignored, staleness catches a dead link

    def latest(self) -> Sample | None:
        return self._last

    def send(self, command: str) -> None:
        self._ser.write(f"{command}\n".encode("ascii"))

    def close(self) -> None:
        self._run = False
        self._ser.close()
