"""Sketch generation entry points used by the Staff sketch service (FR-14, UC-25).

OT-1 (copy / restore)  -> recovery.recover_page per original image
OT-3 (template)        -> text_to_stroke.compose_text (+ the customer's canvas drawing)
OT-2 (learned style)   -> not supported: it needs the R&D style-learning model (LI-10); Staff upload a
                          hand-made trajectory instead.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.errors import AppError
import unicodedata

from app.domain import text_layout
from app.models.order import OrderType
from app.services.stroke_ai import outline_font, path_order, recovery, styled_text, text_to_stroke
from app.services.stroke_ai import regions as regions_mod
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
    regions: list = field(default_factory=list)          # U4: regions.RegionDraft per word (OT-1 only)


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
    pages, stats, regions = [], [], []
    for page_no, src in enumerate(images, start=1):
        page, st = recovery.recover_page(src.data, paper_size=paper_size, rotation_deg=src.rotation_deg,
                                         crop_box=src.crop_box)
        pages.append(page)
        stats.append(st)
        for r in st.regions:
            r.page_no = page_no
            regions.append(r)
    similarity = round(sum(s.similarity for s in stats) / len(stats), 2)
    order_summary = _order_ot1(pages, regions)                                   # U7
    metrics = compute_metrics(pages, v_max_mm_s)
    warnings = sorted({w for s in stats for w in s.warnings})
    engine = {"name": "zhang-suen-skeleton", "version": ENGINE_VERSION, "similarity_method": "ink-iou-v1",
              "pages": [{"similarity": s.similarity, "mm_per_px": s.mm_per_px, "stroke_width_mm": s.stroke_width_mm,
                         "deskew_deg": s.deskew_deg} for s in stats]}
    complexity = suggest_complexity(order_type=OrderType.OT1_COPY_RESTORE, pen_category=pen_category, metrics=metrics,
                                    chars=chars, has_canvas=False, similarity=similarity, font_size_mm=None)
    if any(r.label != "ORIGINAL" for r in regions):
        warnings.append("UNCERTAIN_REGIONS")                 # U4: Staff should review the RESTORED regions
    engine["regions"] = {"method": "word-local-ink-iou-v1", "uncertain_below": regions_mod.UNCERTAIN_BELOW}
    engine["path_order"] = order_summary
    return Generated(pages, engine, metrics, similarity, complexity, warnings, regions)


def _order_ot1(pages: list[Page], regions: list) -> dict[str, Any]:
    """U7 for OT-1: a U4 region (one word) is one cluster; its stroke range is moved with it."""
    by_page: dict[int, list] = {}
    for r in regions:
        by_page.setdefault(r.page_no, []).append(r)
    for page_no, page in enumerate(pages, start=1):
        for r in by_page.get(page_no, []):
            for s in page.strokes[r.stroke_start:r.stroke_end]:
                s.group = r.region_no
    results, summary = path_order.optimise_pages(pages)
    for page_no, res in enumerate(results, start=1):
        new_pos = {old: new for new, old in enumerate(res.order)}
        for r in by_page.get(page_no, []):
            n = r.stroke_end - r.stroke_start
            r.stroke_start = new_pos[r.stroke_start]
            r.stroke_end = r.stroke_start + n
    return summary


def generate_ot3(text: str | None, canvas: dict | None, *, font_uri: str | None, font_size_mm: float | None,
                 alignment: str | None, paper_size: str, seed: int, v_max_mm_s: float, pen_category: str | None,
                 chars: int, font_loader: Callable[[str], bytes | None] | None = None,
                 layout: dict[str, Any] | None = None) -> Generated:
    """`layout` (domain/text_layout.py) carries sizes and styles of parts of the text and the placement on the page (margins,
    vertical alignment); without it the text is plain, 15 mm margins, from the top."""
    size = float(font_size_mm) if font_size_mm else text_to_stroke.DEFAULT_FONT_SIZE_MM
    pages: list[Page] = []
    plain_pages: list[Page] | None = None        # the same text without styles: the complexity (so the price) is judged on this
    styled = None
    placement = text_layout.TextLayout()
    if text and text.strip():
        if not font_uri:
            raise AppError(422, "TEMPLATE_REQUIRED", "Đơn chưa chọn mẫu chữ.")
        if layout:
            try:
                parsed = text_layout.parse(layout, len(unicodedata.normalize("NFC", text)))
            except text_layout.TextLayoutError as exc:
                raise AppError(422, "INVALID_LAYOUT", exc.message, exc.details) from exc
            styled = None if parsed.is_plain else parsed
            placement = parsed
        outline = font_uri.startswith(outline_font.OUTLINE_PREFIX)
        if outline:
            if font_loader is None:
                raise AppError(409, "FONT_FILE_MISSING", "Không đọc được file font của mẫu chữ từ kho lưu trữ.")
            source = outline_font.load_source(font_uri[len(outline_font.OUTLINE_PREFIX):], font_loader)
            name = None
        else:
            source, name = None, text_to_stroke.font_name_from_uri(font_uri)
        where = {"margins": placement.page_margins, "vertical_align": placement.page_vertical_align}
        plain_pages = text_to_stroke.compose_text(text, font_name=name, source=source, paper_size=paper_size,
                                                  font_size_mm=size, alignment=alignment or "LEFT", seed=seed, **where)
        if styled:
            pages = styled_text.compose_styled(text, styled, font_name=name, source=source, paper_size=paper_size,
                                               font_size_mm=size, alignment=alignment or "LEFT", seed=seed, **where)
        else:
            pages = plain_pages
    canvas_strokes = text_to_stroke.canvas_to_strokes(canvas or {}, paper_size)
    if canvas_strokes:
        if not pages:
            pages = [Page(paper_size)]
        pages[0].strokes.extend(canvas_strokes)
        if plain_pages is not None and plain_pages is not pages:
            plain_pages[0].strokes.extend(canvas_strokes)
    if not pages:
        raise AppError(422, "NO_CONTENT", "Đơn chưa có nội dung chữ hoặc hình vẽ để sinh phác thảo.")
    _, order_summary = path_order.optimise_pages(pages)                         # U7: words stay whole
    metrics = compute_metrics(pages, v_max_mm_s)
    kind = ("outline-centerline-compose" if font_uri and font_uri.startswith(outline_font.OUTLINE_PREFIX)
            else "hershey-vi-compose")
    engine = {"name": kind if text else "canvas-passthrough", "version": ENGINE_VERSION,
              "font_uri": font_uri, "font_size_mm": size, "alignment": alignment or "LEFT", "seed": seed}
    if text and text.strip():
        m = placement.page_margins
        engine["margins_mm"] = {"top": m.top, "bottom": m.bottom, "left": m.left, "right": m.right}
        engine["vertical_align"] = placement.page_vertical_align
    engine["path_order"] = order_summary
    if styled:                                              # complexity (and so the price) deliberately ignores styles
        engine["layout"] = {"spans": len(styled.spans), "line_spacing": styled.line_spacing}
    if kind == "outline-centerline-compose" and text:
        engine["stroke_order"] = "reconstructed"          # a person would not write the letters in this order
    judged = compute_metrics(plain_pages, v_max_mm_s) if plain_pages is not None and plain_pages is not pages else metrics
    complexity = suggest_complexity(order_type=OrderType.OT3_TEMPLATE, pen_category=pen_category, metrics=judged,
                                    chars=chars, has_canvas=bool(canvas_strokes), similarity=None, font_size_mm=size)
    return Generated(pages, engine, metrics, None, complexity)
