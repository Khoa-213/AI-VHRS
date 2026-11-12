"""Upgrade U7 (docs/UPGRADE_AI_ROBOT_PLAN.md 3.6): pen-up travel is reduced by changing only the order of whole words;
a word's strokes keep their order and direction, only free strokes may be drawn the other way, never worse than before.
"""
import math

from app.services.stroke_ai import engine, path_order
from app.services.stroke_ai.trajectory import Stroke, compute_metrics
from tests.test_u4_regions import _scan


def _word(x: float, y: float, g: int) -> list[Stroke]:
    """A 'word' of three strokes (two letters and a tone mark above, written last)."""
    return [Stroke([(x, y), (x + 3, y + 5)], "base", g), Stroke([(x + 4, y + 5), (x + 7, y)], "base", g),
            Stroke([(x + 3, y - 2), (x + 4, y - 3)], "mark", g)]


def _words_intact(before: list[Stroke], res: path_order.OrderResult) -> bool:
    pos = {old: new for new, old in enumerate(res.order)}
    for g in {s.group for s in before if s.group is not None}:
        idx = [i for i, s in enumerate(before) if s.group == g]
        if [pos[i] for i in idx] != list(range(pos[idx[0]], pos[idx[0]] + len(idx))):
            return False
    return True


def test_scrambled_words_are_reordered_and_each_word_stays_whole():
    xs = [10, 90, 30, 70, 50, 110, 20, 100]                 # one line, written in a jumping order
    strokes = [s for g, x in enumerate(xs) for s in _word(x, 20, g)]
    res = path_order.optimise(strokes)
    out = path_order.apply(strokes, res.order, res.reversed)
    assert res.travel_after_mm < res.travel_before_mm * 0.6
    assert math.isclose(path_order.travel_mm(out), res.travel_after_mm, abs_tol=0.01)
    assert sorted(res.order) == list(range(len(strokes))) and not res.reversed
    assert _words_intact(strokes, res)
    assert res.order[:3] == [0, 1, 2]                       # the first word stays first
    assert [s.kind for s in out[:3]] == ["base", "base", "mark"]   # marks still after their letters


def test_only_free_strokes_are_turned_round():
    word = _word(10, 20, 0)
    free = [Stroke([(80, 21), (40, 21)], "canvas"), Stroke([(90, 60), (20, 60)], "base")]   # drawn "backwards"
    res = path_order.optimise(word + free)
    assert res.reversed and res.reversed <= {3, 4}
    far_word = _word(60, 20, 1)
    far_word[0] = Stroke(list(reversed(far_word[0].points)), "base", 1)
    res2 = path_order.optimise(word + far_word + free)
    assert not ({3, 4, 5} & res2.reversed)                  # word strokes never reversed


def test_already_good_order_is_left_alone():
    strokes = [s for g, x in enumerate([10, 20, 30, 40]) for s in _word(x, 20, g)]
    res = path_order.optimise(strokes)
    assert res.order == list(range(len(strokes))) and res.travel_after_mm == res.travel_before_mm
    assert path_order.optimise(strokes[:3]).order == [0, 1, 2]


def test_ot3_generation_reports_the_gain_and_the_metrics_use_the_new_order():
    g = engine.generate_ot3("Kính gửi quý khách hàng thân mến, chúc mừng năm mới an khang thịnh vượng", None,
                            font_uri="hershey:scripts", font_size_mm=8, alignment="CENTER", paper_size="A5", seed=1,
                            v_max_mm_s=30, pen_category="GEL", chars=70)
    po = g.engine["path_order"]
    assert po["method"] == path_order.METHOD and po["travel_mm_after"] <= po["travel_mm_before"]
    assert g.metrics.travel_mm == compute_metrics(g.pages, 30).travel_mm == po["travel_mm_after"]


def test_ot1_regions_follow_their_strokes():
    g = engine.generate_ot1([engine.ImageSource(_scan())], paper_size="A5", v_max_mm_s=30, pen_category="GEL", chars=20)
    page = g.pages[0]
    covered = sorted(i for r in g.regions for i in range(r.stroke_start, r.stroke_end))
    assert covered == list(range(len(page.strokes)))
    for r in g.regions:
        x0, y0, x1, y1 = r.bbox
        assert all(x0 - .01 <= x <= x1 + .01 and y0 - .01 <= y <= y1 + .01
                   for s in page.strokes[r.stroke_start:r.stroke_end] for x, y in s.points)
        assert {s.group for s in page.strokes[r.stroke_start:r.stroke_end]} == {r.region_no}
    assert g.engine["path_order"]["travel_mm_after"] <= g.engine["path_order"]["travel_mm_before"]


# ---- opt-in jerk limit (motion/plan.py) ----------------------------------------------------------------
def test_without_a_jerk_limit_the_speed_profile_is_exactly_as_before():
    import numpy as np
    from app.services.motion import plan as mp
    p = mp.resample_stroke([(0, 0), (30, 0), (30, 20)], 0.2)
    kw = dict(v_max=40, a_lat=2000.0, a_tan=1000.0)
    assert np.array_equal(mp.speed_profile(p, **kw), mp.speed_profile(p, **kw, j_max=None))
    assert mp.MotionConfig(a_lat_mm_s2=1.0).missing().count("j_max_mm_s3") == 0


def test_the_jerk_limit_holds_and_keeps_every_other_limit():
    import numpy as np
    from app.services.motion import plan as mp
    from app.services.stroke_ai import text_to_stroke as tts
    strokes = [mp.resample_stroke([(0, 0), (100, 0)], 0.2), mp.resample_stroke([(0, 0), (20, 0), (20, 20), (40, 25)], 0.2)]
    strokes += [mp.resample_stroke(s.points, 0.2) for s in tts.compose_text("Thương nhớ", font_name="scripts",
                                                                           paper_size="A6", font_size_mm=8, seed=2)[0].strokes]
    for J in (100000.0, 20000.0):
        for p in [s for s in strokes if len(s) >= 3]:
            v0 = mp.speed_profile(p, v_max=40, a_lat=2000.0, a_tan=1000.0)
            v = mp.speed_profile(p, v_max=40, a_lat=2000.0, a_tan=1000.0, j_max=J)
            seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
            assert np.all(v <= v0 + 1e-9) and v[0] == v[-1] == 5.0 and v.min() >= 5.0 - 1e-9
            assert np.all(np.abs(v[1:] ** 2 - v[:-1] ** 2) <= 2 * 1000.0 * seg + 1e-6)
            assert np.abs(mp.jerk_of(p, v)).max() <= J * (1 + 1e-6)
    line = strokes[0]
    v = mp.speed_profile(line, v_max=40, a_lat=2000.0, a_tan=1000.0, j_max=100000.0)
    assert v.max() > 39.9                                       # a long line still reaches full speed


def test_a_station_turns_the_jerk_limit_on_in_its_motion_block():
    from app.services.motion import plan as mp
    cfg = mp.MotionConfig.from_dict({"a_lat_mm_s2": 2000, "a_tan_mm_s2": 1000, "travel_speed_mm_s": 100,
                                     "approach_speed_mm_s": 10, "pen_up_clearance_mm": 5, "spring_k_n_per_mm": 1,
                                     "max_spring_travel_mm": 5, "f_target_n": 1, "v_max_mm_s": 40})
    cfg.require()                                               # off: still a complete configuration
    assert cfg.j_max_mm_s3 is None
    on = mp.MotionConfig.from_dict({**cfg.__dict__, "j_max_mm_s3": 50000})
    assert on.j_max_mm_s3 == 50000.0
    bad = mp.MotionConfig.from_dict({**cfg.__dict__, "j_max_mm_s3": -1})
    try:
        bad.require()
        raise AssertionError("negative j_max accepted")
    except mp.PlanError as e:
        assert e.code == "INVALID_CONFIG" and "j_max_mm_s3" in e.message
