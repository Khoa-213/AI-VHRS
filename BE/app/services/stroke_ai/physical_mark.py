"""Upgrade U8: the physical watermark line the robot writes on every sheet (docs/UPGRADE_AI_ROBOT_PLAN.md 3.5, Q3 = A).

One small line, single-stroke Hershey glyphs (Vietnamese marks composed like the template orders), centred in the
bottom margin, or in the top margin when the content reaches into the bottom one:

    "Tái tạo bằng AI-VHRS - Mã XXXX-XXXX"

The code is the order's verification code (product_certificates); the printed certificate card carries a QR code to
the public verification page for the same code. Q3: mandatory for OT-1, optional (customer's choice) for OT-3.

The strokes are part of the trajectory file (kind "watermark"), so the customer sees them on the sketch they approve and
the file's SHA-256 (signed in the production snapshot) covers them. They are always regenerated when a sketch version is
saved: a manual upload or a region edit can neither remove nor fake them. `check` is run by the server when the package
is downloaded and again by the robot agent before LOAD; an OT-1 package without its watermark is refused.

ASSUMPTIONS (not tried on paper yet): 2.2 mm cap height is legible with the workshop pens; 5 mm from the sheet edge is
writable (the same assumption as text_layout.MARGIN_MIN_MM).
"""
from __future__ import annotations

import re
import secrets
from typing import Any

import numpy as np

from app.core import production_signing as ps
from app.core.errors import AppError
from app.services.stroke_ai import text_to_stroke as tts
from app.services.stroke_ai.trajectory import Page, Stroke

KIND = "watermark"
METHOD = "hershey-futural-line-v1"
FONT = "futural"
CAP_MM = 2.2            # cap height of the line (ASSUMPTION, see above)
MIN_CAP_MM = 1.6        # it is shrunk down to this to fit a narrow sheet, never further
EDGE_MM = 5.0           # nearest distance to the sheet edge (= text_layout.MARGIN_MIN_MM)
CLEAR_MM = 0.5          # free space required between the line and the content
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"          # no 0/O, 1/I/L: read aloud or typed from the sheet
TEXT = "Tái tạo bằng AI-VHRS - Mã {code}"
_CODE_RE = re.compile(r"^[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$")
_POINT_TOL_MM = 0.011   # the trajectory file rounds coordinates to 0.01 mm


def new_code() -> str:
    pick = lambda: "".join(secrets.choice(ALPHABET) for _ in range(4))          # noqa: E731
    return f"{pick()}-{pick()}"


def is_code(value: Any) -> bool:
    return isinstance(value, str) and bool(_CODE_RE.match(value))


def normalise_code(value: str) -> str:
    """What a person types from the sheet: any case, with or without the dash."""
    raw = re.sub(r"[\s\-]", "", value or "").upper()
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else raw


def line_text(code: str) -> str:
    return TEXT.format(code=code)


def required(order_type: str, opted_in: bool) -> bool:
    """Q3: mandatory for OT-1, the customer's choice for OT-3 (and for OT-2, which has no automatic sketch)."""
    return order_type == "OT1_COPY_RESTORE" or bool(opted_in)


# ---------------------------------------------------------------------------------------------------- geometry
def _line(text: str, cap_mm: float) -> tuple[list[list[tuple[float, float]]], float]:
    """Polylines of the line in mm, x from 0, baseline at y = 0 (y down), and the line width."""
    source = tts.HersheySource(FONT)
    k = cap_mm / tts.CAP_UNITS
    polys, cursor = [], 0.0
    for ch in text:
        if ch == " ":
            cursor += source.space_units
            continue
        glyph = source.char(ch)
        if glyph is None:                                        # pragma: no cover - the fixed text is all drawable
            raise ValueError(f"the watermark font cannot draw {ch!r}")
        for poly in glyph.base + glyph.marks:
            polys.append([((cursor + x) * k, (y - 9.0) * k) for x, y in poly])
        cursor += glyph.advance
    return polys, cursor * k


def _fit(text: str, page_w: float) -> tuple[list[list[tuple[float, float]]], float, float]:
    cap = CAP_MM
    while True:
        polys, width = _line(text, cap)
        if width <= page_w - 2 * EDGE_MM or cap <= MIN_CAP_MM + 1e-9:
            return polys, width, cap
        cap = round(cap - 0.1, 2)


def render(page: Page, code: str, placement: str, cap_mm: float) -> list[Stroke]:
    """The watermark strokes of one page at a known placement (deterministic: `check` regenerates and compares)."""
    polys, width = _line(line_text(code), cap_mm)
    top, bottom = _extent(polys)
    x0 = (page.width_mm - width) / 2
    dy = page.height_mm - EDGE_MM - bottom if placement == "BOTTOM" else EDGE_MM - top
    return [Stroke([(round(x0 + x, 2), round(dy + y, 2)) for x, y in poly], KIND) for poly in polys if len(poly) >= 2]


def _extent(polys: list[list[tuple[float, float]]]) -> tuple[float, float]:
    ys = [y for poly in polys for _, y in poly]
    return min(ys), max(ys)


def _blocked(page: Page, box: tuple[float, float, float, float]) -> bool:
    """Does any content stroke segment come within the box (segment bounding boxes, so on the safe side)?"""
    x0, y0, x1, y1 = box
    for s in page.strokes:
        if s.kind == KIND or len(s.points) < 2:
            continue
        p = np.asarray(s.points, dtype=float)
        a, b = p[:-1], p[1:]
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        if np.any((hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)):
            return True
    return False


def place(page: Page, code: str) -> tuple[list[Stroke], str, float]:
    """Choose BOTTOM (preferred) or TOP for this page and return (strokes, placement, cap height)."""
    polys, width, cap = _fit(line_text(code), page.width_mm)
    if width > page.width_mm - 2 * EDGE_MM:
        raise AppError(409, "WATERMARK_NO_SPACE", "Khổ giấy quá hẹp để viết dòng xác thực.")
    top, bottom = _extent(polys)
    x0 = (page.width_mm - width) / 2
    height = bottom - top
    bands = {"BOTTOM": page.height_mm - EDGE_MM - height, "TOP": EDGE_MM}
    for placement, band_top in bands.items():
        box = (x0 - CLEAR_MM, band_top - CLEAR_MM, x0 + width + CLEAR_MM, band_top + height + CLEAR_MM)
        if not _blocked(page, box):
            return render(page, code, placement, cap), placement, cap
    raise AppError(409, "WATERMARK_NO_SPACE",
                   "Nội dung chiếm cả lề trên và lề dưới nên không còn chỗ viết dòng xác thực "
                   f"(cần khoảng {height + EDGE_MM + CLEAR_MM:.0f} mm ở lề trên hoặc lề dưới). "
                   "Hãy tăng lề, thu nhỏ nội dung hoặc chọn khổ giấy lớn hơn.")


def strip(pages: list[Page]) -> int:
    """Remove every watermark stroke (an uploaded or edited trajectory never keeps its own). Returns how many."""
    removed = 0
    for page in pages:
        keep = [s for s in page.strokes if s.kind != KIND]
        removed += len(page.strokes) - len(keep)
        page.strokes = keep
    return removed


def apply(pages: list[Page], code: str) -> dict[str, Any]:
    """Strip, then append the watermark at the end of every page (the robot writes it last). Returns the summary kept
    in sketches.watermark and copied into the signed snapshot."""
    strip(pages)
    out = []
    for page_no, page in enumerate(pages, start=1):
        strokes, placement, cap = place(page, code)
        page.strokes.extend(strokes)
        out.append({"page_no": page_no, "placement": placement, "cap_mm": f"{cap:.1f}", "strokes": len(strokes)})
    return {"method": METHOD, "code": code, "text": line_text(code), "pages": out}


# ---------------------------------------------------------------------------------------------------- verification
def check(payload: dict[str, Any], pages: list[Page]) -> None:
    """Server (package download) and robot agent (before LOAD). Raises ps.SignatureError; returns None when it holds.

    A snapshot of schema 1 (issued before U8) is accepted as it is: it predates the watermark and its jobs must finish."""
    if payload.get("schema") == ps.SCHEMA_V1:
        return
    wm = payload.get("watermark")
    order_type = (payload.get("order") or {}).get("type")
    actual = [[s for s in p.strokes if s.kind == KIND] for p in pages]
    if not wm or not wm.get("required"):
        if order_type == "OT1_COPY_RESTORE":
            raise ps.SignatureError("WATERMARK_REQUIRED", "Đơn sao chép / phục dựng bắt buộc có dòng xác thực trên tờ giấy "
                                    "nhưng gói sản xuất không có.")
        if any(actual):
            raise ps.SignatureError("WATERMARK_MISMATCH", "Quỹ đạo có nét dòng xác thực mà gói sản xuất không khai báo.")
        return
    declared = wm.get("pages") or []
    if not is_code(wm.get("code")) or len(declared) != len(pages):
        raise ps.SignatureError("WATERMARK_MISMATCH", "Khối dòng xác thực trong gói sản xuất không hợp lệ.")
    for page, strokes, info in zip(pages, actual, declared):
        expected = render(page, wm["code"], info.get("placement"), float(info.get("cap_mm") or CAP_MM))
        if not strokes or len(strokes) != len(expected) or any(
                len(a.points) != len(b.points)
                or any(abs(pa[0] - pb[0]) > _POINT_TOL_MM or abs(pa[1] - pb[1]) > _POINT_TOL_MM
                       for pa, pb in zip(a.points, b.points))
                for a, b in zip(strokes, expected)):
            raise ps.SignatureError("WATERMARK_MISMATCH", f"Nét dòng xác thực ở trang {info.get('page_no')} không đúng "
                                    "mã đã khai báo trong gói sản xuất.")
