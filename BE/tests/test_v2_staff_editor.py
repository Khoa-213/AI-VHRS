"""V2 Phase H (owner approved 2026-11-19, H-a/H-b/H-c as recommended): the Staff edit the official sketch with the SAME
Geometry Engine, every official version keeps its `vhrs-sketch/2` document, and the production snapshot locks only the
exact version the customer approved (Test 8).

Flow: customer working sketch (one word moved) -> submit -> accept -> v1 = the customer's document (same ids, strokes
marked CUSTOMER) -> Staff move another word -> v2 (only those strokes change, ids kept, marked STAFF) -> finalize v2 ->
quote -> approve -> deposit -> snapshot of v2. No real robot, no real money (MOCK gateway)."""
import json

from app.services import sketch_geometry as geo
from app.services.stroke_ai import trajectory as tj
from tests.test_api_orders import API, _sql, _upload
from tests.test_api_payments import _paid
from tests.test_api_scheduling import _at, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import W, _err, _ot3, _with_sketch, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_u4_regions import _scan

SK = "/sketch"


def _strokes(doc):
    return {st["id"]: st for p in doc["pages"] for st in p["strokes"]}


def _edit(client, h, oid, version, **body):
    return client.post(f"{W}/orders/{oid}/sketches/{version}/edit", headers=h, json={"note": "chỉnh tay", **body})


def _customer_v1(client, cust, sh, wcat):
    """OT-3 order whose customer moved word 1 before sending; returns (order id, customer's last revision, moved ids)."""
    oid = _ot3(client, cust, wcat, text_="Kính gửi quý khách", submit=False)
    w = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).json()
    word = w["document"]["pages"][0]["words"][0]
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1.0}})
    assert r.status_code == 200, r.text
    e = r.json()
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    return oid, e, word["stroke_ids"]


# ---------------------------------------------------------------------------------------------------------- H1 + H3
def test_v1_keeps_the_customer_document_and_shows_what_the_customer_changed(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, e, moved = _customer_v1(client, cust, sh, wcat)
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    doc = det["document"]
    assert doc and not doc.get("derived")
    assert geo.geometry_hash(doc) == e["revision"]["geometry_hash"] == geo.pages_geometry_hash(tj.parse(det["trajectory"]))
    assert set(_strokes(doc)) == set(_strokes(e["document"]))                        # the customer's ids, not new ones
    marks = {sid: st.get("edited_by") for sid, st in _strokes(doc).items()}
    assert all(marks[s] == ["CUSTOMER"] for s in moved)
    assert all(not v for s, v in marks.items() if s not in moved)
    assert det["edit_summary"]["CUSTOMER"] == len(moved) and det["edit_summary"]["STAFF"] == 0
    assert det["edit_summary"]["strokes"] == len(marks)
    # words keep their text (the assistant / the Staff editor can say "chữ 'Kính'")
    assert [w["text"] for w in doc["pages"][0]["words"]] == ["Kính", "gửi", "quý", "khách"]
    assert _sql("select document_uri is not null and geometry_hash = :g from sketches where order_id=:o and version=1",
                o=oid, g=geo.geometry_hash(doc)) is True


# ---------------------------------------------------------------------------------------------------------- H2
def test_the_staff_edit_with_the_same_engine_and_only_the_selection_changes(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, e, moved = _customer_v1(client, cust, sh, wcat)
    v1 = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["document"]
    word = v1["pages"][0]["words"][2]
    r = _edit(client, sh, oid, 1, op="translate", word_ids=[word["id"]], params={"dy_mm": -1.5})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["version"] == 2 and not out["is_final"]
    assert out["report"]["untouched_verified"] and sorted(out["report"]["changed"]) == sorted(word["stroke_ids"])
    v2 = client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()
    doc2 = v2["document"]
    a, b = _strokes(v1), _strokes(doc2)
    assert set(a) == set(b)                                                          # ids kept
    for sid in a:
        if sid in word["stroke_ids"]:
            assert [[x, round(y + 1.5, 2)] for x, y in b[sid]["points"]] == a[sid]["points"]
            assert b[sid]["edited_by"] == ["STAFF"]
        else:
            assert b[sid] == a[sid]                                                  # byte-identical, CUSTOMER marks kept
    assert v2["edit_summary"]["STAFF"] == len(word["stroke_ids"]) and v2["edit_summary"]["CUSTOMER"] == len(moved)
    assert geo.geometry_hash(doc2) == geo.pages_geometry_hash(tj.parse(v2["trajectory"]))
    eng = v2["trajectory"]["engine"]
    assert eng["name"] == "staff-geometry-edit" and eng["from_version"] == 1 and eng["operation"]["op"] == "translate"
    assert v2["trajectory"]["pages"][0]["strokes"][-1]["kind"] == "watermark" or v2["watermark"] is None
    assert _sql("select count(*) from audit_logs where action='SKETCH_GEOMETRY_EDIT' and entity_id=:s", s=out["id"]) == 1

    # the v1 they started from is unchanged and can no longer be edited (two Staff: optimistic check)
    r = _edit(client, sh, oid, 1, op="translate", word_ids=[word["id"]], params={"dx_mm": 1})
    assert r.status_code == 409 and _err(r) == "SKETCH_VERSION_CONFLICT"
    assert client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["document"] == v1
    # H-a: same limits as the customer (OT-3: 3 mm per edit); refusals save nothing
    r = _edit(client, sh, oid, 2, op="translate", word_ids=[word["id"]], params={"dx_mm": 5})
    assert r.status_code == 422 and _err(r) == "EDIT_OUT_OF_RANGE"
    assert _err(_edit(client, sh, oid, 2, op="rotate", stroke_ids=["s9999"], params={"degrees": 3})) == "STROKE_NOT_FOUND"
    assert _edit(client, sh, oid, 2, op="teleport", stroke_ids=["s1"]).status_code == 422
    assert _edit(client, sh, oid, 2, op="translate", stroke_ids=["s1"], params={"dx_mm": 1}, note="").status_code == 422
    assert _edit(client, cust, oid, 2, op="translate", stroke_ids=["s1"], params={"dx_mm": 1}).status_code == 403
    assert sorted(s["version"] for s in client.get(f"{W}/orders/{oid}/sketches", headers=sh).json()) == [1, 2]
    # compare works across the two versions as before
    r = client.get(f"{W}/orders/{oid}/sketches/compare", headers=sh, params={"from_version": 1, "to_version": 2})
    assert r.status_code == 200, r.text


def test_a_version_saved_before_0025_gets_a_derived_document_and_can_be_edited(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat)                                       # engine v1 (has a document now)
    _sql("update sketches set document_uri = null, geometry_hash = null where order_id=:o returning 1", o=oid)  # pre-0025
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    doc = det["document"]
    assert doc["derived"] is True and geo.geometry_hash(doc) == geo.pages_geometry_hash(tj.parse(det["trajectory"]))
    sid = doc["pages"][0]["strokes"][0]["id"]
    r = _edit(client, sh, oid, 1, op="smooth", stroke_ids=[sid], params={"passes": 2})
    assert r.status_code == 201, r.text
    v2 = client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()["document"]
    assert not v2.get("derived") and _strokes(v2)[sid]["edited_by"] == ["STAFF"]
    assert _sql("select document_uri is null from sketches where order_id=:o and version=1", o=oid) is True  # not backfilled
    # a changed trajectory file of the old version is caught (its document is derived from it)
    path = _sql("select trajectory_uri from sketches where order_id=:o and version=1", o=oid)
    store.objects[path] = store.objects[path].replace(b'"format"', b'"format" ', 1)
    r = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh)
    assert r.status_code == 409 and _err(r) == "GEOMETRY_TAMPERED"


def test_a_changed_document_file_is_refused(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat)
    path = _sql("select document_uri from sketches where order_id=:o and version=1", o=oid)
    doc = json.loads(store.objects[path])
    doc["pages"][0]["strokes"][0]["points"][0][0] += 0.5
    store.objects[path] = geo.dumps(doc)
    r = _edit(client, sh, oid, 1, op="smooth", stroke_ids=[doc["pages"][0]["strokes"][0]["id"]], params={"passes": 1})
    assert r.status_code == 409 and _err(r) == "GEOMETRY_TAMPERED"
    assert _sql("select count(*) from sketches where order_id=:o", o=oid) == 1


def test_ot1_regions_follow_a_staff_edit(client, cust, staff, wcat, store):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    assert _upload(client, cust, oid, store, _scan())[0].status_code == 200
    assert client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).status_code == 201
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    v1 = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    word = v1["document"]["pages"][0]["words"][3]
    r = _edit(client, sh, oid, 1, op="slant", word_ids=[word["id"]], params={"degrees": 6})
    assert r.status_code == 201, r.text
    v2 = client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()
    assert len(v2["regions"]) == len(v1["regions"]) == 6
    src = {x["region_no"]: (x["source"], x["label"]) for x in v2["regions"]}
    before = {x["region_no"]: (x["source"], x["label"]) for x in v1["regions"]}
    edited = word.get("region_no")
    # SD-02: a word the Staff changed is no longer "original ink": ORIGINAL becomes RESTORED, so the customer is told
    assert src[edited] == ("STAFF", "RESTORED" if before[edited][1] == "ORIGINAL" else before[edited][1])
    assert before[edited][1] != "ORIGINAL" or src[edited][1] == "RESTORED"
    assert all(src[k] == before[k] for k in src if k != edited)


# ---------------------------------------------------------------------------------------------------------- H4 (Test 8)
def test_the_snapshot_locks_the_staff_edited_version_the_customer_approved(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, _, _ = _customer_v1(client, cust, sh, wcat)
    doc = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["document"]
    r = _edit(client, sh, oid, 1, op="translate", word_ids=[doc["pages"][0]["words"][1]["id"]], params={"dx_mm": -1})
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert client.post(f"{W}/orders/{oid}/sketches/2/finalize", headers=sh).status_code == 200
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert q.status_code == 201, q.text
    assert client.post(f"{W}/quotations/{q.json()['id']}/send", headers=sh).status_code == 200
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    # after the approval the sketch is frozen for the Staff too
    r = _edit(client, sh, oid, 2, op="translate", stroke_ids=["s1"], params={"dx_mm": 1})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_ACCEPTED"
    p = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"}).json()
    assert client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    snap = _sql("select sketch_id from production_snapshots where order_id=:o and revoked_at is null", o=oid)
    assert snap == v2["id"]
    assert _sql("select sketch_content_hash from sketch_approvals where order_id=:o", o=oid) == v2["content_hash"]


def test_scheduling_refuses_a_final_sketch_that_is_not_the_approved_one(client, cust, staff, mgr, wcat, robot, tech):
    oid, q, _ = _paid(client, cust, staff[0], wcat)
    _sql("update production_snapshots set revoked_at = now(), revoked_reason = 'pytest' where order_id=:o returning 1", o=oid)
    # the approval record is append-only (DB trigger): the final sketch row is what changed after the approval
    _sql("update sketches set content_hash = :h where order_id=:o and is_final returning 1", o=oid, h="0" * 64)
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 409 and _err(r) == "SKETCH_NOT_APPROVED", r.text
    assert _sql("select count(*) from production_jobs where order_id=:o", o=oid) == 0
