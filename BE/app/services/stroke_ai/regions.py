"""Upgrade U4: restoration regions (docs/UPGRADE_AI_ROBOT_PLAN.md, III-B).

A region is one word of a recovered page (OT-1): a box in millimetres plus the contiguous run of strokes
[stroke_start, stroke_end) that the recovery wrote for it (recovery.py writes strokes word by word, base strokes then the
word's marks, so a word's strokes are always contiguous).

Every region carries where its strokes come from:
  ORIGINAL  traced from ink that is clearly visible in the customer's image (local fit good);
  RESTORED  traced from ink that is faint, broken or poorly matched (local fit low) or redrawn by Staff from the image;
            the customer is shown these as "uncertain";
  INFERRED  not in the image at all: Staff wrote it from a guess / from text (only allowed in ASSISTED mode).

`confidence` = min(fit, contrast), 0..1: `fit` is the local pixel IoU between the ink and the recovered strokes inside the
region box (how faithfully the strokes trace the ink), `contrast` is the region's ink darkness relative to the page median
(faded / washed-out ink scores low). It is NOT a recognition score (there is no handwriting recognition yet), it cannot
see ink that is missing entirely (a torn-off corner has no strokes and so no region), and the 0.6 threshold is an
assumption to be calibrated on the real Vietnamese test set (U3).

Editing a region (SketchService.edit_region) replaces only that run of strokes; every other stroke of the page is copied
as is, so its bytes in the trajectory file do not change.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError
from app.services.stroke_ai import text_to_stroke
from app.services.stroke_ai.trajectory import PAPER_MM, Page, Stroke

LABELS = ("ORIGINAL", "RESTORED", "INFERRED")
UNCERTAIN_BELOW = 0.6           # ASSUMPTION (not benchmarked): local IoU under this -> RESTORED / uncertain
MAX_REGION_TEXT = 200
MAX_REGION_STROKES = 400
DEFAULT_TEXT_FONT = "cursive"


@dataclass
class RegionDraft:
    page_no: int                                   # 1-based
    region_no: int                                 # 1-based within the page, stable across edits
    stroke_start: int
    stroke_end: int                                # exclusive
    bbox: tuple[float, float, float, float]        # x0, y0, x1, y1 in mm, top-left origin
    label: str
    confidence: float | None
    text: str | None = None
    source: str = "AUTO"                           # AUTO (recovery) | STAFF
    note: str | None = None
    edited_by: int | None = None
    metrics: dict | None = None                    # AUTO only: {"fit": local IoU, "contrast": ink darkness vs page}


def label_for(confidence: float) -> str:
    return "ORIGINAL" if confidence >= UNCERTAIN_BELOW else "RESTORED"


def bbox_of(strokes: list[Stroke]) -> tuple[float, float, float, float]:
    xs = [x for s in strokes for x, _ in s.points]
    ys = [y for s in strokes for _, y in s.points]
    return (round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2))


def strokes_from_points(raw: list[list[list[float]]], page: Page) -> list[Stroke]:
    """Staff-drawn replacement strokes (mm). Same bounds rules as the trajectory parser."""
    if not raw or len(raw) > MAX_REGION_STROKES:
        raise AppError(422, "INVALID_REGION_STROKES", f"Cần 1..{MAX_REGION_STROKES} nét cho vùng.")
    out = []
    for j, pts in enumerate(raw):
        if not isinstance(pts, list) or len(pts) < 2:
            raise AppError(422, "INVALID_REGION_STROKES", f"Nét {j + 1}: cần ít nhất 2 điểm [x, y].")
        try:
            parsed = [(round(float(p[0]), 2), round(float(p[1]), 2)) for p in pts]
        except (TypeError, ValueError, IndexError) as exc:
            raise AppError(422, "INVALID_REGION_STROKES", f"Nét {j + 1}: điểm phải là [x, y].") from exc
        if any(not (0 <= x <= page.width_mm and 0 <= y <= page.height_mm) for x, y in parsed):
            raise AppError(422, "INVALID_REGION_STROKES", f"Nét {j + 1}: có điểm nằm ngoài khổ giấy {page.paper_size}.")
        out.append(Stroke(parsed, "manual"))
    return out


def text_in_box(text: str, box: tuple[float, float, float, float], paper_size: str,
                font: str | None = None) -> list[Stroke]:
    """Write `text` with a single-line font, scaled to fit inside `box` (left-aligned, centred vertically)."""
    text = (text or "").strip()
    if not text or len(text) > MAX_REGION_TEXT:
        raise AppError(422, "INVALID_REGION_TEXT", f"Văn bản cho vùng cần 1..{MAX_REGION_TEXT} ký tự.")
    font = font or DEFAULT_TEXT_FONT
    if font not in text_to_stroke.SUPPORTED_FONTS:
        raise AppError(422, "INVALID_REGION_TEXT", "Font không được hỗ trợ.")
    pages = text_to_stroke.compose_text(text, font_name=font, paper_size="A4", font_size_mm=8.0, seed=0, variation=0.0)
    src = [s for p in pages[:1] for s in p.strokes]
    if len(pages) > 1 or not src:
        raise AppError(422, "INVALID_REGION_TEXT", "Văn bản quá dài cho một vùng.")
    sx0, sy0, sx1, sy1 = bbox_of(src)
    bx0, by0, bx1, by1 = box
    bw, bh = max(bx1 - bx0, 1.0), max(by1 - by0, 1.0)
    k = min(bw / max(sx1 - sx0, 1e-6), bh / max(sy1 - sy0, 1e-6))
    oy = by0 + (bh - (sy1 - sy0) * k) / 2
    pw, ph = PAPER_MM[paper_size]
    out = []
    for s in src:
        pts = [(round(min(max(bx0 + (x - sx0) * k, 0.0), pw), 2), round(min(max(oy + (y - sy0) * k, 0.0), ph), 2))
               for x, y in s.points]
        out.append(Stroke(pts, s.kind))
    return out
