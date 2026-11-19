"""V2 Phase D (owner approved D-a..D-e, 2026-11-19): level 1 = the whole document on the order (plan Test 1).

* D-a: per-paragraph line spacing / alignment / space before, next to the existing per-part size and styles, margins and ink.
* Text edits keep the styles of the unchanged characters (`keep_layout`, the assistant's `update_text`).
* D-b: drawing again over edited strokes needs `discard_edits` (409 SKETCH_HAS_EDITS says how many).
* D-c: undo / redo across drawings put the form back (`inputs_snapshot`, migration 0026); undrawn form changes need
  `discard_input_changes`.
* D-e: the assistant's `set_layout` goes through the same checks as the form.

Geometry is measured on the drawn document (word boxes in mm), not assumed. No test calls a real LLM."""
import pytest

from app.domain import text_layout as tl
from app.services.stroke_ai import styled_text as st, text_to_stroke as tts
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _err, _ot3, cust, staff, store, wcat  # noqa: F401
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_order_assistant import _say, _tool_result
from app.services.ai.llm import Reply

SK = "/sketch"
TEXT2 = "Kính gửi\nquý khách"                      # two paragraphs
KW = dict(font_name="futural", paper_size="A5", font_size_mm=8.0)


# ------------------------------------------------------------------------------------------------- rules (no database)
def test_paragraph_rules_round_trip_and_refusals():
    text = "Một hai\nBa bốn\nNăm"
    raw = {"paragraphs": [{"index": 2, "space_before_mm": 4}, {"index": 0, "line_spacing": 1.5, "alignment": "RIGHT"}]}
    parsed = tl.parse(raw, text)
    assert [p.index for p in parsed.paragraphs] == [0, 2] and not parsed.is_plain
    assert parsed.paragraph(0).alignment == "RIGHT" and parsed.paragraph(1) is None
    assert tl.parse(tl.to_json(parsed), text) == parsed
    assert tl.to_json(parsed)["paragraphs"] == [{"index": 0, "line_spacing": 1.5, "alignment": "RIGHT"},
                                                {"index": 2, "space_before_mm": 4.0}]
    for bad in ({"paragraphs": [{"index": 3, "alignment": "LEFT"}]},                 # only 3 paragraphs
                {"paragraphs": [{"index": 0, "alignment": "LEFT"}, {"index": 0, "line_spacing": 2}]},
                {"paragraphs": [{"index": 0}]},                                       # changes nothing
                {"paragraphs": [{"index": 0, "font": "x"}]},
                {"paragraphs": [{"index": 0, "alignment": "MIDDLE"}]},
                {"paragraphs": [{"index": 0, "space_before_mm": 51}]},
                {"paragraphs": [{"index": 0, "line_spacing": 3}]},
                {"paragraphs": [{"index": True, "alignment": "LEFT"}]},
                {"paragraphs": {"index": 0}}):
        with pytest.raises(tl.TextLayoutError):
            tl.parse(bad, text)
    with pytest.raises(tl.TextLayoutError):                                          # a bare length cannot check paragraphs
        tl.parse({"paragraphs": [{"index": 0, "alignment": "LEFT"}]}, len(text))
    caps = tl.capabilities()["paragraphs"]
    assert caps["keys"] == ["line_spacing", "alignment", "space_before_mm"] and caps["space_before_mm"]["max"] == 50.0


def _dy_dx(base, new):
    """Per stroke (same strokes, same order): how far the first point moved."""
    a, b = base[0].strokes, new[0].strokes
    assert len(a) == len(b)
    return ([round(q.points[0][1] - p.points[0][1], 6) for p, q in zip(a, b)],
            [round(q.points[0][0] - p.points[0][0], 6) for p, q in zip(a, b)])


def test_each_paragraph_setting_moves_only_its_paragraph():
    text = "Một hai\nBa bốn"
    plain = st.compose_styled(text, tl.parse({}, text), **KW, seed=3)
    n0 = sum(1 for s in st.compose_styled("Một hai", tl.parse({}, "Một hai"), **KW, seed=3)[0].strokes)

    def draw(paragraphs):
        return st.compose_styled(text, tl.parse({"paragraphs": paragraphs}, text), **KW, seed=3)

    # line spacing 2.0 on paragraph 0: its one line is taller by exactly one pitch; paragraph 1 moves down by that much
    dy, dx = _dy_dx(plain, draw([{"index": 0, "line_spacing": 2.0}]))
    assert set(dy[:n0]) == {0.0} and set(dx) == {0.0}
    assert {round(v, 4) for v in dy[n0:]} == {round(tts.LINE_PITCH_FACTOR * 8.0 * 1.0, 4)}
    # space before paragraph 1: paragraph 1 moves down by exactly 6 mm
    dy, dx = _dy_dx(plain, draw([{"index": 1, "space_before_mm": 6}]))
    assert set(dy[:n0]) == {0.0} and {round(v, 4) for v in dy[n0:]} == {6.0} and set(dx) == {0.0}
    # alignment RIGHT for paragraph 1 only (the input's own is LEFT): paragraph 1 moves right, paragraph 0 does not
    dy, dx = _dy_dx(plain, draw([{"index": 1, "alignment": "RIGHT"}]))
    assert set(dy) == {0.0} and set(dx[:n0]) == {0.0} and len(set(dx[n0:])) == 1 and dx[n0] > 10
    right_edge = max(p[0] for s in draw([{"index": 1, "alignment": "RIGHT"}])[0].strokes[n0:] for p in s.points)
    assert 148 - 15 - 2 < right_edge <= 148 - 15 + 0.5                                  # A5, 15 mm right margin
    # space before a paragraph is dropped at the top of a page (nothing to separate it from)
    tall = "\n".join(["Dòng"] * 40)
    pages = st.compose_styled(tall, tl.parse({"paragraphs": [{"index": i, "space_before_mm": 50} for i in range(1, 12)]},
                                             tall), **KW, seed=3)
    assert len(pages) > 3 and all(min(p[1] for s in pg.strokes for p in s.points) < 15 + 12 for pg in pages)


def test_remap_keeps_the_styles_of_unchanged_text_and_paragraphs():
    old = "Kính gửi\nquý khách\nthân mến"
    lay = tl.parse({"spans": [{"start": old.index("quý"), "end": old.index("quý") + 3, "size_mm": 12},
                              {"start": 0, "end": 4, "italic": True}],
                    "paragraphs": [{"index": 1, "alignment": "RIGHT"}, {"index": 2, "space_before_mm": 5}]}, old)
    new = "Xin chào\nKính gửi\nquý khách hàng\nthân mến"                         # a paragraph inserted at the top
    out, rep = tl.remap(old, new, lay)
    assert tl.parse(tl.to_json(out), new) == out                                    # valid on the new text
    sized = next(s for s in out.spans if s.style.size_mm == 12)
    assert new[sized.start:sized.end] == "quý"
    assert any(new[s.start:s.end] == "Kính" and s.style.italic for s in out.spans)
    assert {p.index: p.alignment for p in out.paragraphs} == {2: "RIGHT", 3: None}
    assert rep == {"spans_kept": 2, "spans_dropped": 0, "paragraphs_kept": 2, "paragraphs_dropped": 0}
    out, rep = tl.remap(old, "Kính gửi", lay)                                         # the styled parts deleted
    assert [new_s.style.italic for new_s in out.spans] == [True] and not out.paragraphs
    assert rep["spans_dropped"] == 1 and rep["paragraphs_dropped"] == 2
    assert tl.remap_stored(old, "x", {"spans": [{"start": 0, "end": 99, "italic": True}]})[1] == {"invalid": 1}


# ------------------------------------------------------------------------------------------------- Test 1 on an order
def _put(client, h, oid, wcat, text_=TEXT2, layout=None, **kw):
    body = {"text_content": text_, "template_id": wcat["tpl"], "font_size_mm": 8, "alignment": "LEFT", **kw}
    if layout is not None:
        body["layout"] = layout
    return client.put(f"{API}/orders/{oid}/inputs/text", headers=h, json=body)


def _gen(client, h, oid, **body):
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=h, json=body or None)
    assert r.status_code == 201, r.text
    return r.json()


def _words(doc):
    return {w["text"]: w["bbox"] for p in doc["pages"] for w in p["words"]}


def _count(oid):
    return _sql("select count(*) from sketch_revisions where order_id=:o", o=oid)


def test_every_level_one_setting_redraws_the_order_and_is_measured(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    base = _gen(client, cust, oid)
    w0 = _words(base["document"])
    assert set(w0) == {"Kính", "gửi", "quý", "khách"}
    seen = {base["revision"]["id"]}

    def redraw(layout, **kw):
        r = _put(client, cust, oid, wcat, layout=layout, **kw)
        assert r.status_code == 200, r.text
        assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["inputs_changed"]   # form ahead of the sketch
        w = _gen(client, cust, oid)
        assert w["revision"]["id"] not in seen and not w["inputs_changed"] and w["revision"]["author"] == "ENGINE"
        seen.add(w["revision"]["id"])
        return _words(w["document"]), w

    h = lambda b: b[3] - b[1]                                                         # noqa: E731
    # the drawing's random variation is seeded by the content (layout included), so positions are compared within 0.4 mm
    top = {"vertical_align": "TOP"}
    ref, _ = redraw(top)
    # size of one part: "quý" at 14 mm is taller, the other words keep their height
    i = TEXT2.index("quý")
    sized, _ = redraw({**top, "spans": [{"start": i, "end": i + 3, "size_mm": 14}]})
    assert h(sized["quý"]) > 1.5 * h(ref["quý"]) and abs(h(sized["Kính"]) - h(ref["Kính"])) < 0.5
    # paragraph line spacing: paragraph 0 at 2.0 pushes paragraph 1 down by one more pitch (8 mm text)
    spaced, _ = redraw({**top, "paragraphs": [{"index": 0, "line_spacing": 2.0}]})
    assert abs((spaced["quý"][1] - ref["quý"][1]) - tts.LINE_PITCH_FACTOR * 8) < 0.4
    assert abs(spaced["Kính"][1] - ref["Kính"][1]) < 0.4
    # space before paragraph 1: exactly 7 mm lower
    before, _ = redraw({**top, "paragraphs": [{"index": 1, "space_before_mm": 7}]})
    assert abs((before["khách"][1] - ref["khách"][1]) - 7) < 0.4 and abs(before["gửi"][1] - ref["gửi"][1]) < 0.4
    # paragraph alignment: paragraph 1 right-aligned, paragraph 0 still left
    right, _ = redraw({**top, "paragraphs": [{"index": 1, "alignment": "RIGHT"}]})
    assert right["khách"][2] > 148 - 15 - 3 and abs(right["Kính"][0] - ref["Kính"][0]) < 0.4
    # margins: left 40 mm moves everything to x >= 40
    wide, _ = redraw({**top, "margins_mm": {"left": 40}})
    assert min(b[0] for b in wide.values()) >= 40 - 1.0 > max(b[0] for b in ref.values() if b is ref["Kính"])
    # refused, and no revision is made: a size under 4 mm, margins leaving no writing area (A5 is 148 mm wide)
    n = _count(oid)
    r = _put(client, cust, oid, wcat, layout={"spans": [{"start": 0, "end": 4, "size_mm": 3}]})
    assert r.status_code == 422 and _err(r) == "INVALID_LAYOUT"
    r = _put(client, cust, oid, wcat, layout={"paragraphs": [{"index": 5, "alignment": "LEFT"}]})
    assert r.status_code == 422 and _err(r) == "INVALID_LAYOUT"
    assert _put(client, cust, oid, wcat, layout={"margins_mm": {"left": 60, "right": 60}}).status_code == 200
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 422 and _count(oid) == n
    # ink colour changes the look, never the strokes
    assert _put(client, cust, oid, wcat, layout=top).status_code == 200
    cur = _gen(client, cust, oid)
    red = _sql("insert into ink_colors (pen_type_id,name,hex_code,unit_price,stock_qty) values (:p,'Do','#cc0000',0,50) "
               "returning id", p=wcat["gel"])
    jpg_black = client.get(f"{API}/orders/{oid}{SK}/preview", headers=cust).content
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"ink_color_id": red}).status_code == 200
    after = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert not after["inputs_changed"] and after["revision"]["id"] == cur["revision"]["id"]
    assert client.get(f"{API}/orders/{oid}{SK}/preview", headers=cust).content != jpg_black


def test_text_edit_with_keep_layout_carries_the_styles(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    i = TEXT2.index("quý")
    assert _put(client, cust, oid, wcat, layout={"spans": [{"start": i, "end": i + 3, "size_mm": 12}],
                                                 "paragraphs": [{"index": 1, "alignment": "RIGHT"}]}).status_code == 200
    new = "Thân gửi\nquý khách hàng"
    r = _put(client, cust, oid, wcat, text_=new, keep_layout=True)
    assert r.status_code == 200, r.text
    lay = r.json()["layout"]
    assert r.json()["layout_remap"] == {"spans_kept": 1, "spans_dropped": 0, "paragraphs_kept": 1, "paragraphs_dropped": 0}
    s = lay["spans"][0]
    assert new[s["start"]:s["end"]] == "quý" and s["size_mm"] == 12 and lay["paragraphs"] == [{"index": 1, "alignment": "RIGHT"}]
    # without keep_layout the PUT replaces everything (unchanged contract)
    r = _put(client, cust, oid, wcat, text_=new)
    assert r.json()["layout"]["spans"] == [] and "paragraphs" not in r.json()["layout"] and r.json()["layout_remap"] is None


def test_redrawing_over_edited_strokes_needs_discard_edits(client, cust, wcat, store):
    oid = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    w = _gen(client, cust, oid)
    word = w["document"]["pages"][0]["words"][0]
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1}})
    assert r.status_code == 200, r.text
    edited = r.json()["revision"]["id"]
    n = _count(oid)
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 409 and _err(r) == "SKETCH_HAS_EDITS" and _count(oid) == n
    d = r.json()["error"]["details"]
    assert d["edited_strokes"] == len(word["stroke_ids"]) and d["by"]["CUSTOMER"] == len(word["stroke_ids"])
    assert d["current_revision_id"] == edited
    g = _gen(client, cust, oid, discard_edits=True)
    assert g["revision"]["parent_id"] == edited
    assert client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()["revision"]["id"] == edited   # still there
    # a fresh drawing (no edits) is drawn again without the flag
    oid2 = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    _gen(client, cust, oid2)
    _gen(client, cust, oid2)


def test_undo_across_drawings_puts_the_form_back(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    r1 = _gen(client, cust, oid)["revision"]
    snap = _sql("select inputs_snapshot->'text'->>'text_content' from sketch_revisions where id=:i", i=r1["id"])
    assert snap == TEXT2
    i = TEXT2.index("quý")
    assert _put(client, cust, oid, wcat, text_="Chào bạn", layout={"vertical_align": "TOP"}).status_code == 200
    assert client.patch(f"{API}/orders/{oid}", headers=cust,
                        json={"paper_type_id": wcat["gloss"]}).status_code == 200            # a material too
    r2 = _gen(client, cust, oid)["revision"]

    def form():
        o = client.get(f"{API}/orders/{oid}", headers=cust).json()
        t = next(x for x in o["inputs"] if x["kind"] == "TEXT_CONTENT")
        return t["text_content"], t["layout"].get("vertical_align"), o["paper_type_id"]

    assert form() == ("Chào bạn", "TOP", wcat["gloss"])
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert u["revision"]["id"] == r1["id"] and u["inputs_restored"] and not u["inputs_changed"]
    assert form() == (TEXT2, "MIDDLE", wcat["paper"])
    assert _sql("select count(*) from audit_logs where action='ORDER_INPUTS_RESTORED' and entity_id=:o", o=oid) == 1
    rd = client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust).json()
    assert rd["revision"]["id"] == r2["id"] and rd["inputs_restored"] and form() == ("Chào bạn", "TOP", wcat["gloss"])
    # a form change not drawn yet would be lost: refused unless discarded
    assert _put(client, cust, oid, wcat, text_="Chưa vẽ", layout={"spans": [{"start": 0, "end": 4, "italic": True}]}
                ).status_code == 200
    r = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust)
    assert r.status_code == 409 and _err(r) == "UNDRAWN_INPUT_CHANGES"
    assert form()[0] == "Chưa vẽ"
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust, json={"discard_input_changes": True}).json()
    assert u["inputs_restored"] and form() == (TEXT2, "MIDDLE", wcat["paper"]) and i == TEXT2.index("quý")
    # an edit inside one drawing does not touch the form; undo of it does not either
    w = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    word = w["document"]["pages"][0]["words"][0]
    e = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": r1["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1}}).json()
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert u["revision"]["id"] == r1["id"] and not u["inputs_restored"]
    redo = client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust).json()
    assert redo["revision"]["id"] == e["revision"]["id"]
    # revisions stored before 0026 have no snapshot: undo moves the sketch only (as before)
    _sql("update sketch_revisions set inputs_snapshot = null where order_id=:o returning 1", o=oid)
    assert _put(client, cust, oid, wcat, text_="Khác hẳn").status_code == 200
    r3 = _gen(client, cust, oid, discard_edits=True)["revision"]
    _sql("update sketch_revisions set inputs_snapshot = null where id=:i returning 1", i=r3["id"])
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert not u["inputs_restored"] and u["inputs_changed"] and form()[0] == "Khác hẳn"
    # the order still goes through: redraw, send, the Staff get exactly that drawing as v1 (D2)
    last = _gen(client, cust, oid, discard_edits=True)["revision"]
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    assert _sql("select geometry_hash from sketches where order_id=:o and version=1", o=oid) == last["geometry_hash"]


def test_the_assistant_sets_the_layout_through_the_same_checks(client, cust, wcat, store, providers):
    oid = _ot3(client, cust, wcat, text_=TEXT2, submit=False)
    p = Script("anthropic", [                                                         # max 6 tool calls per turn
        _call("set_layout", paragraph={"index": 1, "alignment": "RIGHT", "space_before_mm": 5}),
        _call("set_layout", span={"match": "quý", "size_mm": 12}),
        _call("set_layout", margins_mm={"left": 30}, vertical_align="TOP", line_spacing=1.3),
        _call("set_layout", line_spacing=9),                                          # refused, nothing changes
        Reply("Đã chỉnh bố cục.", [], 10, 5)])
    q = Script("anthropic", [
        _call("set_layout", span={"match": "xyz", "italic": True}),                   # refused
        _call("update_text", text="Thân gửi\nquý khách hàng"),                        # keeps the styled parts
        _call("generate_sketch"),
        Reply("Đã sửa chữ và vẽ lại.", [], 10, 5)])
    providers["list"] = [p]
    r = _say(client, cust, oid, "Căn phải đoạn hai, chữ quý to hơn, lề trái 3 cm")
    assert r.status_code == 200, r.text
    assert "set_layout" in p.seen[0]["tools"]
    providers["list"] = [q]
    assert _say(client, cust, oid, "Đổi Kính thành Thân, thêm chữ hàng, rồi vẽ lại").status_code == 200
    res = [_tool_result(p, k) for k in range(4)] + [_tool_result(q, k) for k in range(3)]
    assert [x["ok"] for x in res] == [True, True, True, False, False, True, True]
    assert res[3]["error"] == "INVALID_LAYOUT" and res[4]["error"] == "TEXT_NOT_FOUND"
    assert res[5]["warnings"] == []
    o = client.get(f"{API}/orders/{oid}", headers=cust).json()
    t = next(x for x in o["inputs"] if x["kind"] == "TEXT_CONTENT")
    lay, text_ = t["layout"], t["text_content"]
    assert text_ == "Thân gửi\nquý khách hàng" and lay["line_spacing"] == 1.3 and lay["vertical_align"] == "TOP"
    assert lay["margins_mm"]["left"] == 30 and lay["margins_mm"]["right"] == 15
    assert lay["paragraphs"] == [{"index": 1, "alignment": "RIGHT", "space_before_mm": 5.0}]
    assert [text_[s["start"]:s["end"]] for s in lay["spans"]] == ["quý"] and lay["spans"][0]["size_mm"] == 12
    w = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert not w["inputs_changed"] and w["revision"]["author"] == "ENGINE"
    assert min(b["bbox"][0] for pg in w["document"]["pages"] for b in pg["words"]) >= 29
    # the assistant cannot draw over edited strokes without the customer's yes
    word = w["document"]["pages"][0]["words"][0]
    assert client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "word_ids": [word["id"]],
        "params": {"dx_mm": 1}}).status_code == 200
    p2 = Script("anthropic", [_call("generate_sketch"), Reply("Phác thảo có nét đã sửa, bạn có muốn vẽ lại?", [], 5, 5)])
    providers["list"] = [p2]
    assert _say(client, cust, oid, "Vẽ lại đi").status_code == 200
    assert _tool_result(p2)["error"] == "SKETCH_HAS_EDITS"
