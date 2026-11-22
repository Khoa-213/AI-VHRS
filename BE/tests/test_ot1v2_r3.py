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
