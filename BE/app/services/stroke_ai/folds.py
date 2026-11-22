"""OT-1 recovery v2, stage S5 (docs/OT1_RECOVERY_V2_PLAN.md): remove fold creases and other long straight thin lines at ANY
angle from the binary ink (S4 handles printed ruling near the page's own angle; a crease of a folded letter runs anywhere).

  * candidates: straight segments at least `MIN_LEN` of the short side long (`cv2.HoughLinesP` on the ink). Handwriting has
    no straight run that long; a row of text can line up, so every candidate must also pass
  * the line test, sampled along the segment: ink on the segment at `ON_SHARE` of the points AND, at a little more than the
    allowed thickness (`MAX_THICK_PENS` pens) away on either side, ink at no more than `SIDE_SHARE` of them (thin across);
  * removed: segment pixels within that thickness; kept: pixels of the band touching ink that is not part of the line
    (a letter crossing the crease), as in S4.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

MIN_LEN = 0.15           # share of the short side
MAX_THICK_PENS = 1.6     # thickness of a crease, in pen widths (min 4 px)
ON_SHARE = 0.8
SIDE_SHARE = 0.3
MAX_GAP_PENS = 2.0       # gaps along a crease bridged by Hough
MAX_SEGMENTS = 400
PEN_SHARE = 0.6          # a segment at least this dark, relative to the ink's median darkness, is a pen stroke (an
                         # underline, the flourish under a signature), not a crease: creases are lighter than the pen


def _segment_ok(ink: np.ndarray, x1: int, y1: int, x2: int, y2: int, off: int) -> bool:
    h, w = ink.shape
    n = int(math.hypot(x2 - x1, y2 - y1))
    if n < 2:
        return False
    t = np.linspace(0.0, 1.0, n)
    xs, ys = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
    nx, ny = -(y2 - y1) / n, (x2 - x1) / n          # unit normal

    def hit(dx: float, dy: float) -> np.ndarray:
        px = np.clip(np.round(xs + dx).astype(int), 0, w - 1)
        py = np.clip(np.round(ys + dy).astype(int), 0, h - 1)
        return ink[py, px] > 0

    on = hit(0, 0) | hit(nx, ny) | hit(-nx, -ny)
    if on.mean() < ON_SHARE:
        return False
    side = hit(off * nx, off * ny) | hit(-off * nx, -off * ny)
    return float(side[on].mean()) <= SIDE_SHARE


def _darkness(dark: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Median darkness along the segment (its darkest pixel across, +-1 px)."""
    h, w = dark.shape
    n = max(2, int(math.hypot(x2 - x1, y2 - y1)))
    t = np.linspace(0.0, 1.0, n)
    xs, ys = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
    nx, ny = -(y2 - y1) / n, (x2 - x1) / n
    best = np.zeros(n, np.uint8)
    for k in (-1, 0, 1):
        px = np.clip(np.round(xs + k * nx).astype(int), 0, w - 1)
        py = np.clip(np.round(ys + k * ny).astype(int), 0, h - 1)
        best = np.maximum(best, dark[py, px])
    return float(np.median(best))


def remove_folds(ink: np.ndarray, pen: float, dark: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, int]:
    """Returns (ink without creases, removed pixels, number of segments removed). `dark` (255 - flattened grey, same
    geometry): when given, a segment as dark as the pen is left alone (`PEN_SHARE`)."""
    h, w = ink.shape
    min_len = max(40, int(MIN_LEN * min(h, w)))
    thick = int(math.ceil(max(4.0, MAX_THICK_PENS * pen)))
    lines = cv2.HoughLinesP(ink, 1, np.pi / 360, threshold=int(0.6 * min_len), minLineLength=min_len,
                            maxLineGap=max(3, int(round(MAX_GAP_PENS * pen))))
    empty = np.zeros_like(ink)
    if lines is None:
        return ink, empty, 0
    band = np.zeros_like(ink)
    n = 0
    pen_dark = PEN_SHARE * float(np.median(dark[ink > 0])) if dark is not None and ink.any() else None
    for x1, y1, x2, y2 in lines.reshape(-1, 4)[:MAX_SEGMENTS]:
        if pen_dark is not None and _darkness(dark, int(x1), int(y1), int(x2), int(y2)) >= pen_dark:
            continue                                 # written with the pen: an underline, not a crease
        if _segment_ok(ink, int(x1), int(y1), int(x2), int(y2), thick // 2 + 2):
            cv2.line(band, (int(x1), int(y1)), (int(x2), int(y2)), 255, thick | 1)
            n += 1
    if not n:
        return ink, empty, 0
    on = band & ink
    rest = ink & ~on
    # letters crossing the crease: band pixels next to ink that is not a sliver of the crease itself
    cnt, lab, st, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
    big = st[:, cv2.CC_STAT_AREA] >= max(8, int(2 * pen * pen))
    big[0] = False
    letters = (big[lab] * 255).astype(np.uint8)
    keep = on & cv2.dilate(letters, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(math.ceil(pen)) + 1,) * 2))
    removed = on & ~keep
    return rest | keep, removed, n
