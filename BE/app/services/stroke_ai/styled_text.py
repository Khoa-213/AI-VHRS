"""Text -> pen strokes with sizes and styles that differ along the text (FR-08; extends the S3/S4 layout of text_to_stroke).

The same glyph sources and the same composed Vietnamese letters as `text_to_stroke.compose_text` are used; what changes is that
every character has its own size and style (domain/text_layout.py):

* size: a character is scaled by its own size; the letters of one line share a baseline and the line is as tall as its largest
  letter (times `line_spacing`);
* italic: the glyph is sheared about the baseline (stroke fonts have no italic face, so the slant is geometric);
* underline / double underline / strike: one extra straight pen stroke per line and run, drawn after the line's letters.

With a plain layout the result is identical to `compose_text` (same wrapping, same seeded variation), which a test checks.
The size, offsets and slant below are design assumptions, not validated on real paper.
"""
from __future__ import annotations

import math
import random
import unicodedata
from dataclasses import dataclass

from app.core.errors import AppError
from app.domain.text_layout import CharStyle, TextLayout
from app.services.stroke_ai import text_to_stroke as tts
from app.services.stroke_ai.trajectory import MAX_PAGES, PAPER_MM, Page, Stroke

SLANT = math.tan(math.radians(12.0))      # italic: x += (baseline - y) * SLANT
BASELINE_U = 9.0                          # Hershey baseline
UNDERLINE_U = 8.0                         # underline: below the descenders (descenders reach ~7 units under the baseline)
UNDERLINE_GAP_U = 2.6                     # second line of a double underline
STRIKE_U = 3.0                            # strike: through the lower-case body (cap line is at -12, baseline at +9)
EPS = 1e-6


@dataclass
class _Item:
    glyph: tts.CharGlyph
    style: CharStyle
    k: float                  # mm per Hershey unit for this character
    index: int

    @property
    def advance_mm(self) -> float:
        return self.glyph.advance * self.k


@dataclass
class _Word:
    items: list[_Item]
    gap_style: CharStyle      # style of the space before the word (underline carries across it)
    gap_k: float

    def width(self) -> float:
        return sum(i.advance_mm for i in self.items)


@dataclass
class _Line:
    words: list[_Word]
    last: bool
    size: float               # tallest character, mm
    height: float = 0.0


@dataclass
class _Run:
    start: float
    end: float
    k: float


def _cells(text: str, styles: list[CharStyle]) -> list[tuple[str, CharStyle]]:
    """S0 with the style carried along: typographic punctuation to ASCII, '...' for an ellipsis, spaces and newlines."""
    out: list[tuple[str, CharStyle]] = []
    for ch, style in zip(unicodedata.normalize("NFC", text), styles):
        ch = tts._PUNCT.get(ch, ch)
        if ch == "…":
            out.extend([(".", style)] * 3)
        elif ch == "\n" or ch.isspace():
            out.append(("\n" if ch == "\n" else " ", style))
        else:
            out.append((ch, style))
    return out


def compose_styled(text: str, layout: TextLayout, *, font_name: str | None = None, source=None, paper_size: str,
                   font_size_mm: float = tts.DEFAULT_FONT_SIZE_MM, alignment: str = "LEFT", seed: int = 0,
                   variation: float = 0.015, margin_mm: float = tts.MARGIN_MM) -> list[Page]:
    source = source or tts.HersheySource(font_name)
    styles = layout.styles_for(len(unicodedata.normalize("NFC", text)))
    cells = _cells(text, styles)
    base_k = font_size_mm / tts.CAP_UNITS
    width_mm, height_mm = PAPER_MM[paper_size]
    avail = width_mm - 2 * margin_mm
    page_avail = height_mm - 2 * margin_mm

    def k_of(style: CharStyle) -> float:
        return (style.size_mm if style.size_mm is not None else font_size_mm) / tts.CAP_UNITS

    # ---- tokenise: paragraphs of words, each character with its own glyph, size and style
    paragraphs: list[list[_Word]] = []
    bad: list[dict] = []
    words: list[_Word] = []
    token: list[_Item] = []
    gap_style, gap_k = CharStyle(), base_k

    def flush() -> None:
        nonlocal token
        if token:
            words.append(_Word(token, gap_style, gap_k))
            token = []

    for index, (ch, style) in enumerate(cells):
        if ch == "\n":
            flush()
            paragraphs.append(words)
            words = []
            gap_style, gap_k = CharStyle(), base_k
        elif ch == " ":
            flush()
            gap_style, gap_k = style, k_of(style)
        else:
            glyph = source.char(ch)
            if glyph is None:
                bad.append({"index": index, "char": ch})
            else:
                token.append(_Item(glyph, style, k_of(style), index))
    flush()
    paragraphs.append(words)
    if bad:
        raise AppError(422, "UNSUPPORTED_CHARS", "Nội dung có ký tự mà mẫu chữ không vẽ được.", bad[:50])

    sizes = [i.k * tts.CAP_UNITS for p in paragraphs for w in p for i in w.items] or [font_size_mm]
    biggest = max(sizes + [font_size_mm])
    space_u = source.space_units
    if avail < 30 * biggest / tts.CAP_UNITS:
        raise AppError(422, "FONT_TOO_LARGE", "Cỡ chữ quá lớn so với khổ giấy.")

    # ---- S3: greedy wrap in millimetres
    def split_long(word: _Word) -> list[_Word]:
        parts, cur, w = [], [], 0.0
        for item in word.items:
            if cur and w + item.advance_mm > avail:
                parts.append(_Word(cur, word.gap_style, word.gap_k))
                cur, w = [], 0.0
            cur.append(item)
            w += item.advance_mm
        if cur:
            parts.append(_Word(cur, word.gap_style, word.gap_k))
        return parts

    lines: list[_Line] = []

    def make_line(ws: list[_Word], last: bool) -> _Line:
        size = max([i.k * tts.CAP_UNITS for w in ws for i in w.items] or [font_size_mm])
        return _Line(ws, last, size, tts.LINE_PITCH_FACTOR * size * layout.line_spacing)

    for p_words in paragraphs:
        expanded: list[_Word] = []
        for w in p_words:
            expanded.extend(split_long(w) if w.width() > avail else [w])
        cur: list[_Word] = []
        cur_w = 0.0
        for w in expanded:
            gap = space_u * w.gap_k if cur else 0.0
            if cur and cur_w + gap + w.width() > avail:
                lines.append(make_line(cur, False))
                cur, cur_w, gap = [], 0.0, 0.0
            cur.append(w)
            cur_w += gap + w.width()
        lines.append(make_line(cur, True))             # an empty paragraph keeps its blank line

    # ---- pages: lines of different heights fill a page until the next does not fit
    page_of: list[tuple[int, float]] = []
    page_no, used = 0, 0.0
    for line in lines:
        if line.height > page_avail + EPS:
            raise AppError(422, "FONT_TOO_LARGE", "Cỡ chữ quá lớn so với khổ giấy.")
        if used + line.height > page_avail + EPS:
            page_no, used = page_no + 1, 0.0
        page_of.append((page_no, used))
        used += line.height
    n_pages = page_no + 1
    if n_pages > MAX_PAGES:
        raise AppError(422, "TEXT_TOO_LONG", f"Nội dung cần {n_pages} trang, tối đa {MAX_PAGES} trang.")

    # ---- S2/S4: draw
    rng = random.Random(seed)
    pages = [Page(paper_size) for _ in range(n_pages)]
    for line, (pn, top) in zip(lines, page_of):
        if not line.words:
            continue
        page = pages[pn]
        line_k = line.size / tts.CAP_UNITS
        baseline = margin_mm + top + (tts.CAP_UNITS + tts.HEADROOM_UNITS) * line_k
        gaps = [space_u * w.gap_k for w in line.words[1:]]
        natural = sum(w.width() for w in line.words) + sum(gaps)
        extra_gap = 0.0
        if alignment == "JUSTIFY" and not line.last and len(line.words) > 1:
            extra_gap = (avail - natural) / (len(line.words) - 1)
            natural = avail
        start = {"LEFT": 0.0, "JUSTIFY": 0.0, "CENTER": (avail - natural) / 2, "RIGHT": avail - natural}.get(alignment, 0.0)

        cursor = start
        under: dict[str, list[_Run]] = {"single": [], "double": []}
        struck: list[_Run] = []

        def extend(runs: list[_Run], x0: float, x1: float, k: float, joined: bool) -> None:
            if joined and runs and abs(runs[-1].end - x0) < EPS:
                runs[-1].end, runs[-1].k = x1, max(runs[-1].k, k)
            else:
                runs.append(_Run(x0, x1, k))

        for wi, word in enumerate(line.words):
            if wi:                                   # the space before the word carries its own style (underline continues)
                gap = space_u * word.gap_k + extra_gap
                if word.gap_style.underline:
                    extend(under[word.gap_style.underline], cursor, cursor + gap, word.gap_k, True)
                if word.gap_style.strike:
                    extend(struck, cursor, cursor + gap, word.gap_k, True)
                cursor += gap
            bases, marks = [], []
            for item in word.items:
                s = 1.0 + rng.uniform(-variation, variation)
                dy = rng.uniform(-variation, variation) * 6.0
                cx = item.glyph.advance / 2
                x0 = cursor
                for target, polys in ((bases, item.glyph.base), (marks, item.glyph.marks)):
                    for poly in polys:
                        pts = []
                        for ux, uy in poly:
                            if item.style.italic:
                                ux += (BASELINE_U - uy) * SLANT
                            pts.append((margin_mm + x0 + (cx + (ux - cx) * s) * item.k,
                                        baseline + (s * (uy - BASELINE_U) + dy) * item.k))
                        target.append(pts)
                cursor += item.advance_mm
                if item.style.underline:
                    extend(under[item.style.underline], x0, cursor, item.k, True)
                if item.style.strike:
                    extend(struck, x0, cursor, item.k, True)
            for kind, polys in (("base", bases), ("mark", marks)):
                for pts in polys:
                    page.strokes.append(Stroke(pts, kind))

        # decorations last: the letters of the line are written first
        for kind, runs in under.items():
            for run in runs:
                y = baseline + UNDERLINE_U * run.k
                page.strokes.append(Stroke([(margin_mm + run.start, y), (margin_mm + run.end, y)], "base"))
                if kind == "double":
                    y2 = baseline + (UNDERLINE_U + UNDERLINE_GAP_U) * run.k
                    page.strokes.append(Stroke([(margin_mm + run.start, y2), (margin_mm + run.end, y2)], "base"))
        for run in struck:
            y = baseline + (STRIKE_U - BASELINE_U) * run.k
            page.strokes.append(Stroke([(margin_mm + run.start, y), (margin_mm + run.end, y)], "base"))
    return [p for p in pages if p.strokes] or pages[:1]
