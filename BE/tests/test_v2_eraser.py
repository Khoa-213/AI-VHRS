"""Eraser (`op: "erase"`, owner request 2026-11-24): paint over unwanted strokes and only the parts under the brush go;
the rest of each stroke stays exactly where it was. Staff and customers, every order type; several brush strokes are
saved in one edit (one revision / one sketch version). The AI assistant cannot erase (it would have to write
coordinates). See FE_API_GUIDE.md 7r / 7t."""
import math

import pytest

from app.core.errors import AppError
from app.services import sketch_geometry as geo
from app.services.ai import order_tools
from app.services.stroke_ai import trajectory as tj
from tests.test_api_orders import API
from tests.test_api_workshop import W, _err, _ot3, cust, staff, store, wcat  # noqa: F401
from tests.test_v2_staff_editor import _customer_v1

SK = "/sketch"


def _doc():
    page = tj.Page("A5")
    page.strokes = [tj.Stroke([(20, 20), (25, 15), (30, 20)], "base", 0), tj.Stroke([(31, 20), (40, 20)], "base", 0),
                    tj.Stroke([(60, 60), (70, 70), (80, 60)], "base", 1)]
    return geo.from_generated([page], {"name": "test"})


def _strokes(doc):
    return {st["id"]: st for p in doc["pages"] for st in p["strokes"]}


def _dist_to_polyline(p, pts):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d2 = dx * dx + dy * dy
        k = 0.0 if d2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
        best = min(best, math.dist(p, (a[0] + k * dx, a[1] + k * dy)))
    return best


def _brush(x, y, r=2.0):
    return {"paths": [{"points": [[x, y]], "radius_mm": r}]}


# ---------------------------------------------------------------------------------------------------------- engine
def test_the_eraser_takes_only_what_is_under_the_brush():
    d = _doc()
    new, rep = geo.apply(d, "erase", [], {"page": 1, **_brush(70, 70)}, geo.FREE_LIMITS)
    assert rep["changed"] == ["s3"] and rep["added"] == ["s4"] and rep["removed"] == [] and rep["untouched_verified"]
    a, b = _strokes(d), _strokes(new)
    assert b["s1"] == a["s1"] and b["s2"] == a["s2"]                          # strokes the brush missed: byte-identical
    first, second = b["s3"]["points"], b["s4"]["points"]
    assert first[0] == [60, 60] and second[-1] == [80, 60]                    # the two outer ends stay where they were
    for p in first + second:
        assert _dist_to_polyline(p, a["s3"]["points"]) < 0.02               # nothing moved off the original line
        assert math.dist(p, (70, 70)) >= 2.0 - 0.06                          # and nothing left under the brush
    assert math.dist(first[-1], (70, 70)) < 2.0 + 0.1 and math.dist(second[0], (70, 70)) < 2.0 + 0.1   # cut at its edge
    assert b["s4"]["word"] == b["s3"]["word"] and b["s3"]["provenance"] == b["s4"]["provenance"] == "EDITED"
    assert [st["id"] for st in new["pages"][0]["strokes"]] == ["s1", "s2", "s3", "s4"]   # the new piece right after
    assert new["pages"][0]["words"][1]["stroke_ids"] == ["s3", "s4"]
    assert d == _doc()                                                        # input never modified


def test_several_brush_strokes_in_one_save_and_a_stroke_erased_whole_goes():
    d = _doc()
    params = {"page": 1, "paths": [{"points": [[18, 15], [42, 15], [42, 20], [18, 20]], "radius_mm": 6},   # y 9-26
                                   {"points": [[80, 60]], "radius_mm": 1}]}
    new, rep = geo.apply(d, "erase", [], params, geo.FREE_LIMITS)
    assert sorted(rep["removed"]) == ["s1", "s2"] and rep["changed"] == ["s3"] and rep["added"] == []
    s3 = _strokes(new)["s3"]["points"]
    assert s3[0] == [60, 60] and math.dist(s3[-1], (80, 60)) == pytest.approx(1.0, abs=0.1)   # only its end went
    assert [w["stroke_ids"] for w in new["pages"][0]["words"]] == [["s3"]]                     # the emptied word too


def test_with_strokes_chosen_only_those_are_erased():
    d = _doc()
    d["pages"][0]["strokes"][1]["points"] = [[60, 70], [80, 70]]               # s2 crosses the same spot as s3
    new, rep = geo.apply(d, "erase", ["s2"], _brush(70, 70), geo.FREE_LIMITS)
    assert rep["changed"] == ["s2"] and rep["added"] == ["s4"]
    assert _strokes(new)["s3"] == _strokes(d)["s3"]                           # under the brush too, but not chosen


@pytest.mark.parametrize("params,code", [
    (_brush(150, 150), "NO_CHANGE"),                                          # touches nothing
    (_brush(70, 70, r=20), "EDIT_OUT_OF_RANGE"),                              # radius 0.2-15 mm
    ({"paths": []}, "INVALID_EDIT_PARAMS"),
    ({"paths": [{"points": [[70, "x"]], "radius_mm": 2}]}, "INVALID_EDIT_PARAMS"),
    ({"paths": [{"points": [[70, 70]], "radius_mm": 2}] * (geo.ERASE_MAX_PATHS + 1)}, "EDIT_OUT_OF_RANGE"),
    ({"page": 2, **_brush(70, 70)}, "EDIT_OUT_OF_RANGE"),                     # the sketch has one page
])
def test_eraser_refusals(params, code):
    with pytest.raises(AppError) as e:
        geo.apply(_doc(), "erase", [], params, geo.FREE_LIMITS)
    assert e.value.code == code


def test_the_text_limits_allow_the_eraser_too():
    new, rep = geo.apply(_doc(), "erase", [], _brush(70, 70), geo.TEXT_LIMITS)      # OT-3: every order type (owner)
    assert rep["added"] == ["s4"]


def test_the_assistant_cannot_erase():
    spec = next(s for s in order_tools.SPECS if s.name == "edit_strokes")
    assert "erase" in geo.OPS and "erase" not in str(spec.parameters) and "erase" not in geo.AI_OPS


# ---------------------------------------------------------------------------------------------------------- API
def _middle(st):
    pts = st["points"]
    return pts[len(pts) // 2]


def test_a_customer_erases_on_the_order_sketch_and_can_undo(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, submit=False)
    w = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).json()
    doc = w["document"]
    target = max(doc["pages"][0]["strokes"], key=lambda st: geo._length(st["points"]))
    x, y = _middle(target)
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "erase",
        "params": {"page": 1, "paths": [{"points": [[x, y]], "radius_mm": 0.3}]}})
    assert r.status_code == 200, r.text
    out = r.json()
    rep = out["report"]
    assert target["id"] in rep["changed"] + rep["removed"] and rep["untouched_verified"]
    touched = set(rep["changed"]) | set(rep["added"]) | set(rep["removed"])
    after = _strokes(out["document"])
    for sid, st in _strokes(doc).items():
        if sid not in touched:
            assert after[sid] == st
    assert out["revision"]["operation"]["op"] == "erase" and out["revision"]["note"].startswith("Tẩy")
    r = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust)
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["document"]["pages"] == doc["pages"]


def test_the_staff_erase_on_the_latest_version_into_a_new_version(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, _, _ = _customer_v1(client, cust, sh, wcat)
    v1 = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["document"]
    target = max(v1["pages"][0]["strokes"], key=lambda st: geo._length(st["points"]))
    x, y = _middle(target)
    r = client.post(f"{W}/orders/{oid}/sketches/1/edit", headers=sh, json={
        "op": "erase", "note": "Tẩy vạch lưới", "params": {"page": 1, "paths": [{"points": [[x, y]], "radius_mm": 0.3}]}})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["version"] == 2 and out["report"]["untouched_verified"]
    v2 = client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()
    touched = set(out["report"]["changed"]) | set(out["report"]["added"]) | set(out["report"]["removed"])
    a, b = _strokes(v1), _strokes(v2["document"])
    assert all(b[s] == a[s] for s in a if s not in touched)
    assert all("STAFF" in b[s]["edited_by"] for s in set(out["report"]["changed"]) | set(out["report"]["added"]))
    assert v2["trajectory"]["engine"]["operation"]["op"] == "erase"
    r = client.post(f"{W}/orders/{oid}/sketches/2/edit", headers=sh, json={
        "op": "erase", "note": "x", "params": {"page": 1, "paths": [{"points": [[x, y]], "radius_mm": 99}]}})
    assert r.status_code == 422 and _err(r) == "EDIT_OUT_OF_RANGE"
