"""Decode an uploaded picture only after its header says it is not enormous (AI-11, audit 2026-11-27).

Every pipeline that reads a customer's or a technician's photo used to call `cv2.imdecode` first and shrink the picture
afterwards. The upload limit is on the FILE size (megabytes), but a well-compressed PNG of a few megabytes can declare
hundreds of megapixels: decoding it takes gigabytes of memory and kills the single API process. The header is read without
decoding a pixel, and a picture above MAX_PIXELS is refused with a message the customer can act on.
"""
from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from app.core.errors import AppError

MAX_PIXELS = 40_000_000        # 40 MP: the same ceiling as catalog photos (services/catalog_media.py); ~120 MB once decoded in colour


def declared_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) the file header declares, or None when the header cannot be read here (cv2 then decides)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        # read by hand: Pillow refuses to even open a PNG far above its own bomb limit, and that refusal must not look
        # like "unknown format, let cv2 try"
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    try:
        with Image.open(BytesIO(data)) as im:      # lazy: reads the header only
            return int(im.size[0]), int(im.size[1])
    except Image.DecompressionBombError:
        return _BOMB
    except Exception:                               # noqa: BLE001 - not a format Pillow knows, or a broken file
        return None


_BOMB = (0, 0)      # Pillow itself called the file a decompression bomb: refused, whatever its exact size


def check(data: bytes) -> None:
    size = declared_size(data)
    if size is _BOMB:
        raise AppError(422, "IMAGE_TOO_LARGE", f"Ảnh quá lớn. Hãy thu nhỏ còn dưới {MAX_PIXELS // 1_000_000} triệu điểm ảnh rồi tải lại.",
                       {"max_pixels": MAX_PIXELS})
    if size is not None and size[0] * size[1] > MAX_PIXELS:
        raise AppError(422, "IMAGE_TOO_LARGE",
                       f"Ảnh {size[0]}×{size[1]} quá lớn. Hãy thu nhỏ còn dưới {MAX_PIXELS // 1_000_000} triệu điểm ảnh rồi tải lại.",
                       {"width": size[0], "height": size[1], "max_pixels": MAX_PIXELS})


def decode(data: bytes, flags: int) -> np.ndarray | None:
    """`cv2.imdecode` behind the size check. None when the bytes are not a picture (as cv2 answers)."""
    check(data)
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
