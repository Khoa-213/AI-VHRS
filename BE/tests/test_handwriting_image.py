"""Image quality + character-count estimate (FR-33). Synthetic images only; no accuracy claim."""
import cv2
import numpy as np
import pytest

from app.core.errors import AppError
from app.services.handwriting_image import analyze_image, sniff_mime


def _page(text_lines: list[str], scale: float = 1.2) -> np.ndarray:
    img = np.full((900, 1200), 245, np.uint8)
    for i, line in enumerate(text_lines):
        cv2.putText(img, line, (60, 120 + i * 110), cv2.FONT_HERSHEY_SIMPLEX, scale * 2, 20, 4, cv2.LINE_AA)
    return img


def _encode(img: np.ndarray, ext: str = ".png") -> bytes:
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()


def test_text_page_gets_positive_estimate_and_ordered_range():
    r = analyze_image(_encode(_page(["Net Viet Nam", "xuong viet tay"])))
    assert r.chars_estimate > 0
    assert r.chars_min <= r.chars_estimate <= r.chars_max
    assert not r.warning


def test_more_text_gives_larger_estimate():
    small = analyze_image(_encode(_page(["abc"])))
    large = analyze_image(_encode(_page(["abcdefgh", "ijklmnop", "qrstuvwx"], scale=0.8)))
    assert large.chars_estimate > small.chars_estimate


def test_blank_page_is_flagged_with_zero_chars():
    r = analyze_image(_encode(np.full((600, 800), 240, np.uint8)))
    assert r.chars_estimate == 0 and r.warning


def test_blurry_image_is_flagged():
    blurred = cv2.GaussianBlur(_page(["Net Viet"]), (0, 0), 25)
    assert analyze_image(_encode(blurred)).warning


def test_dark_image_is_flagged():
    assert analyze_image(_encode((_page(["Net Viet"]) * 0.15).astype(np.uint8))).warning


def test_rotation_swaps_dimensions():
    data = _encode(_page(["Net Viet"]))
    base, rot = analyze_image(data), analyze_image(data, rotation_deg=90)
    assert (rot.width, rot.height) == (base.height, base.width)


def test_crop_reduces_area_and_bad_crop_rejected():
    data = _encode(_page(["Net Viet Nam", "xuong viet tay"]))
    cropped = analyze_image(data, crop_box={"x": 0, "y": 0, "w": 0.5, "h": 0.5})
    assert cropped.width < 1200
    with pytest.raises(AppError) as e:
        analyze_image(data, crop_box={"x": 0.5, "y": 0.5, "w": 0.0, "h": 0.0})
    assert e.value.code == "INVALID_CROP"


def test_garbage_bytes_rejected():
    with pytest.raises(AppError) as e:
        analyze_image(b"not an image")
    assert e.value.status == 422 and e.value.code == "INVALID_IMAGE"


def test_sniff_mime():
    assert sniff_mime(_encode(_page(["a"]))) == "image/png"
    assert sniff_mime(_encode(_page(["a"]), ".jpg")) == "image/jpeg"
    assert sniff_mime(b"%PDF-1.7 ...") == "application/pdf"
    assert sniff_mime(b"MZ\x90\x00") is None
