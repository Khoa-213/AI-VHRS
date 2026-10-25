"""Outline (TrueType / OpenType) fonts -> single pen strokes, for OT-3 template orders.

A computer font describes the OUTLINE of each letter, a pen writes a LINE. This module draws every glyph at a large size,
thins it to its centre line with the same skeleton pipeline used for photographed handwriting (recovery.py) and returns the
centre lines as pen strokes. What that means for the result:

  * the shape follows the font's design, but each letter becomes a thin line: every stroke of the typeface is traced
    once, so a bold font and a light font give the same line;
  * the stroke ORDER and DIRECTION are reconstructed (left-to-right / top-to-bottom, tone marks last), they are NOT the
    way a person writes the letter, and the engine says so in its report;
  * letters that are only drawn as one blob (very heavy fonts) or with decorative flourishes do not thin well: use light,
    monoline handwriting fonts. Every font has to be inspected on a preview before it is offered to customers.

Only fonts with a licence that allows this (SIL OFL, Apache, public domain...) may be added; the licence file is stored
next to the font file and the registry in `app/assets/fonts/REGISTRY.md` records it.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import unicodedata
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

from app.core.errors import AppError
from app.services.stroke_ai import recovery as rc
from app.services.stroke_ai.text_to_stroke import CAP_UNITS, CharGlyph, Poly

OUTLINE_PREFIX = "outline:"
RENDER_PX = 240              # glyph raster size: large enough that the centre line is a fraction of a pixel accurate
BASE_UNITS = 9.0             # Hershey convention used by the layout code: baseline sits at +9, cap line at -12
VI_LOWER = "aăâbcdđeêghiklmnoôơpqrstuưvxy"
VI_TONES = ["", "́", "̀", "̉", "̃", "̣"]
_VOWELS = set("aăâeêioôơuưy")


def vietnamese_charset() -> str:
    """Every letter the SRS asks for (S0): lower and upper case with all tone marks, plus digits and basic punctuation."""
    out = set()
    for ch in VI_LOWER:
        for tone in (VI_TONES if ch in _VOWELS else [""]):
            out.add(unicodedata.normalize("NFC", ch + tone))
    out |= {c.upper() for c in set(out)}
    return "".join(sorted(out)) + "0123456789.,;:!?-'\"()"


def _cmap(data: bytes) -> dict[int, str]:
    try:
        return TTFont(io.BytesIO(data)).getBestCmap() or {}
    except Exception as exc:                                   # fontTools raises several unrelated types for bad files
        raise AppError(422, "FONT_UNREADABLE", "Không đọc được file font.") from exc


def missing_glyphs(data: bytes) -> list[str]:
    """Vietnamese characters the font file has no glyph for (empty list = full coverage)."""
    return [c for c in vietnamese_charset() if ord(c) not in _cmap(data)]


class OutlineSource:
    """Glyph source with the same interface the layout code uses for Hershey fonts."""

    def __init__(self, data: bytes, px: int = RENDER_PX):
        self.px, self.digest = px, hashlib.sha256(data).hexdigest()
        try:
            self.font = ImageFont.truetype(io.BytesIO(data), px)
        except OSError as exc:
            raise AppError(422, "FONT_UNREADABLE", "Không đọc được file font.") from exc
        self._cmap = _cmap(data)
        self.baseline = int(px * 1.3)
        cap = -self.font.getbbox("H", anchor="ls")[1]
        xh = -self.font.getbbox("x", anchor="ls")[1]
        if cap <= 0 or xh <= 0:
            raise AppError(422, "FONT_UNREADABLE", "Font không có chữ H/x để đo cỡ chữ.")
        self.k = CAP_UNITS / cap                      # raster pixel -> layout unit
        self.xh_px = xh
        self.space_units = self.font.getlength(" ") * self.k * 0.7
        self._cache: dict[str, CharGlyph | None] = {}

    # ---- precomputed glyph cache (built once when the font is added, so a request never thins a glyph)
    CACHE_VERSION = 1

    def export_cache(self) -> dict:
        glyphs = {}
        for ch, g in self._cache.items():
            if g is not None:
                glyphs[ch] = {"base": g.base, "marks": g.marks, "advance": g.advance}
        return {"version": self.CACHE_VERSION, "font_sha256": self.digest, "px": self.px, "glyphs": glyphs}

    def load_cache(self, blob: dict) -> int:
        """Accepts a cache only when it was built from exactly this font file, size and algorithm version."""
        if (blob.get("version"), blob.get("font_sha256"), blob.get("px")) != (self.CACHE_VERSION, self.digest, self.px):
            return 0
        for ch, g in blob.get("glyphs", {}).items():
            self._cache[ch] = CharGlyph(base=[[tuple(p) for p in s] for s in g["base"]],
                                        marks=[[tuple(p) for p in s] for s in g["marks"]], advance=float(g["advance"]))
        return len(blob.get("glyphs", {}))

    def precompute(self, chars: str) -> list[str]:
        """Thin every character now. Returns the characters that came out empty (no glyph / no ink)."""
        return [c for c in chars if self.char(c) is None]

    # layout-code interface
    def char(self, ch: str) -> CharGlyph | None:
        if ch not in self._cache:
            self._cache[ch] = self._build(ch)
        return self._cache[ch]

    def _build(self, ch: str) -> CharGlyph | None:
        if ch.isspace():
            return None
        if len(ch) != 1 or ord(ch) not in self._cmap:           # a missing glyph would be drawn as a box: refuse instead
            return None
        pad = self.px // 2
        adv = float(self.font.getlength(ch))
        img = Image.new("L", (int(adv) + 2 * pad, self.px * 2), 0)
        ImageDraw.Draw(img).text((pad, self.baseline), ch, font=self.font, fill=255, anchor="ls")
        ink = (np.array(img) > 127).astype(np.uint8) * 255
        if not ink.any():
            return None
        sk = rc._drop_corner_pixels(rc.zhang_suen(ink))
        width = max(float((ink > 0).sum()) / max(int(sk.sum()), 1), 1.0)
        edges, ends, closed = rc._graph(sk)
        removed = rc._prune_spurs(edges, ends, max_len=max(4.0, 1.2 * width))
        raw = rc._assemble(edges, rc._pair_edges(edges, ends, removed), removed) + closed
        base: list[Poly] = []
        marks: list[Poly] = []
        for p in raw:
            if len(p) < 2:
                continue
            p = rc._orient(rc._simplify(rc._smooth(p), 0.7))
            top, bottom = float(p[:, 1].min()) - self.baseline, float(p[:, 1].max()) - self.baseline
            poly = [((float(x) - pad) * self.k, BASE_UNITS + (float(y) - self.baseline) * self.k) for x, y in p]
            above = bottom < -0.80 * self.xh_px                       # entirely above the x-height: a tone mark / dot
            below = top > 0.10 * self.xh_px                           # entirely under the baseline: dot below
            (marks if above or below else base).append(poly)
        return CharGlyph(base=sorted(base, key=lambda s: s[0][0]), marks=sorted(marks, key=lambda s: s[0][0]),
                         advance=adv * self.k)


_SOURCES: dict[str, OutlineSource] = {}
_BY_PATH: dict[str, tuple[float, OutlineSource]] = {}
PATH_TTL_S = 300.0
CACHE_SUFFIX = ".glyphs.json"


def source_from_bytes(data: bytes) -> OutlineSource:
    key = hashlib.sha256(data).hexdigest()
    if key not in _SOURCES:
        if len(_SOURCES) > 8:
            _SOURCES.clear()
        _SOURCES[key] = OutlineSource(data)
    return _SOURCES[key]


def load_source(path: str, loader: Callable[[str], bytes | None], *, now: Callable[[], float] = time.monotonic) -> OutlineSource:
    """Font file + its precomputed glyph cache from storage. Kept in memory for a few minutes per path."""
    hit = _BY_PATH.get(path)
    if hit is not None and now() - hit[0] < PATH_TTL_S:
        return hit[1]
    data = loader(path)
    if data is None:
        raise AppError(409, "FONT_FILE_MISSING", "Không đọc được file font của mẫu chữ từ kho lưu trữ.")
    src = source_from_bytes(data)
    blob = loader(path + CACHE_SUFFIX)
    if blob:
        try:
            src.load_cache(json.loads(blob))
        except (ValueError, KeyError, TypeError):
            pass                                           # a damaged cache only costs time: glyphs are rebuilt on demand
    _BY_PATH[path] = (now(), src)
    return src
