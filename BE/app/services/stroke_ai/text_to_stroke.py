"""Text -> pen strokes for Template writing orders (OT-3, FR-35, pipeline S0-S5).

Real single-line (Hershey, public domain) glyphs are laid out on the paper. The Hershey fonts only
cover ASCII, so Vietnamese letters are composed the way the SRS describes (S1): NFD split into base
letter + modifier (breve, circumflex, horn) + tone mark, each mark drawn as its own pen stroke
anchored to the base glyph; the tone mark sits beside / above the circumflex or breve, the dot
below goes under the baseline, and d-bar is a crossbar on the stem.

The mark shapes below are hand-designed and have NOT been validated by the workshop on real paper.
Template.font_uri has the form "hershey:<font name>".
"""
import math
import random
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from HersheyFonts import HersheyFonts

from app.core.errors import AppError
from app.services.stroke_ai.trajectory import MAX_PAGES, PAPER_MM, Page, Stroke

Poly = list[tuple[float, float]]

FONT_PREFIX = "hershey:"
SUPPORTED_FONTS = {"futural", "futuram", "rowmans", "rowmand", "scripts", "scriptc", "cursive", "timesr"}
CAP_UNITS = 21.0          # Hershey cap height (cap line -12 .. base line 9)
HEADROOM_UNITS = 12.0     # space above the cap line for stacked marks (circumflex + tone)
LINE_PITCH_FACTOR = 1.9   # line pitch = factor x font size (font size = cap height in mm)
DEFAULT_FONT_SIZE_MM = 8.0
MARGIN_MM = 15.0

_PUNCT = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "‐": "-", " ": " "}
_TONES = {"́": "acute", "̀": "grave", "̉": "hook", "̃": "tilde", "̣": "dot"}
_MODIFIERS = {"̂": "circumflex", "̆": "breve", "̛": "horn"}


@dataclass
class CharGlyph:
    base: list[Poly]
    marks: list[Poly]
    advance: float


def font_name_from_uri(font_uri: str) -> str:
    if not font_uri.startswith(FONT_PREFIX) or font_uri[len(FONT_PREFIX):] not in SUPPORTED_FONTS:
        raise AppError(422, "UNSUPPORTED_TEMPLATE",
                       "Mẫu chữ này chưa hỗ trợ sinh phác thảo tự động (chỉ hỗ trợ font một nét).")
    return font_uri[len(FONT_PREFIX):]


@lru_cache(maxsize=16)
def _glyphs(font_name: str):
    f = HersheyFonts()
    f.load_default_font(font_name)
    return f.all_glyphs


def _normalise(text: str) -> str:
    """S0: NFC and typographic punctuation to ASCII (characters the font cannot draw are reported later)."""
    out = []
    for i, ch in enumerate(unicodedata.normalize("NFC", text)):
        ch = _PUNCT.get(ch, ch)
        if ch == "…":
            out.append("...")
        elif ch.isspace() or ch == "\n":
            out.append("\n" if ch == "\n" else " ")
        else:
            out.append(ch)
    return "".join(out)


def _bbox(polys: list[Poly]) -> tuple[float, float, float, float]:
    xs = [p[0] for s in polys for p in s]
    ys = [p[1] for s in polys for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _mark_polys(kind: str, cx: float, top: float, bottom: float, xmax: float, lift: float, off: float) -> list[Poly]:
    """Pen strokes of one diacritic, in Hershey units (y down). `top`/`bottom` are the base glyph's extremes."""
    if kind == "dot":
        y = bottom + 3.5
        return [[(cx - 0.4, y), (cx + 0.4, y + 0.3)]]
    if kind == "horn":
        return [[(xmax - 0.2, top + 3.0), (xmax + 1.8, top + 2.2), (xmax + 2.6, top + 0.4), (xmax + 2.4, top - 1.0)]]
    y0 = top - 3.5 - lift
    x = cx + off
    if kind == "acute":
        return [[(x - 1.6, y0 + 2.2), (x + 1.6, y0 - 2.2)]]
    if kind == "grave":
        return [[(x - 1.6, y0 - 2.2), (x + 1.6, y0 + 2.2)]]
    if kind == "hook":
        return [[(x - 1.8, y0 - 1.0), (x - 0.6, y0 - 2.6), (x + 1.0, y0 - 2.2), (x + 1.2, y0 - 0.6),
                 (x + 0.2, y0 + 0.6), (x + 0.2, y0 + 1.8)]]
    if kind == "tilde":
        return [[(x - 3.2, y0 + 0.6), (x - 2.0, y0 - 0.8), (x - 0.8, y0 - 1.2), (x + 0.4, y0 - 0.2),
                 (x + 1.6, y0 + 0.8), (x + 2.8, y0 + 0.8), (x + 3.2, y0 - 0.6)]]
    if kind == "circumflex":
        y0 = top - 3.0
        return [[(cx - 3.0, y0 + 1.6), (cx, y0 - 1.6), (cx + 3.0, y0 + 1.6)]]
    if kind == "breve":
        y0 = top - 3.0
        return [[(cx - 3.0, y0 - 1.2), (cx - 1.5, y0 + 0.8), (cx, y0 + 1.4), (cx + 1.5, y0 + 0.8), (cx + 3.0, y0 - 1.2)]]
    raise ValueError(kind)


def _compose_char(glyphs, ch: str) -> CharGlyph | None:
    """Return the pen strokes of one character, or None if the font cannot draw it."""
    bar = False
    if ch in "đĐ":
        base_ch, marks = ("d" if ch == "đ" else "D"), []
        bar = True
    else:
        parts = unicodedata.normalize("NFD", ch)
        base_ch, marks = parts[0], list(parts[1:])
    glyph = glyphs.get(base_ch)
    if glyph is None or any(m not in _TONES and m not in _MODIFIERS for m in marks):
        return None
    lo = glyph.left_offset
    base = [[(x - lo, y) for x, y in s] for s in glyph.strokes]
    if base_ch in "ij" and marks:                         # the tittle is replaced by the marks
        base = [s for s in base if max(p[1] for p in s) > -6.0]
    extra: list[Poly] = []
    if base:
        x0, top, x1, bottom = _bbox(base)
        cx = (x0 + x1) / 2
        if bar:
            if base_ch == "d":
                extra.append([(x1 - 5.5, top + 6.0), (x1 + 1.8, top + 6.0)])
            else:
                ym = (top + bottom) / 2
                extra.append([(x0 - 2.5, ym), (x0 + 5.0, ym)])
        modifier = next((_MODIFIERS[m] for m in marks if m in _MODIFIERS), None)
        tone = next((_TONES[m] for m in marks if m in _TONES), None)
        for m in marks:
            if m in _MODIFIERS:
                extra.extend(_mark_polys(_MODIFIERS[m], cx, top, bottom, x1, 0.0, 0.0))
        if tone:
            stacked = modifier in ("circumflex", "breve")
            lift = (4.5 if tone == "tilde" else 4.0) if stacked else 0.0
            off = 2.6 if modifier == "circumflex" and tone in ("acute", "grave", "hook") else 0.0
            extra.extend(_mark_polys(tone, cx, top, bottom, x1, lift, off))
    return CharGlyph(base=base + ([extra.pop(0)] if bar else []), marks=extra, advance=float(glyph.char_width))


@dataclass
class _Word:
    chars: list[CharGlyph]

    def width(self) -> float:
        return sum(c.advance for c in self.chars)


def _tokenise(text: str, glyphs) -> list[list[_Word | None]]:
    """Paragraphs -> words. Raises 422 listing the characters the font cannot draw."""
    paragraphs, bad = [], []
    pos = 0
    for line in text.split("\n"):
        words: list[_Word | None] = []
        for token in line.split(" "):
            if not token:
                continue
            chars = []
            for ch in token:
                g = _compose_char(glyphs, ch)
                if g is None:
                    bad.append({"index": pos, "char": ch})
                else:
                    chars.append(g)
                pos += 1
            pos += 1
            words.append(_Word(chars))
        paragraphs.append(words)
        pos += 1
    if bad:
        raise AppError(422, "UNSUPPORTED_CHARS", "Nội dung có ký tự mà mẫu chữ không vẽ được.", bad[:50])
    return paragraphs


def _break_long(word: _Word, max_width: float) -> list[_Word]:
    parts, cur, w = [], [], 0.0
    for c in word.chars:
        if cur and w + c.advance > max_width:
            parts.append(_Word(cur))
            cur, w = [], 0.0
        cur.append(c)
        w += c.advance
    if cur:
        parts.append(_Word(cur))
    return parts


def compose_text(text: str, *, font_name: str, paper_size: str, font_size_mm: float = DEFAULT_FONT_SIZE_MM,
                 alignment: str = "LEFT", seed: int = 0, variation: float = 0.015,
                 margin_mm: float = MARGIN_MM) -> list[Page]:
    """S0-S4: lay the text out on one or more pages of `paper_size` and return the pen strokes."""
    text = _normalise(text)
    glyphs = _glyphs(font_name)
    scale = font_size_mm / CAP_UNITS
    width_mm, height_mm = PAPER_MM[paper_size]
    avail_units = (width_mm - 2 * margin_mm) / scale
    pitch_mm = LINE_PITCH_FACTOR * font_size_mm
    lines_per_page = int((height_mm - 2 * margin_mm) // pitch_mm)
    if avail_units < 30 or lines_per_page < 1:
        raise AppError(422, "FONT_TOO_LARGE", "Cỡ chữ quá lớn so với khổ giấy.")
    space = float(glyphs[" "].char_width) * 0.7

    # S3 layout: greedy word wrap into lines of (words, is_last_of_paragraph)
    lines: list[tuple[list[_Word], bool]] = []
    for words in _tokenise(text, glyphs):
        expanded: list[_Word] = []
        for w in words:
            expanded.extend(_break_long(w, avail_units) if w.width() > avail_units else [w])
        cur: list[_Word] = []
        cur_w = 0.0
        for w in expanded:
            add = w.width() + (space if cur else 0.0)
            if cur and cur_w + add > avail_units:
                lines.append((cur, False))
                cur, cur_w = [], 0.0
                add = w.width()
            cur.append(w)
            cur_w += add
        lines.append((cur, True))   # an empty paragraph keeps its blank line

    n_pages = max(1, math.ceil(len(lines) / lines_per_page))
    if n_pages > MAX_PAGES:
        raise AppError(422, "TEXT_TOO_LONG", f"Nội dung cần {n_pages} trang, tối đa {MAX_PAGES} trang.")
    rng = random.Random(seed)
    pages = [Page(paper_size) for _ in range(n_pages)]
    for idx, (words, last) in enumerate(lines):
        page, row = pages[idx // lines_per_page], idx % lines_per_page
        if not words:
            continue
        natural = sum(w.width() for w in words) + space * (len(words) - 1)
        gap = space
        if alignment == "JUSTIFY" and not last and len(words) > 1:
            gap = space + (avail_units - natural) / (len(words) - 1)
            natural = avail_units
        start = {"LEFT": 0.0, "JUSTIFY": 0.0, "CENTER": (avail_units - natural) / 2,
                 "RIGHT": avail_units - natural}.get(alignment, 0.0)
        line_top = margin_mm + row * pitch_mm
        cursor = start
        for w in words:
            bases: list[Poly] = []
            marks: list[Poly] = []
            for c in w.chars:
                s = 1.0 + rng.uniform(-variation, variation)          # S2 natural variation (seeded)
                dy = rng.uniform(-variation, variation) * 6.0
                cx = c.advance / 2
                for target, polys in ((bases, c.base), (marks, c.marks)):
                    for poly in polys:
                        target.append([(cursor + cx + (x - cx) * s, y * s + dy + 9.0 * (1 - s)) for x, y in poly])
                cursor += c.advance
            cursor += gap
            # S4: the word's letters first, its tone marks / modifiers after the word
            for kind, polys in (("base", bases), ("mark", marks)):
                for poly in polys:
                    pts = [(margin_mm + ux * scale, line_top + (uy + CAP_UNITS - 9.0 + HEADROOM_UNITS) * scale)
                           for ux, uy in poly]
                    page.strokes.append(Stroke(pts, kind))
    return [p for p in pages if p.strokes] or pages[:1]


def canvas_to_strokes(canvas: dict, paper_size: str) -> list[Stroke]:
    """Decorative drawing (Pointer Events) -> pen strokes, validated to lie on the paper (FR-08)."""
    width_mm, height_mm = PAPER_MM[paper_size]
    out: list[Stroke] = []
    for stroke in (canvas or {}).get("strokes", []):
        pts: list[tuple[float, float]] = []
        for p in stroke.get("points", []):
            try:
                x, y = float(p["x"]), float(p["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (-0.5 <= x <= width_mm + 0.5 and -0.5 <= y <= height_mm + 0.5):
                raise AppError(422, "CANVAS_OUT_OF_PAPER", f"Hình vẽ vượt ra ngoài khổ giấy {paper_size}.")
            if not pts or math.dist(pts[-1], (x, y)) >= 0.1:
                pts.append((x, y))
        if len(pts) >= 2:
            out.append(Stroke(pts, "canvas"))
    return out
