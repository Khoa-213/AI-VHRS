"""OT-1 recovery v2, stage S4 (docs/OT1_RECOVERY_V2_PLAN.md): remove the printed ruling of a notebook / letter sheet from the
binary ink and keep the places where handwriting crosses it.

Works after S1 (sheet straightened) and deskew, on the binary ink and the flattened grey image it came from:
  * a ruled line = a straight run that stays dark (`LINE_DARK`) along at least `H_RUN` of the width (grey opening of the
    flattened image, so a faint line that binarises only as dashes is still found whole) AND is thin across: within half
    the allowed thickness (`MAX_THICK_PENS` pens) on both sides the darkness falls below half. The test is per pixel: on
    the owner's crumpled letter the ruling, the vertical grid and the writing join into one connected piece. A fold's
    shadow or the gap of a tear is long but wide, so it is not a line (S5, R3);
  * the angle is searched in +-`SEARCH_DEG` (deskew turns only +-5 degrees, a torn piece can lie more crooked); vertical
    margin / grid lines the same way, `V_RUN` of the height;
  * removed: the line (core + 1 px across) and the halo ink that runs along it (ruling in the pen's colour binarises
    with a halo, which would otherwise sit right above and below the cleared line);
  * kept: where a letter crosses a line (ink right above AND right below: a short closing across the line), and line
    pixels within `TOUCH_PX` of letter ink (the foot of a letter standing on the line).
  * kept too (R3, `DARKER`): band ink clearly darker than the line's own darkness there (its lightest pixel along the run):
    pen ink lying on a light ruled line. A stand-in for S3 (ink colour model) that needs no colour.
Not separated yet: an underline or a long dash written with the pen, as dark as the ruling, is removed like a ruled line.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

H_RUN = 0.125            # a horizontal ruled line is at least this share of the image width long
V_RUN = 0.15             # a vertical margin / grid line: at least this share of the height (a piece of a torn sheet)
MIN_RUN_PX = 40
SEARCH_DEG = 15          # the ruling's angle is searched in +-this many degrees
FINE = (-1.0, -0.5, 0.0, 0.5, 1.0)                   # around the angle found
GAP_PX = 5               # specks of paper texture breaking a line: gaps this short are closed before measuring the run
LINE_DARK = 12           # darkness (0-255, flattened image) a run must keep along its whole length to be a printed line
MAX_THICK_PENS = 1.6     # the core of a ruled line is at most this many pen widths thick (min 4 px)
TOUCH_PX = 2             # band pixels this close to letter ink (across the line) stay: letters standing on the line
DARKER_NEAR_PENS = 3.0   # DARKER ink kept only this close (pen widths) to writing off the line (shaded ruling, R3)
DARKER = 30              # band ink this much darker (0-255) than the line itself there is pen ink, kept
RUN_PENS = 4.0           # halo ink of a line is cleared when it runs along the line at least this many pen widths


@dataclass
class Ruling:
    removed: np.ndarray      # uint8 0/255: ink removed as ruling
    kept: np.ndarray         # uint8 0/255: ink on a line kept because a letter crosses there
    n_lines: int
    n_vertical: int
    angle_deg: float


def _pen_px(ink: np.ndarray) -> float:
    """Pen width = 2 x ink area / outline length (a stroke of width w and length L: area wL, outline ~2L). Within 3-10 % of
    v1's area / skeleton length on the benchmark, without a second thinning (2.5 s on an A5 scan at 300 dpi); a median of
    the distance transform jumped between 1.9 and 3.8 px on the same page."""
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    outline = sum(cv2.arcLength(c, True) for c in contours)
    return max(1.0, 2.0 * float((ink > 0).sum()) / max(outline, 1.0))


def _rot(img: np.ndarray, angle: float, inverse: bool = False) -> np.ndarray:
    if not angle:
        return img
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    if inverse:
        m = cv2.invertAffineTransform(m)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR)


def _run_response(dark: np.ndarray, length: int, horizontal: bool) -> np.ndarray:
    """Grey opening along the line direction: how dark the lightest pixel of a straight run of `length` through each pixel
    is. A ruled line stays dark along its whole length; handwriting does not."""
    close_k = np.ones((1, GAP_PX), np.uint8) if horizontal else np.ones((GAP_PX, 1), np.uint8)
    open_k = np.ones((1, length), np.uint8) if horizontal else np.ones((length, 1), np.uint8)
    return cv2.morphologyEx(cv2.morphologyEx(dark, cv2.MORPH_CLOSE, close_k), cv2.MORPH_OPEN, open_k)


def _response(dark: np.ndarray, length: int, horizontal: bool, angle: float) -> np.ndarray:
    return _rot(_run_response(_rot(dark, angle), length, horizontal), angle, inverse=True)


def _ruling_angle(dark: np.ndarray, length: int) -> float:
    """Angle (deg) at which the most darkness lies in long straight runs (half-size copy, 1 degree steps)."""
    small = cv2.resize(dark, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    best, best_a = -1.0, 0.0
    for a in range(-SEARCH_DEG, SEARCH_DEG + 1):
        r = _response(small, max(10, length // 2), True, float(a))
        score = float(r[r >= LINE_DARK].sum())
        if score > best:
            best, best_a = score, float(a)
    return best_a


def _lines(dark: np.ndarray, length: int, horizontal: bool, angles: tuple[float, ...],
           pen: float) -> tuple[np.ndarray, np.ndarray, int]:
    """Printed lines at any of `angles`: pixels of a long dark run (`_run_response` >= LINE_DARK) that are THIN across the
    run: within `half` pixels on BOTH sides the response falls below half its own value. A fold's shadow, the gap of a tear
    or the table along the sheet's edge are long too, but wide. Tested pixel by pixel (not per connected piece: on a real
    crumpled letter the ruling, the vertical grid and the writing join into one piece). Also returns the line's own
    darkness at each pixel (the run response: the lightest pixel along the run, so a letter on the line does not raise it)."""
    half = int(np.ceil(max(4.0, MAX_THICK_PENS * pen) / 2)) + 1
    up = np.zeros((2 * half + 1, 1), np.uint8) if horizontal else np.zeros((1, 2 * half + 1), np.uint8)
    down = up.copy()
    if horizontal:
        up[:half + 1, 0], down[half:, 0] = 1, 1
    else:
        up[0, :half + 1], down[0, half:] = 1, 1
    out = np.zeros_like(dark)
    level = np.zeros_like(dark)
    for a in angles:
        r = _run_response(_rot(dark, a), length, horizontal).astype(np.int16)
        level = np.maximum(level, _rot(r.astype(np.uint8), a, inverse=True))
        thin = (r >= LINE_DARK) & (2 * cv2.erode(r.astype(np.uint8), up).astype(np.int16) < r)             & (2 * cv2.erode(r.astype(np.uint8), down).astype(np.int16) < r)
        out |= _rot((thin * 255).astype(np.uint8), a, inverse=True)
    out = ((out > 127) * 255).astype(np.uint8)
    # a line must still be long after the thin test (a short thin stretch at the edge of a wide band is not a line)
    n, lab, st, _ = cv2.connectedComponentsWithStats(out, connectivity=8)
    size = st[:, cv2.CC_STAT_WIDTH] if horizontal else st[:, cv2.CC_STAT_HEIGHT]
    keep = size >= length // 2
    keep[0] = False
    out = (keep[lab] * 255).astype(np.uint8)
    across = np.ones((3, 1), np.uint8) if horizontal else np.ones((1, 3), np.uint8)
    return cv2.dilate(out, across), level, int(keep.sum())


def _halo(lines: np.ndarray, horizontal: bool, pen: float) -> np.ndarray:
    """The faint edge around a found line, where its anti-aliasing binarises as ink."""
    k = int(np.ceil(max(4.0, MAX_THICK_PENS * pen) / 2)) + 1
    return cv2.dilate(lines, np.ones((2 * k + 1, 1), np.uint8) if horizontal else np.ones((1, 2 * k + 1), np.uint8))


def _along(ink: np.ndarray, length: int, horizontal: bool, angle: float) -> np.ndarray:
    """Ink in straight runs at least `length` long along the line direction (binary opening at `angle`)."""
    h, w = ink.shape
    k = np.ones((1, length), np.uint8) if horizontal else np.ones((length, 1), np.uint8)
    if not angle:
        return cv2.morphologyEx(ink, cv2.MORPH_OPEN, k)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    run = cv2.morphologyEx(cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_NEAREST), cv2.MORPH_OPEN, k)
    return cv2.warpAffine(run, cv2.invertAffineTransform(m), (w, h), flags=cv2.INTER_NEAREST) & ink


def remove_ruling(ink: np.ndarray, flat: np.ndarray) -> tuple[np.ndarray, Ruling]:
    """`ink` binary (0/255), `flat` the flattened grey image it came from (same geometry)."""
    h, w = ink.shape
    pen = _pen_px(ink)
    dark = 255 - flat
    hl = max(MIN_RUN_PX, int(H_RUN * w))
    vl = max(MIN_RUN_PX, int(V_RUN * h))
    base = _ruling_angle(dark, hl)
    angles = tuple(base + d for d in FINE)
    hor, hlevel, nh = _lines(dark, hl, True, angles, pen)
    ver, vlevel, nv = _lines(dark, vl, False, angles, pen)
    hpiece, vpiece = _halo(hor, True, pen), _halo(ver, False, pen)
    # the halo of a line binarises as ink where the line is dark (ruling in the pen's colour): that ink runs ALONG the line,
    # the foot of a letter standing on the line does not. Left in place, it would sit right above and below the cleared
    # core and the crossing test below would bridge the whole line back.
    run = max(8, int(round(RUN_PENS * pen)))
    hor = hor | (hpiece & _along(ink, run, True, base))
    ver = ver | (vpiece & _along(ink, run, False, base))
    if not (hor.any() or ver.any()):
        return ink, Ruling(np.zeros_like(ink), np.zeros_like(ink), 0, 0, base)
    hb, vb = hor & ink, ver & ink
    rest = ink & ~(hb | vb)
    # crossings: ink right above and right below a horizontal band (left / right of a vertical one)
    span = int(np.ceil(max(4.0, MAX_THICK_PENS * pen))) + 4
    bridge = cv2.morphologyEx(rest, cv2.MORPH_CLOSE, np.ones((span, 3), np.uint8)) & hb
    bridge |= cv2.morphologyEx(rest, cv2.MORPH_CLOSE, np.ones((3, span), np.uint8)) & vb
    if TOUCH_PX:
        # the foot of a letter standing on the line: band pixels right next to letter ink (one side is enough)
        bridge |= cv2.dilate(rest, np.ones((2 * TOUCH_PX + 1, 1), np.uint8)) & hb
        bridge |= cv2.dilate(rest, np.ones((1, 2 * TOUCH_PX + 1), np.uint8)) & vb
    if DARKER:
        # S3, by darkness: pen ink lying ON a line is darker than the line itself there (the line's own darkness is its
        # lightest pixel along the run); on the owner's letter the dense ruling hid the horizontal parts of most letters
        over = dark.astype(np.int16) - np.maximum(hlevel, vlevel).astype(np.int16)
        darker = (hb | vb) & (over > DARKER).astype(np.uint8) * 255
        if DARKER_NEAR_PENS:
            # only next to writing off the line: a faded / shaded stretch of the ruling itself is uneven too
            r = int(np.ceil(DARKER_NEAR_PENS * pen))
            darker &= cv2.dilate(rest, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        bridge |= darker
    removed = (hb | vb) & ~bridge
    return rest | bridge, Ruling(removed, bridge, nh, nv, base)
