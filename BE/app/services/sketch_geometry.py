"""V2 canonical sketch geometry (`vhrs-sketch/2`) and the Geometry Engine (owner decisions D2, D3, D5, 2026-11-17).

The document
------------
    {"format": "vhrs-sketch/2", "engine": {...how it was built...}, "next_id": 57,
     "pages": [{"no": 1, "paper_size": "A4", "width_mm": 210, "height_mm": 297,
                "strokes": [{"id": "s1", "kind": "base", "points": [[x, y], ...], "word": "w1", "provenance": "ENGINE"}],
                "words":   [{"id": "w1", "stroke_ids": ["s1", "s2"], "bbox": [x0, y0, x1, y1],
                             "label": null, "confidence": null, "text": null}],
                "lines":   [{"id": "l1", "word_ids": ["w1"], "bbox": [...], "paragraph": "p1"}],          # Phase F
                "paragraphs": [{"id": "p1", "line_ids": ["l1"], "bbox": [...], "source": "TEXT"}]}]}

* Polylines in millimetres, origin top-left, y down: the same as `vhrs-trajectory/1` (D5: polyline is the canonical form;
  a curve edit works on the polyline, nothing stores Bezier control points). `to_pages()` gives the trajectory pages the
  rest of the system (preview, official sketch, motion planning, signed snapshot) already uses, in this exact stroke order.
* Ids are given once and never reused: an edit keeps the ids of the strokes it changes; a split gets a new id from
  `next_id`. A new generation (the customer changed the text or the images) keeps the ids of the words it draws again
  and of their strokes (Phase F `carry_ids`); everything else gets ids never used before.
* Words come from the engine: OT-3 strokes carry their word group (U7), OT-1 strokes belong to the U4 regions.
* `provenance`: ENGINE (text engine), RECOVERED (traced from the photo), INFERRED / RESTORED (U4 labels), CANVAS (the
  customer's drawing), EDITED (changed by an edit; `edits` counts them, `edited_by` lists who: CUSTOMER / AI / STAFF,
  V2 Phase H). Official sketch versions keep their document too (`sketches.document_uri`, migration 0025).

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
                   word_texts: list[str] | None = None, word_paragraphs: list[int] | None = None) -> dict[str, Any]:
    """Build the document from an engine run (`engine.Generated`). `regions` = U4 RegionDraft list (OT-1).

    `word_texts` (OT-3): the words of the order's text in reading order. The engine numbers each word's group in writing
    order, so sorting the groups gives the reading order; the words get their `text` only when the counts match exactly
    (otherwise none do: a wrong label is worse than none, the assistant then works from positions).
    `word_paragraphs` (OT-3): the paragraph of each of those words; the lines and paragraphs are built here (Phase F)."""
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
    para_of = None
    if word_texts is not None and reading and len(reading) == len(word_texts):
        ordered = [w for _, _, w in sorted(reading)]
        text_of = dict(zip(ordered, word_texts))
        for p in out_pages:
            for w in p["words"]:
                w["text"] = text_of.get(w["id"])
        if word_paragraphs is not None and len(word_paragraphs) == len(ordered):
            para_of = dict(zip(ordered, word_paragraphs))
    doc = {"format": FORMAT, "engine": engine_info, "pages": out_pages, "next_id": n + 1}
    return build_structure(doc, para_of)


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
    _refresh_structure(page)

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
    report["affected"] = affected(doc, new, report)
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


EDITORS = ("CUSTOMER", "AI", "STAFF")


def mark_edit(doc: dict[str, Any], report: dict[str, Any], author: str) -> None:
    """V2 Phase H: remember WHO changed each stroke (`edited_by`, in order, no repeats), so the Staff editor can show the
    strokes the customer / the assistant changed in v1 (D2). Metadata only: `geometry_hash` covers kind + points."""
    if author not in EDITORS:
        return
    touched = set(report.get("changed") or []) | set(report.get("added") or [])
    for p in doc["pages"]:
        for st in p["strokes"]:
            if st["id"] in touched:
                who = list(st.get("edited_by") or [])
                if author not in who:
                    who.append(author)
                st["edited_by"] = who


def edit_summary(doc: dict[str, Any]) -> dict[str, int]:
    """{"strokes": n, "edited": n, "CUSTOMER": n, "AI": n, "STAFF": n}: strokes changed by each editor."""
    out = {"strokes": 0, "edited": 0, **{k: 0 for k in EDITORS}}
    for p in doc["pages"]:
        for st in p["strokes"]:
            out["strokes"] += 1
            who = st.get("edited_by") or []
            if who or st.get("provenance") == "EDITED":
                out["edited"] += 1
            for k in who:
                if k in out:
                    out[k] += 1
    return out


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


# ---------------------------------------------------------------------------------------------------- V2 Phase F
# Lines and paragraphs (F1), ids kept across a redraw (F2), whole-word edits re-applied after a redraw (F3) and what an edit
# touched (F4). Owner decisions 2026-11-19: lines and paragraphs only (no glyph ids); ids kept for OT-3 and OT-1; only
# translate / rotate / scale / slant on whole words come back after a redraw.
#
# Each page gets  "lines": [{"id": "l1", "word_ids": [...], "bbox": [...], "paragraph": "p1"}]
#           and   "paragraphs": [{"id": "p1", "line_ids": [...], "bbox": [...], "source": "TEXT" | "LAYOUT"}]
# Lines come from the word boxes with the reading-order line finder measured on real handwriting in E2a
# (`htr_align.units_of`), for both order types. Paragraphs: OT-3 from the order's text (a new line in the text = a new
# paragraph, "TEXT"); otherwise from the layout ("LAYOUT": a gap well above the line pitch, or a clear indent), a guess.
# Membership is decided when the document is built; an edit that moves a word keeps it in its line.
REAPPLY_OPS = ("translate", "rotate", "scale", "slant")
IOU_MATCH = 0.5


def _num_id(i: str) -> int:
    try:
        return int(i[1:])
    except (ValueError, TypeError):
        return 0


def _merge(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _structure_page(page: dict[str, Any], para_of: dict[str, int] | None, next_line: int, next_para: int) -> tuple[int, int]:
    from types import SimpleNamespace

    from app.services.stroke_ai.htr_align import units_of
    words = [w for w in page["words"] if w.get("bbox")]
    regs = [SimpleNamespace(region_no=k, bbox=tuple(w["bbox"]), wid=w["id"]) for k, w in enumerate(words)]
    by_no = {r.region_no: r.wid for r in regs}
    lines: list[list[str]] = []
    last = None
    for u in units_of(regs):
        if u.line != last:
            lines.append([])
            last = u.line
        lines[-1] += [by_no[n] for n in u.regions]
    wb = {w["id"]: w["bbox"] for w in words}
    boxes = [_merge([wb[i] for i in ids]) for ids in lines]
    if para_of and all(i in para_of for ids in lines for i in ids):
        source = "TEXT"
        pidx = [para_of[ids[0]] for ids in lines]
    else:
        source = "LAYOUT"
        pidx = [0] * len(lines)
        if len(lines) > 1:
            cys = [(b[1] + b[3]) / 2 for b in boxes]
            gaps = [cys[i + 1] - cys[i] for i in range(len(cys) - 1)]
            pitch = sorted(gaps)[len(gaps) // 2]
            hs = sorted(wb[i][3] - wb[i][1] for ids in lines for i in ids)
            h = hs[len(hs) // 2]
            x0s = sorted(b[0] for b in boxes)
            margin = x0s[len(x0s) // 4]
            for i in range(1, len(lines)):
                new = gaps[i - 1] > 1.6 * pitch or boxes[i][0] - margin > 2.5 * h
                pidx[i] = pidx[i - 1] + (1 if new else 0)
    page["lines"], page["paragraphs"] = [], []
    for k, ids in enumerate(lines):
        if k == 0 or pidx[k] != pidx[k - 1]:
            page["paragraphs"].append({"id": f"p{next_para}", "line_ids": [], "bbox": None, "source": source})
            next_para += 1
        para = page["paragraphs"][-1]
        lid = f"l{next_line}"
        next_line += 1
        page["lines"].append({"id": lid, "word_ids": ids, "bbox": None, "paragraph": para["id"]})
        para["line_ids"].append(lid)
    _refresh_structure(page)
    return next_line, next_para


def build_structure(doc: dict[str, Any], word_paragraphs: dict[str, int] | None = None) -> dict[str, Any]:
    """(Re)build the lines and paragraphs of every page (ids from 1). In place; returns the document."""
    nl = npar = 1
    for p in doc["pages"]:
        nl, npar = _structure_page(p, word_paragraphs, nl, npar)
    return doc


def ensure_structure(doc: dict[str, Any]) -> dict[str, Any]:
    """Documents written before Phase F have no lines: build them from the layout (the strokes do not change)."""
    if any("lines" not in p for p in doc["pages"]):
        build_structure(doc)
    return doc


def _refresh_structure(page: dict[str, Any]) -> None:
    """After an edit: drop words that are gone, recompute the boxes; a line / paragraph left empty goes."""
    if "lines" not in page:
        return
    wb = {w["id"]: w["bbox"] for w in page["words"]}
    lines = []
    for ln in page["lines"]:
        ln["word_ids"] = [i for i in ln["word_ids"] if i in wb]
        if ln["word_ids"]:
            ln["bbox"] = [_r(v) for v in _merge([wb[i] for i in ln["word_ids"]])]
            lines.append(ln)
    page["lines"] = lines
    lb = {ln["id"]: ln["bbox"] for ln in lines}
    paras = []
    for pa in page.get("paragraphs") or []:
        pa["line_ids"] = [i for i in pa["line_ids"] if i in lb]
        if pa["line_ids"]:
            pa["bbox"] = _merge([lb[i] for i in pa["line_ids"]])
            paras.append(pa)
    page["paragraphs"] = paras


def group_strokes(doc: dict[str, Any], word_ids: list[str] | None = None, line_ids: list[str] | None = None,
                  paragraph_ids: list[str] | None = None) -> list[str]:
    """Stroke ids of whole words / lines / paragraphs (the FE's and the assistant's region-level selection)."""
    words = list(word_ids or [])
    if line_ids or paragraph_ids:
        lines = {ln["id"]: ln for p in doc["pages"] for ln in p.get("lines") or []}
        paras = {pa["id"]: pa for p in doc["pages"] for pa in p.get("paragraphs") or []}
        missing = [i for i in paragraph_ids or [] if i not in paras]
        if missing:
            raise AppError(404, "PARAGRAPH_NOT_FOUND", "Không tìm thấy đoạn đã chọn.", {"paragraph_ids": missing})
        lids = list(line_ids or []) + [i for pid in paragraph_ids or [] for i in paras[pid]["line_ids"]]
        missing = [i for i in lids if i not in lines]
        if missing:
            raise AppError(404, "LINE_NOT_FOUND", "Không tìm thấy dòng đã chọn.", {"line_ids": missing})
        words += [w for lid in lids for w in lines[lid]["word_ids"]]
    words = list(dict.fromkeys(words))
    return list(dict.fromkeys(word_strokes(doc, words))) if words else []


def affected(before: dict[str, Any], after: dict[str, Any], report: dict[str, Any]) -> dict[str, list[str]]:
    """F4: the strokes an edit touched, the words they belong to and the lines of those words (before or after)."""
    strokes = set(report.get("changed") or []) | set(report.get("added") or []) | set(report.get("removed") or [])
    words: set[str] = set()
    lines: set[str] = set()
    for doc in (before, after):
        for p in doc["pages"]:
            hit = {w["id"] for w in p["words"] if strokes & set(w["stroke_ids"])}
            hit |= {st["word"] for st in p["strokes"] if st["id"] in strokes and st.get("word")}
            words |= hit
            lines |= {ln["id"] for ln in p.get("lines") or [] if hit & set(ln["word_ids"])}
    return {k: sorted(v, key=_num_id) for k, v in (("strokes", strokes), ("words", words), ("lines", lines))}


def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _reading_words(doc: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """(page index, word) in reading order: line by line, then any word outside a line."""
    out = []
    for pi, p in enumerate(doc["pages"]):
        wmap = {w["id"]: w for w in p["words"]}
        seen: set[str] = set()
        for ln in p.get("lines") or []:
            for i in ln["word_ids"]:
                if i in wmap and i not in seen:
                    out.append((pi, wmap[i]))
                    seen.add(i)
        out += [(pi, w) for w in p["words"] if w["id"] not in seen]
    return out


def carry_ids(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """F2: give a fresh drawing the ids of the previous one where it draws the same word. In place on `new`.

    Words are matched by their text when both drawings have it (OT-3; difflib over the words in reading order, so a word
    added or removed upstream does not shift the rest), else by position (OT-1: same page, box overlap IoU >= 0.5, best
    first). A matched word keeps its id, and its strokes keep theirs when the count is the same; lines and paragraphs keep
    the id most of their words had. Everything else gets ids above any id the previous drawing used (never reused)."""
    import difflib
    ow, nw = _reading_words(old), _reading_words(new)
    by_text = bool(ow and nw and all(w.get("text") for _, w in ow + nw))
    match: dict[str, str] = {}                        # new word id -> old word id
    if by_text:
        sm = difflib.SequenceMatcher(None, [w["text"] for _, w in ow], [w["text"] for _, w in nw], autojunk=False)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                match[nw[blk.b + k][1]["id"]] = ow[blk.a + k][1]["id"]
    else:
        pairs = sorted(((_iou(a["bbox"], b["bbox"]), b["id"], a["id"]) for pa, a in ow for pb, b in nw
                        if pa == pb and a.get("bbox") and b.get("bbox")), reverse=True)
        used_o: set[str] = set()
        for iou, nid, oid in pairs:
            if iou < IOU_MATCH:
                break
            if nid not in match and oid not in used_o:
                match[nid] = oid
                used_o.add(oid)
    o_words = {w["id"]: w for _, w in ow}

    def top(key: str) -> int:
        return max([_num_id(x["id"]) for p in old["pages"] for x in p.get(key) or []] + [0])

    nxt = {"w": top("words") + 1, "l": top("lines") + 1, "p": top("paragraphs") + 1,
           "s": max(int(old.get("next_id") or 1), top("strokes") + 1)}

    def fresh(pfx: str) -> str:
        v = f"{pfx}{nxt[pfx]}"
        nxt[pfx] += 1
        return v

    wren: dict[str, str] = {}
    sren: dict[str, str] = {}
    for _, w in nw:
        oid = match.get(w["id"])
        wren[w["id"]] = oid if oid else fresh("w")
        if oid and len(o_words[oid]["stroke_ids"]) == len(w["stroke_ids"]):
            sren.update(zip(w["stroke_ids"], o_words[oid]["stroke_ids"]))
    for p in new["pages"]:
        for st in p["strokes"]:
            st["id"] = sren.get(st["id"]) or fresh("s")
            if st.get("word"):
                st["word"] = wren.get(st["word"], st["word"])
        for w in p["words"]:
            w["id"] = wren[w["id"]]
            w["stroke_ids"] = [st["id"] for st in p["strokes"] if st.get("word") == w["id"]]
    o_line_of = {i: ln["id"] for p in old["pages"] for ln in p.get("lines") or [] for i in ln["word_ids"]}
    o_para_of = {ln["id"]: ln.get("paragraph") for p in old["pages"] for ln in p.get("lines") or []}
    used_l: set[str] = set()
    used_p: set[str] = set()
    for p in new["pages"]:
        lren: dict[str, str] = {}
        for ln in p.get("lines") or []:
            ln["word_ids"] = [wren.get(i, i) for i in ln["word_ids"]]
            votes = [o_line_of[i] for i in ln["word_ids"] if i in o_line_of]
            best = max(sorted(set(votes)), key=votes.count) if votes else None
            lren[ln["id"]] = best if best and best not in used_l else fresh("l")
            used_l.add(lren[ln["id"]])
        pren: dict[str, str] = {}
        for pa in p.get("paragraphs") or []:
            votes = [o_para_of[lren[i]] for i in pa["line_ids"] if o_para_of.get(lren[i])]
            best = max(sorted(set(votes)), key=votes.count) if votes else None
            pren[pa["id"]] = best if best and best not in used_p else fresh("p")
            used_p.add(pren[pa["id"]])
            pa["id"] = pren[pa["id"]]
            pa["line_ids"] = [lren[i] for i in pa["line_ids"]]
        for ln in p.get("lines") or []:
            ln["id"] = lren[ln["id"]]
            ln["paragraph"] = pren.get(ln.get("paragraph"), ln.get("paragraph"))
    new["next_id"] = nxt["s"]
    kept = len(match)
    return {"matched_by": "TEXT" if by_text else "POSITION", "words_kept": kept, "words_new": len(nw) - kept,
            "words_gone": len(o_words) - kept, "strokes_kept": len(sren)}


def reapply(doc: dict[str, Any], operations: list[dict[str, Any]], limits: Limits) -> tuple[dict[str, Any], dict[str, Any]]:
    """F3: run the earlier edits again on a fresh drawing (oldest first). Only translate / rotate / scale / slant chosen as
    whole words, lines or paragraphs come back, and only when every word of the selection is still there (same id, F2);
    each is the same Geometry Engine edit with the same checks. Returns (document, {"reapplied": [...], "dropped": [...]})."""
    reapplied, dropped = [], []
    for o in operations:
        item = {k: o.get(k) for k in ("op", "word_ids", "line_ids", "paragraph_ids", "params", "author")}
        if o.get("op") not in REAPPLY_OPS:
            dropped.append({**item, "reason": "OP_NOT_REAPPLIED"})
            continue
        if o.get("stroke_ids") or not (o.get("word_ids") or o.get("line_ids") or o.get("paragraph_ids")):
            dropped.append({**item, "reason": "NOT_WHOLE_WORDS"})
            continue
        try:
            ids = group_strokes(doc, o.get("word_ids"), o.get("line_ids"), o.get("paragraph_ids"))
            doc, rep = apply(doc, o["op"], ids, o.get("params"), limits)
        except AppError as exc:
            dropped.append({**item, "reason": "GONE" if exc.code.endswith("_NOT_FOUND") else exc.code})
            continue
        mark_edit(doc, rep, o.get("author") or "CUSTOMER")
        reapplied.append(item)
    return doc, {"reapplied": reapplied, "dropped": dropped}


def reapplicable(operation: dict[str, Any] | None) -> bool:
    o = operation or {}
    return (o.get("op") in REAPPLY_OPS and not o.get("stroke_ids")
            and bool(o.get("word_ids") or o.get("line_ids") or o.get("paragraph_ids")))
