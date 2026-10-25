"""Trajectory (paper mm) -> robot motion plan (SRS S5-S7, S9 preparation). Pure numpy, no I/O, no robot.

For every page the plan is a list of moves in the robot BASE frame:

  travel   pen up, at the clearance height, from the end of the previous stroke to above the next stroke's start
  plunge   straight down to the writing depth (slow, the Agent watches the gripper for contact on the way)
  write    the stroke, resampled, with a speed per point
  retract  straight up to the clearance height

Every number that depends on the robot, the pen holder or the paper comes from MotionConfig and is None until the
workshop measures it. A plan is refused while anything is missing (UNCONFIGURED), nothing is defaulted.

Writing depth follows the gripper design: the pen tip is pressed below the paper surface by f_target / k (the spring
compression), so the spring, not a fast force loop, holds the contact force (docs: gripper research, section 6.4).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np

from app.services.motion.frame import PaperFrame
from app.services.stroke_ai.trajectory import Page

DEFAULT_DS_MM = 0.2          # SRS S5 resampling step
DEFAULT_CORNER_DEG = 60.0    # SRS S5: corners sharper than this are kept as vertices
V_FLOOR_MM_S = 5.0           # SRS S6: speed at the start / end of a stroke and at corners


class PlanError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


@dataclass(frozen=True)
class MotionConfig:
    """Measured, per-station values. None = UNCONFIGURED (never replaced by a default)."""
    a_lat_mm_s2: float | None = None            # lateral acceleration limit used for the curvature speed cap
    a_tan_mm_s2: float | None = None            # tangential acceleration limit (forward / backward pass)
    travel_speed_mm_s: float | None = None      # pen-up speed
    approach_speed_mm_s: float | None = None    # speed of plunge and retract
    pen_up_clearance_mm: float | None = None    # pen tip height above the paper while travelling
    spring_k_n_per_mm: float | None = None      # gripper spring rate, measured (experiments E1-E2)
    max_spring_travel_mm: float | None = None   # mechanical stop of the gripper slide
    f_target_n: float | None = None             # from the pen profile (pen_types.f_target_n)
    v_max_mm_s: float | None = None             # from the pen profile (pen_types.v_max_mm_s)

    def missing(self) -> list[str]:
        return [f.name for f in fields(self) if getattr(self, f.name) is None]

    def require(self) -> None:
        miss = self.missing()
        if miss:
            raise PlanError("UNCONFIGURED", "Thiếu thông số đã đo; không lập quỹ đạo robot: " + ", ".join(miss), {"missing": miss})
        bad = [f.name for f in fields(self) if not (math.isfinite(getattr(self, f.name)) and getattr(self, f.name) > 0)]
        if bad:
            raise PlanError("INVALID_CONFIG", "Thông số phải là số dương hữu hạn: " + ", ".join(bad), {"invalid": bad})

    @property
    def press_mm(self) -> float:
        """Spring compression that gives f_target (Hooke, F = k x)."""
        return float(self.f_target_n) / float(self.spring_k_n_per_mm)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MotionConfig":
        data = data or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: (None if data.get(k) is None else float(data[k])) for k in known})


# ------------------------------------------------------------------------------------------------ resampling (S5)
def _dedupe(points: np.ndarray) -> np.ndarray:
    keep = [0]
    for i in range(1, len(points)):
        if np.linalg.norm(points[i] - points[keep[-1]]) > 1e-9:
            keep.append(i)
    return points[keep]


def turn_angles_deg(points: np.ndarray) -> np.ndarray:
    """Direction change at each interior vertex, 0 at both ends. Works for (N, 2) and (N, 3)."""
    n = len(points)
    out = np.zeros(n)
    if n < 3:
        return out
    seg = np.diff(points, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    ok = ln > 1e-12
    unit = np.zeros_like(seg)
    unit[ok] = seg[ok] / ln[ok, None]
    cos = np.clip(np.sum(unit[:-1] * unit[1:], axis=1), -1.0, 1.0)
    out[1:-1] = np.degrees(np.arccos(cos))
    return out


def resample_stroke(points: Any, ds: float = DEFAULT_DS_MM, corner_deg: float = DEFAULT_CORNER_DEG) -> np.ndarray:
    """Evenly spaced points (spacing <= ds) along the stroke; vertices sharper than `corner_deg` are kept exactly.

    The path is the same polyline (no smoothing), so the shape is not altered; only the sampling changes."""
    p = _dedupe(np.asarray(points, dtype=np.float64))
    if len(p) < 2:
        return p
    corners = [0] + [i for i, a in enumerate(turn_angles_deg(p)) if a > corner_deg and 0 < i < len(p) - 1] + [len(p) - 1]
    out: list[np.ndarray] = []
    for a, b in zip(corners, corners[1:]):
        sub = p[a:b + 1]
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(sub, axis=0), axis=1))])
        total = float(cum[-1])
        n = max(1, int(math.ceil(total / ds)))
        t = np.linspace(0.0, total, n + 1)
        res = np.stack([np.interp(t, cum, sub[:, c]) for c in range(sub.shape[1])], axis=1)
        out.append(res if not out else res[1:])
    return np.concatenate(out)


def max_deviation_mm(original: Any, resampled: np.ndarray) -> float:
    """Largest distance from a resampled point to the original polyline (verifies that resampling kept the shape)."""
    o = np.asarray(original, dtype=np.float64)
    worst = 0.0
    for q in resampled:
        a, b = o[:-1], o[1:]
        ab = b - a
        denom = np.maximum(np.sum(ab * ab, axis=1), 1e-18)
        t = np.clip(np.sum((q - a) * ab, axis=1) / denom, 0.0, 1.0)
        d = np.linalg.norm(a + t[:, None] * ab - q, axis=1)
        worst = max(worst, float(d.min()))
    return worst


# ------------------------------------------------------------------------------------------------ speed profile (S6)
def curvature(points: np.ndarray, ds: float = DEFAULT_DS_MM, window_mm: float = 1.0) -> np.ndarray:
    """Menger curvature (1/mm) over a window of about `window_mm` of arc length on each side."""
    n = len(points)
    k = np.zeros(n)
    m = max(1, int(round(window_mm / ds)))
    for i in range(1, n - 1):
        a, c = points[max(0, i - m)], points[min(n - 1, i + m)]
        b = points[i]
        ab, bc, ac = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(c - a)
        if ab < 1e-12 or bc < 1e-12 or ac < 1e-12:
            continue
        cross = abs(float(np.cross(b - a, c - a))) if points.shape[1] == 2 else float(np.linalg.norm(np.cross(b - a, c - a)))
        k[i] = 2.0 * cross / (ab * bc * ac)
    return k


def speed_profile(points: np.ndarray, *, v_max: float, a_lat: float, a_tan: float, ds: float = DEFAULT_DS_MM,
                  corner_deg: float = DEFAULT_CORNER_DEG) -> np.ndarray:
    """mm/s at each point: min(v_max, sqrt(a_lat / kappa)), corners and both ends at 5 mm/s, then the
    forward / backward passes limit the tangential acceleration."""
    n = len(points)
    floor = min(V_FLOOR_MM_S, v_max)
    kappa = curvature(points, ds)
    v = np.full(n, float(v_max))
    pos = kappa > 1e-9
    v[pos] = np.minimum(v[pos], np.sqrt(a_lat / kappa[pos]))
    v[turn_angles_deg(points) > corner_deg] = floor
    v[0] = v[-1] = floor
    v = np.maximum(v, floor)
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    for i in range(n - 1):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2.0 * a_tan * seg[i]))
    for i in range(n - 2, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2.0 * a_tan * seg[i]))
    return v


def duration_s(points: np.ndarray, speeds: np.ndarray) -> float:
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return float(np.sum(2.0 * seg / np.maximum(speeds[:-1] + speeds[1:], 1e-9)))


# ------------------------------------------------------------------------------------------------ plan
@dataclass
class Move:
    kind: str                       # travel | plunge | write | retract
    points: np.ndarray              # (N, 3) robot base frame, mm
    speeds: np.ndarray              # (N,) mm/s at each point
    stroke_index: int | None = None


@dataclass
class PagePlan:
    moves: list[Move] = field(default_factory=list)
    n_strokes: int = 0
    write_length_mm: float = 0.0
    duration_s: float = 0.0
    press_mm: float = 0.0
    resample_dev_mm: float = 0.0

    def all_points(self) -> np.ndarray:
        return np.concatenate([m.points for m in self.moves]) if self.moves else np.zeros((0, 3))


def plan_page(page: Page, frame: PaperFrame, cfg: MotionConfig, *, ds: float = DEFAULT_DS_MM,
              start_above: np.ndarray | None = None) -> PagePlan:
    """Plan one sheet. Raises PlanError (UNCONFIGURED, SPRING_TRAVEL_EXCEEDED, ...) instead of guessing."""
    cfg.require()
    press = cfg.press_mm
    if press > cfg.max_spring_travel_mm:
        raise PlanError("SPRING_TRAVEL_EXCEEDED",
                        f"Lực mục tiêu cần nén lò xo {press:.2f} mm, vượt hành trình tối đa {cfg.max_spring_travel_mm:g} mm.",
                        {"press_mm": press, "max_spring_travel_mm": cfg.max_spring_travel_mm})
    clearance = cfg.pen_up_clearance_mm
    plan = PagePlan(press_mm=press)
    prev_up: np.ndarray | None = start_above
    for idx, stroke in enumerate(page.strokes):
        if len(stroke.points) < 2:
            continue
        xy = resample_stroke(stroke.points, ds)
        if len(xy) < 2:
            continue
        plan.resample_dev_mm = max(plan.resample_dev_mm, max_deviation_mm(np.asarray(stroke.points), xy))
        speeds = speed_profile(xy, v_max=cfg.v_max_mm_s, a_lat=cfg.a_lat_mm_s2, a_tan=cfg.a_tan_mm_s2, ds=ds)
        down = frame.to_base(xy, lift_mm=-press)                 # tip pressed into the spring
        above_start = frame.to_base(xy[:1], lift_mm=clearance)[0]
        above_end = frame.to_base(xy[-1:], lift_mm=clearance)[0]
        if prev_up is not None:
            plan.moves.append(Move("travel", np.stack([prev_up, above_start]),
                                   np.full(2, cfg.travel_speed_mm_s), idx))
        plan.moves.append(Move("plunge", np.stack([above_start, down[0]]), np.full(2, cfg.approach_speed_mm_s), idx))
        plan.moves.append(Move("write", down, speeds, idx))
        plan.moves.append(Move("retract", np.stack([down[-1], above_end]), np.full(2, cfg.approach_speed_mm_s), idx))
        prev_up = above_end
        plan.n_strokes += 1
        plan.write_length_mm += float(np.sum(np.linalg.norm(np.diff(xy, axis=0), axis=1)))
        plan.duration_s += duration_s(down, speeds)
    for m in plan.moves:
        if m.kind != "write":
            plan.duration_s += duration_s(m.points, m.speeds)
    return plan
