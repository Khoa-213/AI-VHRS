"""OT-1 recovery v2, R2 / S4 (docs/OT1_RECOVERY_V2_PLAN.md): printed ruling removed, letters crossing it kept.
Images are drawn here (no files, no database)."""
import cv2
import numpy as np

from app.services.stroke_ai import recovery as v1
from app.services.stroke_ai import recovery_v2 as R2
from app.services.stroke_ai.ruling import remove_ruling

W, H = 1400, 700
LINE_YS = list(range(80, H, 70))


def _page(ruled: bool = True, angle: float = 0.0, line_grey: int = 150) -> np.ndarray:
    img = np.full((H, W), 236, np.uint8)
    if ruled:
        t = np.tan(np.radians(angle))
        for y in LINE_YS:
            cv2.line(img, (0, y), (W, int(round(y + t * W))), line_grey, 2, cv2.LINE_AA)
    return img


def _pole(img: np.ndarray, x: int, y0: int, y1: int) -> None:
    """A letter's downstroke crossing a ruled line."""
    cv2.line(img, (x, y0), (x + 6, y1), 40, 4, cv2.LINE_AA)


def _loops(img: np.ndarray) -> None:
    rng = np.random.default_rng(3)
    for row, y in enumerate(LINE_YS[:-1]):
        x = 120
        while x < W - 160:
            pts = np.array([[x + i * 7, y + 32 + int(14 * np.sin(i * 0.9 + row))] for i in range(10)], np.int32)
            cv2.polylines(img, [pts], False, 40, 4, cv2.LINE_AA)
            x += int(rng.uniform(90, 130))


def _run(gray: np.ndarray):
    ink = v1._binarise(gray)
    return ink, *remove_ruling(ink, v1._flatten(gray))


def _between_letters(mask: np.ndarray, y: int) -> int:
    """Ink on the ruled line at y, in the empty right margin (x > 1300)."""
    return int((mask[y - 3:y + 4, 1300:] > 0).sum())


def test_ruled_lines_go_and_a_letter_crossing_one_stays_whole():
    img = _page()
    _loops(img)
    _pole(img, 700, 120, 190)                                  # crosses the line at y=150
    ink, out, ru = _run(img)
    assert ru.n_lines >= len(LINE_YS) - 1
    assert all(_between_letters(ink, y) > 0 for y in LINE_YS)   # the lines were ink before
    assert all(_between_letters(out, y) == 0 for y in LINE_YS)  # and are gone
    n, lab = cv2.connectedComponents(out[118:193, 690:715])     # the downstroke: still one piece through the line
    assert n == 2


def test_a_page_without_ruling_is_left_alone():
    img = _page(ruled=False)
    _loops(img)
    ink, out, ru = _run(img)
    assert ru.n_lines == 0 and np.array_equal(ink, out)


def test_ruling_tilted_eight_degrees_is_found():
    """A torn piece lying crooked: deskew turns only +-5 degrees, S4 searches +-15. What stays: the ends of lines cut off
    by the image corners, shorter than a ruled-line run (~5 % of the ruling here)."""
    img = _page(angle=8.0)
    ink, out, ru = _run(img)
    assert ru.n_lines >= 5 and abs(abs(ru.angle_deg) - 8.0) <= 1.0
    assert (out > 0).sum() < 0.10 * (ink > 0).sum()


def test_a_wide_dark_band_is_not_a_ruled_line():
    """A fold's shadow or the gap of a tear is long but wide: S4 leaves it (S5 / R3)."""
    img = _page(ruled=False)
    cv2.rectangle(img, (0, 300), (W, 322), 90, cv2.FILLED)
    ink, out, ru = _run(img)
    assert ru.n_lines == 0 and (out[300:323] > 0).sum() == (ink[300:323] > 0).sum()


def test_v2_recovers_no_stroke_along_the_ruling():
    g = _page()
    _loops(g)
    img = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    page, _, geo = R2.recover_page(cv2.imencode(".png", img)[1].tobytes(), paper_size="A4")
    assert page.strokes
    long_flat = 0
    for st in page.strokes:
        p = R2.to_photo_px(np.asarray(st.points), geo)
        if np.ptp(p[:, 0]) > 200 and np.ptp(p[:, 1]) < 6:          # a stroke running along a ruled line
            long_flat += 1
    assert long_flat == 0


def test_a_letter_stem_lying_on_a_light_grid_line_stays():
    """The owner's notebook letter (2026-11-22): the stem of an L / a T written exactly on a light vertical grid line was
    removed with the line (it reaches farther than DARKER's zone around the writing). A short piece much darker than the
    line around it, touching the writing, is pen ink and stays whole; the grid line around it still goes."""
    img = _page(line_grey=200)
    _loops(img)
    cv2.line(img, (1290, 0), (1290, H), 200, 2, cv2.LINE_AA)     # a light vertical grid line, right of the writing
    cv2.line(img, (1290, 226), (1290, 280), 40, 4, cv2.LINE_AA)  # the stem of an L on it
    cv2.line(img, (1290, 280), (1325, 280), 40, 4, cv2.LINE_AA)  # its foot, between two ruled lines
    ink, out, ru = _run(img)
    assert ru.n_vertical >= 1
    stem = ink[228:270, 1285:1296] > 0
    assert (out[228:270, 1285:1296] > 0)[stem].mean() > 0.97
    assert (out[H - 40:H - 5, 1285:1296] > 0).sum() == 0        # the grid line itself is removed
