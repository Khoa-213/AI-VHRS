"""OT-2 Phase O1(a) (owner approved 2026-11-20, docs/OT2_LEARNED_STYLE_PLAN.md): can a writer's own letters, harvested from
their handwriting, be reused to write new text that looks like that writer?

Public UIT-HWDB pages only (benchmarks/data/viet_hw, the U3 / E set; never a customer image). Assumption: one page = one
writer (the manifest has no writer id; if two pages share a writer the identification score below is lower, not higher).

Per page:
1. recover the strokes with the product recovery (U3) and its word regions (U4); attach the human label's words to the
   regions with the product matcher (`htr_align.match`, E2a: ~4 % of regions get a wrong word);
2. split the words in two halves by reading order: the first half is the "sample" the glyphs are harvested from, the second
   half is held out;
3. a word is "separable" when its base ink falls into exactly as many connected pieces as it has base letters and its
   small marks are exactly the marks its letters need (tone marks, breve / circumflex, the dot of i / j); only those words
   give glyphs (letter by letter, marks to letters by x then y). Joined-up writing is not separable: on a free page this
   is the limit of method A, which is why the product uses a sample sheet with one letter per box (Q1).
Measured:
* separable share of words, glyphs per page, letters / marks covered;
* coverage: share of held-out words whose letters and marks all exist in the page's glyph set;
* writer identity: for each held-out real letter (from separable held-out words), the chamfer distance to the same
  letter's glyphs of every page; top-1 = its own page is the nearest, compared with chance (1 / pages that have it).
No model call in this stage. Writes benchmarks/data/ot2/glyphs.json (not committed) and prints a summary.
    .venv/Scripts/python.exe scripts/benchmark_ot2_glyphs.py
"""
from __future__ import annotations

import json
import math
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

from benchmark_htr import PAGES, manifest                   # noqa: E402
from app.core.errors import AppError                         # noqa: E402
from app.services.stroke_ai import htr_align, recovery       # noqa: E402

OUT = BASE / "benchmarks" / "data" / "ot2"
PAPER, MARGIN = "A4", 10.0
TOUCH_MM = 0.6            # two base strokes closer than this are one connected piece (skeleton split at a junction)

TONES = {"̀": "grave", "́": "acute", "̉": "hook", "̃": "tilde", "̣": "dot_below"}
HATS = {"̆": "breve", "̂": "circumflex"}
HORN = "̛"


def split_char(ch: str) -> tuple[str, list[str]] | None:
    """'ấ' -> ('a', ['circumflex', 'acute']); base letters keep the horn (ơ, ư) and đ; None for non-letters."""
    d = unicodedata.normalize("NFD", ch.lower())
    base, marks = d[0], []
    if not base.isalpha():
        return None
    rest = d[1:]
    if HORN in rest:
        base = unicodedata.normalize("NFC", base + HORN)
    for m in rest:
        if m in HATS:
            marks.append(HATS[m])
    for m in rest:
        if m in TONES:
            marks.append(TONES[m])
    if base in "ij":
        marks.insert(0, "dot_i")
    return base, marks


def clean_word(w: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", w) if split_char(c) is not None)


def pieces(strokes: list[np.ndarray]) -> list[list[int]]:
    """Connected pieces of a set of strokes (union-find on near points)."""
    n = len(strokes)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    boxes = [(s[:, 0].min(), s[:, 1].min(), s[:, 0].max(), s[:, 1].max()) for s in strokes]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if a[0] - TOUCH_MM > b[2] or b[0] - TOUCH_MM > a[2] or a[1] - TOUCH_MM > b[3] or b[1] - TOUCH_MM > a[3]:
                continue
            d = np.min(np.linalg.norm(strokes[i][:, None, :] - strokes[j][None, :, :], axis=2))
            if d <= TOUCH_MM:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=lambda g: min(strokes[i][:, 0].min() for i in g))


def box(strokes: list[np.ndarray]) -> tuple[float, float, float, float]:
    p = np.concatenate(strokes)
    return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())


SHORT = set("acemnorsuvwxzăâêôơư")     # letters with no ascender / descender: their box is the body (x-height) band


def harvest_word(word: str, base_strokes: list[np.ndarray], mark_strokes: list[np.ndarray]):
    """-> (letters, marks) or None. letters: [(base letter, [strokes])]; marks: [(mark name, host index, [strokes])]."""
    chars = [split_char(c) for c in word]
    if not chars or any(c is None for c in chars):
        return None
    bp = pieces(base_strokes) if base_strokes else []
    if len(bp) != len(chars):
        return None
    letters = [(chars[k][0], [base_strokes[i] for i in g]) for k, g in enumerate(bp)]
    need = [(k, m) for k, (_, ms) in enumerate(chars) for m in ms]
    mp = pieces(mark_strokes) if mark_strokes else []
    if len(mp) != len(need):
        return None
    mboxes = [box([mark_strokes[i] for i in g]) for g in mp]
    order = sorted(range(len(mp)), key=lambda i: (round((mboxes[i][0] + mboxes[i][2]) / 2, 0), -mboxes[i][3]))
    # marks of one letter: sort the observed ones bottom-up (circumflex / breve under the tone, dot below lowest)
    marks = []
    for (k, name), i in zip(need, order):
        marks.append((name, k, [mark_strokes[j] for j in mp[i]]))
    # sanity: each mark sits over (or under) its host letter's x range, with some slack
    for name, k, st in marks:
        hb, mb = box(letters[k][1]), box(st)
        cx, slack = (mb[0] + mb[2]) / 2, (hb[2] - hb[0]) * 0.8 + 1.0
        if not (hb[0] - slack <= cx <= hb[2] + slack):
            return None
    return letters, marks


def norm_glyph(strokes: list[np.ndarray], x0: float, base_y: float, xh: float) -> list[list[list[float]]]:
    return [[[round((x - x0) / xh, 4), round((y - base_y) / xh, 4)] for x, y in s] for s in strokes]


def body_band(letters) -> tuple[float, float] | None:
    tops, bots = [], []
    for b, st in letters:
        if b in SHORT:
            bb = box(st)
            tops.append(bb[1])
            bots.append(bb[3])
    if not tops:
        return None
    return float(np.median(tops)), float(np.median(bots))


def page_words(data: bytes, label: str):
    _, page_stats = None, None
    try:
        page, stats = recovery.recover_page(data, paper_size=PAPER, margin_mm=MARGIN)
    except AppError:
        return None
    m = htr_align.match(stats.regions, label)
    by_word: dict[int, list] = defaultdict(list)
    for r in stats.regions:
        v = m["regions"][r.region_no]
        if v["status"] == "READ" and v["word"] is not None:
            by_word[v["word"]].append(r)
    out = []
    for wi, word in enumerate(m["words"]):
        regs = by_word.get(wi)
        w = clean_word(word)
        if not w:
            continue
        if not regs:
            out.append((wi, w, None, None))
            continue
        base, marks = [], []
        for r in regs:
            for s in page.strokes[r.stroke_start:r.stroke_end]:
                (marks if s.kind == "mark" else base).append(np.array(s.points, float))
        out.append((wi, w, base, marks))
    return out, len(m["words"]), stats


def why(w: str, base, marks) -> str:
    """Why a word gives (or not) glyphs: counts only, the same tests as harvest_word."""
    if base is None:
        return "no ink (word UNREAD)"
    chars = [split_char(c) for c in w]
    bp = len(pieces(base)) if base else 0
    if bp < len(chars):
        return "base: fewer pieces than letters (joined-up)"
    if bp > len(chars):
        return "base: more pieces than letters (broken)"
    need = sum(len(ms) for _, ms in chars)
    if (len(pieces(marks)) if marks else 0) != need:
        return "base ok, mark count differs"
    return "counts match"


def resample(strokes, step=0.05) -> np.ndarray:
    pts = []
    for s in strokes:
        s = np.asarray(s, float)
        if len(s) == 1:
            pts.append(s)
            continue
        seg = np.linalg.norm(np.diff(s, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        n = max(2, int(cum[-1] / step) + 1)
        t = np.linspace(0, cum[-1], n)
        pts.append(np.stack([np.interp(t, cum, s[:, 0]), np.interp(t, cum, s[:, 1])], 1))
    return np.concatenate(pts)


def chamfer(a: np.ndarray, b: np.ndarray) -> float:
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return float(d.min(1).mean() + d.min(0).mean()) / 2


WHY: dict[str, int] = defaultdict(int)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = manifest()
    pages = {}
    for r in rows:
        pid = str(r["id"])
        res = page_words((PAGES / r["file"]).read_bytes(), r["label"])
        if res is None:
            print(pid, "refused by recovery")
            continue
        words, nwords, stats = res
        for _, w, base, marks in words:
            WHY[why(w, base, marks)] += 1
        half = nwords // 2
        sample, held = [w for w in words if w[0] < half], [w for w in words if w[0] >= half]
        harvested = []                     # (word, letters, marks, band)
        for _, w, base, marks in sample:
            if base is None:
                continue
            h = harvest_word(w, base, marks)
            if h is None:
                continue
            band = body_band(h[0])
            if band is None:
                continue
            harvested.append((w, h[0], h[1], band))
        held_real = []
        for _, w, base, marks in held:
            if base is None:
                continue
            h = harvest_word(w, base, marks)
            if h is None:
                continue
            band = body_band(h[0])
            if band is None:
                continue
            held_real.append((w, h[0], h[1], band))
        xhs = [b[1] - b[0] for *_, b in harvested if b[1] - b[0] > 0.3]
        if not xhs:
            print(pid, "no separable word")
            pages[pid] = {"glyphs": {}, "marks": {}, "held": [], "sample_words": len(sample), "separable": 0,
                          "held_words": [w for _, w, *_ in held], "xh_mm": None}
            continue
        glyphs, mks = defaultdict(list), defaultdict(list)
        for w, letters, marks, (top, bot) in harvested:
            xh = max(bot - top, 0.3)
            for b, st in letters:
                bb = box(st)
                glyphs[b].append(norm_glyph(st, bb[0], bot, xh))
            for name, k, st in marks:
                hb, mb = box(letters[k][1]), box(st)
                # mark glyph relative to its own box; placement = (mark centre - host centre, mark bottom - host top) / xh
                mks[name].append({"g": norm_glyph(st, mb[0], mb[3], xh),
                                  "dx": round(((mb[0] + mb[2]) - (hb[0] + hb[2])) / 2 / xh, 4),
                                  "dy": round((mb[3] - hb[1]) / xh, 4)})
        held_glyphs = []
        for w, letters, marks, (top, bot) in held_real:
            xh = max(bot - top, 0.3)
            for b, st in letters:
                bb = box(st)
                held_glyphs.append((b, norm_glyph(st, bb[0], bot, xh)))
        pages[pid] = {"glyphs": glyphs, "marks": mks, "held": held_glyphs, "sample_words": len(sample),
                      "separable": len(harvested), "held_words": [w for _, w, *_ in held],
                      "xh_mm": round(float(np.median(xhs)), 3), "similarity": stats.similarity}
        print(pid, "sample", len(sample), "separable", len(harvested), "letters", len(glyphs), "marks", len(mks),
              "held letters", len(held_glyphs), flush=True)
    (OUT / "glyphs.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def coverage(pages):
    rows = []
    for pid, p in pages.items():
        have, mk = set(p["glyphs"]), set(p["marks"])
        ok = 0
        for w in p["held_words"]:
            parts = [split_char(c) for c in w]
            if all(b in have and all(m in mk for m in ms) for b, ms in parts):
                ok += 1
        rows.append((pid, ok, len(p["held_words"])))
    return rows


def identity(pages, max_per_letter=6):
    """Held-out real letters of a page vs every page's glyphs of that letter (chamfer, nearest glyph)."""
    clouds = {pid: {b: [resample(g) for g in gs[:max_per_letter]] for b, gs in p["glyphs"].items()} for pid, p in pages.items()}
    hits, chance, n = 0, 0.0, 0
    per_page = defaultdict(lambda: [0, 0])
    for pid, p in pages.items():
        for b, g in p["held"]:
            cands = {q: c[b] for q, c in clouds.items() if b in c and c[b]}
            if pid not in cands or len(cands) < 2:
                continue
            a = resample(g)
            best = min(cands, key=lambda q: min(chamfer(a, x) for x in cands[q]))
            hits += best == pid
            per_page[pid][0] += best == pid
            per_page[pid][1] += 1
            chance += 1 / len(cands)
            n += 1
    return hits, chance, n, dict(per_page)


if __name__ == "__main__":
    pages = run()
    cov = coverage(pages)
    sep = sum(p["separable"] for p in pages.values())
    smp = sum(p["sample_words"] for p in pages.values())
    print("separable sample words", sep, "/", smp)
    print("held words fully covered", sum(c[1] for c in cov), "/", sum(c[2] for c in cov))
    h, ch, n, _ = identity(pages)
    print("identity top-1", h, "/", n, "chance", round(ch, 1))
    for k, v in sorted(WHY.items(), key=lambda kv: -kv[1]):
        print(v, k)
    json.dump({"why": WHY, "separable": [sep, smp], "covered": [sum(c[1] for c in cov), sum(c[2] for c in cov)],
               "identity": [h, round(ch, 2), n], "pages": len(pages),
               "no_glyph_pages": sum(1 for p in pages.values() if not p["glyphs"])},
              open(OUT / "summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
