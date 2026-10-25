"""Service G: how close is the written sheet to the approved sketch? (FR-49 support, NFR-04)

Input: a photo of the written sheet and the approved sketch page. Output: millimetre measurements and an overlay image.

  1. find the sheet in the photo and flatten it (perspective warp) to the sheet's real size at PX_PER_MM;
  2. pick the one of the four possible orientations that matches the sketch best;
  3. take the ink (anything clearly darker than the paper around it, so any ink colour works) and thin it to a centre-line;
  4. fine-align the ink to the sketch (small shift/rotation, reported, never hidden);
  5. measure, in mm: coverage (how much of the planned line has ink within `tol_mm`), extra ink, Chamfer, HD95, Hausdorff.

Honest limits, repeated in the result:
  * the measurement is only as good as the photo: a sheet that cannot be found gives PAPER_NOT_FOUND, not a guess;
  * the flattening assumes a flat sheet whose four corners are visible; its mm accuracy depends on the photo and has NOT been
    calibrated against a ruler: use `scale_check` with a photographed ruler before treating a mm value as a measurement;
  * PASS / NEEDS_REVIEW / FAIL use DEFAULT thresholds nobody has validated on real writing yet (`thresholds_source`).
    The technician's QC verdict stays the decision; this is a second opinion with numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError
from app.services.stroke_ai import recovery
from app.services.stroke_ai.trajectory import Page

PX_PER_MM = 5.0
MAX_SIDE_PX = 2400
MARGIN_MM = 2.0                         # the sheet's edge and its shadow are not ink
INK_RATIO = 0.78                        # darker than 78 % of the paper around it = ink
THRESHOLDS = {"pass": {"coverage_pct": 90.0, "chamfer_mm": 1.0, "extra_ink_pct": 10.0},
              "review": {"coverage_pct": 70.0},
              "tol_mm": 1.0, "source": "DEFAULT_UNCALIBRATED"}
METHOD = "service-g/1"


class EvalError(AppError):
    pass


@dataclass
class Measured:
    code: str
    metrics: dict[str, Any]
    overlay_jpeg: bytes | None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"method": METHOD, "verdict": self.code, **self.metrics, "warnings": self.warnings, "thresholds": THRESHOLDS}


# ---------------------------------------------------------------------------------------------- finding the sheet
def _order(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)   # tl, tr, br, bl


def find_sheet(img: np.ndarray) -> tuple[np.ndarray, str]:
    """Corners (tl, tr, br, bl) of the largest paper-like region, and how they were found."""
    h, w = img.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 3)
    best = None
    for inv in (False, True):                                       # a light sheet on a dark table, or the reverse
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU if inv else cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
        cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 0.15 * w * h or area > 0.985 * w * h:         # nothing paper-sized, or the whole frame (no background visible)
                continue
            hull = cv2.convexHull(c)
            approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
            quad, how = (approx.reshape(4, 2), "quad") if len(approx) == 4 else (cv2.boxPoints(cv2.minAreaRect(hull)), "rect_fallback")
            fill = area / max(cv2.contourArea(quad.astype(np.float32)), 1.0)
            if fill < 0.85:                                         # the region is not a quadrilateral: not a sheet
                continue
            if best is None or area > best[0]:
                best = (area, _order(quad.astype(np.float32)), how)
    if best is None:
        raise EvalError(422, "PAPER_NOT_FOUND", "Không tìm thấy tờ giấy trong ảnh. Chụp thấy đủ 4 góc tờ giấy, đặt trên nền tương phản (bàn tối màu), đủ sáng.")
    return best[1], best[2]


def _warp(img: np.ndarray, corners: np.ndarray, w_mm: float, h_mm: float) -> np.ndarray:
    W, H = int(round(w_mm * PX_PER_MM)), int(round(h_mm * PX_PER_MM))
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(corners, dst), (W, H), flags=cv2.INTER_AREA)


# ---------------------------------------------------------------------------------------------- ink and sketch masks
def ink_mask(flat_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(flat_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) + 1.0
    paper = cv2.GaussianBlur(cv2.dilate(gray, np.ones((15, 15), np.uint8)), (0, 0), 20)     # local paper brightness, ignoring thin ink
    ink = (gray / paper < INK_RATIO).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    m = int(MARGIN_MM * PX_PER_MM)
    ink[:m, :], ink[-m:, :], ink[:, :m], ink[:, -m:] = 0, 0, 0, 0
    return ink


def sketch_masks(page: Page, width_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """(thick: where ink should be, thin: the 1-px centre-line of the plan)."""
    W, H = int(round(page.width_mm * PX_PER_MM)), int(round(page.height_mm * PX_PER_MM))
    thick, thin = np.zeros((H, W), np.uint8), np.zeros((H, W), np.uint8)
    t = max(1, int(round(width_mm * PX_PER_MM)))
    for s in page.strokes:
        pts = np.round(np.array(s.points, np.float32) * PX_PER_MM).astype(np.int32)
        if len(pts) == 1:
            cv2.circle(thick, tuple(int(v) for v in pts[0]), max(1, t // 2), 1, -1)
            thin[int(pts[0][1]), int(pts[0][0])] = 1
        else:
            cv2.polylines(thick, [pts], False, 1, t, cv2.LINE_8)
            cv2.polylines(thin, [pts], False, 1, 1, cv2.LINE_8)
    return thick, thin


def _blur(m: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), 4)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


def _align(ink: np.ndarray, thick: np.ndarray) -> tuple[np.ndarray, dict[str, float] | None]:
    """Small Euclidean alignment of the measured ink onto the plan. Returns the aligned ink and what was applied (None: identity)."""
    s = 0.25                                                        # coarse enough to be fast and to tolerate thin-stroke noise
    a = cv2.resize(_blur(thick), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    b = cv2.resize(_blur(ink), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_EUCLIDEAN,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5), None, 5)
    except cv2.error:
        return ink, None
    full = warp.copy()
    full[:, 2] /= s
    aligned = cv2.warpAffine(ink, full, (ink.shape[1], ink.shape[0]), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
    return aligned, {"dx_mm": round(float(full[0, 2]) / PX_PER_MM, 2), "dy_mm": round(float(full[1, 2]) / PX_PER_MM, 2),
                     "rot_deg": round(float(np.degrees(np.arctan2(full[1, 0], full[0, 0]))), 2)}


# ---------------------------------------------------------------------------------------------- the evaluation
def evaluate(photo: bytes, page: Page, *, stroke_width_mm: float = 0.5, tol_mm: float | None = None) -> Measured:
    tol = tol_mm or THRESHOLDS["tol_mm"]
    img = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise EvalError(422, "PHOTO_UNREADABLE", "Không đọc được ảnh.")
    if max(img.shape[:2]) > MAX_SIDE_PX:
        f = MAX_SIDE_PX / max(img.shape[:2])
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    corners, how = find_sheet(img)
    thick, thin = sketch_masks(page, stroke_width_mm)
    if thin.sum() == 0:
        raise EvalError(422, "SKETCH_EMPTY", "Phác thảo không có nét nào để so sánh.")
    warnings: list[str] = []
    if how != "quad":
        warnings.append("Không thấy rõ 4 góc tờ giấy; đã ước lượng bằng hình chữ nhật bao: kết quả mm kém tin cậy hơn.")

    best = None
    for k in range(4):                                              # which corner is the sheet's top-left? try all four
        rolled = np.roll(corners, -k, axis=0)
        flat = _warp(img, rolled, page.width_mm, page.height_mm)
        ink = ink_mask(flat)
        score = _ncc(_blur(ink), _blur(thick))
        if best is None or score > best[0]:
            best = (score, flat, ink, k)
    score, flat, ink, k = best
    if score < 0.05:
        raise EvalError(422, "NO_MATCH", "Ảnh không khớp với phác thảo (không thấy chữ tương ứng). Kiểm tra đúng tờ và đúng đơn.",
                        {"match_score": round(score, 3)})
    ink, align = _align(ink, thick)
    skel = recovery.zhang_suen(ink)
    if skel.sum() == 0:
        raise EvalError(422, "NO_INK", "Không thấy nét mực trên tờ giấy trong ảnh.")

    mm = 1.0 / PX_PER_MM
    dt_plan = cv2.distanceTransform((1 - thin).astype(np.uint8), cv2.DIST_L2, 5) * mm        # distance to the plan's centre-line
    dt_ink = cv2.distanceTransform((1 - skel.astype(np.uint8)), cv2.DIST_L2, 5) * mm          # distance to the measured centre-line
    d_extra = dt_plan[skel]                                          # measured ink -> plan ("is there ink where it should not be")
    d_missing = dt_ink[thin > 0]                                     # plan -> measured ink ("is the planned line there")
    coverage = 100.0 * float((d_missing <= tol).mean())
    extra = 100.0 * float((d_extra > tol).mean())
    chamfer = 0.5 * (float(d_extra.mean()) + float(d_missing.mean()))
    allv = np.concatenate([d_extra, d_missing])
    metrics = {"coverage_pct": round(coverage, 1), "extra_ink_pct": round(extra, 1), "chamfer_mm": round(chamfer, 3),
               "hd95_mm": round(float(np.percentile(allv, 95)), 3), "hausdorff_mm": round(float(allv.max()), 3), "tol_mm": tol,
               "match_score": round(score, 3), "alignment": align, "sheet_found": how, "sheet_mm": [page.width_mm, page.height_mm],
               "px_per_mm": PX_PER_MM, "stroke_width_mm": stroke_width_mm,
               "scale_check": "NOT_CALIBRATED: mm values assume a flat sheet; photograph a ruler to verify before trusting them"}
    p, r = THRESHOLDS["pass"], THRESHOLDS["review"]
    if coverage >= p["coverage_pct"] and chamfer <= p["chamfer_mm"] and extra <= p["extra_ink_pct"]:
        code = "PASS"
    elif coverage >= r["coverage_pct"]:
        code = "NEEDS_REVIEW"
    else:
        code = "FAIL"

    # overlay: the photo, flattened; blue = measured centre-line, green = planned and present, red = planned but missing
    ov = flat.copy()
    ov[skel] = (255, 120, 0)
    present = (thin > 0) & (dt_ink <= tol)
    missing = (thin > 0) & (dt_ink > tol)
    ov[cv2.dilate(present.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0] = (60, 180, 60)
    ov[cv2.dilate(missing.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0] = (40, 40, 230)
    ok, buf = cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Measured(code, metrics, buf.tobytes() if ok else None, warnings)
