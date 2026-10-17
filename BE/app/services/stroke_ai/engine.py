"""Sketch generation entry points used by the Staff sketch service (FR-14, UC-25).

OT-1 (copy / restore)  -> recovery.recover_page per original image
OT-3 (template)        -> text_to_stroke.compose_text (+ the customer's canvas drawing)
OT-2 (learned style)   -> not supported: it needs the R&D style-learning model (LI-10); Staff upload a
                          hand-made trajectory instead.
"""
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError
from app.models.order import OrderType
from app.services.stroke_ai import recovery, text_to_stroke
from app.services.stroke_ai.trajectory import Metrics, Page, compute_metrics

ENGINE_VERSION = "1"
MAX_AI_PAGES = 5                       # OT-1 images per generation run (keeps the request within NFR-01 limits)
EXPENSIVE_PENS = {"FOUNTAIN", "BRUSH"}  # SRS 3.2: fountain / brush pens are "complex" (FR-29)


@dataclass
class Generated:
    pages: list[Page]
    engine: dict[str, Any]
    metrics: Metrics
    similarity: float | None
    complexity: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImageSource:
    data: bytes
    rotation_deg: int = 0
    crop_box: dict[str, Any] | None = None


def suggest_complexity(*, order_type: OrderType, pen_category: str | None, metrics: Metrics, chars: int,
                       has_canvas: bool, similarity: float | None, font_size_mm: float | None) -> str:
    """K_cx suggestion (FR-29): the SRS defines the levels in words, these thresholds are ASSUMPTIONS
    that Staff confirm and the Manager can calibrate once real orders exist."""
    if has_canvas or (pen_category in EXPENSIVE_PENS):
        return "COMPLEX"
    lifts_per_char = metrics.pen_lift_count / max(chars, 1)
    if order_type == OrderType.OT3_TEMPLATE:
        return "MEDIUM" if (font_size_mm or 8.0) < 6.0 or lifts_per_char > 2.5 else "SIMPLE"
    if (similarity is not None and similarity < 70.0) or lifts_per_char > 4.0:
        return "COMPLEX"
    return "SIMPLE" if lifts_per_char <= 1.5 and (similarity or 0.0) >= 85.0 else "MEDIUM"


def generate_ot1(images: list[ImageSource], *, paper_size: str, v_max_mm_s: float, pen_category: str | None,
                 chars: int) -> Generated:
    if not images:
        raise AppError(422, "NO_ORIGINAL_IMAGE", "Đơn chưa có ảnh bản gốc để phục dựng.")
    if len(images) > MAX_AI_PAGES:
        raise AppError(422, "AI_TOO_MANY_PAGES",
                       f"Phục dựng tự động tối đa {MAX_AI_PAGES} ảnh mỗi lần; hãy tải phác thảo thủ công.")
    pages, stats = [], []
    for src in images:
        page, st = recovery.recover_page(src.data, paper_size=paper_size, rotation_deg=src.rotation_deg,
                                         crop_box=src.crop_box)
        pages.append(page)
        stats.append(st)
    similarity = round(sum(s.similarity for s in stats) / len(stats), 2)
    metrics = compute_metrics(pages, v_max_mm_s)
    warnings = sorted({w for s in stats for w in s.warnings})
    engine = {"name": "zhang-suen-skeleton", "version": ENGINE_VERSION, "similarity_method": "ink-iou-v1",
              "pages": [{"similarity": s.similarity, "mm_per_px": s.mm_per_px, "stroke_width_mm": s.stroke_width_mm,
                         "deskew_deg": s.deskew_deg} for s in stats]}
    complexity = suggest_complexity(order_type=OrderType.OT1_COPY_RESTORE, pen_category=pen_category, metrics=metrics,
                                    chars=chars, has_canvas=False, similarity=similarity, font_size_mm=None)
    return Generated(pages, engine, metrics, similarity, complexity, warnings)


def generate_ot3(text: str | None, canvas: dict | None, *, font_uri: str | None, font_size_mm: float | None,
                 alignment: str | None, paper_size: str, seed: int, v_max_mm_s: float, pen_category: str | None,
                 chars: int) -> Generated:
    size = float(font_size_mm) if font_size_mm else text_to_stroke.DEFAULT_FONT_SIZE_MM
    pages: list[Page] = []
    if text and text.strip():
        if not font_uri:
            raise AppError(422, "TEMPLATE_REQUIRED", "Đơn chưa chọn mẫu chữ.")
        pages = text_to_stroke.compose_text(
            text, font_name=text_to_stroke.font_name_from_uri(font_uri), paper_size=paper_size, font_size_mm=size,
            alignment=alignment or "LEFT", seed=seed)
    canvas_strokes = text_to_stroke.canvas_to_strokes(canvas or {}, paper_size)
    if canvas_strokes:
        if not pages:
            pages = [Page(paper_size)]
        pages[0].strokes.extend(canvas_strokes)
    if not pages:
        raise AppError(422, "NO_CONTENT", "Đơn chưa có nội dung chữ hoặc hình vẽ để sinh phác thảo.")
    metrics = compute_metrics(pages, v_max_mm_s)
    engine = {"name": "hershey-vi-compose" if text else "canvas-passthrough", "version": ENGINE_VERSION,
              "font_uri": font_uri, "font_size_mm": size, "alignment": alignment or "LEFT", "seed": seed}
    complexity = suggest_complexity(order_type=OrderType.OT3_TEMPLATE, pen_category=pen_category, metrics=metrics,
                                    chars=chars, has_canvas=bool(canvas_strokes), similarity=None, font_size_mm=size)
    return Generated(pages, engine, metrics, None, complexity)
