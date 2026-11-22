"""OT-1 recovery v2, R4 (docs/OT1_RECOVERY_V2_PLAN.md): v2 behind the Admin setting `ot1_recovery_engine`, similarity v2,
`noise_removed`. Images are drawn here (no files, no database); the API path is in tests/test_api_workshop.py."""
import cv2
import numpy as np
import pytest

from app.services.admin_system import SPECS, SettingError
from app.services.stroke_ai import engine, recovery_v2 as R2

W, H = 1400, 700
LINE_YS = list(range(80, H, 70))


def _ruled_letter() -> bytes:
    img = np.full((H, W), 236, np.uint8)
    for y in LINE_YS:
        cv2.line(img, (0, y), (W, y), 150, 2, cv2.LINE_AA)
    rng = np.random.default_rng(3)
    for row, y in enumerate(LINE_YS[:-1]):
        x = 120
        while x < W - 160:
            pts = np.array([[x + i * 7, y + 32 + int(14 * np.sin(i * 0.9 + row))] for i in range(10)], np.int32)
            cv2.polylines(img, [pts], False, 40, 4, cv2.LINE_AA)
            x += int(rng.uniform(90, 130))
    return cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))[1].tobytes()


def _gen(engine_name: str | None):
    kw = {} if engine_name is None else {"recovery_engine": engine_name}
    return engine.generate_ot1([engine.ImageSource(_ruled_letter())], paper_size="A4", v_max_mm_s=40.0,
                               pen_category="GEL", chars=200, **kw)


def test_the_product_default_is_v2_and_the_engine_call_default_stays_v1():
    """Owner 2026-11-22: OT-1 sketches are drawn with v2 unless Admin sets "v1". `generate_ot1` itself (used directly by
    engine tests) keeps v1 when no engine is passed; the product always passes the setting."""
    g = _gen(None)
    assert g.engine["name"] == "zhang-suen-skeleton" and g.engine["version"] == engine.ENGINE_VERSION
    assert g.engine["similarity_method"] == "ink-iou-v1" and "noise_removed" not in g.engine["pages"][0]
    assert SPECS["ot1_recovery_engine"].default == "v2"


def test_v2_records_what_it_removed_and_its_own_similarity():
    g = _gen("v2")
    assert g.engine["name"] == "ot1-recovery-v2" and g.engine["version"] == "2"
    assert g.engine["similarity_method"] == "ink-f1-v2" and g.engine["regions"]["method"] == "word-local-ink-f1-v2"
    noise = g.engine["pages"][0]["noise_removed"]
    assert noise["counts"]["RULING"] >= len(LINE_YS) - 1                  # the ruled lines (in pieces between letters)
    assert noise["pieces"] and all(p["reason"] in ("RULING", "FOLD", "EDGE", "BLOB", "COLOUR") for p in noise["pieces"])
    assert len(noise["pieces"]) <= R2.NOISE_MAX_PIECES
    x0, y0, x1, y1 = noise["pieces"][0]["bbox_mm"]
    assert 0 <= x0 < x1 <= 210 and 0 <= y0 <= y1 <= 297                  # page millimetres (A4)
    assert 80.0 <= g.similarity <= 100.0 and g.complexity in ("SIMPLE", "MEDIUM", "COMPLEX")
    assert g.regions and all(0.0 <= r.confidence <= 1.0 for r in g.regions)


def test_unknown_engine_value_falls_back_to_v1():
    assert _gen("v9").engine["name"] == "zhang-suen-skeleton"


def test_setting_accepts_only_v1_or_v2():
    check = SPECS["ot1_recovery_engine"].check
    assert check("v2") == "v2" and check("v1") == "v1"
    for bad in ("v3", 2, None, "V2"):
        with pytest.raises(SettingError):
            check(bad)


def test_ink_f1_is_high_for_a_perfect_trace_and_low_for_junk():
    ink = np.zeros((200, 400), np.uint8)
    cv2.line(ink, (20, 100), (380, 100), 255, 5)
    good = [np.array([[20.0, 100.0], [380.0, 100.0]])]
    junk = [np.array([[20.0, 20.0], [380.0, 20.0]])]
    assert R2.ink_f1(good, ink, 5.0) > 95.0
    assert R2.ink_f1(junk, ink, 5.0) < 5.0


def test_v2_complexity_does_not_use_the_similarity():
    """Owner, 2026-11-22 (option b): with v2 the K_cx suggestion ignores the similarity; v1 keeps its thresholds."""
    from app.models.order import OrderType
    from app.services.stroke_ai.trajectory import Metrics
    m = Metrics(total_stroke_mm=1000.0, pen_lift_count=100, estimated_writing_sec=60, travel_mm=0.0)
    kw = dict(order_type=OrderType.OT1_COPY_RESTORE, pen_category="GEL", metrics=m, chars=100, has_canvas=False,
              font_size_mm=None)
    assert engine.suggest_complexity(similarity=10.0, **kw) == "COMPLEX"                                  # v1: low -> COMPLEX
    assert engine.suggest_complexity(similarity=10.0, similarity_method="ink-f1-v2", **kw) == "SIMPLE"
    assert engine.suggest_complexity(similarity=99.0, similarity_method="ink-f1-v2", **kw) == "SIMPLE"
    assert _gen("v2").engine["complexity_basis"] == "pen-lifts-and-pen-type"
