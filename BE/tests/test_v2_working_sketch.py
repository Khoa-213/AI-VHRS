"""V2 Phase B: the customer's working sketch of an order, the Geometry Engine, and v1 = what the customer sent (D2).

Vertical slice (D6): OT-3 order DRAFT -> engine draws r1 -> the customer bends one stroke and moves one word -> submit ->
the Staff accept -> official v1 has exactly those strokes (hash) -> motion planning / validation of v1 passes."""
import math

import pytest

from app.core.errors import AppError
from app.services import sketch_geometry as geo
from app.services.motion import validate as mv
from app.services.stroke_ai import trajectory as tj
from tests.test_api_orders import API, _sql, _upload
from tests.test_api_workshop import W, _err, _ot3, cust, staff, store, wcat  # noqa: F401
from tests.test_motion_geometry import BOX, CFG, probes
from tests.test_u4_regions import _scan
from tests.conftest import auth

SK = "/sketch"


def _work(client, h, oid):
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _strokes(doc):
    return {st["id"]: st for p in doc["pages"] for st in p["strokes"]}


# ---------------------------------------------------------------------------------------------------------- vertical slice
def test_the_staff_receive_exactly_the_strokes_the_customer_edited_and_they_plan(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = _ot3(client, cust, wcat, text_="Kính gửi quý khách", submit=False)
    w = _work(client, cust, oid)
    r1 = w["revision"]
    assert r1["author"] == "ENGINE" and r1["seq"] == 1 and not w["can_undo"] and not w["inputs_changed"]
    doc = w["document"]
    assert doc["format"] == "vhrs-sketch/2" and w["limits"]["name"] == "TEXT"
    page = doc["pages"][0]
    assert page["words"] and all(st["word"] for st in page["strokes"] if st["kind"] == "base")
    before = _strokes(doc)

    # 1. bend one stroke (the AI / the FE picks the id; the engine does the geometry)
    target = next(st for st in page["strokes"] if len(st["points"]) >= 4)
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": r1["id"], "op": "curvature", "stroke_ids": [target["id"]], "params": {"factor": 1.4}})
    assert r.status_code == 200, r.text
    e1 = r.json()
    after = _strokes(e1["document"])
    assert e1["report"]["changed"] == [target["id"]] and e1["report"]["untouched_verified"]
    assert after[target["id"]]["points"][0] == target["points"][0] and after[target["id"]]["points"][-1] == target["points"][-1]
    assert after[target["id"]]["points"] != target["points"] and after[target["id"]]["provenance"] == "EDITED"
    assert {k: v for k, v in after.items() if k != target["id"]} == {k: v for k, v in before.items() if k != target["id"]}

    # 2. move one word (region-level selection); a stale base revision is refused, nothing overwritten
    word = page["words"][1]
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": r1["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1.0}})
    assert r.status_code == 409 and _err(r) == "STALE_REVISION"
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": e1["revision"]["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1.0}})
    assert r.status_code == 200, r.text
    e2 = r.json()
    moved = _strokes(e2["document"])
    for sid in word["stroke_ids"]:
        assert [[round(x - 1.0, 2), y] for x, y in moved[sid]["points"]] == [[x, y] for x, y in after[sid]["points"]]
    assert e2["revision"]["parent_id"] == e1["revision"]["id"] and e2["can_undo"]

    # 3. undo / redo move the cursor; history kept
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert u["revision"]["id"] == e1["revision"]["id"] and u["can_redo"]
    rd = client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust).json()
    assert rd["revision"]["id"] == e2["revision"]["id"]
    hist = client.get(f"{API}/orders/{oid}{SK}/revisions", headers=cust).json()
    assert [h["author"] for h in hist] == ["ENGINE", "CUSTOMER", "CUSTOMER"]
    assert hist[1]["operation"]["op"] == "curvature" and hist[2]["operation"]["word_ids"] == [word["id"]]
    assert client.get(f"{API}/orders/{oid}{SK}/preview", headers=cust).content[:2] == b"\xff\xd8"

    # 4. submit -> the working sketch is read-only; the Staff accept -> v1 = these strokes
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": e2["revision"]["id"], "op": "translate", "stroke_ids": [target["id"]], "params": {"dx_mm": 1}})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE"
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    sketches = client.get(f"{W}/orders/{oid}/sketches", headers=sh).json()
    assert [s["version"] for s in sketches] == [1]
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    eng = det["trajectory"]["engine"]
    assert eng["name"] == "customer-working-sketch" and eng["source_revision_id"] == e2["revision"]["id"]
    v1_pages = tj.parse(det["trajectory"])
    assert geo.pages_geometry_hash(v1_pages) == e2["revision"]["geometry_hash"]          # Test 7: nothing changed silently
    assert _sql("select source_revision_id from sketches where order_id=:o and version=1", o=oid) == e2["revision"]["id"]

    # 5. motion simulation of v1 (planning + validation with a measured config; no robot)
    rep, plans = mv.validate(v1_pages, probes(), CFG, BOX)
    assert rep.passed, rep.error_texts()
    assert plans and sum(len(p.moves) for p in plans) > 0


def test_a_changed_content_needs_a_new_drawing_before_submit(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, text_="Một hai ba", submit=False)
    w = _work(client, cust, oid)
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
                   json={"text_content": "Bốn năm sáu", "template_id": wcat["tpl"], "font_size_mm": 8, "alignment": "LEFT"})
    assert r.status_code == 200
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["inputs_changed"] is True
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 409 and _err(r) == "SKETCH_OUTDATED"
    w2 = _work(client, cust, oid)
    assert w2["revision"]["parent_id"] == w["revision"]["id"] and not w2["inputs_changed"]
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200


def test_edits_are_bounded_and_only_the_owner_may_touch_the_sketch(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, submit=False)
    w = _work(client, cust, oid)
    rid = w["revision"]["id"]
    sid = w["document"]["pages"][0]["strokes"][0]["id"]

    def edit(op, ids, params, h=cust):
        return client.post(f"{API}/orders/{oid}{SK}/edit", headers=h,
                           json={"base_revision_id": rid, "op": op, "stroke_ids": ids, "params": params})

    r = edit("translate", [sid], {"dx_mm": 5})                      # OT-3: at most 3 mm per edit (D3)
    assert r.status_code == 422 and _err(r) == "EDIT_OUT_OF_RANGE" and r.json()["error"]["details"]["max"] == 3.0
    assert _err(edit("translate", ["s9999"], {"dx_mm": 1})) == "STROKE_NOT_FOUND"
    assert _err(edit("rotate", [], {"degrees": 5})) == "EMPTY_SELECTION"
    assert _err(edit("scale", [sid], {"factor": "big"})) == "INVALID_EDIT_PARAMS"
    assert client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": rid, "op": "teleport", "stroke_ids": [sid]}).status_code == 422
    other = auth(client, "CUSTOMER")
    assert _err(edit("translate", [sid], {"dx_mm": 1}, h=other)) == "ORDER_NOT_FOUND"
    assert client.get(f"{API}/orders/{oid}{SK}", headers=other).status_code == 404
    r = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust)
    assert r.status_code == 409 and _err(r) == "NOTHING_TO_UNDO"
    assert client.get(f"{API}/orders/{oid}{SK}/revisions", headers=cust).json()[0]["id"] == rid   # refusals saved nothing


def test_an_ot1_working_sketch_keeps_its_word_regions_into_v1(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    assert _upload(client, cust, oid, store, _scan())[0].status_code == 200
    w = _work(client, cust, oid)
    doc = w["document"]
    assert w["limits"]["name"] == "FREE" and len(doc["pages"][0]["words"]) == 6
    assert {st["provenance"] for st in doc["pages"][0]["strokes"]} == {"RECOVERED"}
    word = doc["pages"][0]["words"][2]
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "slant", "word_ids": [word["id"]], "params": {"degrees": -8}})
    assert r.status_code == 200, r.text
    rev = r.json()["revision"]
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert geo.pages_geometry_hash(tj.parse(det["trajectory"])) == rev["geometry_hash"]
    assert len(det["regions"]) == 6 and {x["source"] for x in det["regions"]} == {"CUSTOMER"}


def test_an_order_without_a_working_sketch_is_accepted_as_before(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    assert client.get(f"{W}/orders/{oid}/sketches", headers=sh).json() == []
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).status_code == 404


# ---------------------------------------------------------------------------------------------------------- engine unit
def _doc():
    page = tj.Page("A5")
    page.strokes = [tj.Stroke([(20, 20), (25, 15), (30, 20)], "base", 0), tj.Stroke([(31, 20), (40, 20)], "base", 0),
                    tj.Stroke([(60, 60), (70, 70), (80, 60)], "base", 1)]
    return geo.from_generated([page], {"name": "test"})


def test_geometry_ops_change_only_the_selection_and_keep_shapes():
    d = _doc()
    new, rep = geo.apply(d, "rotate", ["s3"], {"degrees": 30}, geo.FREE_LIMITS)
    a, b = d["pages"][0]["strokes"][2]["points"], new["pages"][0]["strokes"][2]["points"]
    assert abs(geo._length(a) - geo._length(b)) < 0.05 and rep["changed"] == ["s3"]
    assert new["pages"][0]["strokes"][:2] == d["pages"][0]["strokes"][:2]
    flat, _ = geo.apply(d, "curvature", ["s1"], {"factor": 0.0}, geo.FREE_LIMITS)
    assert flat["pages"][0]["strokes"][0]["points"] == [[20, 20], [25, 20], [30, 20]]           # straight onto the chord
    joined, rep = geo.apply(d, "join", ["s1", "s2"], {}, geo.FREE_LIMITS)
    assert rep["removed"] == ["s2"] and len(joined["pages"][0]["strokes"]) == 2
    assert joined["pages"][0]["words"][0]["stroke_ids"] == ["s1"]
    split, rep = geo.apply(d, "split", ["s3"], {"at": 0.5}, geo.FREE_LIMITS)
    assert rep["added"] == ["s4"] and split["next_id"] == 5
    ids = [st["id"] for st in split["pages"][0]["strokes"]]
    assert ids == ["s1", "s2", "s3", "s4"]
    trimmed, _ = geo.apply(d, "trim", ["s2"], {"mm": 4, "end": "end"}, geo.FREE_LIMITS)
    assert math.isclose(geo._length(trimmed["pages"][0]["strokes"][1]["points"]), 5.0, abs_tol=0.01)
    assert d == _doc()                                                                         # input never modified


@pytest.mark.parametrize("op,ids,params,code", [
    ("join", ["s1", "s3"], {}, "JOIN_TOO_FAR"),
    ("translate", ["s1"], {"dx_mm": -4.5}, "EDIT_OUTSIDE_PAPER"),
    ("trim", ["s2"], {"mm": 9}, "STROKE_TOO_SHORT"),
    ("translate", ["s1"], {"dx_mm": 0, "dy_mm": 0}, "NO_CHANGE"),
    ("scale", ["s1"], {"factor": 3}, "EDIT_OUT_OF_RANGE"),
])
def test_geometry_refusals(op, ids, params, code):
    d = _doc()
    d["pages"][0]["strokes"][0]["points"] = [[5, 20], [15, 15], [20, 20]]
    with pytest.raises(AppError) as e:
        geo.apply(d, op, ids, params, geo.FREE_LIMITS)
    assert e.value.code == code
