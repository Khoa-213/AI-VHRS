"""Image quality check and character-count estimate for uploaded originals (FR-33, FR-10, UC-08).

Classic computer vision only (OpenCV): no OCR and no ML model, so the count is an ESTIMATE meant
for the instant price range (BR-08). The official quote is made by Staff after the sketch.
The constants below are starting assumptions, NOT validated on a Vietnamese handwriting test set;
they must be benchmarked (NFR-02 test set) and tuned before relying on the numbers.
"""
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError

MAX_SIDE_PX = 2000
SHARPNESS_MIN = 50.0            # Laplacian variance below this -> blurry (MSG04)
BRIGHTNESS_RANGE = (80.0, 252.0)  # median grey level of the page (white paper scans bright)
CONTRAST_MIN = 40.0             # paper level minus ink level (p50 - p1); faded ink / yellowed paper is low
MARK_HEIGHT_RATIO = 0.35        # components shorter than this x median height are diacritics/dots, not letters
STROKES_PER_GLYPH_HEIGHT = 3.0  # assumed average pen-path length of one letter, in glyph heights


@dataclass(frozen=True)
class ImageAnalysis:
    width: int
    height: int
    sharpness: float
    brightness: float
    contrast: float
    warning: bool
    chars_min: int
    chars_max: int
    chars_estimate: int

    def as_quality_result(self) -> dict[str, Any]:
        d = asdict(self)
        d["analysed"] = True
        d["method"] = "opencv-heuristic-v1"
        return d


def _apply_orientation(img: np.ndarray, rotation_deg: int, crop_box: dict[str, Any] | None) -> np.ndarray:
    rotate = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(rotation_deg)
    if rotate is not None:
        img = cv2.rotate(img, rotate)
    if crop_box:
        h, w = img.shape[:2]
        try:
            x, y, cw, ch = (float(crop_box[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(422, "INVALID_CROP", "Vùng cắt ảnh không hợp lệ.") from exc
        if max(x, y, cw, ch) <= 1.0:  # normalised 0..1 box; otherwise pixels of the rotated image
            x, y, cw, ch = x * w, y * h, cw * w, ch * h
        x0, y0 = max(int(x), 0), max(int(y), 0)
        x1, y1 = min(int(x + cw), w), min(int(y + ch), h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            raise AppError(422, "INVALID_CROP", "Vùng cắt ảnh không hợp lệ.")
        img = img[y0:y1, x0:x1]
    return img


def _estimate_chars(gray: np.ndarray) -> tuple[int, int, int]:
    """Return (low, high, point estimate) of the number of letters."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    ink = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    min_area = max(6, int(0.00002 * h * w))
    comps = [(int(s[cv2.CC_STAT_HEIGHT]), int(s[cv2.CC_STAT_AREA])) for s in stats[1:]
             if min_area <= s[cv2.CC_STAT_AREA] <= 0.25 * h * w]
    if not comps:
        return 0, 0, 0
    overall = median(c[0] for c in comps)
    tall = [c for c in comps if c[0] >= MARK_HEIGHT_RATIO * overall]
    median_h = median(c[0] for c in tall)
    by_components = sum(1 for c in comps if c[0] >= MARK_HEIGHT_RATIO * median_h)  # undercounts cursive

    ink_area = sum(c[1] for c in comps)
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = sum(cv2.arcLength(c, True) for c in contours) or 1.0
    stroke_width = max(2.0 * ink_area / perimeter, 1.0)
    by_ink_length = int(round((ink_area / stroke_width) / (STROKES_PER_GLYPH_HEIGHT * max(median_h, 1))))

    low, high = sorted((by_components, by_ink_length))
    return low, high, int(round((low + high) / 2))


def analyze_image(data: bytes, *, rotation_deg: int = 0, crop_box: dict[str, Any] | None = None) -> ImageAnalysis:
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg/png.")
    img = _apply_orientation(img, rotation_deg, crop_box)
    scale = MAX_SIDE_PX / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    sharpness = float(cv2.Laplacian(img, cv2.CV_64F).var())
    brightness = float(np.median(img))
    contrast = brightness - float(np.percentile(img, 1))
    low, high, est = _estimate_chars(img)
    warning = (sharpness < SHARPNESS_MIN or not BRIGHTNESS_RANGE[0] <= brightness <= BRIGHTNESS_RANGE[1]
               or contrast < CONTRAST_MIN or est == 0)
    return ImageAnalysis(width=int(img.shape[1]), height=int(img.shape[0]), sharpness=round(sharpness, 1),
                         brightness=round(brightness, 1), contrast=round(contrast, 1), warning=warning,
                         chars_min=low, chars_max=high, chars_estimate=est)


def sniff_mime(data: bytes) -> str | None:
    """Detect the real file type from magic bytes; never trust the client-declared mime."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None
