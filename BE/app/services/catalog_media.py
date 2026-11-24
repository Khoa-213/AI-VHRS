"""Catalog images (owner request 2026-11-24, migration 0030): the workshop's own photo of a paper, a pen or an ink, so the
web app shows the real product instead of a drawing made from numbers or a picture taken from somewhere else.

`normalise` turns what the Manager uploads into the one form that is stored and served:
* the real type is read from the file's first bytes (JPEG, PNG or WebP), never from the declared type;
* the pixel count is read from the header BEFORE decoding, so a small file that unpacks to a huge picture is refused;
* a JPEG is turned upright as its EXIF orientation says, then every image is scaled so its longer side is at most
  `MAX_SIDE` px and written as WebP. Nothing but pixels is written: EXIF (camera, GPS position, date) does not survive;
* transparency is kept (a pen cut out of its background), dropped when the image has none.
The object path carries a hash of the stored bytes: a changed image has a new address (no stale cache) and the same
image uploaded twice is the same object.
"""
from __future__ import annotations

import hashlib

import cv2
import numpy as np

from app.core.errors import AppError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000                 # 40 MP decodes to ~120 MB; above that the upload is refused, not decoded
MIN_SIDE = 32
MAX_SIDE = 800
WEBP_QUALITY = 85
CONTENT_TYPE = "image/webp"
FOLDERS = {"paper": "papers", "pen": "pens", "ink": "inks"}

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:                                  # fill byte before a marker
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:  # markers without a length
            i += 2
            continue
        if i + 9 > len(data):
            return None
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _JPEG_SOF:
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        if length < 2:
            return None
        i += 2 + length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    kind = data[12:16]
    if kind == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
    if kind == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X" and len(data) >= 30:
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def header_size(data: bytes, kind: str) -> tuple[int, int] | None:
    """(width, height) from the file header, without decoding the pixels."""
    if kind == "png":
        if len(data) < 24 or data[12:16] != b"IHDR":
            return None
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return _jpeg_size(data) if kind == "jpeg" else _webp_size(data)


def _eight_bit(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    if img.dtype == np.uint16:
        return (img >> 8).astype(np.uint8)
    return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def normalise(data: bytes) -> tuple[bytes, int, int]:
    """The stored form of an uploaded image: (WebP bytes, width, height). Refusals are AppError 422 with a Vietnamese message."""
    if not data:
        raise AppError(422, "INVALID_IMAGE", "Chưa có file ảnh.")
    if len(data) > MAX_BYTES:
        raise AppError(422, "FILE_TOO_LARGE", f"Ảnh tối đa {MAX_BYTES // (1024 * 1024)} MB.")
    kind = sniff(data)
    if kind is None:
        raise AppError(422, "UNSUPPORTED_FILE", "Chỉ nhận ảnh jpg, png hoặc webp.")
    size = header_size(data, kind)
    if size is None or min(size) < 1:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg, png hoặc webp.")
    if size[0] * size[1] > MAX_PIXELS:
        raise AppError(422, "IMAGE_TOO_MANY_PIXELS",
                       f"Ảnh {size[0]}×{size[1]} quá lớn. Hãy thu nhỏ còn dưới {MAX_PIXELS // 1_000_000} triệu điểm ảnh.",
                       {"width": size[0], "height": size[1], "max_pixels": MAX_PIXELS})
    # a JPEG has no transparency: IMREAD_COLOR also turns it upright (EXIF orientation); the others keep their alpha
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR if kind == "jpeg" else cv2.IMREAD_UNCHANGED)
    if img is None or img.size == 0:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg, png hoặc webp.")
    img = _eight_bit(img)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4 and int(img[:, :, 3].min()) == 255:        # an alpha channel that hides nothing
        img = np.ascontiguousarray(img[:, :, :3])
    elif img.shape[2] == 2:                                          # grey + alpha
        img = cv2.merge([img[:, :, 0], img[:, :, 0], img[:, :, 0], img[:, :, 1]])
    h, w = img.shape[:2]
    if min(h, w) < MIN_SIDE:
        raise AppError(422, "IMAGE_TOO_SMALL", f"Ảnh cần mỗi cạnh ít nhất {MIN_SIDE} điểm ảnh.", {"width": w, "height": h})
    if max(h, w) > MAX_SIDE:
        k = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    ok, out = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, WEBP_QUALITY])
    if not ok:
        raise AppError(422, "INVALID_IMAGE", "Không xử lý được ảnh này.")
    return out.tobytes(), w, h


def object_path(material: str, row_id: int, stored: bytes) -> str:
    """Where the image of one paper / pen / ink lives in the media bucket."""
    return f"{FOLDERS[material]}/{row_id}/{hashlib.sha256(stored).hexdigest()[:16]}.webp"
