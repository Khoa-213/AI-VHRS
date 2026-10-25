"""Paper frame -> robot base frame (SRS S7). Pure numpy, no I/O, no robot.

The paper frame is the trajectory frame: millimetres, origin at the top-left corner, x to the right, y downwards.
The technician probes the sheet with the pen tip and the robot reports the TCP positions in the robot BASE frame:

  P0  the paper origin (top-left corner)
  P1  a point on the paper's +x axis (e.g. the top-right corner)
  P2  a point on the paper's +y axis (e.g. the bottom-left corner)
  P3.. optional extra touch points anywhere on the sheet (a grid); they only refine the height map.

p_base = origin + x * x_hat + y * y_hat + (h(x, y) + lift) * normal, where `normal` points away from the paper towards
the tool side and h is the paper's height above the plane through P0, P1, P2 as measured by the extra points
(a least-squares plane over all probes, so a sheet that is not parallel to the robot plane is handled).

Nothing here guesses a physical value. A frame is built only from probe points; the sanity thresholds in FrameChecks
are software acceptance limits for the probe data, not properties of the robot or the paper.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


class FrameError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


@dataclass(frozen=True)
class FrameChecks:
    """Acceptance limits for the probe data (software limits, adjustable per workshop)."""
    min_baseline_mm: float = 20.0       # P0-P1 and P0-P2 must be at least this far apart
    max_axes_skew_deg: float = 3.0      # P1-P0 and P2-P0 must be perpendicular within this (a sheet is rectangular)
    min_normal_z: float = 0.5           # |normal . robot +Z|: the sheet may not be steeper than ~60 deg from horizontal
    max_plane_residual_mm: float = 1.0  # extra probes further than this from the fitted plane mean a bad probe


@dataclass(frozen=True)
class PaperFrame:
    origin: np.ndarray                   # robot-frame position of paper (0, 0) on the plane through P0
    x_axis: np.ndarray
    y_axis: np.ndarray
    normal: np.ndarray                   # unit, towards the tool side (positive robot Z component)
    height_coeffs: tuple[float, float, float]   # h(x, y) = a*x + b*y + c, mm along `normal` (zero for 3 probes)
    n_probes: int
    plane_rms_mm: float                  # RMS distance of all probes to the fitted plane (0.0 with 3 probes)
    plane_max_mm: float

    def height(self, x_mm: float | np.ndarray, y_mm: float | np.ndarray) -> float | np.ndarray:
        a, b, c = self.height_coeffs
        return a * np.asarray(x_mm) + b * np.asarray(y_mm) + c

    def to_base(self, xy_mm: np.ndarray, lift_mm: float | np.ndarray = 0.0) -> np.ndarray:
        """Map paper points (N, 2) to robot base-frame points (N, 3); `lift_mm` is along the normal (+ = off the paper)."""
        xy = np.atleast_2d(np.asarray(xy_mm, dtype=np.float64))
        h = self.height(xy[:, 0], xy[:, 1]) + lift_mm
        return (self.origin + np.outer(xy[:, 0], self.x_axis) + np.outer(xy[:, 1], self.y_axis)
                + np.outer(h, self.normal))

    def to_dict(self) -> dict[str, Any]:
        return {"origin": self.origin.tolist(), "x_axis": self.x_axis.tolist(), "y_axis": self.y_axis.tolist(),
                "normal": self.normal.tolist(), "height_coeffs": list(self.height_coeffs), "n_probes": self.n_probes,
                "plane_rms_mm": self.plane_rms_mm, "plane_max_mm": self.plane_max_mm}


def _vec(p: Any, i: int) -> np.ndarray:
    try:
        v = np.array([float(p["x"]), float(p["y"]), float(p["z"])], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise FrameError("INVALID_PROBE_POINTS", f"Điểm dò {i}: cần x, y, z là số.") from exc
    if not np.all(np.isfinite(v)):
        raise FrameError("INVALID_PROBE_POINTS", f"Điểm dò {i}: toạ độ không hữu hạn.")
    return v


def build_frame(probe_points: Sequence[Any], checks: FrameChecks = FrameChecks()) -> PaperFrame:
    """Build the paper frame from probe points given as [{"x","y","z"}] in the robot base frame, in mm."""
    if len(probe_points) < 3:
        raise FrameError("INVALID_PROBE_POINTS", "Cần ít nhất 3 điểm dò (P0, P1, P2).")
    pts = [_vec(p, i) for i, p in enumerate(probe_points)]
    p0, p1, p2 = pts[:3]
    v1, v2 = p1 - p0, p2 - p0
    l1, l2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
    if l1 < checks.min_baseline_mm or l2 < checks.min_baseline_mm:
        raise FrameError("PROBE_BASELINE_TOO_SHORT",
                         f"P0-P1 và P0-P2 phải dài ít nhất {checks.min_baseline_mm:g} mm.", {"p0p1_mm": l1, "p0p2_mm": l2})
    x_hat = v1 / l1
    y_raw = v2 - float(np.dot(v2, x_hat)) * x_hat           # Gram-Schmidt
    ly = float(np.linalg.norm(y_raw))
    if ly < 1e-9:
        raise FrameError("INVALID_PROBE_POINTS", "P0, P1, P2 thẳng hàng: không xác định được mặt giấy.")
    y_hat = y_raw / ly
    cos_axes = float(np.dot(v1, v2)) / (l1 * l2)
    skew = abs(90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_axes)))))
    if skew > checks.max_axes_skew_deg:
        raise FrameError("PROBE_AXES_NOT_PERPENDICULAR",
                         f"P0-P1 và P0-P2 lệch vuông góc {skew:.2f} độ (tối đa {checks.max_axes_skew_deg:g}).",
                         {"skew_deg": skew})
    normal = np.cross(x_hat, y_hat)
    if normal[2] < 0:
        normal = -normal                                      # the tool side is the side that looks up
    if abs(float(normal[2])) < checks.min_normal_z:
        raise FrameError("PAPER_PLANE_TOO_STEEP", "Mặt giấy dốc quá giới hạn so với mặt phẳng nằm ngang của robot.",
                         {"normal_z": float(normal[2])})

    # height of each probe above the plane P0/x_hat/y_hat, as a function of its paper coordinates
    rel = np.array([p - p0 for p in pts])
    u, w, h = rel @ x_hat, rel @ y_hat, rel @ normal
    if len(pts) > 3:
        a_mat = np.stack([u, w, np.ones_like(u)], axis=1)
        (a, b, c), *_ = np.linalg.lstsq(a_mat, h, rcond=None)
        resid = h - a_mat @ np.array([a, b, c])
        rms, mx = float(np.sqrt(np.mean(resid ** 2))), float(np.max(np.abs(resid)))
        if mx > checks.max_plane_residual_mm:
            raise FrameError("PROBE_NOT_ON_PLANE",
                             f"Có điểm dò cách mặt phẳng khớp {mx:.2f} mm (tối đa {checks.max_plane_residual_mm:g}).",
                             {"max_residual_mm": mx})
        coeffs = (float(a), float(b), float(c))
    else:
        coeffs, rms, mx = (0.0, 0.0, 0.0), 0.0, 0.0
    return PaperFrame(origin=p0, x_axis=x_hat, y_axis=y_hat, normal=normal, height_coeffs=coeffs,
                      n_probes=len(pts), plane_rms_mm=rms, plane_max_mm=mx)
