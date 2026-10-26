"""Pure rules for the text layout of a template (OT-3) order: size and style of parts of the text (FR-08). No DB, no I/O.

A layout is stored in `order_inputs.layout` (jsonb, no schema change) next to `text_content`:

    {"version": 1, "line_spacing": 1.2,
     "spans": [{"start": 0, "end": 12, "size_mm": 14, "italic": true, "underline": "single", "strike": false}]}

* `start`/`end` index the stored text, which is Unicode NFC (see `orders.set_text`), in code points: `[start, end)`.
* A span changes only what it names; the rest keeps the input's own `font_size_mm` and plain style.
* Bold is deliberately not offered: the robot would have to go over each line again (owner's decision, 2026-10-26).
* Styles never change the price (owner's decision): the quote is still characters x complexity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VERSION = 1
MIN_FONT_SIZE_MM = 4.0          # ASSUMPTION (owner, 2026-10-26): the finest size the pens can write cleanly; confirm on real paper
MAX_FONT_SIZE_MM = 100.0
DEFAULT_FONT_SIZE_MM = 8.0
LINE_SPACING_MIN, LINE_SPACING_MAX, LINE_SPACING_DEFAULT = 0.8, 2.5, 1.0
MAX_SPANS = 200
UNDERLINES = ("single", "double")
STYLE_FLAGS = ("italic", "strike")
_SPAN_KEYS = {"start", "end", "size_mm", "italic", "underline", "strike"}
_TOP_KEYS = {"version", "line_spacing", "spans"}


class TextLayoutError(ValueError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.message, self.details = message, details


@dataclass(frozen=True)
class CharStyle:
    size_mm: float | None = None        # None = the input's own size
    italic: bool = False
    underline: str | None = None
    strike: bool = False


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    style: CharStyle


@dataclass(frozen=True)
class TextLayout:
    spans: tuple[Span, ...] = ()
    line_spacing: float = LINE_SPACING_DEFAULT

    @property
    def is_plain(self) -> bool:
        return not self.spans and self.line_spacing == LINE_SPACING_DEFAULT

    def styles_for(self, length: int) -> list[CharStyle]:
        """The style of each of the `length` characters."""
        plain = CharStyle()
        out = [plain] * length
        for span in self.spans:
            for i in range(span.start, min(span.end, length)):
                out[i] = span.style
        return out


def _number(value: Any, what: str, lo: float, hi: float, where: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TextLayoutError(f"{what} phải là số.", where)
    if not lo <= float(value) <= hi:
        raise TextLayoutError(f"{what} phải nằm trong {lo:g}–{hi:g}.", where)
    return float(value)


def parse(raw: Any, text_length: int) -> TextLayout:
    """Check a layout against a text of `text_length` characters. Strict: unknown keys, overlaps and empty spans are refused."""
    if not isinstance(raw, dict):
        raise TextLayoutError("Bố cục phải là một đối tượng.")
    extra = set(raw) - _TOP_KEYS
    if extra:
        raise TextLayoutError("Bố cục có trường không hỗ trợ.", {"unknown": sorted(extra)})
    if raw.get("version", VERSION) != VERSION:
        raise TextLayoutError(f"Chỉ hỗ trợ bố cục phiên bản {VERSION}.", {"version": raw.get("version")})
    spacing = raw.get("line_spacing", LINE_SPACING_DEFAULT)
    spacing = _number(spacing, "line_spacing", LINE_SPACING_MIN, LINE_SPACING_MAX, {"line_spacing": spacing})
    spans_raw = raw.get("spans", [])
    if not isinstance(spans_raw, list):
        raise TextLayoutError("spans phải là một danh sách.")
    if len(spans_raw) > MAX_SPANS:
        raise TextLayoutError(f"Tối đa {MAX_SPANS} đoạn định dạng.", {"count": len(spans_raw)})

    spans: list[Span] = []
    for i, item in enumerate(spans_raw):
        where = {"index": i}
        if not isinstance(item, dict):
            raise TextLayoutError("Mỗi đoạn định dạng phải là một đối tượng.", where)
        extra = set(item) - _SPAN_KEYS
        if extra:
            raise TextLayoutError("Đoạn định dạng có trường không hỗ trợ.", {**where, "unknown": sorted(extra)})
        start, end = item.get("start"), item.get("end")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)):
            raise TextLayoutError("start và end phải là số nguyên.", where)
        if not 0 <= start < end <= text_length:
            raise TextLayoutError("Đoạn định dạng nằm ngoài nội dung (hoặc rỗng).",
                                  {**where, "start": start, "end": end, "text_length": text_length})
        size = item.get("size_mm")
        if size is not None:
            size = _number(size, "size_mm", MIN_FONT_SIZE_MM, MAX_FONT_SIZE_MM, {**where, "size_mm": size})
        underline = item.get("underline")
        if underline is not None and underline not in UNDERLINES:
            raise TextLayoutError("underline chỉ nhận single hoặc double.", {**where, "underline": underline})
        flags = {}
        for flag in STYLE_FLAGS:
            value = item.get(flag, False)
            if not isinstance(value, bool):
                raise TextLayoutError(f"{flag} phải là true/false.", {**where, flag: value})
            flags[flag] = value
        style = CharStyle(size_mm=size, italic=flags["italic"], underline=underline, strike=flags["strike"])
        if style == CharStyle():
            raise TextLayoutError("Đoạn định dạng không đổi gì (hãy bỏ nó đi).", where)
        spans.append(Span(start, end, style))

    spans.sort(key=lambda s: s.start)
    for before, after in zip(spans, spans[1:]):
        if after.start < before.end:
            raise TextLayoutError("Các đoạn định dạng không được chồng nhau.",
                                  {"first": [before.start, before.end], "second": [after.start, after.end]})
    return TextLayout(spans=tuple(spans), line_spacing=spacing)


def to_json(layout: TextLayout) -> dict[str, Any]:
    """Canonical stored form: spans in order, defaults left out."""
    spans = []
    for s in layout.spans:
        item: dict[str, Any] = {"start": s.start, "end": s.end}
        if s.style.size_mm is not None:
            item["size_mm"] = s.style.size_mm
        if s.style.italic:
            item["italic"] = True
        if s.style.underline:
            item["underline"] = s.style.underline
        if s.style.strike:
            item["strike"] = True
        spans.append(item)
    return {"version": VERSION, "line_spacing": layout.line_spacing, "spans": spans}


def capabilities() -> dict[str, Any]:
    """What the web app may offer (GET /catalog/text-styles)."""
    return {"version": VERSION, "min_font_size_mm": MIN_FONT_SIZE_MM, "max_font_size_mm": MAX_FONT_SIZE_MM,
            "default_font_size_mm": DEFAULT_FONT_SIZE_MM,
            "line_spacing": {"min": LINE_SPACING_MIN, "max": LINE_SPACING_MAX, "default": LINE_SPACING_DEFAULT},
            "max_spans": MAX_SPANS, "styles": ["italic", "underline", "strike"], "underline": list(UNDERLINES),
            "alignments": ["LEFT", "CENTER", "RIGHT", "JUSTIFY"], "offsets": "code points of the NFC text, [start, end)",
            "bold": False}
