"""Upgrade U2 (rest): compare two versions of an order's sketch.

What changed between version A ("from") and version B ("to"):
  - the metrics the customer / Staff care about (pages, writing time, stroke length, pen lifts) and their delta;
  - per page, which strokes were kept, added or removed. A stroke is compared by its exact points (the trajectory file
    stores them rounded to 0.01 mm), so a stroke that moved by any amount counts as removed + added. That is the honest
    answer for a robot plan: the pen will not follow the old path;
  - per page, an overlay JPEG: kept strokes grey, removed red, added blue, with the visible AI mark (U2) like every
    customer-facing image;
  - for an OT-1 sketch, the regions (U4) whose label, text or strokes changed.

It reads the two immutable trajectory files; nothing is written to the DB.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.sketch import Sketch, SketchRegion
from app.services.stroke_ai import trajectory as tj, watermark

PX_PER_MM = 2.0
KEPT, REMOVED, ADDED = (175, 175, 175), (40, 40, 220), (200, 110, 20)     # BGR: grey, red, blue


@dataclass
class _Side:
    row: Sketch
    pages: list[tj.Page]
    regions: list[SketchRegion]


def _load(store: ObjectStorage, row: Sketch, regions: list[SketchRegion]) -> _Side:
    raw = store.read(row.trajectory_uri)
    if raw is None:
        raise AppError(409, "FILE_MISSING", "Không đọc được file quỹ đạo từ kho lưu trữ.")
    return _Side(row, tj.parse(json.loads(raw)), regions)


def _key(s: tj.Stroke) -> tuple:
    return tuple(s.points)


def _page_diff(a: tj.Page | None, b: tj.Page | None) -> tuple[list[tj.Stroke], list[tj.Stroke], list[tj.Stroke]]:
    """(kept, removed, added) strokes; duplicates are matched one for one."""
    left = Counter(_key(s) for s in a.strokes) if a else Counter()
    kept, added = [], []
    for s in (b.strokes if b else []):
        k = _key(s)
        if left[k] > 0:
            left[k] -= 1
            kept.append(s)
        else:
            added.append(s)
    removed = []
    for s in (a.strokes if a else []):
        k = _key(s)
        if left[k] > 0:
            left[k] -= 1
            removed.append(s)
    return kept, removed, added


def overlay_jpeg(page: tj.Page, kept: list[tj.Stroke], removed: list[tj.Stroke], added: list[tj.Stroke],
                 order_code: str | None) -> bytes:
    w, h = int(round(page.width_mm * PX_PER_MM)), int(round(page.height_mm * PX_PER_MM))
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (200, 200, 200), 1)
    for strokes, color, thick in ((kept, KEPT, 1), (removed, REMOVED, 2), (added, ADDED, 2)):
        for s in strokes:
            pts = np.round(np.array([[x * PX_PER_MM, y * PX_PER_MM] for x, y in s.points], np.float32)).astype(np.int32)
            cv2.polylines(img, [pts], False, color, thick, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:  # pragma: no cover - imencode only fails on invalid input
        raise AppError(500, "PREVIEW_FAILED", "Không tạo được ảnh so sánh.")
    return watermark.apply_bytes(buf.tobytes(), order_code, fmt="jpg")


def _metric(a: Any, b: Any) -> dict[str, Any]:
    fa = float(a) if a is not None else None
    fb = float(b) if b is not None else None
    delta = round(fb - fa, 2) if fa is not None and fb is not None else None
    if delta is not None and delta == int(delta):
        delta = int(delta)
    return {"from": a, "to": b, "delta": delta}


def _region_changes(a: list[SketchRegion], b: list[SketchRegion]) -> list[dict[str, Any]]:
    """Regions matched by (page, region number): numbers are stable across region edits (U4)."""
    left = {(r.page_no, r.region_no): r for r in a}
    right = {(r.page_no, r.region_no): r for r in b}
    out = []
    for key in sorted(set(left) | set(right)):
        ra, rb = left.get(key), right.get(key)
        if ra is None or rb is None:
            r = rb or ra
            out.append({"page_no": key[0], "region_no": key[1], "change": "ADDED" if ra is None else "REMOVED",
                        "from_label": ra.label if ra else None, "to_label": rb.label if rb else None,
                        "text": r.text, "note": rb.note if rb else None})
            continue
        if ra.label != rb.label:
            change = "LABEL_CHANGED"
        elif (ra.text or None) != (rb.text or None) or (rb.stroke_end - rb.stroke_start) != (ra.stroke_end - ra.stroke_start) \
                or (rb.source, rb.note) != (ra.source, ra.note):
            change = "EDITED"
        else:
            continue
        out.append({"page_no": key[0], "region_no": key[1], "change": change, "from_label": ra.label,
                    "to_label": rb.label, "text": rb.text, "note": rb.note})
    return out


def compare(store: ObjectStorage, a: Sketch, b: Sketch, regions_a: list[SketchRegion], regions_b: list[SketchRegion], *,
            order_id: int, order_code: str | None, images: bool = True) -> dict[str, Any]:
    if a.id == b.id:
        raise AppError(422, "SAME_VERSION", "Hãy chọn hai phiên bản khác nhau để so sánh.")
    sa, sb = _load(store, a, regions_a), _load(store, b, regions_b)
    pages = []
    for n in range(1, max(len(sa.pages), len(sb.pages)) + 1):
        pa = sa.pages[n - 1] if n <= len(sa.pages) else None
        pb = sb.pages[n - 1] if n <= len(sb.pages) else None
        kept, removed, added = _page_diff(pa, pb)
        entry: dict[str, Any] = {"page_no": n, "in_from": pa is not None, "in_to": pb is not None, "kept": len(kept),
                                 "removed": len(removed), "added": len(added), "changed": bool(removed or added),
                                 "image_url": None}
        if images and entry["changed"]:
            path = f"orders/{order_id}/sketches/compare_v{a.version}_v{b.version}_p{n}.jpg"
            store.write(path, overlay_jpeg(pb or pa, kept, removed, added, order_code), "image/jpeg")
            entry["image_url"] = store.create_download_url(path, 600)
        pages.append(entry)
    return {
        "from_version": a.version, "to_version": b.version, "from_sketch_id": a.id, "to_sketch_id": b.id,
        "identical": a.content_hash is not None and a.content_hash == b.content_hash,
        "metrics": {"pages": _metric(len(sa.pages), len(sb.pages)),
                    "estimated_writing_sec": _metric(a.estimated_writing_sec, b.estimated_writing_sec),
                    "total_stroke_mm": _metric(a.total_stroke_mm, b.total_stroke_mm),
                    "pen_lift_count": _metric(a.pen_lift_count, b.pen_lift_count)},
        "pages": pages,
        "regions": _region_changes(regions_a, regions_b),
        "legend": {"kept": "xám", "removed": "đỏ", "added": "xanh dương"},
    }
