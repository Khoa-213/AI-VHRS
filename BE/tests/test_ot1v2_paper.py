"""OT-1 recovery v2, R1 (docs/OT1_RECOVERY_V2_PLAN.md): finding the sheet in a photo, straightening it, and keeping only the
ink on it. Images are drawn here (no files, no database)."""
import cv2
import numpy as np
import pytest

from app.services.stroke_ai import paper as P
from app.services.stroke_ai import recovery_v2 as R2


def _writing(h: int, w: int) -> np.ndarray:
    """A light sheet with a few lines of pen-like scribbles."""
    sheet = np.full((h, w, 3), (232, 238, 242), np.uint8)
    rng = np.random.default_rng(7)
    for row in range(4):
        y = int(h * (0.25 + 0.15 * row))
        x = int(w * 0.12)
        while x < w * 0.85:
            pts = np.array([[x + i * 6, y + int(10 * np.sin(i * 1.3 + row))] for i in range(8)], np.int32)
            cv2.polylines(sheet, [pts], False, (140, 40, 30), 3, cv2.LINE_AA)
            x += int(rng.uniform(60, 90))
    return sheet


def _on_wood(sheet: np.ndarray, angle: float = 9.0) -> tuple[np.ndarray, np.ndarray]:
    """The sheet rotated onto a dark striped backdrop; returns the photo and the sheet's corners in it."""
    h, w = sheet.shape[:2]
    H, W = h * 2, w * 2
    yy, xx = np.mgrid[0:H, 0:W]
    back = np.zeros((H, W, 3), np.uint8)
    back[:] = (40, 70, 115)
    back[(yy + xx // 4) % 50 < 3] = (15, 20, 25)                  # dark seams, like the owner's floor
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    m[:, 2] += (W / 2 - w / 2, H / 2 - h / 2)
    dst = cv2.transform(src.reshape(-1, 1, 2), m).reshape(-1, 2)
    hm = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    warped = cv2.warpPerspective(sheet, hm, (W, H))
    inside = cv2.warpPerspective(np.full((h, w), 255, np.uint8), hm, (W, H), flags=cv2.INTER_NEAREST)
    photo = np.where(inside[..., None] > 0, warped, back)
    return photo, dst


def _jpg(img: np.ndarray) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def test_a_tilted_sheet_on_a_table_is_found_and_straightened():
    sheet = _writing(500, 900)
    photo, corners = _on_wood(sheet)
    found = P.find_paper(photo)
    assert found is not None and found.method == "quad" and found.pieces == 1
    x, y, w, h = found.inner
    assert abs(w / h - 900 / 500) < 0.08                        # true aspect ratio back
    straight = cv2.perspectiveTransform(corners.reshape(-1, 1, 2).astype(np.float64), found.homography).reshape(-1, 2)
    assert np.abs(straight[:, 1].min() - y) < 0.02 * h and np.abs(straight[:, 0].min() - x) < 0.02 * w


def test_a_photo_of_the_page_only_has_nothing_to_cut():
    assert P.find_paper(_writing(600, 900)) is None             # the frame looks like the centre


def test_torn_pieces_are_all_kept():
    sheet = _writing(600, 900)
    photo = np.full((1100, 1500, 3), (70, 90, 110), np.uint8)
    photo[100:420, 200:1100] = sheet[:320]
    photo[470:750, 230:1130] = sheet[320:]                        # the lower piece, shifted
    found = P.find_paper(photo)
    assert found is not None and found.pieces == 2 and found.method == "box"
    x, y, w, h = found.inner
    assert w >= 900 * 0.97 and h >= 650 * 0.95                     # both pieces inside the straightened box


def test_v2_draws_no_stroke_on_the_table_and_maps_back_to_the_photo():
    photo, corners = _on_wood(_writing(500, 900))
    page, stats, geo = R2.recover_page(_jpg(photo), paper_size="A4")
    assert geo["paper"]["method"] == "quad" and page.strokes
    poly = corners.astype(np.float32).reshape(-1, 1, 2)
    outside = 0
    for st in page.strokes:
        for x, y in R2.to_photo_px(np.asarray(st.points), geo):
            if cv2.pointPolygonTest(poly, (float(x), float(y)), True) < -3:    # more than 3 px off the sheet
                outside += 1
    assert outside == 0


def test_v2_on_a_page_only_photo_matches_v1_strokes():
    from app.services.stroke_ai import recovery as v1
    data = _jpg(_writing(600, 900))
    p1, _ = v1.recover_page(data, paper_size="A4")
    p2, _, geo = R2.recover_page(data, paper_size="A4")
    assert geo["paper"] is None and len(p2.strokes) == len(p1.strokes)


def test_a_rotated_landscape_sheet_maps_onto_a_landscape_page_only():
    photo, _ = _on_wood(_writing(500, 900))
    _, _, geo = R2.recover_page(_jpg(photo), paper_size="A4")      # A4 is portrait, the sheet landscape
    assert geo["placement"] == "fit"


def test_a_narrow_strip_of_clear_writing_is_not_called_low_resolution():
    """Why S0 measures the pen instead of the photo's short side: a 700 px strip of clear 4 px writing is fine.
    The other direction (a thin pen DOES warn) is not tested: the measured width (ink area / skeleton length) grows with
    blur, so a blurred 1 px pen can measure 3-4 px and not warn. Known R1 limit, see docs/benchmarks/OT1v2_R1_*.md."""
    sheet = np.full((700, 1000, 3), 238, np.uint8)
    for row in range(5):
        y = 120 + 100 * row
        for x in range(100, 880, 90):
            cv2.polylines(sheet, [np.array([[x + i * 5, y + int(9 * np.sin(i))] for i in range(10)], np.int32)],
                          False, (60, 40, 40), 4)
    _, stats, _ = R2.recover_page(_jpg(sheet), paper_size="A4")
    assert "LOW_RESOLUTION" not in stats.warnings


def test_a_sheet_running_out_of_the_photo_is_not_straightened_as_a_rectangle():
    """Owner's photo, 2026-11-22: the sheet leaves the photo on the left and at the bottom. Its outline there is the
    photo's border, not the sheet's edge; warping those four "corners" to a rectangle slanted the writing and cut words
    off. Such a sheet is taken as it lies (bounding box), like a torn one."""
    photo, _ = _on_wood(_writing(600, 900))
    cut = photo[300:, 480:]                                     # the photo's left and top borders now run through the sheet
    found = P.find_paper(cut)
    assert found is not None and found.method == "box"
    assert P.find_paper(photo).method == "quad"                 # the whole sheet in view: straightened as before
