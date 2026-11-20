"""V2 Phase E2b: attach the words of a page transcript to the OT-1 word regions (U4), locally.

Measured in Phase E2a (`docs/benchmarks/E2a_htr_regions_2026-11-19.md`, 2026-11-19): the reader (Gemini) transcribes the
whole page and this module places the words; asking the reader to label numbered boxes put words in the wrong boxes.
Regions -> lines (followed across the page, cut descenders back to their line) -> units (regions stacked on each other,
e.g. a tone mark over its letters, are one unit) -> a monotone dynamic-programming match of words to units over the page.
A word takes 1-4 consecutive units of one line (U4 often cuts a word in two); two short words may share a unit; a unit
with no word (noise) or a word with no ink (reader mistake) can be skipped at a cost; "[?]" / "..." are holes that take
unreadable ink. The cost of a word is how far its expected width (letters x the page's letter width) is from the ink it
is given, plus the gaps it swallows; a line of the transcript starts on a line of ink. A word whose cost is high, or
that the reader marked "[?]", is returned UNREAD instead of guessed. Pure Python, no dependency.

E2a: 24/612 = 3.9 % wrong regions on 6 random held-out pages (judged by eye), none invented; words still slide on pages
with a missing middle (cut letters merge with the line below in the recovery), so the text is a hint, never applied.
`regions`: objects with `region_no` and `bbox` (x0, y0, x1, y1) in one page's coordinates.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

PUNCT = ".,;:!?\"'()[]…-–—«»“”‘’"
MAX_UNITS_PER_WORD = 4
SKIP_UNIT, SKIP_TINY_UNIT, SKIP_WORD, SHARE_UNIT = 1.2, 0.3, 1.6, 0.9
GAP_WEIGHT = 1.2
LINE_BREAK = 1.0            # a line of the transcript starts on a line of ink (and, when the reader kept the lines, back)
UNREAD_ABOVE = 0.9          # a word costing more than this is not trusted
# V2 Phase I (Test 5): a reading with far more words than there is ink is not matched at all. On the 48 public pages of E2a
# with a reading the most was 1.22 words per unit; invented text tried was 1.67 - 2.5.
MAX_WORDS_PER_UNIT = 1.5


@dataclass
class Unit:
    regions: list[int]        # region_no
    line: int
    x0: float
    y0: float
    x1: float
    y1: float


def letters(word: str) -> float:
    """Width of a word in 'letters': base letters count 1, punctuation 0.4 (tone marks add no width)."""
    base = unicodedata.normalize("NFD", word)
    n = 0.0
    for ch in base:
        if unicodedata.combining(ch):
            continue
        n += 0.4 if ch in PUNCT else 1.0
    return max(n, 0.4)


def placeholder(word: str) -> bool:
    """"[?]", "..." or a lone dash: the reader saying "something unreadable here", not a word with a width."""
    w = word.replace("[?]", "").strip(PUNCT)
    return not w and ("[?]" in word or "..." in word or "…" in word or word.strip() in ("-", "–", "—"))


def words_of(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def units_of(regions) -> list[Unit]:
    """regions: objects with region_no and bbox (x0, y0, x1, y1). Returns units in reading order."""
    if not regions:
        return []
    hs = sorted(r.bbox[3] - r.bbox[1] for r in regions)
    ref_h = max(hs[int(0.75 * (len(hs) - 1))], 0.5)
    base = [r for r in regions if r.bbox[3] - r.bbox[1] >= 0.45 * ref_h]
    marks = [r for r in regions if r.bbox[3] - r.bbox[1] < 0.45 * ref_h]
    cy_of = lambda r: (r.bbox[1] + r.bbox[3]) / 2

    def local(ms, x, k=3):
        """Members of a line nearest to x (lines drift up / down across a page, so a page-wide mean is not enough)."""
        return sorted(ms, key=lambda m: abs((m.bbox[0] + m.bbox[2]) / 2 - x))[:k]

    members: list[list] = []
    for r in sorted(base, key=lambda r: r.bbox[0]):   # left to right, each line followed at its right end
        best, dy = None, 0.6 * ref_h
        for li, ms in enumerate(members):
            tail = sorted(ms, key=lambda m: m.bbox[2])[-3:]
            d = abs(cy_of(r) - sorted(cy_of(m) for m in tail)[len(tail) // 2])
            if d < dy:
                best, dy = li, d
        if best is None:
            members.append([r])
        else:
            members[best].append(r)
    if not members:                       # only small marks on the page
        members, marks = [list(marks)], []
    # A cut-off descender ("g", "y") sits half a line low and would open a line of its own, which breaks the reading
    # order; members of a small line that lie mostly inside the local band of a big line move there.
    sizes = sorted(len(ms) for ms in members)
    big = [i for i, ms in enumerate(members) if len(ms) > max(3, 0.3 * sizes[len(sizes) // 2])]
    bcy = sorted(sorted(cy_of(m) for m in members[i])[len(members[i]) // 2] for i in big)
    pitch = sorted(bcy[i + 1] - bcy[i] for i in range(len(bcy) - 1))[(len(bcy) - 2) // 2] if len(bcy) > 1 else 2 * ref_h
    for li, ms in enumerate(members):
        if li in big or not big:
            continue
        for r in list(ms):
            cx, cy = (r.bbox[0] + r.bbox[2]) / 2, cy_of(r)
            best, bs = None, None
            for bi in big:
                near = local(members[bi], cx)
                ly = sorted(cy_of(m) for m in near)[len(near) // 2]
                if abs(ly - cy) > 0.75 * pitch:
                    continue
                s = abs(ly - cy) - (0.3 * pitch if ly < cy else 0)     # a descender hangs below its own line
                if bs is None or s < bs:
                    best, bs = bi, s
            if best is not None:
                ms.remove(r)
                members[best].append(r)
    members = [ms for ms in members if ms]
    # One ink line can come out as two (its tail was a descender, so the next word looked a line apart); two lines whose
    # members sit at the same local height are one line.
    merged = True
    while merged and len(members) > 1:
        merged = False
        for a in range(len(members)):
            for b in range(len(members)):
                if a == b or len(members[b]) > len(members[a]):
                    continue
                ovs = []
                for r in members[b]:
                    near = local(members[a], (r.bbox[0] + r.bbox[2]) / 2)
                    b0 = sorted(m.bbox[1] for m in near)[len(near) // 2]
                    b1 = sorted(m.bbox[3] for m in near)[len(near) // 2]
                    h = min(r.bbox[3] - r.bbox[1], b1 - b0)
                    ovs.append((min(b1, r.bbox[3]) - max(b0, r.bbox[1])) / h if h > 0 else 0.0)
                if sorted(ovs)[len(ovs) // 2] >= 0.6:
                    members[a] += members[b]
                    del members[b]
                    merged = True
                    break
            if merged:
                break
    for r in marks:                       # a mark belongs to the line just below it (tone marks sit above the letters)
        cy, cx = cy_of(r), (r.bbox[0] + r.bbox[2]) / 2

        def score(ms):
            near = local(ms, cx, 2)
            ly = sum(cy_of(m) for m in near) / len(near)
            return abs(ly - cy) + (0 if ly >= cy else 0.4 * ref_h)
        min(members, key=score).append(r)
    line_cy = [sorted(cy_of(m) for m in ms)[len(ms) // 2] for ms in members]
    order = sorted(range(len(line_cy)), key=lambda i: line_cy[i])
    units: list[Unit] = []
    for ln, li in enumerate(order):
        cur: Unit | None = None
        for r in sorted(members[li], key=lambda r: r.bbox[0]):
            x0, y0, x1, y1 = r.bbox
            if cur is not None:
                ov = min(cur.x1, x1) - max(cur.x0, x0)
                if ov > 0.5 * min(x1 - x0, cur.x1 - cur.x0):       # stacked: same unit
                    cur.regions.append(r.region_no)
                    cur.x0, cur.y0, cur.x1, cur.y1 = min(cur.x0, x0), min(cur.y0, y0), max(cur.x1, x1), max(cur.y1, y1)
                    continue
                units.append(cur)
            cur = Unit([r.region_no], ln, x0, y0, x1, y1)
        if cur is not None:
            units.append(cur)
    return units


def match(regions, text: str) -> dict:
    """Return {"regions": {region_no: {"text", "word", "status": READ|UNREAD}}, "words": [...], "cost": page cost,
    "refused": None | "TOO_MANY_WORDS"}."""
    units = units_of(regions)
    words, starts = [], []
    for tl in (text or "").splitlines():
        ws = words_of(tl)
        words += ws
        starts += [True] + [False] * (len(ws) - 1) if ws else []
    out = {r.region_no: {"text": None, "word": None, "status": "UNREAD"} for r in regions}
    if not units or not words:
        return {"regions": out, "words": words, "cost": None, "refused": None}
    if sum(not placeholder(w) for w in words) > MAX_WORDS_PER_UNIT * len(units):
        return {"regions": out, "words": words, "cost": None, "refused": "TOO_MANY_WORDS"}
    hs = sorted(u.y1 - u.y0 for u in units)
    ref_h = max(hs[len(hs) // 2], 0.5)
    lw = sum(letters(w) for w in words)
    ink = sum(u.x1 - u.x0 for u in units)
    gaps = sum(max(0.0, units[i + 1].x0 - units[i].x1) for i in range(len(units) - 1) if units[i + 1].line == units[i].line)
    cw = max((ink + 0.6 * gaps * len(words) / max(len(units), 1)) / lw, 0.1)      # letter width incl. inner gaps

    def span_cost(i: int, k: int, nletters: float) -> float | None:
        a, b = units[i], units[i + k - 1]
        if a.line != b.line:
            return None
        inner = sum(max(0.0, units[t + 1].x0 - units[t].x1) for t in range(i, i + k - 1))
        width = max(b.x1 - a.x0, 0.1)
        return abs(math.log(nletters * cw / width)) + GAP_WEIGHT * inner / ref_h

    n, m = len(units), len(words)
    tiny = [(u.y1 - u.y0) < 0.5 * ref_h and (u.x1 - u.x0) < 0.6 * ref_h for u in units]
    first = []                                              # unit i is the first real ink of its line
    for i, u in enumerate(units):
        k = i - 1
        while k >= 0 and units[k].line == u.line and tiny[k]:
            k -= 1
        first.append(k < 0 or units[k].line != u.line)
    both_ways = sum(starts) >= 0.7 * (units[-1].line + 1)   # the reader kept the page's lines (lists, addresses)

    def brk(i: int, j: int) -> float:
        if starts[j] and not first[i]:
            return LINE_BREAK
        if both_ways and first[i] and not starts[j]:
            return LINE_BREAK
        return 0.0
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c0 = cost[i][j]
            if c0 == INF:
                continue
            if i < n:                                          # skip a unit (noise / stray mark)
                u = units[i]
                sk = SKIP_TINY_UNIT if tiny[i] else SKIP_UNIT
                if c0 + sk < cost[i + 1][j]:
                    cost[i + 1][j], back[i + 1][j] = c0 + sk, ("su", i, j)
            hole = j < m and placeholder(words[j])
            sw = 0.0 if hole else SKIP_WORD
            if j < m and c0 + sw < cost[i][j + 1]:             # a word with no ink (a placeholder costs nothing)
                cost[i][j + 1], back[i][j + 1] = c0 + sw, ("sw", i, j)
            if hole:                                            # unreadable ink: takes 1-4 units, all UNREAD
                for k in range(1, MAX_UNITS_PER_WORD + 1):
                    if i + k > n or units[i + k - 1].line != units[i].line:
                        break
                    tot = c0 + 0.2 * k
                    if tot < cost[i + k][j + 1]:
                        cost[i + k][j + 1], back[i + k][j + 1] = tot, ("w", i, j, k, UNREAD_ABOVE + 1)
                continue
            if j < m:
                nl = letters(words[j])
                for k in range(1, MAX_UNITS_PER_WORD + 1):
                    if i + k > n:
                        break
                    sc = span_cost(i, k, nl)
                    if sc is None:
                        break
                    tot = c0 + sc + brk(i, j)
                    if tot < cost[i + k][j + 1]:
                        cost[i + k][j + 1], back[i + k][j + 1] = tot, ("w", i, j, k, sc)
            if j + 1 < m and i < n and not placeholder(words[j + 1]):   # two short words written as one unit
                sc = span_cost(i, 1, letters(words[j]) + letters(words[j + 1]) + 0.6)
                if sc is not None and not starts[j + 1]:
                    tot = c0 + sc + SHARE_UNIT + brk(i, j)
                    if tot < cost[i + 1][j + 2]:
                        cost[i + 1][j + 2], back[i + 1][j + 2] = tot, ("w2", i, j, 1, sc)
    i, j = n, m
    steps = []
    while (i, j) != (0, 0):
        st = back[i][j]
        steps.append(st)
        i, j = st[1], st[2]
    for st in steps:
        if st[0] in ("w", "w2"):
            _, i, j, k, sc = st
            text_ = words[j] if st[0] == "w" else f"{words[j]} {words[j + 1]}"
            unsure = "[?]" in text_                             # the reader said it could not read this part
            status = "READ" if sc <= UNREAD_ABOVE and not unsure else "UNREAD"
            for u in units[i:i + k]:
                for rn in u.regions:
                    out[rn] = {"text": text_ if status == "READ" else None, "word": j, "status": status,
                               "cost": round(sc, 3), "guess": text_}
    return {"regions": out, "words": words, "cost": round(cost[n][m], 3), "refused": None}
