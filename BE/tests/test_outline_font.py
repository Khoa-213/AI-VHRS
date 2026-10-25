"""Outline fonts -> pen strokes (OT-3). Uses DejaVu Sans, the font already shipped with the backend (free licence), so the
tests do not depend on any downloaded file. Pure computation, no database."""
import json
from pathlib import Path

import numpy as np
import pytest

from app.core.errors import AppError
from app.integrations.storage import InMemoryStorage
from app.services.stroke_ai import engine, outline_font as of, text_to_stroke as tts

FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "DejaVuSans.ttf"


@pytest.fixture(scope="module")
def data():
    return FONT.read_bytes()


@pytest.fixture(scope="module")
def src(data):
    return of.OutlineSource(data)


def test_charset_covers_the_srs_vietnamese_letters():
    cs = of.vietnamese_charset()
    for ch in "ăâêôơưđĐắầẳẵặếềểễệốồổỗộớờởỡợứừửữựỳỷỹỵạẠ":
        assert ch in cs
    assert len([c for c in cs if c.isalpha()]) >= 178            # 89 lower + 89 upper (SRS S0)


def test_font_coverage_check_reports_missing_glyphs(data):
    assert of.missing_glyphs(data) == []
    with pytest.raises(AppError):
        of.missing_glyphs(b"not a font")                          # an unreadable file is an error, never "full coverage"


def test_garbage_is_not_a_font():
    with pytest.raises(AppError) as e:
        of.OutlineSource(b"not a font at all")
    assert e.value.code == "FONT_UNREADABLE"


def test_a_vietnamese_letter_becomes_a_body_and_separate_marks(src):
    g = src.char("ế")
    assert g is not None and g.base and g.marks                  # e body, circumflex and acute as their own strokes
    assert src.char("e").marks == []
    assert src.char("ạ").marks                                   # the dot below is a mark too
    assert src.char(" ") is None


def test_strokes_stay_inside_the_glyph_box_and_the_baseline_is_where_the_layout_expects(src):
    g = src.char("H")
    ys = [y for s in g.base for _, y in s]
    assert -12.5 < min(ys) < -9.0 and 7.0 < max(ys) < 10.5       # cap line ~ -12, baseline ~ +9 (Hershey convention)
    assert g.advance > 5


def test_compose_text_with_an_outline_font_lays_out_lines_and_keeps_marks_after_words(src):
    pages = tts.compose_text("Việt Nam\nxin chào", source=src, paper_size="A5", font_size_mm=8.0)
    kinds = [s.kind for s in pages[0].strokes]
    assert "base" in kinds and "mark" in kinds
    first_word = kinds[:kinds.index("mark")]
    assert first_word and all(k == "base" for k in first_word)
    xs = [p[0] for s in pages[0].strokes for p in s.points]
    ys = [p[1] for s in pages[0].strokes for p in s.points]
    assert min(xs) >= tts.MARGIN_MM - 1 and max(xs) <= 148 - tts.MARGIN_MM + 1 and 0 < min(ys) and max(ys) < 210


def test_unsupported_characters_are_reported_not_invented(src):
    with pytest.raises(AppError) as e:
        tts.compose_text("abc 中", source=src, paper_size="A5")
    assert e.value.code == "UNSUPPORTED_CHARS"


def test_glyph_cache_roundtrip_is_exact_and_rejects_another_font(src, data):
    for ch in "Việt":
        src.char(ch)
    blob = json.loads(json.dumps(src.export_cache()))
    fresh = of.OutlineSource(data)
    assert fresh.load_cache(blob) == len(blob["glyphs"]) > 0
    a, b = src.char("ế"), fresh.char("ế")
    assert a.base == b.base and a.marks == b.marks and a.advance == b.advance
    other = of.OutlineSource(data)
    blob["font_sha256"] = "0" * 64
    assert other.load_cache(blob) == 0                            # cache of another file is never trusted


def test_engine_uses_the_stored_font_and_flags_the_reconstructed_order(data):
    store = InMemoryStorage()
    store.put("fonts/dejavu/DejaVuSans.ttf", data)
    of._BY_PATH.clear()
    gen = engine.generate_ot3("Nét Việt", None, font_uri="outline:fonts/dejavu/DejaVuSans.ttf", font_size_mm=8.0,
                              alignment="LEFT", paper_size="A5", seed=1, v_max_mm_s=30.0, pen_category="GEL", chars=8,
                              font_loader=store.read)
    assert gen.engine["name"] == "outline-centerline-compose" and gen.engine["stroke_order"] == "reconstructed"
    assert gen.metrics.total_stroke_mm > 0
    with pytest.raises(AppError) as e:                           # a missing font file is a clear error, never a silent fallback
        of._BY_PATH.clear()
        engine.generate_ot3("x", None, font_uri="outline:fonts/none/none.ttf", font_size_mm=8.0, alignment="LEFT",
                            paper_size="A5", seed=1, v_max_mm_s=30.0, pen_category="GEL", chars=1, font_loader=store.read)
    assert e.value.code == "FONT_FILE_MISSING"


def test_load_source_uses_the_precomputed_cache_from_storage(data):
    store = InMemoryStorage()
    s0 = of.OutlineSource(data)
    s0.precompute("Việt")
    store.put("fonts/x/f.ttf", data)
    store.put("fonts/x/f.ttf" + of.CACHE_SUFFIX, json.dumps(s0.export_cache()).encode())
    of._BY_PATH.clear()
    of._SOURCES.clear()
    s1 = of.load_source("fonts/x/f.ttf", store.read)
    assert "ế" in s1._cache or "V" in s1._cache                  # preloaded, no thinning needed at request time
    assert of.load_source("fonts/x/f.ttf", store.read) is s1     # and kept in memory for the next request
