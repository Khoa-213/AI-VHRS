import cv2
import numpy as np

from app.services.stroke_ai import render_image
from app.services.stroke_ai.trajectory import Page, Stroke


def _decode(buf):
    return cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)


def test_render_jpeg_is_a_real_jpeg_with_ink_colour_on_paper():
    page = Page("A5", [Stroke([(10.0, 10.0), (100.0, 10.0), (100.0, 100.0)])])
    buf = render_image.render_jpeg(page, ink_hex="#FF0000", stroke_width_mm=1.0, paper_surface="CARD")
    assert buf[:3] == bytes([0xFF, 0xD8, 0xFF])
    img = _decode(buf)
    assert img.shape[:2] == (int(round(210 * render_image.PX_PER_MM)), int(round(148 * render_image.PX_PER_MM)))
    b, g, r = (int(v) for v in img[int(10 * render_image.PX_PER_MM), int(55 * render_image.PX_PER_MM)])
    assert r > 180 and g < 90 and b < 90                      # red ink on the stroke
    assert img[5, 5].min() > 200                                # paper elsewhere


def test_render_jpeg_tolerates_bad_ink_and_single_point():
    page = Page("A6", [Stroke([(20.0, 20.0)])])
    assert _decode(render_image.render_jpeg(page, ink_hex="not-a-colour")) is not None
