"""OT-2 Phase O3 (owner approved 2026-11-21, docs/OT2_LEARNED_STYLE_PLAN.md section 10): a glyph source built from a writer's
approved handwriting style (the `ot2-glyphs/1` glyph set written by Phase O2), with the interface the OT-3 layout code uses
(`char(ch) -> CharGlyph | None`, `space_units`), so the same composer, layout, editing and motion checks apply.

* Units: the glyph set is in x-height units (y down, baseline 0). The layout works in Hershey units (cap height 21, baseline
  y = 9). The scale comes from the writer's own capitals (median cap height in x-heights), so capitals keep the height that
  person writes them at; a style without capitals uses CAP_XH_DEFAULT (an assumption, reported in `scale_source`).
* Letters stay separate (O3-c): each glyph is its strokes with a fixed side bearing; there is no joined-up writing.
* Vietnamese letters (Q2): `ơ ư đ` (and capitals) come straight from the sheet; every other accented letter is the writer's base
  letter plus the writer's own marks (breve / circumflex / tone / dot below) at the offset measured on the sheet's carrier boxes.
  A missing base letter or mark gives None, which the composer reports as UNSUPPORTED_CHARS; no other font is ever used.
* Variation (O3-d): each occurrence of a letter takes the next sample of a per-letter order shuffled by `seed`, so repeats
  differ but the same content always gives the same strokes. Build a fresh source for every composition.
"""
import random
import statistics
import unicodedata

from app.services.stroke_ai.text_to_stroke import CAP_UNITS, CharGlyph, Poly

GLYPH_FORMAT = "ot2-glyphs/1"
CAP_XH_DEFAULT = 1.45            # ASSUMPTION: cap height / x-height when the style has no capital to measure
SIDE_BEARING_XH = 0.15           # each side of a letter, in x-heights (no measured letter spacing: boxes are separate)
SPACE_XH = 0.8                   # word space, in x-heights
BASELINE_UNITS = 9.0             # Hershey base line

_TONES = {"́": "acute", "̀": "grave", "̉": "hook", "̃": "tilde", "̣": "dot_below"}
_HATS = {"̂": "circumflex", "̆": "breve"}
_HORN = "̛"
_HORNED = {"o": "ơ", "u": "ư", "O": "Ơ", "U": "Ư"}


class StyleError(ValueError):
    pass


def _box(polys: list[Poly]) -> tuple[float, float, float, float]:
    xs = [p[0] for s in polys for p in s]
    ys = [p[1] for s in polys for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _polys(strokes) -> list[Poly]:
    return [[(float(x), float(y)) for x, y in s] for s in strokes if len(s) >= 1]


class StyleSource:
    def __init__(self, glyph_set: dict, seed: int = 0):
        if not isinstance(glyph_set, dict) or glyph_set.get("format") != GLYPH_FORMAT:
            raise StyleError("unknown glyph set format")
        self.glyphs: dict[str, list[dict]] = {k: v for k, v in (glyph_set.get("glyphs") or {}).items() if v}
        self.marks: dict[str, list[dict]] = {k: v for k, v in (glyph_set.get("marks") or {}).items() if v}
        self.seed = seed
        caps = [-_box(_polys(s["strokes"]))[1] for ch, samples in self.glyphs.items()
                if len(ch) == 1 and ch.isalpha() and ch.isupper() and ch not in "ĐƠƯ" for s in samples if s["strokes"]]
        caps = [c for c in caps if c > 0.5]
        self.cap_xh = statistics.median(caps) if caps else CAP_XH_DEFAULT
        self.scale_source = "writer_capitals" if caps else "default"
        self.u = CAP_UNITS / self.cap_xh                 # layout units per x-height
        self.space_units = SPACE_XH * self.u
        a = [_box(_polys(s["strokes"])) for s in self.glyphs.get("a", []) if s["strokes"]]
        self.a_height = statistics.median(b[3] - b[1] for b in a) if a else 1.0
        self._order: dict[str, list[int]] = {}
        self._next: dict[str, int] = {}

    # ---- sample choice (O3-d)
    def _pick(self, kind: str, key: str, samples: list[dict]) -> dict:
        k = f"{kind}:{key}"
        if k not in self._order:
            order = list(range(len(samples)))
            random.Random(f"{self.seed}:{k}").shuffle(order)
            self._order[k], self._next[k] = order, 0
        i = self._next[k]
        self._next[k] = i + 1
        return samples[self._order[k][i % len(samples)]]

    def _glyph(self, ch: str) -> list[Poly] | None:
        samples = self.glyphs.get(ch)
        if not samples:
            return None
        polys = _polys(self._pick("g", ch, samples)["strokes"])
        return polys or None

    def _mark(self, name: str) -> dict | None:
        samples = self.marks.get(name)
        if not samples:
            return None
        s = self._pick("m", name, samples)
        polys = _polys(s["strokes"])
        return {"polys": polys, "dx": float(s["dx"]), "dy": float(s["dy"])} if polys else None

    # ---- composition (x-height units)
    def _compose_xh(self, ch: str) -> tuple[list[Poly], list[Poly]] | None:
        direct = self._glyph(ch)
        if direct is not None:
            return direct, []
        parts = unicodedata.normalize("NFD", ch)
        base_ch, rest = parts[0], list(parts[1:])
        if _HORN in rest:
            if base_ch not in _HORNED:
                return None
            base_ch = _HORNED[base_ch]
            rest.remove(_HORN)
        hats = [_HATS[m] for m in rest if m in _HATS]
        tones = [_TONES[m] for m in rest if m in _TONES]
        if not rest or len(hats) + len(tones) != len(rest) or len(hats) > 1 or len(tones) > 1:
            return None
        base = self._glyph(base_ch)
        if base is None:
            return None
        if base_ch in "ij":                                   # the dot of i / j gives way to the marks
            body = [s for s in base if max(p[1] for p in s) > -0.9]
            base = body or base
        x0, top, x1, _ = _box(base)
        cx = (x0 + x1) / 2
        marks: list[Poly] = []
        for name in hats + [t for t in tones if t != "dot_below"]:
            m = self._mark(name)
            if m is None:
                return None
            mx0, mtop, mx1, _ = _box(m["polys"])
            left = cx + m["dx"] - (mx1 - mx0) / 2 - mx0
            floor = top + m["dy"]                              # the mark's bottom sits dy above the top of what is under it
            marks.extend([(x + left, y + floor) for x, y in p] for p in m["polys"])
            top = floor + mtop
        if "dot_below" in tones:
            m = self._mark("dot_below")
            if m is None:
                return None
            mx0, _, mx1, _ = _box(m["polys"])
            left = cx + m["dx"] - (mx1 - mx0) / 2 - mx0
            floor = m["dy"] - self.a_height             # under the baseline, as measured under the "a" of the sheet
            marks.extend([(x + left, y + floor) for x, y in p] for p in m["polys"])
        return base, marks

    # ---- layout-code interface
    def char(self, ch: str) -> CharGlyph | None:
        got = self._compose_xh(ch)
        if got is None:
            return None
        base, marks = got
        x0, _, x1, _ = _box(base + marks)
        shift = SIDE_BEARING_XH - x0

        def conv(polys: list[Poly]) -> list[Poly]:
            return [[((x + shift) * self.u, BASELINE_UNITS + y * self.u) for x, y in p] for p in polys]

        return CharGlyph(base=conv(base), marks=conv(marks), advance=(x1 - x0 + 2 * SIDE_BEARING_XH) * self.u)

    def missing(self, chars: str) -> list[str]:
        """The characters of `chars` this style cannot write (no sample consumed: uses a throwaway copy)."""
        probe = StyleSource.__new__(StyleSource)
        probe.__dict__.update(self.__dict__)
        probe._order, probe._next = {}, {}
        return sorted({c for c in chars if not c.isspace() and probe._compose_xh(c) is None})
