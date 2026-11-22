"""OT-1 recovery v2, R3 (docs/OT1_RECOVERY_V2_PLAN.md): fold creases at any angle (S5), ink just outside a torn sheet's mask
(rim), tracing polish (S8). Images are drawn here (no files, no database)."""
import cv2
import numpy as np

from app.services.stroke_ai import recovery as v1
from app.services.stroke_ai import recovery_v2 as R2
from app.services.stroke_ai.folds import remove_folds
from app.services.stroke_ai.ruling import _pen_px

W, H = 1400, 700


def _loops(img: np.ndarray, rows=range(110, H - 60, 90), x0: int = 120, x1: int = W - 160, grey: int = 40) -> None:
    """Rows of short wavy handwriting-like pieces, 4 px pen."""
    rng = np.random.default_rng(3)
    for row, y in enumerate(rows):
        x = x0
        while x < x1:
            pts = np.array([[x + i * 7, y + int(14 * np.sin(i * 0.9 + row))] for i in range(10)], np.int32)
            cv2.polylines(img, [pts], False, grey, 4, cv2.LINE_AA)
            x += int(rng.uniform(90, 130))


def test_a_diagonal_crease_goes_and_the_writing_stays():
    clean = np.full((H, W), 236, np.uint8)
    _loops(clean)
    creased = clean.copy()
    cv2.line(creased, (0, 40), (W, 660), 140, 2, cv2.LINE_AA)            # ~24 degrees, crosses every row of writing
    letters = v1._binarise(clean)
    ink = v1._binarise(creased)
    out, removed, n = remove_folds(ink, _pen_px(ink))
    assert n >= 1
    crease = (ink > 0) & (letters == 0)
    assert (out[crease] > 0).mean() < 0.15                               # the crease is gone (crossings may stay)
    assert (out[letters > 0] > 0).mean() > 0.97                          # the writing is not


def test_writing_without_a_crease_is_left_alone():
    img = np.full((H, W), 236, np.uint8)
    _loops(img)
    ink = v1._binarise(img)
    out, removed, n = remove_folds(ink, _pen_px(ink))
    assert n == 0 and np.array_equal(ink, out) and not removed.any()


def _torn_sheet(outside: int) -> tuple[np.ndarray, np.ndarray]:
    """A sheet whose mask misses its top strip (rows 60-100). `outside`: the grey above the strip (white backdrop / wood)."""
    gray = np.full((H, W), outside, np.uint8)
    gray[60:, :] = 205                                                   # the paper, including the missed strip
    _loops(gray, rows=range(160, H - 60, 90))                            # writing inside the mask
    mask = np.zeros((H, W), np.uint8)
    mask[100:, :] = 255
    return gray, mask


def test_a_word_just_outside_the_mask_is_kept_on_a_white_backdrop():
    gray, mask = _torn_sheet(outside=250)
    _loops(gray, rows=[80], x0=200, x1=520)                              # the "title", wholly outside the mask
    seeds, _, rim = R2._sheet_ink(gray, mask, np.zeros_like(mask))
    title = rim[66:96, 190:560] > 0
    assert title.sum() > 0.5 * (v1._binarise(gray)[66:96, 190:560] > 0).sum()
    assert not seeds[:100].any()                                         # seeds never leave the mask


def test_rim_ignores_the_table_and_a_tear_gap():
    gray, mask = _torn_sheet(outside=110)                                # wood above the paper
    cv2.rectangle(gray, (700, 70), (1300, 88), 120, cv2.FILLED)          # the table seen through a gap in the missed strip
    _, _, rim = R2._sheet_ink(gray, mask, np.zeros_like(mask))
    assert (rim[:60] > 0).sum() == 0                                     # wood: never ink
    assert (rim[66:94, 700:1300] > 0).sum() < 0.05 * 600 * 18            # the gap: a thick piece, not a letter


def test_trace_defaults_are_unchanged_for_v1():
    """R3 polishes v2's paths lighter (window 3, 0.4 px); v1 (the product) keeps window 5, 0.7 px."""
    import inspect
    sig = inspect.signature(v1.trace)
    assert sig.parameters["smooth_window"].default == 5 and sig.parameters["simplify_eps"].default == 0.7
    assert (R2.SMOOTH_WINDOW, R2.SIMPLIFY_EPS) == (3, 0.4)


def _two_colours(red_marks: int) -> tuple[np.ndarray, np.ndarray]:
    """Blue writing on white paper plus `red_marks` red pieces (print: a margin mark, a logo). Returns (ink, BGR image)."""
    g = np.full((H, W), 255, np.uint8)
    _loops(g)
    bgr = np.full((H, W, 3), 255, np.uint8)
    bgr[g < 200] = (150, 40, 20)                                         # blue pen (BGR)
    for i in range(red_marks):
        cv2.line(bgr, (40, 100 + 40 * i), (90, 100 + 40 * i), (40, 40, 220), 4)
    ink = ((bgr.min(axis=2) < 200) * 255).astype(np.uint8)
    return ink, bgr


def test_print_in_another_colour_than_the_pen_is_removed():
    ink, bgr = _two_colours(red_marks=3)
    gone = R2._off_colour(ink, bgr)
    assert (gone[80:200, 30:100] > 0).sum() == (ink[80:200, 30:100] > 0).sum() > 0    # the red marks, all of them
    assert not gone[:, 110:].any()                                                    # no letter


def test_a_second_pen_is_not_print():
    """Red pieces holding a large share of the ink are a second pen, not a logo: nothing is removed."""
    ink, bgr = _two_colours(red_marks=0)
    half = W // 2
    bgr[:, half:][ink[:, half:] > 0] = (40, 40, 220)                    # the right half written in red
    assert not R2._off_colour(ink, bgr).any()


def test_an_underline_written_with_the_pen_is_not_a_crease():
    """The flourish under a signature (owner's photo, 2026-11-22) is long, straight and thin like a crease, but as dark as
    the writing; a crease is much lighter. With the darkness given, it stays; without it (or lighter), it goes."""
    g = np.full((H, W), 236, np.uint8)
    _loops(g, rows=range(110, 400, 90))
    pen_line, crease = g.copy(), g.copy()
    cv2.line(pen_line, (300, 560), (1100, 500), 40, 4, cv2.LINE_AA)       # written with the pen
    cv2.line(crease, (300, 560), (1100, 500), 150, 3, cv2.LINE_AA)        # a crease: lighter
    for img, stays in ((pen_line, True), (crease, False)):
        ink = v1._binarise(img)
        out, removed, n = remove_folds(ink, _pen_px(ink), 255 - v1._flatten(img))
        line = ink[480:580, 280:1120] > 0
        assert bool((out[480:580, 280:1120] > 0)[line].mean() > 0.9) is stays, stays


def test_a_punch_hole_is_not_traced():
    g = np.full((H, W), 236, np.uint8)
    _loops(g)
    cv2.circle(g, (60, 50), 22, 15, cv2.FILLED)                           # a punch hole in the corner
    bgr = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    ink = v1._binarise(g)
    cv2.circle(ink, (60, 50), 22, 255, 2)                                 # what the local binarisation leaves: a ring
    gone = R2._blobs(ink, bgr, _pen_px(ink))
    assert (ink[20:80, 30:90] > 0).sum() > 0 and ((ink & ~gone)[20:80, 30:90] > 0).sum() == 0
    assert not gone[100:, 110:].any()                                     # no letter


def test_thin_writing_is_traced_on_an_enlarged_copy():
    """S8b (owner's 720 px photos, 2026-11-22): a pen line 2-3 px wide closes the bowls of o / a / b when binarised and the
    letters come out unreadable. Small bowls drawn large, shrunk and blurred like a small photo: traced on the enlarged
    copy they stay open loops; traced at the photo's own size they collapse into a line."""
    assert R2._fine_factor(3.0, 900) == 7.0 / 3.0 and R2._fine_factor(8.0, 900) == 1.0
    assert R2._fine_factor(3.0, 2000) == 1.0                              # a large photo: not worth a copy

    big = np.full((1600, 2400), 236, np.uint8)
    centres = [(200 + 220 * i, 300 + 400 * j) for j in range(3) for i in range(10)]
    for x, y in centres:
        cv2.circle(big, (x, y), 17, 40, 13, cv2.LINE_AA)                  # a bowl with a 21 px hole, 13 px pen
        cv2.line(big, (x + 17, y), (x + 110, y + 20), 40, 13, cv2.LINE_AA)
    small = cv2.GaussianBlur(cv2.resize(big, (480, 320), interpolation=cv2.INTER_AREA), (0, 0), 0.8)   # 1/5, soft
    data = cv2.imencode(".png", cv2.cvtColor(small, cv2.COLOR_GRAY2BGR))[1].tobytes()

    def open_bowls() -> int:
        """Bowls whose centre the traced path leaves free and goes around (seen in at least 7 of 8 directions)."""
        page, _, geo = R2.recover_page(data, paper_size="A4")
        k = 4
        path = np.zeros((small.shape[0] * k, small.shape[1] * k), np.uint8)
        for st in page.strokes:
            pts = np.round(R2.to_photo_px(np.asarray(st.points, float), geo) * k).astype(np.int32)
            cv2.polylines(path, [pts.reshape(-1, 1, 2)], False, 255, 1)
        n = 0
        for x, y in centres:
            cx, cy = x * k // 5, y * k // 5
            if path[cy - 1:cy + 2, cx - 1:cx + 2].any():
                continue
            hits = 0
            for a in range(8):
                dx, dy = np.cos(a * np.pi / 4), np.sin(a * np.pi / 4)
                hits += any(path[int(round(cy + dy * r)) - 1:int(round(cy + dy * r)) + 2,
                                 int(round(cx + dx * r)) - 1:int(round(cx + dx * r)) + 2].any() for r in range(2, 26))
            n += hits >= 7
        return n

    fine = open_bowls()
    saved, R2.FINE_MAX = R2.FINE_MAX, 1.0
    try:
        plain = open_bowls()
    finally:
        R2.FINE_MAX = saved
    assert fine >= 27 and plain <= 3, (fine, plain)
