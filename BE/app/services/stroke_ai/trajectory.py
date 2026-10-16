"""Trajectory data model shared by the stroke-recovery (OT-1) and text-to-stroke (OT-3) pipelines.

A trajectory is a list of pages; a page is one sheet of paper with pen strokes in millimetres,
origin at the top-left corner, x to the right, y downwards. Pen-up moves between strokes are
implicit: the robot lifts the pen after every stroke. Motion planning (velocity profile, paper ->
robot transform, FR-37) is a later phase and consumes this format.
"""
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError

FORMAT = "vhrs-trajectory/1"
PAPER_MM = {"A6": (105.0, 148.0), "A5": (148.0, 210.0), "A4": (210.0, 297.0)}  # BR-07: up to A4
MAX_PAGES = 10
MAX_POINTS = 400_000
STROKE_KINDS = {"base", "mark", "canvas", "manual"}

# ESTIMATE constants for the writing-time figure (used by price and scheduling). The robot speed
# profile (S6) is not implemented yet, so these are assumptions to be replaced by measured values.
AVG_SPEED_FACTOR = 0.6        # average writing speed = factor x pen v_max (curvature slows the pen)
TRAVEL_SPEED_MM_S = 100.0     # pen-up travel between strokes
PEN_CYCLE_SEC = 0.5           # lift + lower per stroke


@dataclass
class Stroke:
    points: list[tuple[float, float]]
    kind: str = "base"

    def length_mm(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.points, self.points[1:]))


@dataclass
class Page:
    paper_size: str
    strokes: list[Stroke] = field(default_factory=list)
    preview_path: str | None = None

    @property
    def width_mm(self) -> float:
        return PAPER_MM[self.paper_size][0]

    @property
    def height_mm(self) -> float:
        return PAPER_MM[self.paper_size][1]


@dataclass(frozen=True)
class Metrics:
    total_stroke_mm: float
    pen_lift_count: int
    travel_mm: float
    estimated_writing_sec: int


def compute_metrics(pages: list[Page], v_max_mm_s: float) -> Metrics:
    total, travel, lifts = 0.0, 0.0, 0
    for page in pages:
        prev_end = None
        for s in page.strokes:
            if len(s.points) < 2:
                continue
            total += s.length_mm()
            lifts += 1
            if prev_end is not None:
                travel += math.dist(prev_end, s.points[0])
            prev_end = s.points[-1]
    writing = total / max(v_max_mm_s * AVG_SPEED_FACTOR, 1e-6)
    seconds = writing + travel / TRAVEL_SPEED_MM_S + lifts * PEN_CYCLE_SEC
    return Metrics(round(total, 2), lifts, round(travel, 2), int(math.ceil(seconds)))


def to_dict(pages: list[Page], engine: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": FORMAT, "unit": "mm", "origin": "top-left", "engine": engine,
        "pages": [{
            "paper": {"size": p.paper_size, "width_mm": p.width_mm, "height_mm": p.height_mm},
            "preview_path": p.preview_path,
            "strokes": [{"kind": s.kind, "points": [[round(x, 2), round(y, 2)] for x, y in s.points]}
                        for s in p.strokes if len(s.points) >= 2],
        } for p in pages],
    }


def dumps(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def content_hash(raw: bytes) -> str:
    """SHA-256 (hex, 64 chars) of the stored trajectory file (FR-38)."""
    return hashlib.sha256(raw).hexdigest()


def parse(data: Any) -> list[Page]:
    """Validate an uploaded / edited trajectory (Staff sketch editor) and return its pages."""
    def bad(msg: str) -> AppError:
        return AppError(422, "INVALID_TRAJECTORY", f"Quỹ đạo không hợp lệ: {msg}")

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise bad(f'cần "format": "{FORMAT}"')
    raw_pages = data.get("pages")
    if not isinstance(raw_pages, list) or not 1 <= len(raw_pages) <= MAX_PAGES:
        raise bad(f"cần 1..{MAX_PAGES} trang")
    pages, n_points = [], 0
    for i, rp in enumerate(raw_pages):
        size = (rp.get("paper") or {}).get("size") if isinstance(rp, dict) else None
        if size not in PAPER_MM:
            raise bad(f"trang {i + 1}: khổ giấy phải là A6, A5 hoặc A4")
        page = Page(paper_size=size)
        for j, rs in enumerate(rp.get("strokes") or []):
            kind = rs.get("kind", "manual") if isinstance(rs, dict) else None
            pts = rs.get("points") if isinstance(rs, dict) else None
            if kind not in STROKE_KINDS or not isinstance(pts, list) or len(pts) < 2:
                raise bad(f"trang {i + 1}, nét {j + 1}: cần kind hợp lệ và ≥ 2 điểm")
            try:
                parsed = [(float(p[0]), float(p[1])) for p in pts]
            except (TypeError, ValueError, IndexError) as exc:
                raise bad(f"trang {i + 1}, nét {j + 1}: điểm phải là [x, y]") from exc
            if any(not (math.isfinite(x) and math.isfinite(y)) for x, y in parsed):
                raise bad(f"trang {i + 1}, nét {j + 1}: toạ độ không hữu hạn")
            if any(not (-0.5 <= x <= page.width_mm + 0.5 and -0.5 <= y <= page.height_mm + 0.5) for x, y in parsed):
                raise bad(f"trang {i + 1}, nét {j + 1}: có điểm nằm ngoài khổ giấy {size}")
            n_points += len(parsed)
            page.strokes.append(Stroke(parsed, kind))
        if not page.strokes:
            raise bad(f"trang {i + 1}: không có nét nào")
        pages.append(page)
    if n_points > MAX_POINTS:
        raise bad(f"tối đa {MAX_POINTS} điểm")
    return pages


def render_preview(page: Page, px_per_mm: float = 2.0) -> bytes:
    """PNG preview of one page: strokes on white paper, green dot = where each stroke starts."""
    w, h = int(round(page.width_mm * px_per_mm)), int(round(page.height_mm * px_per_mm))
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (200, 200, 200), 1)
    for s in page.strokes:
        pts = np.array([[x * px_per_mm, y * px_per_mm] for x, y in s.points], np.float32)
        cv2.polylines(img, [np.round(pts).astype(np.int32)], False, (30, 30, 30), 1, cv2.LINE_AA)
    for s in page.strokes:
        x, y = s.points[0]
        cv2.circle(img, (int(round(x * px_per_mm)), int(round(y * px_per_mm))), 2, (60, 170, 60), -1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:  # pragma: no cover - imencode only fails on invalid input
        raise AppError(500, "PREVIEW_FAILED", "Không tạo được ảnh xem trước.")
    return buf.tobytes()
