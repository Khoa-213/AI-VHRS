"""FR-08: sizes and styles along the text. Rules (domain/text_layout.py) and the stroke composer (stroke_ai/styled_text.py).
Pure computation, no database. The shapes, offsets and slant are design assumptions: these tests prove the code does what it
says, not that the result looks right on real paper."""
import math

import pytest

from app.core.errors import AppError
from app.domain import text_layout as tl
from app.services.stroke_ai import engine, styled_text as st, text_to_stroke as tts

TEXT = "Xin chào các bạn, chúc mừng năm mới"
KW = dict(font_name="futural", paper_size="A5", font_size_mm=8.0)


def span(sub, text=TEXT, **kw):
    i = text.index(sub)
    return {"start": i, "end": i + len(sub), **kw}


def layout(*spans, text=TEXT, **top):
    return tl.parse({"version": 1, "spans": list(spans), **top}, len(text))


def lines_of(page, tol=0.5):
    """y of the text lines (baselines are where most stroke points sit): group stroke start points by y."""
    ys = sorted(s.points[0][1] for s in page.strokes)
    return ys


def bbox(strokes):
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    return min(xs), min(ys), max(xs), max(ys)


# ===================================================================================== the rules
def test_a_valid_layout_is_kept_in_canonical_form():
    raw = {"version": 1, "line_spacing": 1.5, "spans": [
        {"start": 10, "end": 14, "underline": "double", "italic": False}, {"start": 0, "end": 3, "size_mm": 12, "italic": True}]}
    parsed = tl.parse(raw, 40)
    assert [(s.start, s.end) for s in parsed.spans] == [(0, 3), (10, 14)]                         # sorted
    assert tl.to_json(parsed) == {"version": 1, "line_spacing": 1.5, "spans": [
        {"start": 0, "end": 3, "size_mm": 12.0, "italic": True}, {"start": 10, "end": 14, "underline": "double"}]}
    assert tl.parse(tl.to_json(parsed), 40) == parsed                                              # stable
    assert tl.parse({}, 5).is_plain and tl.parse({"spans": [], "line_spacing": 1}, 5).is_plain
    assert not tl.parse({"line_spacing": 1.2}, 5).is_plain


@pytest.mark.parametrize("raw", [
    "bold", [], {"version": 2}, {"unknown": 1}, {"spans": "x"}, {"line_spacing": 0.5}, {"line_spacing": 3}, {"line_spacing": "1"},
    {"line_spacing": True},
    {"spans": [{"start": 0, "end": 3}]},                                                           # changes nothing
    {"spans": [{"start": 0, "end": 3, "bold": True}]},                                            # no bold
    {"spans": [{"start": 0, "end": 3, "italic": True, "bold": True}]},
    {"spans": [{"start": 0, "end": 3, "italic": "yes"}]}, {"spans": [{"start": 0, "end": 3, "underline": "wavy"}]},
    {"spans": [{"start": 0, "end": 3, "underline": True}]},
    {"spans": [{"start": 3, "end": 3, "italic": True}]}, {"spans": [{"start": 4, "end": 2, "italic": True}]},
    {"spans": [{"start": -1, "end": 2, "italic": True}]}, {"spans": [{"start": 0, "end": 41, "italic": True}]},
    {"spans": [{"start": 0.5, "end": 3, "italic": True}]}, {"spans": [{"start": True, "end": 3, "italic": True}]},
    {"spans": [{"start": 0, "end": 3, "size_mm": 3.9}]}, {"spans": [{"start": 0, "end": 3, "size_mm": 100.1}]},
    {"spans": [{"start": 0, "end": 3, "size_mm": "8"}]}, {"spans": [{"start": 0, "end": 3, "size_mm": False}]},
    {"spans": [{"start": 0, "end": 5, "italic": True}, {"start": 4, "end": 8, "italic": True}]},   # overlap
    {"spans": ["x"]}, {"spans": [{"start": 0, "end": 3, "italic": True, "colour": "red"}]},
    {"spans": [{"start": i, "end": i + 1, "italic": True} for i in range(201)]},
])
def test_bad_layouts_are_refused(raw):
    with pytest.raises(tl.TextLayoutError) as exc:
        tl.parse(raw, 40)
    assert exc.value.message


def test_limits_are_inclusive_and_touching_spans_are_fine():
    ok = tl.parse({"spans": [{"start": 0, "end": 5, "size_mm": 4, "italic": True},
                             {"start": 5, "end": 40, "size_mm": 100}]}, 40)
    assert [s.style.size_mm for s in ok.spans] == [4.0, 100.0]
    assert len(tl.parse({"spans": [{"start": i, "end": i + 1, "italic": True} for i in range(200)]}, 200).spans) == 200
    styles = ok.styles_for(40)
    assert styles[4].italic and not styles[5].italic and styles[5].size_mm == 100.0 and len(styles) == 40


def test_capabilities_describe_the_limits():
    c = tl.capabilities()
    assert c["min_font_size_mm"] == 4.0 and c["bold"] is False and c["styles"] == ["italic", "underline", "strike"]
    assert c["underline"] == ["single", "double"] and c["max_spans"] == 200


# ===================================================================================== the composer
def test_a_plain_layout_gives_exactly_the_plain_composition():
    for text, size, align in ((TEXT, 8.0, "LEFT"), ("Xin chào các bạn. " * 25, 6.0, "JUSTIFY"), ("Việt Nam\n\nxin chào", 9.0, "CENTER"),
                              ("Hà Nội mùa thu " * 8, 10.0, "RIGHT"), ("x" * 120, 7.0, "LEFT")):
        plain = tts.compose_text(text, **{**KW, "font_size_mm": size}, alignment=align, seed=7)
        styled = st.compose_styled(text, tl.parse({}, len(text)), **{**KW, "font_size_mm": size}, alignment=align, seed=7)
        assert len(plain) == len(styled), (text[:10], size, align)
        for a, b in zip(plain, styled):
            assert len(a.strokes) == len(b.strokes) and [s.kind for s in a.strokes] == [s.kind for s in b.strokes]
            for sa, sb in zip(a.strokes, b.strokes):
                assert len(sa.points) == len(sb.points)
                assert all(math.dist(u, v) < 1e-6 for u, v in zip(sa.points, sb.points)), (text[:10], size, align)


def test_the_result_is_deterministic_and_the_seed_matters():
    lay = layout(span("chào", italic=True, underline="single"), span("mừng", size_mm=12))
    a = st.compose_styled(TEXT, lay, **KW, seed=3)
    b = st.compose_styled(TEXT, lay, **KW, seed=3)
    c = st.compose_styled(TEXT, lay, **KW, seed=4)
    pts = lambda pages: [s.points for p in pages for s in p.strokes]
    assert pts(a) == pts(b) and pts(a) != pts(c)


def test_italic_slants_only_the_styled_letters():
    plain = st.compose_styled("Il", tl.parse({}, 2), **KW, variation=0.0)[0].strokes
    slanted = st.compose_styled("Il", layout(span("l", "Il", italic=True), text="Il"), **KW, variation=0.0)[0].strokes
    assert len(plain) == len(slanted) == 2
    assert plain[0].points == slanted[0].points                                    # "I" is untouched
    k = KW["font_size_mm"] / tts.CAP_UNITS
    top_plain, top_slant = min(plain[1].points, key=lambda p: p[1]), min(slanted[1].points, key=lambda p: p[1])
    base_plain, base_slant = max(plain[1].points, key=lambda p: p[1]), max(slanted[1].points, key=lambda p: p[1])
    assert top_slant[1] == pytest.approx(top_plain[1]) and base_slant[1] == pytest.approx(base_plain[1])   # heights unchanged
    assert top_slant[0] - top_plain[0] == pytest.approx(st.SLANT * (9.0 - (-12.0)) * k, abs=1e-6)         # top leans right
    assert base_slant[0] == pytest.approx(base_plain[0], abs=1e-6)                                          # the baseline stays put
    angle = math.degrees(math.atan2(top_slant[0] - base_slant[0], base_slant[1] - top_slant[1]))
    assert 11 < angle < 13


def test_underline_is_one_stroke_per_line_and_run_below_the_letters():
    word = "Xin chào"
    base = st.compose_styled(word, tl.parse({}, len(word)), **KW, variation=0.0)[0].strokes
    under = st.compose_styled(word, layout(span("Xin chào", word, underline="single"), text=word), **KW, variation=0.0)[0].strokes
    assert len(under) == len(base) + 1 and under[:-1] == base                       # letters first, the line last
    line = under[-1]
    assert len(line.points) == 2 and line.points[0][1] == line.points[1][1] and line.kind == "base"
    x0, y0, x1, y1 = bbox(base)
    assert line.points[0][0] == pytest.approx(x0, abs=1.5) and line.points[1][0] >= x1 - 0.1   # spans the text (joined across the space)
    k = KW["font_size_mm"] / tts.CAP_UNITS
    baseline = tts.MARGIN_MM + (tts.CAP_UNITS + tts.HEADROOM_UNITS) * k
    assert line.points[0][1] > y1                                                   # below every letter
    assert line.points[0][1] == pytest.approx(baseline + st.UNDERLINE_U * k)        # below where the descenders reach (7 units)

    # a space that is not underlined splits the run in two
    apart = st.compose_styled(word, layout(span("Xin", word, underline="single"), span("chào", word, underline="single"), text=word),
                              **KW, variation=0.0)[0].strokes
    assert len(apart) == len(base) + 2
    assert apart[-2].points[1][0] < apart[-1].points[0][0]


def test_double_underline_and_strike():
    word = "Xin chào"
    base = len(st.compose_styled(word, tl.parse({}, 8), **KW, variation=0.0)[0].strokes)
    double = st.compose_styled(word, layout(span("Xin chào", word, underline="double"), text=word), **KW, variation=0.0)[0].strokes
    assert len(double) == base + 2
    assert double[-1].points[0][1] > double[-2].points[0][1]
    assert double[-1].points[0][1] - double[-2].points[0][1] == pytest.approx(st.UNDERLINE_GAP_U * 8.0 / tts.CAP_UNITS)
    strike = st.compose_styled(word, layout(span("Xin chào", word, strike=True), text=word), **KW, variation=0.0)[0].strokes
    plain = st.compose_styled(word, tl.parse({}, 8), **KW, variation=0.0)[0].strokes
    assert len(strike) == base + 1
    y_line = strike[-1].points[0][1]
    x0, y0, x1, y1 = bbox(plain)
    assert y0 < y_line < y1                                                         # through the letters, not under them
    assert strike[-1].points[0][0] <= x0 + 1.5 and strike[-1].points[1][0] >= x1 - 0.1   # across all of them, not only the space


def test_underline_that_wraps_is_one_stroke_per_line():
    text = "chữ " * 40
    lay = layout(span("chữ chữ", text, underline="single"), text=text)
    big = tl.parse({"spans": [{"start": 0, "end": len(text) - 1, "underline": "single"}]}, len(text))
    pages = st.compose_styled(text, big, **KW, variation=0.0)
    lines = {round(s.points[0][1], 3) for p in pages for s in p.strokes if len(s.points) == 2 and s.points[0][1] == s.points[1][1]
             and s.points[1][0] - s.points[0][0] > 30}
    assert len(lines) >= 3                                                           # several lines each have their own underline
    assert lay is not None


def test_sizes_vary_along_a_line_and_share_the_baseline():
    text = "aa AA aa"
    lay = layout(span("AA", text, size_mm=16), text=text)
    plain_h = lambda t, **kw: bbox(st.compose_styled(t, tl.parse({}, len(t)), **KW, variation=0.0)[0].strokes)
    page = st.compose_styled(text, lay, **KW, variation=0.0)[0]
    big = [s for s in page.strokes if max(p[1] for p in s.points) - min(p[1] for p in s.points) > 12]    # the 16 mm capitals
    small = [s for s in page.strokes if max(p[1] for p in s.points) - min(p[1] for p in s.points) <= 8]
    assert len(big) >= 2 and len(small) >= 4
    assert max(p[1] for s in big for p in s.points) == pytest.approx(max(p[1] for s in small for p in s.points), abs=0.01)   # one baseline
    assert bbox(page.strokes)[0] == pytest.approx(plain_h("aa AA aa")[0], abs=0.5)
    assert bbox(page.strokes)[1] >= tts.MARGIN_MM - 0.01                            # the tall letters stay inside the margin
    # a larger size widens the text
    assert bbox(page.strokes)[2] > plain_h(text)[2] + 5
    # and the line is as tall as its tallest letter: the next line starts lower than with plain text
    two = "aa AA aa\nbb"
    lay2 = layout(span("AA", two, size_mm=16), text=two)
    y_plain = max(p[1] for s in st.compose_styled(two, tl.parse({}, len(two)), **KW, variation=0.0)[0].strokes for p in s.points)
    y_big = max(p[1] for s in st.compose_styled(two, lay2, **KW, variation=0.0)[0].strokes for p in s.points)
    assert y_big > y_plain + 8


def test_line_spacing_moves_the_lines_apart():
    text = "ab\ncd\nef"
    ys = lambda sp: sorted({round(max(p[1] for p in s.points), 1) for s in st.compose_styled(
        text, tl.parse({"line_spacing": sp}, len(text)), **KW, variation=0.0)[0].strokes})
    tight, wide = ys(0.8), ys(2.0)
    assert wide[-1] - wide[0] == pytest.approx((tight[-1] - tight[0]) * 2.0 / 0.8, rel=0.02)


def test_pages_fill_by_line_height_and_the_limits_are_reported():
    text = "Xin chào các bạn. " * 15
    plain = tts.compose_text(text, **{**KW, "paper_size": "A6"})
    tall = st.compose_styled(text, tl.parse({"line_spacing": 2.0}, len(text)), **{**KW, "paper_size": "A6"})
    assert len(tall) > len(plain)                                                   # taller lines: more pages
    with pytest.raises(AppError) as exc:
        st.compose_styled("A", tl.parse({"spans": [{"start": 0, "end": 1, "size_mm": 100}]}, 1), **{**KW, "paper_size": "A6"})
    assert exc.value.code == "FONT_TOO_LARGE"
    with pytest.raises(AppError) as exc:                                            # span sizes count for the page, not only the base size
        st.compose_styled("A" * 3, tl.parse({"spans": [{"start": 0, "end": 3, "size_mm": 60}]}, 3), **{**KW, "paper_size": "A6"})
    assert exc.value.code == "FONT_TOO_LARGE"
    with pytest.raises(AppError) as exc:
        st.compose_styled("Xin chào các bạn. " * 4000, tl.parse({"line_spacing": 1.5}, 72000), **{**KW, "paper_size": "A6"})
    assert exc.value.code == "TEXT_TOO_LONG"
    with pytest.raises(AppError) as exc:
        st.compose_styled("Xin 漢", tl.parse({"line_spacing": 1.5}, 5), **KW)
    assert exc.value.code == "UNSUPPORTED_CHARS" and exc.value.details == [{"index": 4, "char": "漢"}]


def test_styles_follow_their_characters_through_normalisation_and_wrapping():
    text = "Việt…Nam"                                                                # the ellipsis becomes three dots
    lay = layout(span("Nam", text, underline="single"), text=text)
    out = st.compose_styled(text, lay, **KW, variation=0.0)[0].strokes
    under = [s for s in out if len(s.points) == 2 and s.points[0][1] == s.points[1][1] and s.points[1][0] - s.points[0][0] > 10]
    assert len(under) == 1
    ink = bbox([s for s in out if s not in under])
    assert under[0].points[1][0] == pytest.approx(ink[2], abs=2.5) and under[0].points[0][0] > ink[0] + 15   # only under "Nam"


# ===================================================================================== the engine
def test_the_engine_uses_the_layout_and_does_not_touch_the_complexity():
    kw = dict(font_uri="hershey:futural", font_size_mm=8, alignment="LEFT", paper_size="A5", seed=1, v_max_mm_s=40.0,
              pen_category="BALLPOINT", chars=30)
    plain = engine.generate_ot3(TEXT, None, **kw)
    lay = tl.to_json(layout(span("chào", underline="double", italic=True), span("năm", size_mm=5)))
    styled = engine.generate_ot3(TEXT, None, **kw, layout=lay)
    assert styled.complexity == plain.complexity                                       # styles never change the price
    assert len(styled.pages[0].strokes) > len(plain.pages[0].strokes) and styled.engine["layout"] == {"spans": 2, "line_spacing": 1.0}
    assert "layout" not in plain.engine
    same = engine.generate_ot3(TEXT, None, **kw, layout={"version": 1, "spans": [], "line_spacing": 1.0})
    assert "layout" not in same.engine and same.pages[0].strokes[0].points == plain.pages[0].strokes[0].points
    for bad in ({"spans": [{"start": 0, "end": 999, "italic": True}]}, {"version": 9}, {"spans": [{"start": 0, "end": 2, "bold": True}]}):
        with pytest.raises(AppError) as exc:
            engine.generate_ot3(TEXT, None, **kw, layout=bad)
        assert exc.value.status == 422 and exc.value.code == "INVALID_LAYOUT"


def test_underlines_add_strokes_but_never_push_the_complexity_up():
    """The suggestion looks at pen lifts per character; the extra strokes of an underline must not tip it (no surcharge for styles)."""
    kw = dict(font_uri="hershey:futural", font_size_mm=8, alignment="LEFT", paper_size="A5", seed=1, v_max_mm_s=40.0, pen_category="BALLPOINT")
    probe = engine.generate_ot3(TEXT, None, **kw, chars=100)
    chars = int(probe.metrics.pen_lift_count / 2.4)                                   # plain: 2.4 lifts per character, just under 2.5
    words = [m for m in __import__("re").finditer(r"\S+", TEXT)]
    lay = {"spans": [{"start": m.start(), "end": m.end(), "underline": "single"} for m in words]}
    plain = engine.generate_ot3(TEXT, None, **kw, chars=chars)
    styled = engine.generate_ot3(TEXT, None, **kw, chars=chars, layout=lay)
    assert styled.metrics.pen_lift_count / chars > 2.5 >= plain.metrics.pen_lift_count / chars    # the styled page alone would tip it
    assert plain.complexity == styled.complexity == "SIMPLE"


# ===================================================================================== placement on the page (2026-11-07)
SHORT = "Kính gửi quý khách hàng thân mến"


def centre(strokes):
    x0, y0, x1, y1 = bbox(strokes)
    return (x0 + x1) / 2, (y0 + y1) / 2


def test_margins_and_vertical_alignment_are_checked_and_stored_in_canonical_form():
    lay = tl.parse({"margins_mm": {"top": 40, "left": 25.5}, "vertical_align": "BOTTOM"}, 5)
    assert lay.is_plain                                                               # placement is not a style
    assert tl.to_json(lay) == {"version": 1, "line_spacing": 1.0, "spans": [], "vertical_align": "BOTTOM",
                               "margins_mm": {"top": 40.0, "bottom": 15.0, "left": 25.5, "right": 15.0}}
    old = tl.parse({"spans": []}, 5)                                                  # stored before: from the top, 15 mm
    assert old.page_vertical_align == "TOP" and old.page_margins == tl.Margins.even(15) and "vertical_align" not in tl.to_json(old)
    assert old.with_defaults().vertical_align == "MIDDLE" and lay.with_defaults().vertical_align == "BOTTOM"
    assert tl.parse({"margins_mm": {"top": 5, "bottom": 80}}, 1).page_margins.bottom == 80      # limits are inclusive
    for bad in ({"margins_mm": {"top": 4.9}}, {"margins_mm": {"left": 81}}, {"margins_mm": {"top": "10"}},
                {"margins_mm": {"top": True}}, {"margins_mm": {"middle": 10}}, {"margins_mm": 10},
                {"vertical_align": "CENTER"}, {"vertical_align": "middle"}):
        with pytest.raises(tl.TextLayoutError):
            tl.parse(bad, 5)


def test_capabilities_describe_the_placement():
    c = tl.capabilities()
    assert c["default_alignment"] == "CENTER" and c["default_vertical_align"] == "MIDDLE"
    assert c["vertical_alignments"] == ["TOP", "MIDDLE", "BOTTOM"]
    assert c["margins_mm"] == {"min": 5.0, "max": 80.0, "default": 15.0, "sides": ["top", "bottom", "left", "right"],
                               "min_writing_area_mm": 30.0}


@pytest.mark.parametrize("styled", [False, True])
def test_centred_text_sits_in_the_middle_of_the_sheet(styled):
    kw = dict(KW, alignment="CENTER", vertical_align="MIDDLE", variation=0.0)
    if styled:
        page = st.compose_styled(SHORT, layout(span("quý", text=SHORT, size_mm=12), text=SHORT), **kw)[0]
    else:
        page = tts.compose_text(SHORT, **kw)[0]
    cx, cy = centre(page.strokes)
    assert abs(cx - 148 / 2) < 1.0 and abs(cy - 210 / 2) < 0.01                     # A5 is 148 x 210 mm


def test_the_customer_margins_move_and_bound_the_text():
    m = tl.Margins(top=40, bottom=20, left=25, right=35)
    kw = dict(KW, variation=0.0, margins=m)
    mid = tts.compose_text(SHORT, alignment="CENTER", vertical_align="MIDDLE", **kw)[0]
    cx, cy = centre(mid.strokes)
    assert abs(cy - (40 + 210 - 20) / 2) < 0.01 and abs(cx - (25 + 148 - 35) / 2) < 1.0
    top = tts.compose_text(SHORT, alignment="LEFT", vertical_align="TOP", **kw)[0]
    x0, y0, _, _ = bbox(top.strokes)
    assert 25 - 0.5 <= x0 < 27 and 40 <= y0 < 40 + 8 * 2                               # from the top-left of the writing area
    low = tts.compose_text(SHORT, alignment="RIGHT", vertical_align="BOTTOM", **kw)[0]
    _, _, x1, y1 = bbox(low.strokes)
    assert abs(y1 - (210 - 20)) < 0.01 and 148 - 35 - 2 < x1 <= 148 - 35 + 0.5
    # wider side margins leave a narrower line: more lines for the same text
    long = " ".join([SHORT] * 4)
    assert len(set(round(y) for y in lines_of(tts.compose_text(long, **KW, margins=tl.Margins(left=50, right=50))[0]))) > \
        len(set(round(y) for y in lines_of(tts.compose_text(long, **KW)[0])))


def test_margins_that_leave_no_room_are_refused():
    with pytest.raises(AppError) as exc:
        tts.compose_text("Xin chào", font_name="futural", paper_size="A6", margins=tl.Margins(left=50, right=40))
    assert exc.value.status == 422 and exc.value.code == "MARGINS_TOO_LARGE" and exc.value.details["area_mm"][0] == 15
    with pytest.raises(AppError) as exc:
        st.compose_styled("Xin chào", layout(text="Xin chào"), font_name="futural", paper_size="A5",
                          margins=tl.Margins(left=60, right=60))
    assert exc.value.code == "MARGINS_TOO_LARGE"


def test_every_page_of_a_long_text_is_placed_and_stays_on_the_sheet():
    long = "\n".join([SHORT] * 40)
    top = tts.compose_text(long, **KW, variation=0.0)
    mid = tts.compose_text(long, **KW, variation=0.0, vertical_align="MIDDLE")
    assert len(top) == len(mid) > 1
    for page in mid:
        x0, y0, x1, y1 = bbox(page.strokes)
        assert 0 <= y0 and y1 <= 210 and abs((y0 + y1) / 2 - 105) < 0.01
    assert bbox(mid[-1].strokes)[1] > bbox(top[-1].strokes)[1] + 20                  # the short last page comes down


def test_the_engine_places_the_text_and_keeps_the_complexity():
    kw = dict(font_uri="hershey:futural", font_size_mm=8, paper_size="A5", seed=1, v_max_mm_s=40.0,
              pen_category="BALLPOINT", chars=30)
    legacy = engine.generate_ot3(SHORT, None, alignment="LEFT", **kw)                # no layout: as before
    assert legacy.engine["vertical_align"] == "TOP" and legacy.engine["margins_mm"]["top"] == 15
    assert legacy.pages[0].strokes[0].points == tts.compose_text(SHORT, font_name="futural", paper_size="A5", seed=1)[0].strokes[0].points
    lay = {"version": 1, "vertical_align": "MIDDLE", "margins_mm": {"top": 30}}
    placed = engine.generate_ot3(SHORT, None, alignment="CENTER", **kw, layout=lay)
    assert placed.engine["vertical_align"] == "MIDDLE" and placed.engine["margins_mm"]["top"] == 30
    assert "layout" not in placed.engine                                             # no styles
    assert placed.complexity == legacy.complexity and placed.metrics.pen_lift_count == legacy.metrics.pen_lift_count
    assert abs(centre(placed.pages[0].strokes)[1] - (30 + 210 - 15) / 2) < 0.01
    canvas = {"strokes": [{"points": [{"x": 10, "y": 10}, {"x": 20, "y": 12}]}]}
    drawn = engine.generate_ot3(SHORT, canvas, alignment="CENTER", **kw, layout=lay)
    # the drawing stays where it was drawn (U7 may move it in the writing order and draw it the other way)
    assert [sorted([s.points[0], s.points[-1]]) for s in drawn.pages[0].strokes if s.kind == "canvas"] == [[(10.0, 10.0), (20.0, 12.0)]]
    with pytest.raises(AppError) as exc:
        engine.generate_ot3(SHORT, None, alignment="LEFT", **kw, layout={"margins_mm": {"left": 80, "right": 80}})
    assert exc.value.code == "MARGINS_TOO_LARGE"
    with pytest.raises(AppError) as exc:
        engine.generate_ot3(SHORT, None, alignment="LEFT", **kw, layout={"vertical_align": "UP"})
    assert exc.value.code == "INVALID_LAYOUT"
