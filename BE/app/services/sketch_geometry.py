"""V2 canonical sketch geometry (`vhrs-sketch/2`) and the Geometry Engine (owner decisions D2, D3, D5, 2026-11-17).

The document
------------
    {"format": "vhrs-sketch/2", "engine": {...how it was built...}, "next_id": 57,
     "pages": [{"no": 1, "paper_size": "A4", "width_mm": 210, "height_mm": 297,
                "strokes": [{"id": "s1", "kind": "base", "points": [[x, y], ...], "word": "w1", "provenance": "ENGINE"}],
                "words":   [{"id": "w1", "stroke_ids": ["s1", "s2"], "bbox": [x0, y0, x1, y1],
                             "label": null, "confidence": null, "text": null}]}]}

* Polylines in millimetres, origin top-left, y down: the same as `vhrs-trajectory/1` (D5: polyline is the canonical form;
  a curve edit works on the polyline, nothing stores Bezier control points). `to_pages()` gives the trajectory pages the
  rest of the system (preview, official sketch, motion planning, signed snapshot) already uses, in this exact stroke order.
* Ids are given once and never reused: an edit keeps the ids of the strokes it changes; a split gets a new id from
  `next_id`. A new generation (the customer changed the text or the images) starts new ids, which the revision says.
* Words come from the engine: OT-3 strokes carry their word group (U7), OT-1 strokes belong to the U4 regions.
* `provenance`: ENGINE (text engine), RECOVERED (traced from the photo), INFERRED / RESTORED (U4 labels), CANVAS (the
  customer's drawing), EDITED (changed by an edit; `edits` counts them).

The Geometry Engine
-------------------
`apply(doc, op, stroke_ids, params, limits)` runs ONE structured edit. A language model only chooses `op`, the ids the customer
selected and parameters inside `limits`; it never writes coordinates. Each op is plain geometry, the result is validated
(inside the paper, no empty stroke, size caps) and the strokes outside the selection are checked to be byte-identical.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError
from app.services.stroke_ai import trajectory as tj

FORMAT = "vhrs-sketch/2"
EDGE_MM = 1.0                    # a point closer than this to the paper edge is refused (the pen holder needs room)
MIN_STROKE_MM = 0.2
MAX_SELECTION = 500
OPS = ("translate", "rotate", "scale", "slant", "curvature", "smooth", "extend", "trim", "join", "split", "delete")


@dataclass(frozen=True)
class Limits:
    """How far one edit may go. TEXT = OT-3 (strokes of a typeface: small corrections only, D3), FREE = OT-1 / OT-2."""
    name: str
    max_shift_mm: float
    max_rotate_deg: float
    scale_range: tuple[float, float]
    max_slant_deg: float
    curvature_range: tuple[float, float]
    max_extend_mm: float
    max_join_gap_mm: float


TEXT_LIMITS = Limits("TEXT", 3.0, 15.0, (0.8, 1.25), 15.0, (0.5, 1.5), 3.0, 2.0)
FREE_LIMITS = Limits("FREE", 10.0, 45.0, (0.5, 2.0), 30.0, (0.0, 2.0), 10.0, 5.0)


def limits_for(order_type: str) -> Limits:
    return TEXT_LIMITS if order_type == "OT3_TEMPLATE" else FREE_LIMITS


# ---------------------------------------------------------------------------------------------------------- document
def _r(v: float) -> float:
    return round(float(v), 2)          # 0.01 mm: the precision of the trajectory file, so hashes compare across the two


def _bbox(points: list[list[float]]) -> list[float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [_r(min(xs)), _r(min(ys)), _r(max(xs)), _r(max(ys))]


def from_generated(pages: list[tj.Page], engine_info: dict[str, Any], regions: list[Any] | None = None,
                   word_texts: list[str] | None = None) -> dict[str, Any]:
    """Build the document from an engine run (`engine.Generated`). `regions` = U4 RegionDraft list (OT-1).

    `word_texts` (OT-3): the words of the order's text in reading order. The engine numbers each word's group in writing
    order, so sorting the groups gives the reading order; the words get their `text` only when the counts match exactly
    (otherwise none do: a wrong label is worse than none, the assistant then works from positions)."""
    n = 0
    reading: list[tuple[int, int, str]] = []            # (page, group, word id) of OT-3 words
    out_pages = []
    by_page: dict[int, list[Any]] = {}
    for r in regions or []:
        by_page.setdefault(r.page_no, []).append(r)
    word_seq = 0
    for page_no, page in enumerate(pages, start=1):
        strokes: list[dict[str, Any]] = []
        words: list[dict[str, Any]] = []
        word_of: dict[int, str] = {}                    # stroke index -> word id
        meta: dict[str, dict[str, Any]] = {}
        if by_page.get(page_no):
            for r in sorted(by_page[page_no], key=lambda x: x.region_no):
                word_seq += 1
                wid = f"w{word_seq}"
                meta[wid] = {"label": r.label, "confidence": round(float(r.confidence), 3) if r.confidence is not None else None,
                             "text": r.text, "region_no": r.region_no}
                for i in range(r.stroke_start, r.stroke_end):          # stroke_end is exclusive
                    word_of[i] = wid
        else:
            group_ids: dict[int, str] = {}
            for i, s in enumerate(page.strokes):
                if s.group is not None:
                    if s.group not in group_ids:
                        word_seq += 1
                        group_ids[s.group] = f"w{word_seq}"
                    word_of[i] = group_ids[s.group]
            reading.extend((page_no, g, w) for g, w in group_ids.items())
        for i, s in enumerate(page.strokes):
            if s.kind == "watermark":                    # U8 line: added again on every official save, never edited
                continue
            n += 1
            wid = word_of.get(i)
            label = meta.get(wid, {}).get("label") if wid else None
            if s.kind == "canvas":
                prov = "CANVAS"
            elif label in ("INFERRED", "RESTORED"):
                prov = label
            elif regions is not None:
                prov = "RECOVERED"
            else:
                prov = "ENGINE"
            strokes.append({"id": f"s{n}", "kind": s.kind, "points": [[_r(x), _r(y)] for x, y in s.points],
                            "word": wid, "provenance": prov})
        order: list[str] = []
        for st in strokes:
            if st["word"] and st["word"] not in order:
                order.append(st["word"])
        for wid in order:
            ids = [st["id"] for st in strokes if st["word"] == wid]
            pts = [p for st in strokes if st["word"] == wid for p in st["points"]]
            words.append({"id": wid, "stroke_ids": ids, "bbox": _bbox(pts), **{k: v for k, v in meta.get(wid, {}).items()}})
        out_pages.append({"no": page_no, "paper_size": page.paper_size, "width_mm": page.width_mm,
                          "height_mm": page.height_mm, "strokes": strokes, "words": words})
    if word_texts is not None and reading and len(reading) == len(word_texts):
        text_of = {w: word_texts[k] for k, (_, _, w) in enumerate(sorted(reading))}
        for p in out_pages:
            for w in p["words"]:
                w["text"] = text_of.get(w["id"])
    return {"format": FORMAT, "engine": engine_info, "pages": out_pages, "next_id": n + 1}


def to_pages(doc: dict[str, Any]) -> list[tj.Page]:
    """Trajectory pages in document order (word ids become U7 groups so path optimisation keeps words whole)."""
    pages = []
    for p in doc["pages"]:
        page = tj.Page(p["paper_size"])
        groups: dict[str, int] = {}
        for st in p["strokes"]:
            g = groups.setdefault(st["word"], len(groups)) if st.get("word") else None
            page.strokes.append(tj.Stroke([(float(x), float(y)) for x, y in st["points"]], st["kind"], g))
        pages.append(page)
    return pages


def dumps(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(doc: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(doc)).hexdigest()


def geometry_hash(doc: dict[str, Any]) -> str:
    """Hash of the strokes only (kind + points, in order): equal for two documents that draw exactly the same thing."""
    flat = [[st["kind"], st["points"]] for p in doc["pages"] for st in p["strokes"]]
    return hashlib.sha256(json.dumps(flat, separators=(",", ":")).encode()).hexdigest()


def pages_geometry_hash(pages: list[tj.Page]) -> str:
    """The same hash for trajectory pages (watermark strokes left out): checks an official sketch against a revision."""
    flat = [[s.kind, [[_r(x), _r(y)] for x, y in s.points]] for p in pages for s in p.strokes if s.kind != "watermark"]
    return hashlib.sha256(json.dumps(flat, separators=(",", ":")).encode()).hexdigest()


def stroke_index(doc: dict[str, Any]) -> dict[str, tuple[int, int]]:
    return {st["id"]: (pi, si) for pi, p in enumerate(doc["pages"]) for si, st in enumerate(p["strokes"])}


def _stroke_digest(st: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(st, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------------- geometry
def _centroid(pts: list[list[float]]) -> tuple[float, float]:
    b = _bbox(pts)
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _length(pts: list[list[float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _curvature(pts: list[list[float]], f: float) -> list[list[float]]:
    """Scale each point's offset from the chord (first -> last point) by f: f < 1 flattens, f > 1 bends more; ends stay."""
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    out = [pts[0]]
    for x, y in pts[1:-1]:
        t = 0.0 if L2 == 0 else ((x - ax) * dx + (y - ay) * dy) / L2
        cx, cy = ax + t * dx, ay + t * dy
        out.append([cx + f * (x - cx), cy + f * (y - cy)])
    out.append(pts[-1])
    return out


def _smooth(pts: list[list[float]], passes: int) -> list[list[float]]:
    """Moving average of 3 points, ends fixed (keeps where the stroke starts and stops)."""
    for _ in range(passes):
        if len(pts) < 3:
            break
        pts = [pts[0]] + [[(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3]
                          for a, b, c in zip(pts, pts[1:], pts[2:])] + [pts[-1]]
    return pts


def _extend(pts: list[list[float]], mm: float, end: str) -> list[list[float]]:
    if end == "start":
        return list(reversed(_extend(list(reversed(pts)), mm, "end")))
    (ax, ay), (bx, by) = pts[-2], pts[-1]
    d = math.dist((ax, ay), (bx, by))
    if d == 0:
        raise AppError(422, "INVALID_EDIT", "Không xác định được hướng của đầu nét.")
    return pts + [[bx + (bx - ax) / d * mm, by + (by - ay) / d * mm]]


def _trim(pts: list[list[float]], mm: float, end: str) -> list[list[float]]:
    if end == "start":
        return list(reversed(_trim(list(reversed(pts)), mm, "end")))
    left = mm
    out = list(pts)
    while left > 0 and len(out) >= 2:
        a, b = out[-2], out[-1]
        d = math.dist(a, b)
        if d <= left:
            out.pop()
            left -= d
        else:
            k = (d - left) / d
            out[-1] = [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]
            left = 0
    return out


def _split_at(pts: list[list[float]], frac: float) -> tuple[list[list[float]], list[list[float]]]:
    target = _length(pts) * frac
    run = 0.0
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        d = math.dist(a, b)
        if run + d >= target and d > 0:
            k = (target - run) / d
            m = [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]
            return pts[:i + 1] + [m], [m] + pts[i + 1:]
        run += d
    raise AppError(422, "INVALID_EDIT", "Không tách được nét tại vị trí này.")


def _num(params: dict[str, Any], key: str, lo: float, hi: float, *, default: float | None = None) -> float:
    v = params.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise AppError(422, "INVALID_EDIT_PARAMS", f"Tham số '{key}' phải là số.", {"param": key})
    if not lo <= v <= hi:
        raise AppError(422, "EDIT_OUT_OF_RANGE", f"Tham số '{key}' phải trong khoảng {lo:g} đến {hi:g}.",
                       {"param": key, "min": lo, "max": hi, "value": v})
    return float(v)


def _end(params: dict[str, Any]) -> str:
    end = params.get("end", "end")
    if end not in ("start", "end"):
        raise AppError(422, "INVALID_EDIT_PARAMS", "Tham số 'end' là 'start' hoặc 'end'.", {"param": "end"})
    return end


def apply(doc: dict[str, Any], op: str, stroke_ids: list[str], params: dict[str, Any] | None,
          limits: Limits) -> tuple[dict[str, Any], dict[str, Any]]:
    """One structured edit -> (new document, report). Raises AppError with a stable code; `doc` is never modified."""
    params = params or {}
    if op not in OPS:
        raise AppError(422, "INVALID_EDIT_OP", f"Lệnh sửa không hợp lệ. Có: {', '.join(OPS)}.", {"ops": list(OPS)})
    ids = list(dict.fromkeys(stroke_ids or []))
    if not ids:
        raise AppError(422, "EMPTY_SELECTION", "Chưa chọn nét nào để sửa.")
    if len(ids) > MAX_SELECTION:
        raise AppError(422, "SELECTION_TOO_LARGE", f"Mỗi lần sửa tối đa {MAX_SELECTION} nét.")
    new = copy.deepcopy(doc)
    index = stroke_index(new)
    missing = [i for i in ids if i not in index]
    if missing:
        raise AppError(404, "STROKE_NOT_FOUND", "Không tìm thấy nét đã chọn (phác thảo đã đổi?).", {"stroke_ids": missing})
    pages_of = {index[i][0] for i in ids}
    if len(pages_of) > 1:
        raise AppError(422, "SELECTION_SPANS_PAGES", "Các nét được chọn phải cùng một trang.")
    before = {i: _stroke_digest(st) for p in new["pages"] for st in p["strokes"] for i in [st["id"]]}
    page = new["pages"][pages_of.pop()]
    sel = [page["strokes"][index[i][1]] for i in ids]
    all_pts = [p for st in sel for p in st["points"]]
    cx, cy = _centroid(all_pts)
    added: list[str] = []
    removed: list[str] = []

    def each(fn) -> None:
        for st in sel:
            st["points"] = [[_r(x), _r(y)] for x, y in fn(st["points"])]

    if op == "translate":
        dx = _num(params, "dx_mm", -limits.max_shift_mm, limits.max_shift_mm, default=0.0)
        dy = _num(params, "dy_mm", -limits.max_shift_mm, limits.max_shift_mm, default=0.0)
        if dx == 0 and dy == 0:
            raise AppError(422, "NO_CHANGE", "Lệnh không làm thay đổi gì.")
        each(lambda pts: [[x + dx, y + dy] for x, y in pts])
    elif op == "rotate":
        a = math.radians(_num(params, "degrees", -limits.max_rotate_deg, limits.max_rotate_deg))
        c, s = math.cos(a), math.sin(a)
        each(lambda pts: [[cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c] for x, y in pts])
    elif op == "scale":
        f = _num(params, "factor", *limits.scale_range)
        each(lambda pts: [[cx + (x - cx) * f, cy + (y - cy) * f] for x, y in pts])
    elif op == "slant":
        k = math.tan(math.radians(_num(params, "degrees", -limits.max_slant_deg, limits.max_slant_deg)))
        each(lambda pts: [[x - (y - cy) * k, y] for x, y in pts])          # positive = lean right (y grows downwards)
    elif op == "curvature":
        f = _num(params, "factor", *limits.curvature_range)
        each(lambda pts: _curvature(pts, f))
    elif op == "smooth":
        n = int(_num(params, "passes", 1, 5, default=1))
        each(lambda pts: _smooth(pts, n))
    elif op in ("extend", "trim"):
        mm = _num(params, "mm", 0.1, limits.max_extend_mm)
        end = _end(params)
        for st in sel:
            if op == "trim" and _length(st["points"]) - mm < MIN_STROKE_MM:
                raise AppError(422, "STROKE_TOO_SHORT", "Cắt như vậy thì nét không còn gì.", {"stroke_id": st["id"]})
        each(lambda pts: (_extend if op == "extend" else _trim)(pts, mm, end))
    elif op == "join":
        if len(sel) != 2:
            raise AppError(422, "INVALID_EDIT", "Nối nét cần chọn đúng 2 nét (theo thứ tự: nét trước, nét sau).")
        a, b = sel
        gap = math.dist(a["points"][-1], b["points"][0])
        if gap > limits.max_join_gap_mm:
            raise AppError(422, "JOIN_TOO_FAR", f"Hai đầu nét cách nhau {gap:.1f} mm, quá {limits.max_join_gap_mm:g} mm.",
                           {"gap_mm": round(gap, 2), "max_mm": limits.max_join_gap_mm})
        a["points"] = a["points"] + b["points"]
        page["strokes"].remove(b)
        removed.append(b["id"])
        sel = [a]
    elif op == "split":
        if len(sel) != 1:
            raise AppError(422, "INVALID_EDIT", "Tách nét cần chọn đúng 1 nét.")
        frac = _num(params, "at", 0.05, 0.95, default=0.5)
        first, second = _split_at(sel[0]["points"], frac)
        sel[0]["points"] = [[_r(x), _r(y)] for x, y in first]
        nid = f"s{new['next_id']}"
        new["next_id"] += 1
        twin = {**copy.deepcopy(sel[0]), "id": nid, "points": [[_r(x), _r(y)] for x, y in second]}
        page["strokes"].insert(page["strokes"].index(sel[0]) + 1, twin)
        added.append(nid)
        sel = [sel[0], twin]
    elif op == "delete":
        for st in sel:
            page["strokes"].remove(st)
            removed.append(st["id"])
        sel = []

    # validation of the result
    w, h = page["width_mm"], page["height_mm"]
    for st in sel:
        pts = st["points"]
        if len(pts) < 2 or _length(pts) < MIN_STROKE_MM:
            raise AppError(422, "STROKE_TOO_SHORT", "Nét sau khi sửa quá ngắn.", {"stroke_id": st["id"]})
        if any(not (EDGE_MM <= x <= w - EDGE_MM and EDGE_MM <= y <= h - EDGE_MM) for x, y in pts):
            raise AppError(422, "EDIT_OUTSIDE_PAPER", "Nét sau khi sửa ra ngoài mép giấy.", {"stroke_id": st["id"]})
        st["provenance"] = "EDITED"
        st["edits"] = int(st.get("edits") or 0) + 1
    if not any(st for p in new["pages"] for st in p["strokes"]):
        raise AppError(422, "NO_CONTENT", "Phác thảo không còn nét nào.")
    if sum(len(st["points"]) for p in new["pages"] for st in p["strokes"]) > tj.MAX_POINTS:
        raise AppError(422, "TOO_MANY_POINTS", "Phác thảo quá nhiều điểm.")
    _refresh_words(page)

    changed = sorted({st["id"] for st in sel} - set(added), key=lambda s: int(s[1:]))
    touched = set(changed) | set(added) | set(removed)
    after = {st["id"]: _stroke_digest(st) for p in new["pages"] for st in p["strokes"]}
    untouched_ok = all(after.get(i) == d for i, d in before.items() if i not in touched)
    if not untouched_ok:                                # a bug in an op, never the customer's fault
        raise AppError(500, "EDIT_SCOPE_VIOLATION", "Lệnh sửa làm đổi nét ngoài vùng chọn; đã huỷ.")
    moved = 0.0
    old_index = stroke_index(doc)
    for i in changed:
        op_pts = doc["pages"][old_index[i][0]]["strokes"][old_index[i][1]]["points"]
        np_pts = page["strokes"][[s["id"] for s in page["strokes"]].index(i)]["points"]
        if len(op_pts) == len(np_pts):
            moved = max(moved, max(math.dist(a, b) for a, b in zip(op_pts, np_pts)))
    report = {"op": op, "params": params, "page": page["no"], "changed": changed, "added": added, "removed": removed,
              "untouched_verified": True, "max_point_shift_mm": round(moved, 3), "limits": limits.name}
    return new, report


def _refresh_words(page: dict[str, Any]) -> None:
    by_word: dict[str, list[dict[str, Any]]] = {}
    for st in page["strokes"]:
        if st.get("word"):
            by_word.setdefault(st["word"], []).append(st)
    kept = []
    for w in page["words"]:
        sts = by_word.get(w["id"])
        if not sts:
            continue
        w["stroke_ids"] = [s["id"] for s in sts]
        w["bbox"] = _bbox([p for s in sts for p in s["points"]])
        kept.append(w)
    page["words"] = kept


def word_strokes(doc: dict[str, Any], word_ids: list[str]) -> list[str]:
    """Stroke ids of the selected words (region-level selection on the FE)."""
    out: list[str] = []
    found = set()
    for p in doc["pages"]:
        for w in p["words"]:
            if w["id"] in word_ids:
                out += w["stroke_ids"]
                found.add(w["id"])
    missing = [w for w in word_ids if w not in found]
    if missing:
        raise AppError(404, "WORD_NOT_FOUND", "Không tìm thấy từ đã chọn.", {"word_ids": missing})
    return out
