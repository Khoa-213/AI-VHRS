"""OT-1 recovery v2, stage S1 (docs/OT1_RECOVERY_V2_PLAN.md): find the sheet of paper in a photo, straighten it and say which
pixels are paper. Everything outside the paper (a wooden table, a backdrop, a hand) can then never become a stroke.

Classic computer vision, no learned model, no new dependency:
  * paper vs background by colour: the photo's frame seeds the background, GrabCut separates the sheet; holes (the writing
    itself) filled; pieces smaller than 15 % of the biggest are dropped, so a torn letter keeps all its pieces;
  * one piece with four corners -> perspective transform to a straight rectangle (the envelope, a tilted photo);
    otherwise (several pieces, a torn or rounded outline) -> the bounding box of all pieces, not rotated;
  * nothing found (paper fills the photo, or no bright region) -> None, and recovery works on the whole photo as before.
Torn edges: `edge_band` gives a thin band inside the paper outline; v2 drops ink that lives only in that band (fibres, shadows
of the tear) but keeps strokes that come from inside the paper.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.services.stroke_ai import recovery as v1

WORK_SIDE = 480              # detection runs on a copy this size; the result is scaled back
FRAME_SHARE = 0.04           # the outer frame of the photo (this share of the short side) is background
MIN_CONTRAST = 10.0          # Lab distance frame <-> centre below this: no visible background
MAX_PAPER_ON_FRAME = 0.6     # more of the frame than this looks like the paper: the sheet fills the photo
MARGIN = 0.03                # surroundings kept around the straightened sheet (share of its long side)
MIN_PAPER_SHARE = 0.12       # the paper must cover at least this share of the photo
FULL_FRAME_SHARE = 0.97      # paper covering more than this = photo of the page only: nothing to cut
PIECE_SHARE = 0.15           # pieces of a torn sheet: kept when at least this share of the biggest piece
GRABCUT_SEED = 2026          # same photo -> same sheet, whatever ran before it


@dataclass
class PaperFind:
    mask: np.ndarray             # uint8 0/255 in the INPUT image, paper (holes filled)
    homography: np.ndarray       # 3x3, input pixels -> straightened pixels
    size: tuple[int, int]        # (width, height) of the straightened image
    pieces: int
    method: str                  # "quad" (perspective) | "box" (bounding box, no rotation)
    inner: tuple[int, int, int, int]   # (x, y, w, h) of the sheet itself in the straightened image (margin around it)
    share: float                 # paper area / photo area


def _order(pts: np.ndarray) -> np.ndarray:
    """Top-left, top-right, bottom-right, bottom-left (works for tilts below 45 degrees)."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.float32([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]])


def _rect_homography(corners: np.ndarray, margin: float = 0.0) -> tuple[np.ndarray, tuple[int, int], tuple[int, int, int, int]]:
    """Corners (TL, TR, BR, BL) -> a straight rectangle, with `margin` (share of the long side) of the surroundings kept on
    every side so letters touching the sheet's outline are not cut."""
    tl, tr, br, bl = corners
    w = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2))
    h = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2))
    w, h = max(w, 8), max(h, 8)
    m = int(round(margin * max(w, h)))
    dst = np.float32([[m, m], [m + w - 1, m], [m + w - 1, m + h - 1], [m, m + h - 1]])
    return cv2.getPerspectiveTransform(corners, dst), (w + 2 * m, h + 2 * m), (m, m, w, h)


def paper_mask(bgr: np.ndarray) -> np.ndarray | None:
    """Paper pixels (holes filled) at the size of `bgr`, or None when there is no clear sheet on a background.

    The photo's outer frame is taken as BACKGROUND and its centre as PAPER: when the two look alike (the photo shows the page
    only) or the centre's colour runs along much of the frame (the sheet touches the border), there is nothing to cut. Else
    GrabCut (OpenCV), seeded with the frame as background and pixels close to the frame's colour as probable background,
    separates the sheet; a brightness threshold failed on a white backdrop next to yellowed, partly shaded paper (owner's
    letter, 2026-11-21)."""
    h0, w0 = bgr.shape[:2]
    k = min(1.0, WORK_SIDE / max(h0, w0))
    small = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else bgr.copy()
    h, w = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    weight = np.float32([0.5, 1.0, 1.0])                  # lightness counts half: shade must not look like another material
    b = max(3, int(FRAME_SHARE * min(h, w)))
    frame = np.zeros((h, w), bool)
    frame[:b], frame[-b:], frame[:, :b], frame[:, -b:] = True, True, True, True
    bg = np.median(lab[frame], axis=0)
    centre = np.median(lab[int(0.3 * h):int(0.7 * h), int(0.3 * w):int(0.7 * w)].reshape(-1, 3), axis=0)
    contrast = float(np.linalg.norm((bg - centre) * weight))
    paper_on_frame = float((np.linalg.norm((lab[frame] - centre) * weight, axis=1) < 8.0).mean())
    if contrast < MIN_CONTRAST or paper_on_frame > MAX_PAPER_ON_FRAME:
        return None
    seeds = np.full((h, w), cv2.GC_PR_FGD, np.uint8)
    seeds[np.linalg.norm((lab - bg) * weight, axis=2) < 0.35 * contrast] = cv2.GC_PR_BGD
    seeds[frame] = cv2.GC_BGD
    bgm, fgm = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    # GrabCut starts its colour models with k-means on OpenCV's global random generator: without a fixed seed the same photo
    # gave 651 or 689 strokes depending on what ran before it in the process (found in R2)
    cv2.setRNGSeed(GRABCUT_SEED)
    cv2.grabCut(small, seeds, None, bgm, fgm, 5, cv2.GC_INIT_WITH_MASK)
    cand = np.isin(seeds, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8) * 255
    r = max(3, int(round(min(h, w) * 0.01)) | 1)
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))
    contours, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    areas = np.array([cv2.contourArea(c) for c in contours])
    keep = [c for c, a in zip(contours, areas) if a >= PIECE_SHARE * areas.max() and a >= 0.01 * h * w]
    mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(mask, keep, -1, 255, cv2.FILLED)          # fills the writing and stains inside each piece
    share = float((mask > 0).mean())
    if share < MIN_PAPER_SHARE or share > FULL_FRAME_SHARE:
        return None
    if k < 1:
        mask = cv2.resize(mask, (w0, h0), interpolation=cv2.INTER_NEAREST)
    return mask


CUT_OFF_SHARE = 0.05     # more of the outline than this on the photo's border: the sheet runs out of the photo
RULED_MIN = 10.0         # thin ruled-line pixels per 1000 inside the sheet: from here on the sheet is ruled / squared paper
GRID_OUT_SHARE = 0.25    # ... and the same ruling this dense OUTSIDE the found sheet (vs inside): the outline is wrong


CUT_LETTERS = 8          # letter-sized ink pieces cut in two by the found outline: from this many the outline may have cut
                         # into the sheet itself (a book page in shade, 2026-11-24: 11; the owner's torn letter: 4)


def cut_letters(bgr: np.ndarray, mask: np.ndarray) -> int:
    """How many letter-sized ink pieces the sheet's outline cuts in two (at least a quarter of the piece on each side).
    A real sheet edge runs past the writing, not through it; on GrabCut's mistakes (a shaded half taken for the table)
    the outline slices whole lines of words. Long pieces (the table's edge, a shadow) and the photo's frame are left out."""
    ink = v1._binarise(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    ih, iw = ink.shape
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    pen = max(1.0, 2.0 * float((ink > 0).sum()) / max(sum(cv2.arcLength(c, True) for c in contours), 1.0))
    inside = mask > 0
    edge = inside ^ (cv2.erode(mask, np.ones((3, 3), np.uint8)) > 0)
    m = int(1.5 * FRAME_SHARE * min(ih, iw))
    edge[:m], edge[-m:], edge[:, :m], edge[:, -m:] = False, False, False, False
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    count = 0
    for i in np.unique(lab[edge]):
        if i == 0:
            continue
        x, y, w, h, a = st[i]
        if max(w, h) > 12 * pen:
            continue
        piece = lab[y:y + h, x:x + w] == i
        on = int((piece & inside[y:y + h, x:x + w]).sum())
        if min(on, a - on) >= 0.25 * a:
            count += 1
    return count


def _ruling_runs_out(bgr: np.ndarray, mask: np.ndarray) -> bool:
    """The ruling of the sheet continues outside the outline GrabCut found: the "background" is more of the same sheet.

    A squared notebook in hand shadow (owner's photo, 2026-11-24): GrabCut took the shaded half and the top corner for
    background and "Đồi", "THẰNG" were never traced. Thin long horizontal / vertical ink is ruling; solid dark areas (a dark
    table, wood) are left out of the count, so only a ruled sheet with ruling beyond its outline trips this."""
    ink = v1._binarise(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    ih, iw = ink.shape
    k = max(15, int(0.05 * min(ih, iw)))
    lines = (cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, k), np.uint8))
             | cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((k, 1), np.uint8))) > 0
    solid = cv2.dilate(cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8)), np.ones((15, 15), np.uint8)) > 0
    lines &= ~solid
    m = int(1.5 * FRAME_SHARE * min(ih, iw))
    lines[:m], lines[-m:], lines[:, :m], lines[:, -m:] = False, False, False, False
    inside = cv2.dilate(mask, np.ones((9, 9), np.uint8)) > 0
    framed = np.zeros_like(inside)
    framed[m:-m, m:-m] = True
    n_in, n_out = int(inside.sum()), int((~inside & framed).sum())
    if n_in == 0 or n_out == 0:
        return False
    d_in = 1000.0 * float((lines & inside).sum()) / n_in
    d_out = 1000.0 * float((lines & ~inside).sum()) / n_out
    return d_in >= RULED_MIN and d_out >= GRID_OUT_SHARE * d_in


def find_paper(bgr: np.ndarray) -> PaperFind | None:
    mask = paper_mask(bgr)
    if mask is None:
        return None
    if _ruling_runs_out(bgr, mask):
        return None
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    share = float((mask > 0).mean())
    if len(contours) == 1:
        c = contours[0]
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        # a sheet cut off by the edge of the photo is no rectangle to straighten: its four "corners" are where the photo
        # ends, and warping them to a rectangle slanted the writing and cut words off (owner's photo, 2026-11-22)
        ih, iw = mask.shape
        pts = c.reshape(-1, 2)
        m = 1.5 * FRAME_SHARE * min(ih, iw)                 # the photo's outer frame is always background (FRAME_SHARE)
        on_edge = (pts[:, 0] <= m) | (pts[:, 1] <= m) | (pts[:, 0] >= iw - 1 - m) | (pts[:, 1] >= ih - 1 - m)
        cut_off = float(on_edge.mean()) > CUT_OFF_SHARE
        if (not cut_off and len(approx) == 4 and cv2.isContourConvex(approx)
                and cv2.contourArea(approx) >= 0.85 * cv2.contourArea(c)):
            H, size, inner = _rect_homography(_order(approx), MARGIN)
            return PaperFind(mask, H, size, 1, "quad", inner, share)
    # torn / irregular outline: no rotation (a minimum-area rectangle of ragged pieces cut the top of the owner's letter);
    # the bounding box plus margin, deskew later straightens the writing
    x, y, w, h = cv2.boundingRect(np.vstack([c.reshape(-1, 2) for c in contours]))
    H, size, inner = _rect_homography(np.float32([[x, y], [x + w - 1, y], [x + w - 1, y + h - 1], [x, y + h - 1]]), MARGIN)
    return PaperFind(mask, H, size, len(contours), "box", inner, share)


def edge_band(mask: np.ndarray, width_px: int) -> np.ndarray:
    """Pixels of the paper within `width_px` of its outline (outer edge and torn edges)."""
    inner = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * width_px + 1, 2 * width_px + 1)))
    return ((mask > 0) & (inner == 0)).astype(np.uint8) * 255
