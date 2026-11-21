"""V2 Phase F (owner approved 2026-11-19): lines and paragraphs, ids kept across a redraw, whole-word edits applied again.

* F1: every page of the document has `lines` and `paragraphs`; an edit can select them (customer, assistant, Staff).
* F2: drawing again keeps the ids of the words drawn again (OT-3 by text, OT-1 by position) and of their strokes.
* F3: translate / rotate / scale / slant on whole words come back after a redraw; other edits are dropped, with a reason.
* F4: an edit reports the strokes, words and lines it touched.
"""
from app.services.ai.llm import Reply
from tests.test_api_orders import API, _upload
from tests.test_api_workshop import W, _err, _ot3, cust, staff, store, wcat  # noqa: F401
from tests.test_u4_regions import _scan
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_document_level import _gen, _put
from tests.test_v2_order_assistant import _say, _tool_result

SK = "/sketch"
TEXT = "Kính gửi ông bà\nCon xin chào cả nhà\nThương"


def _edit(client, h, oid, base, **body):
    return client.post(f"{API}/orders/{oid}{SK}/edit", headers=h, json={"base_revision_id": base, **body})


def _ids(doc):
    return {w["text"]: (w["id"], tuple(w["stroke_ids"])) for p in doc["pages"] for w in p["words"]}


def test_ot3_lines_paragraphs_and_a_redraw_that_keeps_ids_and_edits(client, cust, wcat, store, providers):
    oid = _ot3(client, cust, wcat, text_=TEXT, submit=False)
    w = _gen(client, cust, oid)
    page = w["document"]["pages"][0]
    assert w["redraw"] is None                                         # first drawing: nothing to carry
    # F1: one paragraph per line of the text, from the text itself; every word in exactly one line
    assert [pa["source"] for pa in page["paragraphs"]] == ["TEXT"] * 3
    assert [len(pa["line_ids"]) for pa in page["paragraphs"]] == [1, 1, 1]
    text_of = {x["id"]: x["text"] for x in page["words"]}
    assert [[text_of[i] for i in ln["word_ids"]] for ln in page["lines"]] == [
        ["Kính", "gửi", "ông", "bà"], ["Con", "xin", "chào", "cả", "nhà"], ["Thương"]]
    assert sorted(i for ln in page["lines"] for i in ln["word_ids"]) == sorted(text_of)
    l2, p3 = page["lines"][1], page["paragraphs"][2]
    # F1 + F4: a whole line moves; the report names its strokes, words and only that line
    r = _edit(client, cust, oid, w["revision"]["id"], op="translate", line_ids=[l2["id"]], params={"dx_mm": 1})
    assert r.status_code == 200, r.text
    aff = r.json()["report"]["affected"]
    assert aff["lines"] == [l2["id"]] and sorted(aff["words"]) == sorted(l2["word_ids"])
    assert len(aff["strokes"]) == sum(len(x["stroke_ids"]) for x in page["words"] if x["id"] in l2["word_ids"])
    base = r.json()["revision"]["id"]
    r = _edit(client, cust, oid, base, op="rotate", paragraph_ids=[p3["id"]], params={"degrees": 5})
    assert r.status_code == 200, r.text
    base = r.json()["revision"]["id"]
    gui = next(x for x in page["words"] if x["text"] == "gửi")
    r = _edit(client, cust, oid, base, op="smooth", word_ids=[gui["id"]], params={"passes": 2})        # not re-applied
    assert r.status_code == 200
    base = r.json()["revision"]["id"]
    r = _edit(client, cust, oid, base, op="translate", stroke_ids=[gui["stroke_ids"][0]], params={"dy_mm": 0.5})
    assert r.status_code == 200
    assert _err(_edit(client, cust, oid, r.json()["revision"]["id"], op="translate", line_ids=["l999"],
                      params={"dx_mm": 1})) == "LINE_NOT_FOUND"
    assert _err(_edit(client, cust, oid, r.json()["revision"]["id"], op="translate", paragraph_ids=["p999"],
                      params={"dx_mm": 1})) == "PARAGRAPH_NOT_FOUND"
    before, last_edit = r.json()["document"], r.json()["revision"]["id"]
    # the customer changes the text, then draws again: 409 says how many edits come back
    assert _put(client, cust, oid, wcat, text_="Kính gửi ông bà nội\nCon xin chào cả nhà\nThương").status_code == 200
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 409 and _err(r) == "SKETCH_HAS_EDITS"
    assert r.json()["error"]["details"]["edits"] == 4 and r.json()["error"]["details"]["reapplicable_edits"] == 2
    g = _gen(client, cust, oid, discard_edits=True)
    rd = g["redraw"]
    # F2: every old word keeps its id (and its strokes'), the new word "nội" gets an id never used before
    assert rd["ids"] == {"matched_by": "TEXT", "words_kept": 10, "words_new": 1, "words_gone": 0,
                         "strokes_kept": sum(len(x["stroke_ids"]) for x in page["words"])}
    old, new = _ids(before), _ids(g["document"])
    assert all(new[t] == old[t] for t in old)
    used = {int(s["id"][1:]) for pg in before["pages"] for s in pg["strokes"]}
    assert new["nội"][0] not in {v[0] for v in old.values()} and min(int(s[1:]) for s in new["nội"][1]) > max(used)
    npage = g["document"]["pages"][0]
    assert [ln["id"] for ln in npage["lines"]] == [ln["id"] for ln in page["lines"]]
    assert [pa["id"] for pa in npage["paragraphs"]] == [pa["id"] for pa in page["paragraphs"]]
    # F3: the line move and the paragraph rotation come back; smooth and the single stroke do not
    assert [(x["op"], x["line_ids"], x["paragraph_ids"]) for x in rd["reapplied"]] == [
        ("translate", [l2["id"]], None), ("rotate", None, [p3["id"]])]
    assert [(x["op"], x["reason"]) for x in rd["dropped"]] == [("smooth", "OP_NOT_REAPPLIED"),
                                                               ("translate", "NOT_WHOLE_WORDS")]
    moved = set(l2["word_ids"]) | {i for ln in page["lines"] if ln["id"] in p3["line_ids"] for i in ln["word_ids"]}
    edited = {s["id"] for pg in g["document"]["pages"] for s in pg["strokes"] if s.get("edited_by")}
    assert edited == {s for x in npage["words"] if x["id"] in moved for s in x["stroke_ids"]}
    assert g["revision"]["author"] == "ENGINE"
    assert client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()["revision"]["id"] == last_edit
    # the assistant sees the lines and edits a whole line (the customer selected it)
    g = _gen(client, cust, oid, discard_edits=True)
    lid = g["document"]["pages"][0]["lines"][0]["id"]
    p = Script("anthropic", [_call("get_sketch"), _call("edit_strokes", op="translate", line_ids=[lid],
                                                         params={"dy_mm": 1}),
                             _call("edit_strokes", op="translate", line_ids=[g["document"]["pages"][0]["lines"][1]["id"]],
                                   params={"dy_mm": 1}),
                             Reply("Đã dời dòng đầu.", [], 5, 5)])
    providers["list"] = [p]
    assert _say(client, cust, oid, "Dời dòng này xuống 1 mm", selection={"line_ids": [lid]}).status_code == 200
    seen = _tool_result(p, 0)
    assert [ln["id"] for ln in seen["pages"][0]["lines"]] == [ln["id"] for ln in g["document"]["pages"][0]["lines"]]
    assert _tool_result(p, 1)["ok"] and _tool_result(p, 1)["report"]["affected"]["lines"] == [lid]
    assert _tool_result(p, 2)["error"] == "OUTSIDE_SELECTION"


def test_ot1_redraw_keeps_regions_by_position_and_the_staff_edit_lines(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    assert _upload(client, cust, oid, store, _scan())[0].status_code == 200
    w = _gen(client, cust, oid)
    page = w["document"]["pages"][0]
    # F1: the six regions "Net Viet Nam / xuong viet tay" are two lines of three, paragraphs from the layout
    assert [len(ln["word_ids"]) for ln in page["lines"]] == [3, 3]
    assert {pa["source"] for pa in page["paragraphs"]} == {"LAYOUT"}
    word = page["words"][2]
    r = _edit(client, cust, oid, w["revision"]["id"], op="slant", word_ids=[word["id"]], params={"degrees": -8})
    assert r.status_code == 200, r.text
    assert r.json()["report"]["affected"]["words"] == [word["id"]]
    # F2 by position: the same photo drawn again keeps every region id; F3: the slant comes back
    g = _gen(client, cust, oid, discard_edits=True)
    assert g["redraw"]["ids"]["matched_by"] == "POSITION"
    assert g["redraw"]["ids"]["words_kept"] == 6 and g["redraw"]["ids"]["words_new"] == 0
    assert [x["id"] for x in g["document"]["pages"][0]["words"]] == [x["id"] for x in page["words"]]
    assert [x["op"] for x in g["redraw"]["reapplied"]] == ["slant"] and g["redraw"]["dropped"] == []
    assert g["document"]["pages"][0]["strokes"] == r.json()["document"]["pages"][0]["strokes"]
    # the Staff select a whole line of v1
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    line = det["document"]["pages"][0]["lines"][1]
    r = client.post(f"{W}/orders/{oid}/sketches/1/edit", headers=sh, json={
        "op": "translate", "line_ids": [line["id"]], "params": {"dy_mm": 2}, "note": "dòng hai xuống"})
    assert r.status_code == 201, r.text
    assert r.json()["report"]["affected"]["lines"] == [line["id"]]
    assert sorted(r.json()["report"]["affected"]["words"]) == sorted(line["word_ids"])
