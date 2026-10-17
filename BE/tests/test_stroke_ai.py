"""Stroke recovery (OT-1) and text-to-stroke (OT-3) pipelines. Pure computation, no database.

The recovery tests use synthetic images (known geometry) so they check correctness of the algorithm,
NOT accuracy on real Vietnamese handwriting (that needs the NFR-02 benchmark set).
"""
import unicodedata

import cv2
import numpy as np
import pytest

from app.core.errors import AppError
from app.services.stroke_ai import engine, recovery, text_to_stroke as tts
from app.services.stroke_ai import trajectory as tj

VI_BASES = "aăâeêioôơuưy"
VI_TONES = ["", "́", "̀", "̉", "̃", "̣"]


def _png(img) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def _blank(h=600, w=800):
    return np.full((h, w), 245, np.uint8)


def _text_image(lines=("Net Viet Nam", "xuong viet tay")):
    img = _blank(900, 1200)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (60, 140 + i * 130), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.6, 30, 5, cv2.LINE_AA)
    return img


# ---- thinning / graph ------------------------------------------------------------------------------
def test_zhang_suen_thins_a_thick_line_to_one_pixel():
    ink = np.zeros((100, 300), np.uint8)
    cv2.line(ink, (20, 50), (280, 50), 255, 9)
    sk = recovery.zhang_suen(ink)
    assert sk.sum() == pytest.approx(260, abs=15)
    assert sk.sum(axis=0).max() == 1                       # one pixel per column in the middle


def test_t_shape_gives_two_pen_paths_through_the_junction():
    img = _blank(400, 400)
    cv2.line(img, (60, 100), (340, 100), 20, 8)             # horizontal bar
    cv2.line(img, (200, 100), (200, 340), 20, 8)            # stem
    page, stats = recovery.recover_page(_png(img), paper_size="A5")
    assert len(page.strokes) == 2
    lengths = sorted(round(s.length_mm()) for s in page.strokes)
    assert lengths[1] > lengths[0] > 0
    assert stats.similarity > 75


def test_text_image_is_recovered_with_reasonable_similarity():
    page, stats = recovery.recover_page(_png(_text_image()), paper_size="A4")
    assert stats.n_strokes >= 8 and stats.similarity >= 70
    w, h = tj.PAPER_MM["A4"]
    assert all(0 <= x <= w and 0 <= y <= h for s in page.strokes for x, y in s.points)


def test_strokes_start_left_for_horizontal_and_top_for_vertical():
    img = _blank(400, 600)
    cv2.line(img, (80, 100), (500, 130), 20, 7)
    cv2.line(img, (300, 200), (300, 360), 20, 7)
    page, _ = recovery.recover_page(_png(img), paper_size="A5")
    for s in page.strokes:
        (x0, y0), (x1, y1) = s.points[0], s.points[-1]
        if abs(x1 - x0) >= 0.3 * abs(y1 - y0):
            assert x0 < x1
        else:
            assert y0 < y1


def test_small_marks_are_written_after_the_letters_of_their_word():
    img = _blank(500, 700)
    for x in (150, 210, 270):                               # three tall strokes (a word) ...
        cv2.line(img, (x, 200), (x, 380), 20, 8)
    cv2.circle(img, (210, 130), 8, 20, -1)                  # ... and a dot above the middle one
    page, _ = recovery.recover_page(_png(img), paper_size="A5")
    kinds = [s.kind for s in page.strokes]
    assert kinds.count("base") == 3 and kinds[-1] == "mark"


def test_two_lines_are_read_top_to_bottom():
    page, _ = recovery.recover_page(_png(_text_image()), paper_size="A4")
    ys = [np.mean([p[1] for p in s.points]) for s in page.strokes if s.kind == "base"]
    half = len(ys) // 2
    assert np.mean(ys[:half]) < np.mean(ys[half:])


def test_deskew_corrects_a_tilted_page():
    img = _text_image()
    h, w = img.shape
    tilted = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), 3.0, 1.0), (w, h), borderValue=245)
    _, stats = recovery.recover_page(_png(tilted), paper_size="A4")
    assert 1.5 <= abs(stats.deskew_deg) <= 4.5


def test_rotation_param_is_applied():
    img = _text_image()
    rot = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    _, upright = recovery.recover_page(_png(img), paper_size="A4")
    _, fixed = recovery.recover_page(_png(rot), paper_size="A4", rotation_deg=90)
    assert abs(upright.n_strokes - fixed.n_strokes) <= 3 and fixed.similarity >= 70


def test_blank_image_has_no_strokes():
    with pytest.raises(AppError) as e:
        recovery.recover_page(_png(_blank()), paper_size="A4")
    assert e.value.code == "NO_STROKES_FOUND"


def test_garbage_bytes_are_rejected():
    with pytest.raises(AppError) as e:
        recovery.recover_page(b"not an image", paper_size="A4")
    assert e.value.code == "INVALID_IMAGE"


def test_bad_crop_is_rejected():
    with pytest.raises(AppError) as e:
        recovery.recover_page(_png(_text_image()), paper_size="A4", crop_box={"x": 0, "y": 0, "w": 0.001, "h": 0.001})
    assert e.value.code == "INVALID_CROP"


def test_recovery_of_our_own_vietnamese_rendering():
    """Round trip: compose Vietnamese text, rasterise it like a scan, recover it."""
    page = tts.compose_text("Xưởng Nét Việt chúc mừng", font_name="scripts", paper_size="A5", font_size_mm=9)[0]
    ppm = 8
    img = np.full((int(page.height_mm * ppm), int(page.width_mm * ppm)), 235, np.uint8)
    for s in page.strokes:
        cv2.polylines(img, [np.round(np.array(s.points) * ppm).astype(np.int32).reshape(-1, 1, 2)], False, 40, 5,
                      cv2.LINE_AA)
    _, stats = recovery.recover_page(_png(img), paper_size="A5")
    assert stats.similarity >= 75 and stats.n_strokes >= len(page.strokes) * 0.6


# ---- text to stroke --------------------------------------------------------------------------------
@pytest.mark.parametrize("font", sorted(tts.SUPPORTED_FONTS))
def test_every_supported_font_draws_vietnamese(font):
    text = " ".join(unicodedata.normalize("NFC", b + t) for b in VI_BASES for t in VI_TONES) + " đ Đ"
    pages = tts.compose_text(text, font_name=font, paper_size="A4", font_size_mm=7)
    assert pages and all(len(p.strokes) > 0 for p in pages)


def test_marks_follow_the_base_letters_of_each_word():
    pages = tts.compose_text("ắn ở", font_name="futural", paper_size="A5", font_size_mm=8)
    kinds = [s.kind for s in pages[0].strokes]
    assert kinds == ["base", "base", "base", "mark", "mark", "base", "base", "mark"][: len(kinds)] or \
        kinds.index("mark") > 0
    first_word = kinds[:5]
    assert first_word.index("mark") >= 2                    # letters a, n before the breve + acute


def test_stacked_marks_do_not_overlap_the_base_glyph():
    pages = tts.compose_text("ấ", font_name="futural", paper_size="A5", font_size_mm=21, variation=0.0)
    base = [s for s in pages[0].strokes if s.kind == "base"]
    marks = [s for s in pages[0].strokes if s.kind == "mark"]
    assert len(marks) == 2
    top_base = min(y for s in base for _, y in s.points)
    assert all(y < top_base for s in marks for _, y in s.points)


def test_unsupported_characters_are_reported_with_position():
    with pytest.raises(AppError) as e:
        tts.compose_text("abc 漢 def", font_name="futural", paper_size="A4")
    assert e.value.code == "UNSUPPORTED_CHARS" and e.value.details[0]["char"] == "漢" and e.value.details[0]["index"] == 4


def test_typographic_punctuation_is_accepted():
    assert tts.compose_text("“Xin chào” — vâng… ok", font_name="futural", paper_size="A4")


def test_alignment_right_and_center():
    kw = dict(font_name="futural", paper_size="A5", font_size_mm=7, variation=0.0)

    def extent(align):
        p = tts.compose_text("Xin chao", alignment=align, **kw)[0]
        xs = [x for s in p.strokes for x, _ in s.points]
        return min(xs), max(xs)

    w = tj.PAPER_MM["A5"][0]
    l, r = extent("LEFT"), extent("RIGHT")
    c = extent("CENTER")
    assert l[0] == pytest.approx(tts.MARGIN_MM, abs=1.0)
    assert r[1] == pytest.approx(w - tts.MARGIN_MM, abs=2.0)
    assert (c[0] + c[1]) / 2 == pytest.approx(w / 2, abs=2.0)


def test_justify_fills_the_line_except_the_last():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma"
    p = tts.compose_text(text, font_name="futural", paper_size="A5", font_size_mm=6, alignment="JUSTIFY", variation=0.0)[0]
    rows: dict[int, list[float]] = {}
    for s in p.strokes:
        if s.kind == "base":
            for x, y in s.points:
                rows.setdefault(round(y / 11.4), []).append(x)
    ordered = [rows[k] for k in sorted(rows)]
    first = max(ordered[0])
    assert first == pytest.approx(tj.PAPER_MM["A5"][0] - tts.MARGIN_MM, abs=3.0)


def test_long_text_wraps_and_paginates():
    pages = tts.compose_text("Xin chào các bạn. " * 40, font_name="futural", paper_size="A6", font_size_mm=6)
    assert 1 < len(pages) <= tj.MAX_PAGES
    for p in pages:
        assert all(0 <= x <= p.width_mm and 0 <= y <= p.height_mm for s in p.strokes for x, y in s.points)


def test_text_too_long_is_rejected():
    with pytest.raises(AppError) as e:
        tts.compose_text("Xin chào các bạn. " * 4000, font_name="futural", paper_size="A6", font_size_mm=6)
    assert e.value.code == "TEXT_TOO_LONG"


def test_font_too_large_is_rejected():
    with pytest.raises(AppError) as e:
        tts.compose_text("A", font_name="futural", paper_size="A6", font_size_mm=100)
    assert e.value.code == "FONT_TOO_LARGE"


def test_very_long_word_is_broken_to_fit():
    pages = tts.compose_text("x" * 200, font_name="futural", paper_size="A6", font_size_mm=6)
    assert all(max(x for s in p.strokes for x, _ in s.points) <= p.width_mm - tts.MARGIN_MM + 3 for p in pages)


def test_variation_is_deterministic_per_seed():
    a = tts.compose_text("Nét Việt", font_name="futural", paper_size="A5", seed=7)
    b = tts.compose_text("Nét Việt", font_name="futural", paper_size="A5", seed=7)
    c = tts.compose_text("Nét Việt", font_name="futural", paper_size="A5", seed=8)
    assert tj.to_dict(a, {}) == tj.to_dict(b, {}) and tj.to_dict(a, {}) != tj.to_dict(c, {})


def test_font_uri_is_validated():
    assert tts.font_name_from_uri("hershey:scripts") == "scripts"
    for bad in ("scripts", "hershey:nope", "file:///etc/passwd"):
        with pytest.raises(AppError):
            tts.font_name_from_uri(bad)


def test_canvas_strokes_are_validated_and_deduplicated():
    ok = tts.canvas_to_strokes({"strokes": [{"points": [{"x": 10, "y": 10}, {"x": 10.01, "y": 10}, {"x": 30, "y": 40}]}]}, "A5")
    assert len(ok) == 1 and len(ok[0].points) == 2 and ok[0].kind == "canvas"
    with pytest.raises(AppError) as e:
        tts.canvas_to_strokes({"strokes": [{"points": [{"x": 10, "y": 10}, {"x": 500, "y": 10}]}]}, "A5")
    assert e.value.code == "CANVAS_OUT_OF_PAPER"


# ---- trajectory model ------------------------------------------------------------------------------
def test_metrics_time_estimate():
    page = tj.Page("A5", [tj.Stroke([(0, 0), (48, 0)])])
    m = tj.compute_metrics([page], v_max_mm_s=40)            # 48 mm / (40 * 0.6) = 2 s + 0.5 s lift cycle
    assert m.total_stroke_mm == 48.0 and m.pen_lift_count == 1 and m.estimated_writing_sec == 3


def test_metrics_include_pen_up_travel():
    page = tj.Page("A5", [tj.Stroke([(0, 0), (10, 0)]), tj.Stroke([(110, 0), (120, 0)])])
    m = tj.compute_metrics([page], v_max_mm_s=40)
    assert m.travel_mm == 100.0 and m.pen_lift_count == 2


def test_trajectory_roundtrip_and_hash():
    pages = tts.compose_text("Xin chào", font_name="futural", paper_size="A5")
    raw = tj.dumps(tj.to_dict(pages, {"name": "t"}))
    again = tj.parse(__import__("json").loads(raw))
    assert len(again[0].strokes) == len(pages[0].strokes)
    assert len(tj.content_hash(raw)) == 64 and tj.content_hash(raw) == tj.content_hash(raw)


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(format="x"), "INVALID_TRAJECTORY"),
    (lambda d: d.update(pages=[]), "INVALID_TRAJECTORY"),
    (lambda d: d["pages"][0]["paper"].update(size="A3"), "INVALID_TRAJECTORY"),
    (lambda d: d["pages"][0]["strokes"].__setitem__(0, {"kind": "base", "points": [[0, 0]]}), "INVALID_TRAJECTORY"),
    (lambda d: d["pages"][0]["strokes"].__setitem__(0, {"kind": "base", "points": [[0, 0], [999, 0]]}), "INVALID_TRAJECTORY"),
    (lambda d: d["pages"][0]["strokes"].__setitem__(0, {"kind": "pen", "points": [[0, 0], [1, 1]]}), "INVALID_TRAJECTORY"),
    (lambda d: d["pages"][0]["strokes"].__setitem__(0, {"kind": "base", "points": [[0, 0], [float("nan"), 1]]}), "INVALID_TRAJECTORY"),
])
def test_trajectory_validation(mutate, code):
    d = tj.to_dict(tts.compose_text("Xin", font_name="futural", paper_size="A5"), {})
    mutate(d)
    with pytest.raises(AppError) as e:
        tj.parse(d)
    assert e.value.code == code


def test_preview_is_a_png_of_the_page_size():
    page = tts.compose_text("Xin", font_name="futural", paper_size="A6")[0]
    png = tj.render_preview(page, px_per_mm=2)
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (296, 210)


# ---- engine ----------------------------------------------------------------------------------------
def test_engine_ot1_end_to_end():
    g = engine.generate_ot1([engine.ImageSource(_png(_text_image()))], paper_size="A4", v_max_mm_s=40,
                            pen_category="BALLPOINT", chars=20)
    assert g.similarity and g.metrics.pen_lift_count > 5 and g.complexity in {"SIMPLE", "MEDIUM", "COMPLEX"}
    assert g.engine["name"] == "zhang-suen-skeleton"


def test_engine_ot1_requires_images_and_caps_pages():
    with pytest.raises(AppError) as e:
        engine.generate_ot1([], paper_size="A4", v_max_mm_s=40, pen_category=None, chars=0)
    assert e.value.code == "NO_ORIGINAL_IMAGE"
    with pytest.raises(AppError) as e:
        engine.generate_ot1([engine.ImageSource(b"x")] * (engine.MAX_AI_PAGES + 1), paper_size="A4", v_max_mm_s=40,
                            pen_category=None, chars=0)
    assert e.value.code == "AI_TOO_MANY_PAGES"


def test_engine_ot3_text_and_canvas_on_page_one():
    canvas = {"strokes": [{"points": [{"x": 20, "y": 150}, {"x": 80, "y": 160}]}]}
    g = engine.generate_ot3("Chúc mừng năm mới", canvas, font_uri="hershey:scripts", font_size_mm=8, alignment="CENTER",
                            paper_size="A5", seed=1, v_max_mm_s=30, pen_category="GEL", chars=14)
    assert g.similarity is None and g.complexity == "COMPLEX"          # a drawing makes it complex (SRS 3.2)
    assert g.pages[0].strokes[-1].kind == "canvas"


def test_engine_ot3_needs_template_and_content():
    with pytest.raises(AppError) as e:
        engine.generate_ot3("Xin chào", None, font_uri=None, font_size_mm=8, alignment=None, paper_size="A5", seed=0,
                            v_max_mm_s=30, pen_category=None, chars=7)
    assert e.value.code == "TEMPLATE_REQUIRED"
    with pytest.raises(AppError) as e:
        engine.generate_ot3("  ", None, font_uri="hershey:futural", font_size_mm=8, alignment=None, paper_size="A5",
                            seed=0, v_max_mm_s=30, pen_category=None, chars=0)
    assert e.value.code == "NO_CONTENT"


def test_engine_rejects_non_font_templates():
    with pytest.raises(AppError) as e:
        engine.generate_ot3("Xin", None, font_uri="fonts/calligraphy.json", font_size_mm=8, alignment=None,
                            paper_size="A5", seed=0, v_max_mm_s=30, pen_category=None, chars=3)
    assert e.value.code == "UNSUPPORTED_TEMPLATE"


def test_complexity_follows_pen_category():
    m = tj.Metrics(100.0, 10, 10.0, 30)
    kw = dict(order_type=engine.OrderType.OT3_TEMPLATE, metrics=m, chars=20, has_canvas=False, similarity=None,
              font_size_mm=8.0)
    assert engine.suggest_complexity(pen_category="BALLPOINT", **kw) == "SIMPLE"
    assert engine.suggest_complexity(pen_category="FOUNTAIN", **kw) == "COMPLEX"
    assert engine.suggest_complexity(pen_category="BRUSH", **kw) == "COMPLEX"
