"""Stroke recovery from a photo/scan of handwriting (OT-1, FR-33, FR-34).

Classic computer vision, no learned model:
  1. illumination flattening + Otsu binarisation, small-angle deskew, speckle removal
  2. Zhang-Suen thinning (the skeletonisation named in the project proposal)
  3. skeleton -> pixel graph -> edges between end/junction pixels, short spurs pruned
  4. at every junction edges are paired by direction continuity, so a pen path runs straight through
  5. polylines smoothed + simplified; start point chosen left-to-right (top-to-bottom for verticals)
  6. strokes ordered in reading order (lines -> words), small marks (tone marks, dots) written after
     the word they belong to, as the SRS asks for Vietnamese diacritics (S4)
  7. fitted onto the paper; similarity = IoU between the original ink and the recovered strokes redrawn
     at the measured pen width.

Limits (not validated on a Vietnamese handwriting test set yet; NFR-02 needs that benchmark):
the stroke ORDER and DIRECTION are heuristics (Doermann & Rosenfeld style), overlapping strokes and
heavy cursive loops can be traced in a different order than the writer used, and the similarity is a
pixel IoU, not the stroke-aligned IoU against ground-truth pen trajectories.
"""
import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError
from app.services.handwriting_image import _apply_orientation
from app.services.stroke_ai.trajectory import PAPER_MM, Page, Stroke

MAX_SIDE_PX = 1600
MAX_STROKES = 4000
_NEIGH = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class RecoveryStats:
    similarity: float                 # 0..100, pixel IoU of ink vs redrawn strokes
    n_strokes: int
    mm_per_px: float
    stroke_width_mm: float
    deskew_deg: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# 1. preprocessing
# ---------------------------------------------------------------------------------------------
def _binarise(gray: np.ndarray) -> np.ndarray:
    k = max(15, (min(gray.shape) // 30) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    flat = cv2.divide(gray, np.maximum(background, 1), scale=255)           # flatten uneven light / yellowed paper
    flat = cv2.GaussianBlur(flat, (3, 3), 0)
    _, ink = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return ink


def _deskew(ink: np.ndarray) -> tuple[np.ndarray, float]:
    """Rotate by the angle in [-5, 5] deg that makes text lines most horizontal (projection profile)."""
    small = cv2.resize(ink, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) if max(ink.shape) > 800 else ink
    h, w = small.shape
    centre = (w / 2, h / 2)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rot = cv2.warpAffine(small, m, (w, h), flags=cv2.INTER_NEAREST)
        return float(np.var(rot.sum(axis=1, dtype=np.float64)))

    base = score(0.0)
    best, best_angle = base, 0.0
    for a in np.arange(-5.0, 5.01, 0.5):
        s = score(float(a))
        if s > best:
            best, best_angle = s, float(a)
    if best_angle == 0.0 or best < base * 1.05:
        return ink, 0.0
    hh, ww = ink.shape
    m = cv2.getRotationMatrix2D((ww / 2, hh / 2), best_angle, 1.0)
    return cv2.warpAffine(ink, m, (ww, hh), flags=cv2.INTER_NEAREST), best_angle


def _remove_specks(ink: np.ndarray) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    h, w = ink.shape
    keep = np.zeros(n, bool)
    min_area = max(6, int(0.000012 * h * w))
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        keep[i] = min_area <= a <= 0.3 * h * w
    return (keep[lab] * 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------
# 2. Zhang-Suen thinning (vectorised)
# ---------------------------------------------------------------------------------------------
def zhang_suen(ink: np.ndarray) -> np.ndarray:
    img = np.pad((ink > 0).astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p = img
            p2, p3, p4, p5 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:]
            p6, p7, p8, p9 = p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2]
            centre = p[1:-1, 1:-1]
            b = (p2.astype(np.int16) + p3 + p4 + p5 + p6 + p7 + p8 + p9)
            seq = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            a = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int16) for i in range(8))
            if step == 0:
                cond = ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                cond = ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
            mask = (centre == 1) & (b >= 2) & (b <= 6) & (a == 1) & cond
            if mask.any():
                centre[mask] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def _drop_corner_pixels(sk: np.ndarray) -> np.ndarray:
    """Remove L-shaped redundant pixels left by thinning so that chains are 1 pixel wide (deg 2)."""
    pad = np.pad(sk.astype(np.uint8), 1)
    for _ in range(3):
        n8 = sum(np.roll(np.roll(pad, dy, 0), dx, 1) for dy, dx in _NEIGH)
        cand = np.argwhere((pad == 1) & (n8 == 2))
        removed = False
        for y, x in cand:
            if pad[y, x] != 1:
                continue
            n, s, w, e = pad[y - 1, x], pad[y + 1, x], pad[y, x - 1], pad[y, x + 1]
            diag = pad[y - 1, x - 1] + pad[y - 1, x + 1] + pad[y + 1, x - 1] + pad[y + 1, x + 1]
            total = int(n + s + w + e + diag)
            if total == 2 and int(n + s + w + e) == 2 and not (n and s) and not (w and e):
                pad[y, x] = 0
                removed = True
        if not removed:
            break
    return pad[1:-1, 1:-1].astype(bool)


# ---------------------------------------------------------------------------------------------
# 3-4. skeleton -> graph -> strokes
# ---------------------------------------------------------------------------------------------
@dataclass
class _Edge:
    pts: np.ndarray              # (n, 2) float x, y; first/last are node centroids when the edge has nodes
    a: int | None                # node cluster at the start (None for a closed loop)
    b: int | None


def _graph(sk: np.ndarray) -> tuple[list[_Edge], dict[int, list[tuple[int, int]]], list[np.ndarray]]:
    ys, xs = np.nonzero(sk)
    n = len(ys)
    idmap = -np.ones((sk.shape[0] + 2, sk.shape[1] + 2), np.int32)
    idmap[ys + 1, xs + 1] = np.arange(n, dtype=np.int32)
    adj: list[list[int]] = [[] for _ in range(n)]
    for dy, dx in _NEIGH:
        nb = idmap[ys + 1 + dy, xs + 1 + dx]
        ok = nb >= 0
        for i, j in zip(np.nonzero(ok)[0].tolist(), nb[ok].tolist()):
            adj[i].append(j)
    deg = np.array([len(a) for a in adj])
    coord = np.stack([xs, ys], axis=1).astype(np.float64)
    is_node = deg != 2

    # cluster adjacent node pixels (junction blobs) into one node
    cluster = -np.ones(n, np.int32)
    centroids: list[np.ndarray] = []
    for s in np.nonzero(is_node)[0].tolist():
        if cluster[s] >= 0:
            continue
        cid = len(centroids)
        stack, members = [s], []
        cluster[s] = cid
        while stack:
            u = stack.pop()
            members.append(u)
            for v in adj[u]:
                if is_node[v] and cluster[v] < 0:
                    cluster[v] = cid
                    stack.append(v)
        centroids.append(coord[members].mean(axis=0))

    visited = np.zeros(n, bool)
    edges: list[_Edge] = []
    for u in np.nonzero(is_node)[0].tolist():
        for v in adj[u]:
            if is_node[v] or visited[v]:
                continue
            chain, prev, cur = [v], u, v
            visited[v] = True
            end_cluster = None
            while True:
                nxt = [w for w in adj[cur] if w != prev]
                if not nxt:
                    break
                w = nxt[0]
                if is_node[w]:
                    end_cluster = int(cluster[w])
                    break
                if visited[w]:
                    break
                visited[w] = True
                chain.append(w)
                prev, cur = cur, w
            a = int(cluster[u])
            pts = [centroids[a]] + [coord[i] for i in chain] + ([centroids[end_cluster]] if end_cluster is not None else [])
            edges.append(_Edge(np.array(pts), a, end_cluster))

    closed: list[np.ndarray] = []                     # isolated loops, dots
    for s in range(n):
        if visited[s] or is_node[s]:
            continue
        chain, prev, cur = [s], -1, s
        visited[s] = True
        while True:
            nxt = [w for w in adj[cur] if w != prev and not visited[w]]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            visited[cur] = True
            chain.append(cur)
        closed.append(coord[chain])
    for u in np.nonzero(is_node & (deg == 0))[0].tolist():     # isolated pixel = a dot
        x, y = coord[u]
        closed.append(np.array([[x - 0.6, y], [x + 0.6, y]]))

    ends: dict[int, list[tuple[int, int]]] = {}
    for i, e in enumerate(edges):
        if e.a is not None:
            ends.setdefault(e.a, []).append((i, 0))
        if e.b is not None:
            ends.setdefault(e.b, []).append((i, 1))
    return edges, ends, closed


def _edge_len(e: _Edge) -> float:
    return float(np.sum(np.linalg.norm(np.diff(e.pts, axis=0), axis=1))) if len(e.pts) > 1 else 0.0


def _prune_spurs(edges: list[_Edge], ends: dict[int, list[tuple[int, int]]], max_len: float) -> set[int]:
    removed: set[int] = set()
    for _ in range(2):
        changed = False
        for i, e in enumerate(edges):
            if i in removed or e.a is None or e.b is None or e.a == e.b:
                continue
            da = sum(1 for j, _ in ends[e.a] if j not in removed)
            db = sum(1 for j, _ in ends[e.b] if j not in removed)
            if ((da == 1 and db >= 3) or (db == 1 and da >= 3)) and _edge_len(e) < max_len:
                removed.add(i)
                changed = True
        if not changed:
            break
    return removed


def _outgoing(e: _Edge, end: int, k: int = 10) -> np.ndarray:
    pts = e.pts if end == 0 else e.pts[::-1]
    j = min(k, len(pts) - 1)
    v = pts[j] - pts[0]
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 1e-9 else v


def _pair_edges(edges, ends, removed) -> dict[tuple[int, int], tuple[int, int]]:
    pair: dict[tuple[int, int], tuple[int, int]] = {}
    for node, lst in ends.items():
        live = [(i, end) for i, end in lst if i not in removed]
        if len(live) < 2:
            continue
        vecs = {x: _outgoing(edges[x[0]], x[1]) for x in live}
        cands = []
        for ai in range(len(live)):
            for bi in range(ai + 1, len(live)):
                a, b = live[ai], live[bi]
                if a[0] == b[0]:
                    continue
                cos = float(np.clip(np.dot(vecs[a], vecs[b]), -1, 1))
                cands.append((math.degrees(math.acos(cos)), a, b))
        cands.sort(key=lambda t: -t[0])
        used: set[tuple[int, int]] = set()
        for angle, a, b in cands:
            if a in used or b in used:
                continue
            if len(live) == 2 or angle >= 120.0:      # straight enough (turn <= 60 deg), or no choice
                pair[a], pair[b] = b, a
                used.update((a, b))
    return pair


def _assemble(edges, pair, removed) -> list[np.ndarray]:
    seen: set[int] = set()
    strokes: list[np.ndarray] = []
    for i in range(len(edges)):
        if i in removed or i in seen:
            continue
        seen.add(i)
        forward = [edges[i].pts]
        nxt = pair.get((i, 1))
        while nxt and nxt[0] not in seen:
            j, end = nxt
            seen.add(j)
            forward.append(edges[j].pts if end == 0 else edges[j].pts[::-1])
            nxt = pair.get((j, 1 - end))
        backward = []
        prv = pair.get((i, 0))
        while prv and prv[0] not in seen:
            j, end = prv
            seen.add(j)
            backward.append(edges[j].pts[::-1] if end == 0 else edges[j].pts)
            prv = pair.get((j, 1 - end))
        parts = backward[::-1] + forward
        merged = [parts[0]]
        for p in parts[1:]:
            merged.append(p[1:] if np.allclose(merged[-1][-1], p[0], atol=1e-6) else p)
        strokes.append(np.concatenate(merged))
    return strokes


# ---------------------------------------------------------------------------------------------
# 5. polish
# ---------------------------------------------------------------------------------------------
def _smooth(pts: np.ndarray, window: int = 5) -> np.ndarray:
    if len(pts) < window + 2:
        return pts
    k = window // 2
    padded = np.concatenate([np.repeat(pts[:1], k, 0), pts, np.repeat(pts[-1:], k, 0)])
    kernel = np.ones(window) / window
    out = np.stack([np.convolve(padded[:, c], kernel, mode="valid") for c in range(2)], axis=1)
    out[0], out[-1] = pts[0], pts[-1]
    return out


def _simplify(pts: np.ndarray, eps: float) -> np.ndarray:
    if len(pts) < 3:
        return pts
    approx = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps, False).reshape(-1, 2)
    return approx.astype(np.float64) if len(approx) >= 2 else pts


def _orient(pts: np.ndarray) -> np.ndarray:
    dx, dy = pts[-1, 0] - pts[0, 0], pts[-1, 1] - pts[0, 1]
    if abs(dx) < 0.3 * abs(dy):
        flip = dy < 0
    else:
        flip = dx < 0
    return pts[::-1] if flip else pts


# ---------------------------------------------------------------------------------------------
# 6. reading order
# ---------------------------------------------------------------------------------------------
def _reading_order(strokes: list[np.ndarray], comp_of: list[int]) -> list[tuple[int, str]]:
    """Return [(stroke index, kind)] in writing order; kind is 'base' or 'mark'."""
    comps: dict[int, list[int]] = {}
    for i, c in enumerate(comp_of):
        comps.setdefault(c, []).append(i)
    boxes: dict[int, tuple[float, float, float, float]] = {}
    for c, idx in comps.items():
        allp = np.concatenate([strokes[i] for i in idx])
        boxes[c] = (allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max())
    heights = sorted(b[3] - b[1] for b in boxes.values())
    ref_h = max(heights[int(0.75 * (len(heights) - 1))], 4.0)
    is_base = {c: (b[3] - b[1]) >= 0.35 * ref_h or (b[2] - b[0]) >= 0.8 * ref_h for c, b in boxes.items()}
    if not any(is_base.values()):
        is_base = {c: True for c in boxes}

    bases = sorted((c for c in boxes if is_base[c]), key=lambda c: (boxes[c][1] + boxes[c][3]) / 2)
    lines: list[list[int]] = []
    line_cy: list[float] = []
    for c in bases:
        cy = (boxes[c][1] + boxes[c][3]) / 2
        for li, ly in enumerate(line_cy):
            if abs(cy - ly) < 0.6 * ref_h:
                lines[li].append(c)
                line_cy[li] = (ly * (len(lines[li]) - 1) + cy) / len(lines[li])
                break
        else:
            lines.append([c])
            line_cy.append(cy)
    words: list[list[int]] = []
    for li in sorted(range(len(lines)), key=lambda i: line_cy[i]):
        cur: list[int] = []
        right = -1e9
        for c in sorted(lines[li], key=lambda c: boxes[c][0]):
            if cur and boxes[c][0] - right > 0.45 * ref_h:
                words.append(cur)
                cur = []
            cur.append(c)
            right = max(right, boxes[c][2])
        if cur:
            words.append(cur)

    word_marks: dict[int, list[int]] = {wi: [] for wi in range(len(words))}
    owner = {c: wi for wi, w in enumerate(words) for c in w}
    for c in boxes:
        if is_base[c]:
            continue
        mx, my = (boxes[c][0] + boxes[c][2]) / 2, (boxes[c][1] + boxes[c][3]) / 2

        def dist(b: int) -> float:
            x0, y0, x1, y1 = boxes[b]
            dx = max(x0 - mx, 0.0, mx - x1)
            dy = max(y0 - my, 0.0, my - y1)
            return math.hypot(dx, dy)

        nearest = min(owner, key=dist)
        word_marks[owner[nearest]].append(c)

    order: list[tuple[int, str]] = []
    for wi, w in enumerate(words):
        for c in sorted(w, key=lambda c: boxes[c][0]):
            for i in sorted(comps[c], key=lambda i: strokes[i][0, 0]):
                order.append((i, "base"))
        for c in sorted(word_marks[wi], key=lambda c: boxes[c][0]):
            for i in sorted(comps[c], key=lambda i: strokes[i][0, 0]):
                order.append((i, "mark"))
    return order


# ---------------------------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------------------------
def recover_page(data: bytes, *, paper_size: str, rotation_deg: int = 0, crop_box: dict[str, Any] | None = None,
                 margin_mm: float = 10.0) -> tuple[Page, RecoveryStats]:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg/png.")
    img = _apply_orientation(img, rotation_deg, crop_box)
    scale = MAX_SIDE_PX / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = img.shape

    ink = _remove_specks(_binarise(img))
    ink, angle = _deskew(ink)
    ink = _remove_specks(ink)
    if not ink.any():
        raise AppError(422, "NO_STROKES_FOUND", "Không tìm thấy nét chữ trong ảnh. Hãy kiểm tra độ tương phản.")

    sk = _drop_corner_pixels(zhang_suen(ink))
    sk_len = int(sk.sum())
    width_px = max(float((ink > 0).sum()) / max(sk_len, 1), 1.0)      # ink area / skeleton length

    edges, ends, closed = _graph(sk)
    removed = _prune_spurs(edges, ends, max_len=max(4.0, 1.2 * width_px))
    pair = _pair_edges(edges, ends, removed)
    raw = _assemble(edges, pair, removed) + closed
    raw = [p for p in raw if len(p) >= 2]
    if not raw:
        raise AppError(422, "NO_STROKES_FOUND", "Không tìm thấy nét chữ trong ảnh. Hãy kiểm tra độ tương phản.")
    if len(raw) > MAX_STROKES:
        raise AppError(422, "IMAGE_TOO_NOISY", "Ảnh quá nhiễu hoặc quá phức tạp để phục dựng tự động.")

    labels = cv2.connectedComponents(sk.astype(np.uint8), connectivity=8)[1]
    lab_max = cv2.dilate(labels.astype(np.uint8) if labels.max() < 256 else labels.astype(np.uint16),
                         np.ones((3, 3), np.uint8))
    comp_of = []
    for p in raw:
        comp = 0
        for q in p[:: max(1, len(p) // 6)]:
            x, y = int(round(q[0])), int(round(q[1]))
            if 0 <= y < h and 0 <= x < w and lab_max[y, x] > 0:
                comp = int(lab_max[y, x])
                break
        comp_of.append(comp)

    strokes_px = [_orient(_simplify(_smooth(p), 0.7)) for p in raw]
    order = _reading_order(strokes_px, comp_of)

    # similarity: redraw at the measured pen width, IoU with the cleaned ink
    canvas = np.zeros_like(ink)
    thick = max(1, int(round(width_px)))
    for p in strokes_px:
        cv2.polylines(canvas, [np.round(p).astype(np.int32).reshape(-1, 1, 2)], False, 255, thick)
    inter = int(np.logical_and(canvas > 0, ink > 0).sum())
    union = int(np.logical_or(canvas > 0, ink > 0).sum())
    similarity = round(100.0 * inter / union, 2) if union else 0.0

    # fit onto the paper, centred
    pw, ph = PAPER_MM[paper_size]
    s = min((pw - 2 * margin_mm) / w, (ph - 2 * margin_mm) / h)
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    page = Page(paper_size)
    for i, kind in order:
        pts = [(ox + float(x) * s, oy + float(y) * s) for x, y in strokes_px[i]]
        page.strokes.append(Stroke(pts, kind))

    warnings = []
    if similarity < 80.0:
        warnings.append("SIMILARITY_BELOW_80")      # NFR-02 target; Staff should edit or reject the image
    return page, RecoveryStats(similarity=similarity, n_strokes=len(page.strokes), mm_per_px=round(s, 5),
                               stroke_width_mm=round(width_px * s, 3), deskew_deg=angle, warnings=warnings)
