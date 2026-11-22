"""OT-1 recovery v2 (docs/OT1_RECOVERY_V2_PLAN.md). Same stroke tracing as v1 (`recovery.trace`), with noise removal in front.

Done so far (R1):
  S0  LOW_RESOLUTION warning when the pen line is narrower than 2.5 px in the photo (the plan said "short side under 1,200
      px"; that fired on every narrow strip of clear writing, so R1 measures the pen width instead);
  S1  find the sheet, straighten it (perspective for a four-cornered sheet, rotation for a torn one), ink outside the sheet
      is never ink, ink that lives only in the thin band along the sheet's outline (torn fibres, edge shadow) is dropped;
  S2  illumination flattening sees only the sheet (the area outside is filled with the paper's own grey first);
  S9  when the sheet was found and its orientation matches the chosen paper, it is mapped onto the whole page (true size and
      position of the writing) instead of shrinking the writing into the margins.
R2:
  S4  printed ruling (horizontal lines, vertical margin / grid) removed, letters crossing or standing on it kept
      (`ruling.py`).
  S6 (hysteresis binarisation) was tried and dropped: +0.4 F1 on clean pages, but the faint threshold flooded fold shadows
      on the mixed family (69 -> 43 % unbounded, 58 % with growth limited to 2 px). S3 (ink colour) not done, see R2 report.
  S4 also keeps pen ink lying on a line that is clearly darker than the line itself (`ruling.DARKER`, R3).
R3:
  S1/S2 rim: ink just outside a torn sheet's mask (GrabCut misses paper next to a white backdrop: the title and date of the
      owner's letter) is used where the surroundings are paper-bright and the piece is pen-thin (`_sheet_ink`);
  S5  fold creases / long straight thin lines at any angle removed, crossings kept (`folds.py`);
  S8  tracing: working size 2,000 px (was 1,600), lighter polish (window 3, Douglas-Peucker 0.4 px), strokes mapped back
      to the photo on pixel centres.
  Not done: a separate piece classifier (S7) and stain handling; the shadow edge of a grey tear gap still traces as a thin
  line (tear family), see the R3 report.
R4:
  S10 similarity = tolerant F1 between paths and cleaned ink (`ink_f1`), region fit measured the same way; the pieces taken
      out are summarised in `geometry["noise_removed"]`. Used by the product when the Admin setting `ot1_recovery_engine` is
      "v2" (engine.generate_ot1); "v1" (default) keeps recovery.py.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError
from app.services.handwriting_image import _apply_orientation
from app.services.stroke_ai import folds as folds_mod
from app.services.stroke_ai import paper as paper_mod
from app.services.stroke_ai import recovery as v1
from app.services.stroke_ai import ruling as ruling_mod
from app.services.stroke_ai.regions import RegionDraft, label_for
from app.services.stroke_ai.trajectory import PAPER_MM, Page, Stroke

QUAD_INSET = 0.02         # a four-cornered sheet: its rectangle pulled in by this share of the short side (edge shadow)
NEAR_SHEET = 0.03         # letters clipped by the sheet mask are looked for this far outside it (share of the short side)
EDGE_BAND = 0.012         # outline band of the sheet, share of its short side (edge shadow of the envelope: ~1 %)
LOW_RES_PEN_PX = 2.5      # S0: a pen line narrower than this in the photo is hard to tell from printed ruling / paper texture
RULING = True             # S4 on (switch off to measure R1 alone)
SMOOTH_WINDOW = 3         # S8: polish of the traced paths. v1's (window 5, Douglas-Peucker 0.7 px) pulled the path off
SIMPLIFY_EPS = 0.4        # the stroke's centre: F1 +4 points, fewer sharp turns, 40 % more points (R3 report)
MAX_SIDE_PX = 2000        # S8: working resolution (v1: 1,600); 1,600 -> 2,000 gave F1 +2.3 on the benchmark
FOLDS = True              # S5 on (switch off to measure without it)
EDGE_AGAIN = True         # S1's band rule again after S4 / S5 (outline joined to the writing only by ruling)
RIM_MAX_PENS = 2.5        # rim pieces thicker than this many pen widths are the table seen through a tear gap
RIM_PAPER_TOL = 0.12      # rim ink counts only where the surroundings are not darker than the paper by more than this


def _sheet_ink(gray: np.ndarray, mask: np.ndarray, band: np.ndarray,
               grow: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Ink of the sheet, the grey image the rest of recovery measures darkness on, and the RIM candidates.

    1. Seeds: v1's binarisation of the image with everything outside the sheet painted in the paper's grey, so the
       background (dark wood, a backdrop) cannot move the threshold; seeds are the pieces with a pixel inside the sheet away
       from its outline (torn fibres / edge shadow along the outline are not seeds).
    2. Rim (when `grow`): the same threshold applied to the real pixels just outside the sheet mask (within `NEAR_SHEET`):
       GrabCut misses paper next to a white backdrop (the title and the date of the owner's letter). Only where the
       surroundings (grey closing, v1's flattening kernel) are not darker than the paper by more than `RIM_PAPER_TOL`: the
       table / wood around a sheet is darker, its edge and the sheet's shadow would otherwise come back as an outline
       (mixed family 86 -> 75 %). Two other rules were tried in R3 and dropped: keeping rim pieces that touch seeds before
       the ruling is removed (wood joined the letters through ruled lines) and after it (words lying wholly outside the
       mask, "cho" and "22" of the letter, were lost; folds and tear gaps still joined the outline).
    Returns (seeds, the grey image with the far background painted paper grey, rim or None); the caller joins seeds + rim."""
    paper_grey = int(np.median(gray[mask > 0])) if (mask > 0).any() else 255
    filled = gray.copy()
    filled[mask == 0] = paper_grey
    seeds = v1._binarise(filled)
    n, lab = cv2.connectedComponents(seeds, connectivity=8)
    good = np.zeros(n, bool)
    good[np.unique(lab[(seeds > 0) & (mask > 0) & (band == 0)])] = True
    good[0] = False
    seeds = (good[lab] * 255).astype(np.uint8)
    if not grow:
        return seeds, filled, None
    h, w = gray.shape
    r = max(3, int(round(NEAR_SHEET * min(h, w))))
    disc = lambda rad: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rad + 1, 2 * rad + 1))
    near = cv2.dilate(mask, disc(r))
    wide = cv2.dilate(mask, disc(2 * r))        # pieces are judged here, then cut back to `near`: a gap half inside
    t, _ = cv2.threshold(v1._flatten(filled)[mask > 0].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    real = gray.copy()
    real[wide == 0] = paper_grey
    k = max(15, (min(h, w) // 30) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    paperlike = background.astype(np.int16) >= (1 - RIM_PAPER_TOL) * paper_grey
    rim = ((v1._flatten(real) < t) & (wide > 0) & (mask == 0) & paperlike).astype(np.uint8) * 255
    if RIM_MAX_PENS:
        # a gap between torn pieces shows the table: the whole gap binarises as one thick piece, a letter is pen-thin
        pen = ruling_mod._pen_px(seeds) if seeds.any() else 2.0
        n, lab, st, _ = cv2.connectedComponentsWithStats(rim, connectivity=8)
        bad = np.zeros(n, bool)
        for i in range(1, n):
            x, y, bw, bh, area = st[i]
            if area < 4 * pen * pen:
                continue
            piece = (lab[y:y + bh, x:x + bw] == i).astype(np.uint8)
            bad[i] = ruling_mod._pen_px(cv2.copyMakeBorder(piece, 1, 1, 1, 1, cv2.BORDER_CONSTANT)) > RIM_MAX_PENS * pen
        rim[bad[lab]] = 0
    rim[near == 0] = 0
    real[near == 0] = paper_grey
    return seeds, real, rim


def _path_mask(strokes_px: list[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    """The traced paths drawn 1 px wide."""
    out = np.zeros(shape, np.uint8)
    for p in strokes_px:
        if len(p) >= 2:
            cv2.polylines(out, [np.round(p).astype(np.int32).reshape(-1, 1, 2)], False, 255, 1)
        elif len(p) == 1:
            x, y = np.round(p[0]).astype(int)
            if 0 <= y < shape[0] and 0 <= x < shape[1]:
                out[y, x] = 255
    return out


def _local_f1(path: np.ndarray, ink_dist: np.ndarray, ink: np.ndarray, path_dist: np.ndarray, width_px: float) -> float:
    tau = max(1.0, width_px / 2)
    pp = path > 0
    precision = float((ink_dist[pp] <= tau).mean()) if pp.any() else 0.0
    recall = float((path_dist[ink] <= width_px / 2 + tau).mean()) if ink.any() else 0.0
    return round(100 * 2 * precision * recall / (precision + recall), 2) if precision + recall else 0.0


def ink_f1(strokes_px: list[np.ndarray], ink: np.ndarray, width_px: float) -> float:
    """R4 (S10, Q1) similarity shown in the product, 0..100: F1 with a tolerance of half a pen width between the traced
    paths and the CLEANED ink. Precision = path pixels within tolerance of ink; recall = ink pixels within half a pen width +
    tolerance of a path. Without the true ink mask (the benchmark's ground truth) it only says "the strokes follow the ink
    that was kept"; how well noise was removed is measured by scripts/benchmark_ot1v2.py. Cheaper than the benchmark's
    skeleton F1 (no second thinning)."""
    path = _path_mask(strokes_px, ink.shape)
    ink_dist = cv2.distanceTransform((ink == 0).astype(np.uint8), cv2.DIST_L2, 3)
    path_dist = cv2.distanceTransform((path == 0).astype(np.uint8), cv2.DIST_L2, 3)
    return _local_f1(path, ink_dist, ink > 0, path_dist, width_px)


NOISE_MAX_PIECES = 100          # noise_removed lists at most this many pieces (the largest), the rest only counted


def noise_summary(removed: dict[str, np.ndarray], mm_per_px: float, offset_mm: tuple[float, float]) -> dict:
    """R4: the ink pieces the noise stages took out, for the Staff: per reason (RULING, FOLD, EDGE) the number of pieces, and
    the largest pieces with their box in page millimetres (same frame as the strokes)."""
    ox, oy = offset_mm
    counts: dict[str, int] = {}
    pieces = []
    for reason, mask in removed.items():
        if mask is None or not mask.any():
            counts[reason] = 0
            continue
        n, _, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        counts[reason] = n - 1
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in st[i])
            pieces.append((area, reason, x, y, w, h))
    pieces.sort(reverse=True)
    return {"counts": counts, "pieces": [
        {"reason": r, "bbox_mm": [round(ox + x * mm_per_px, 1), round(oy + y * mm_per_px, 1),
                                  round(ox + (x + w) * mm_per_px, 1), round(oy + (y + h) * mm_per_px, 1)], "px": a}
        for a, r, x, y, w, h in pieces[:NOISE_MAX_PIECES]]}


def _anchored(ink: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Pieces of `ink` with at least one pixel in `anchor`."""
    n, lab = cv2.connectedComponents(ink, connectivity=8)
    good = np.zeros(n, bool)
    good[np.unique(lab[(ink > 0) & (anchor > 0)])] = True
    good[0] = False
    return (good[lab] * 255).astype(np.uint8)


def recover_page(data: bytes, *, paper_size: str, rotation_deg: int = 0, crop_box: dict[str, Any] | None = None,
                 margin_mm: float = 10.0) -> tuple[Page, v1.RecoveryStats, dict]:
    """Like `recovery.recover_page`; the third value describes the geometry (benchmark: map strokes back to the photo)."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg/png.")
    img = _apply_orientation(img, rotation_deg, crop_box)
    warnings: list[str] = []

    # S1: the sheet, found on the photo at full size and straightened from it, THEN reduced to MAX_SIDE_PX: the writing keeps
    # all the photo's pixels instead of sharing them with the table around the sheet
    found = paper_mod.find_paper(img)
    if found is not None:
        w0, h0 = found.size
        sc = min(1.0, MAX_SIDE_PX / max(w0, h0))
        homography = np.diag([sc, sc, 1.0]) @ found.homography
        w, h = max(8, int(round(w0 * sc))), max(8, int(round(h0 * sc)))
        if found.method == "quad":
            # four clear corners: the sheet is exactly this rectangle after straightening; GrabCut's outline runs a few
            # pixels into the shadow around an envelope, so the rectangle (pulled in a little) replaces it
            x, y, iw, ih = (v * sc for v in found.inner)
            inset = QUAD_INSET * min(iw, ih)
            mask = np.zeros((h, w), np.uint8)
            cv2.rectangle(mask, (int(round(x + inset)), int(round(y + inset))),
                          (int(round(x + iw - 1 - inset)), int(round(y + ih - 1 - inset))), 255, cv2.FILLED)
        else:
            mask = cv2.warpPerspective(found.mask, homography, (w, h), flags=cv2.INTER_NEAREST)
        img = cv2.warpPerspective(img, homography, (w, h), flags=cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR,
                                  borderValue=(255, 255, 255))
        geo_scale = 1.0
    else:
        sc = min(1.0, MAX_SIDE_PX / max(img.shape[:2]))
        if sc < 1:
            img = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
        mask = np.full((h, w), 255, np.uint8)
        homography = np.eye(3)
        geo_scale = sc

    # S2: flatten the sheet only
    anchor = None                                           # where a piece of ink must have a pixel to stay
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if found is not None and found.method == "quad":
        ink, gray, _ = _sheet_ink(gray, mask, np.zeros_like(mask), grow=False)
    elif found is not None:
        band = paper_mod.edge_band(mask, max(3, int(round(EDGE_BAND * min(h, w)))))
        ink, gray, rim = _sheet_ink(gray, mask, band)
        ink = ink | rim
        anchor = ((mask > 0) & (band == 0) | (rim > 0)).astype(np.uint8) * 255
    else:
        ink = v1._binarise(gray)
    ink = v1._remove_specks(ink)
    ink, angle = v1._deskew(ink)
    flat = v1._flatten(gray)
    if angle:
        rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        flat = cv2.warpAffine(flat, rot, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
        if anchor is not None:
            anchor = cv2.warpAffine(anchor, rot, (w, h), flags=cv2.INTER_NEAREST)
    removed: dict[str, np.ndarray] = {}                     # R4: what each stage took out (for `noise_removed`)
    ruling = None
    if RULING:                                              # S4: printed ruling out, crossings kept
        ink, ruling = ruling_mod.remove_ruling(ink, flat)
        removed["RULING"] = ruling.removed
    if FOLDS:                                               # S5: creases / long straight lines at any angle
        ink, removed["FOLD"], _ = folds_mod.remove_folds(ink, ruling_mod._pen_px(ink))
    if anchor is not None and EDGE_AGAIN:
        # the band rule of S1 again, now that ruling and creases are gone: outline shadow joined to the writing only through
        # a ruled line (the owner's letter, R3) is a piece of its own and is dropped
        before = ink
        ink = _anchored(ink, anchor)
        removed["EDGE"] = before & ~ink
    ink = v1._remove_specks(ink)
    if not ink.any():
        raise AppError(422, "NO_STROKES_FOUND", "Không tìm thấy nét chữ trong ảnh. Hãy kiểm tra độ tương phản.")

    strokes_px, comp_of, width_px = v1.trace(ink, SMOOTH_WINDOW, SIMPLIFY_EPS)
    if width_px / sc < LOW_RES_PEN_PX:                     # S0: pen width in pixels of the photo as uploaded
        warnings.append("LOW_RESOLUTION")
    order = v1._reading_order(strokes_px, comp_of)

    thick = max(1, int(round(width_px)))
    similarity = ink_f1(strokes_px, ink, width_px)                      # R4 (Q1): replaces v1's pixel IoU

    # S9: the sheet onto the page at its true size when the orientations match; otherwise v1's fit inside the margins
    pw, ph = PAPER_MM[paper_size]
    if found is not None and (w >= h) == (pw >= ph):
        s = min(pw / w, ph / h)
        placement = "sheet"
    else:
        s = min((pw - 2 * margin_mm) / w, (ph - 2 * margin_mm) / h)
        placement = "fit"
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    page = Page(paper_size)
    for i, kind, _ in order:
        page.strokes.append(Stroke([(ox + float(x) * s, oy + float(y) * s) for x, y in strokes_px[i]], kind))

    # regions (S10): v1's confidence = min(fit relative to the page, contrast), with the fit measured as the same tolerant F1
    # as the page similarity instead of v1's pixel IoU
    path_px = _path_mask(strokes_px, ink.shape)
    ink_dist = cv2.distanceTransform((ink == 0).astype(np.uint8), cv2.DIST_L2, 3)
    path_dist = cv2.distanceTransform((path_px == 0).astype(np.uint8), cv2.DIST_L2, 3)
    runs: dict[int, list[int]] = {}
    for pos, (_, _, wi) in enumerate(order):
        runs.setdefault(wi, []).append(pos)
    page_dark = float(np.median(255 - flat[ink > 0])) if ink.any() else 1.0
    measured = []
    for wi in sorted(runs, key=lambda k: runs[k][0]):
        pos = runs[wi]
        allp = np.concatenate([strokes_px[order[k][0]] for k in pos])
        x0, y0 = np.floor(allp.min(axis=0)).astype(int) - thick
        x1, y1 = np.ceil(allp.max(axis=0)).astype(int) + thick + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        k = ink[y0:y1, x0:x1] > 0
        fit = round(_local_f1(path_px[y0:y1, x0:x1], ink_dist[y0:y1, x0:x1], k, path_dist[y0:y1, x0:x1], width_px) / 100, 3)
        dark = float(np.median(255 - flat[y0:y1, x0:x1][k])) if k.any() else 0.0
        measured.append((pos, fit, round(min(dark / max(page_dark, 1.0), 1.0), 3)))
    page_fit = float(np.median([m[1] for m in measured])) if measured else 1.0
    regions = []
    for n, (pos, fit, contrast) in enumerate(measured, start=1):
        fit_rel = round(min(fit / max(page_fit, 1e-6), 1.0), 3)
        conf = min(fit_rel, contrast)
        mm = [page.strokes[k2] for k2 in range(pos[0], pos[-1] + 1)]
        bx = (min(p[0] for st in mm for p in st.points), min(p[1] for st in mm for p in st.points),
              max(p[0] for st in mm for p in st.points), max(p[1] for st in mm for p in st.points))
        regions.append(RegionDraft(1, n, pos[0], pos[-1] + 1, tuple(round(v, 2) for v in bx), label_for(conf), conf,
                                   metrics={"fit": fit, "fit_rel": fit_rel, "contrast": contrast}))

    stats = v1.RecoveryStats(similarity=similarity, n_strokes=len(page.strokes), mm_per_px=round(s, 5),
                             stroke_width_mm=round(width_px * s, 3), deskew_deg=angle, warnings=warnings, regions=regions)
    geometry = {"scale": geo_scale, "homography": homography, "size": (w, h), "deskew_deg": angle, "mm_per_px": s,
                "offset_mm": (ox, oy), "placement": placement,
                "noise_removed": noise_summary(removed, s, (ox, oy)),
                "paper": None if found is None else {"method": found.method, "pieces": found.pieces,
                                                     "share": round(found.share, 3)}}
    return page, stats, geometry


def to_photo_px(points_mm: np.ndarray, geometry: dict) -> np.ndarray:
    """Page millimetres -> pixels of the photo after orientation / crop (inverse of every step above)."""
    s, (ox, oy) = geometry["mm_per_px"], geometry["offset_mm"]
    w, h = geometry["size"]
    p = (np.asarray(points_mm, np.float64) - (ox, oy)) / s
    if geometry["deskew_deg"]:
        inv = cv2.invertAffineTransform(cv2.getRotationMatrix2D((w / 2, h / 2), geometry["deskew_deg"], 1.0))
        p = p @ inv[:, :2].T + inv[:, 2]
    hinv = np.linalg.inv(geometry["homography"])
    q = np.c_[p, np.ones(len(p))] @ hinv.T
    p = q[:, :2] / q[:, 2:3]
    # cv2.resize maps pixel CENTRES: x_small + 0.5 = scale * (x_photo + 0.5) (dividing by the scale alone was off by
    # 0.5 * (1 / scale - 1) px, ~0.1 px at 1,900 -> 1,600)
    return (p + 0.5) / geometry["scale"] - 0.5
