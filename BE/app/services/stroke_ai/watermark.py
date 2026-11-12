"""Upgrade U2: visible AI-reconstruction mark on every customer-facing picture of a sketch (docs/UPGRADE_AI_ROBOT_PLAN.md 3.5).

The mark is drawn ONLY on the rendered image (preview PNG, customer JPEG), never in the strokes: the trajectory file, its
hash and the robot's work are untouched. The physical mark the robot writes on the sheet is a separate step (U8).

Two layers, so that cropping one does not remove the other:
  * a band along the bottom edge (outside the usual writing area) with the full sentence and the order code;
  * a faint diagonal text repeated across the page (light enough not to hide the handwriting).

Vietnamese text needs a Unicode font: DejaVu Sans from app/assets/fonts (OpenCV's own fonts are ASCII only).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans.ttf"
TILE_TEXT = "AI-VHRS · TÁI TẠO BẰNG AI ·"
BAND_TEXT = "AI-VHRS · Bản xem trước tái tạo bằng AI · Không phải bản gốc"
BAND_INK = (90, 90, 90)          # RGB
TILE_ALPHA = 0.10                # opacity of the diagonal text
BAND_ALPHA = 0.92


def band_text(order_code: str | None) -> str:
    return f"{BAND_TEXT} · {order_code}" if order_code else BAND_TEXT


@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def _diagonal_layer(w: int, h: int) -> Image.Image:
    size = max(12, int(min(w, h) * 0.045))
    font = _font(size)
    step_x, step_y = int(size * 14), int(size * 6)
    side = int((w ** 2 + h ** 2) ** 0.5) + step_x
    tile = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(tile)
    for row, y in enumerate(range(0, side, step_y)):
        for x in range(-step_x + (row % 2) * step_x // 2, side, step_x):
            draw.text((x, y), TILE_TEXT, font=font, fill=255)
    tile = tile.rotate(30, resample=Image.BILINEAR)
    left, top = (side - w) // 2, (side - h) // 2
    return tile.crop((left, top, left + w, top + h))


def apply_rgb(img: Image.Image, order_code: str | None) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    mask = _diagonal_layer(w, h).point(lambda v: int(v * TILE_ALPHA))
    img.paste(Image.new("RGB", (w, h), BAND_INK), (0, 0), mask)
    text = band_text(order_code)
    size = max(10, int(w * 0.018))
    font = _font(size)
    while font.getlength(text) > w * 0.94 and size > 8:
        size -= 1
        font = _font(size)
    band_h = int(size * 2.0)
    band = Image.new("RGB", (w, band_h), (255, 255, 255))
    ImageDraw.Draw(band).text(((w - font.getlength(text)) / 2, (band_h - size) / 2 - 1), text, font=font, fill=BAND_INK)
    img.paste(band, (0, h - band_h), Image.new("L", (w, band_h), int(255 * BAND_ALPHA)))
    return img


def apply_bytes(data: bytes, order_code: str | None, *, fmt: str) -> bytes:
    """`fmt` is "png" or "jpg". Returns the encoded image with the mark."""
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("not an image")
    rgb = apply_rgb(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)), order_code)
    out = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    params = [cv2.IMWRITE_JPEG_QUALITY, 90] if fmt == "jpg" else []
    ok, buf = cv2.imencode("." + fmt, out, params)
    if not ok:  # pragma: no cover
        raise ValueError("encode failed")
    return buf.tobytes()
