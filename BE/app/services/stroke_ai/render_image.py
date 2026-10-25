"""Customer-facing sketch image: what the finished page would look like, as a JPEG.

This is a picture of the planned strokes (ink colour, pen width, paper tone); it is NOT a photo of a real result and the
page says so nowhere on the image itself, FE shows the caption. The technical PNG preview (with stroke start dots) stays for staff.
"""
import re

import cv2
import numpy as np

from app.core.errors import AppError
from app.services.stroke_ai.trajectory import Page

PX_PER_MM = 5.0          # A4 -> 1050 x 1485 px
SUPERSAMPLE = 2
JPEG_QUALITY = 90
PAPER_BGR = {"PLAIN": (247, 250, 252), "ART": (244, 248, 250), "GLOSSY": (252, 252, 252), "COATED": (250, 251, 252),
             "CARD": (236, 243, 247), "OTHER": (248, 250, 252)}
DEFAULT_INK = "#1A1A2E"


def _bgr(hex_code: str | None) -> tuple[int, int, int]:
    h = hex_code if hex_code and re.fullmatch(r"#[0-9a-fA-F]{6}", hex_code) else DEFAULT_INK
    return int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)


def render_jpeg(page: Page, *, ink_hex: str | None = None, stroke_width_mm: float | None = None,
                paper_surface: str | None = None) -> bytes:
    s = PX_PER_MM * SUPERSAMPLE
    w, h = int(round(page.width_mm * s)), int(round(page.height_mm * s))
    img = np.empty((h, w, 3), np.uint8)
    img[:] = PAPER_BGR.get(paper_surface or "PLAIN", PAPER_BGR["PLAIN"])
    width_mm = min(max(stroke_width_mm or 0.5, 0.2), 3.0)
    thick = max(1, int(round(width_mm * s)))
    ink = _bgr(ink_hex)
    for st in page.strokes:
        pts = np.round(np.array(st.points, np.float32) * s).astype(np.int32)
        if len(pts) == 1:
            cv2.circle(img, tuple(int(v) for v in pts[0]), max(1, thick // 2), ink, -1, cv2.LINE_AA)
        else:
            cv2.polylines(img, [pts], False, ink, thick, cv2.LINE_AA)
    img = cv2.resize(img, (int(round(page.width_mm * PX_PER_MM)), int(round(page.height_mm * PX_PER_MM))),
                     interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:  # pragma: no cover
        raise AppError(500, "IMAGE_RENDER_FAILED", "Không tạo được ảnh phác thảo.")
    return buf.tobytes()
