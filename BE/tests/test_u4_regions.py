"""Upgrade U4 (docs/UPGRADE_AI_ROBOT_PLAN.md III-B): restoration regions, provenance labels, FAITHFUL / ASSISTED modes,
editing ONE region without touching the strokes of any other region.
"""
import json

import cv2
import numpy as np

from app.services.stroke_ai import recovery, regions as rg
from app.services.stroke_ai.trajectory import Page
from tests.test_api_orders import API, _sql, _upload
from tests.test_api_workshop import W, _err, cust, policy, staff, store, wcat  # noqa: F401


def _scan(faded_gray=None) -> bytes:
    """Two lines of six words; with `faded_gray` the third word ("Nam") is written in washed-out ink."""
    img = np.full((900, 1200), 245, np.uint8)
    cv2.putText(img, "Net Viet", (60, 140), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.6, 30, 5, cv2.LINE_AA)
    cv2.putText(img, "Nam", (560, 140), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.6, faded_gray or 30, 5, cv2.LINE_AA)
    cv2.putText(img, "xuong viet tay", (60, 270), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.6, 30, 5, cv2.LINE_AA)
    return cv2.imencode(".png", img)[1].tobytes()


def _ot1(client, cust, staff, wcat, store, *, mode=None, faded_gray=None):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    body = {"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}
    if mode:
        body["restoration_mode"] = mode
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json=body)
    assert r.status_code == 200 and r.json()["restoration_mode"] == mode, r.text
    assert _upload(client, cust, oid, store, _scan(faded_gray))[0].status_code == 200
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201, r.text
    return oid, r.json()


def _detail(client, sh, oid, v):
    return client.get(f"{W}/orders/{oid}/sketches/{v}", headers=sh).json()


def _region_strokes(detail):
    """{(page, region_no): [compact JSON of each stroke]} — the exact bytes written for every region."""
    out = {}
    for r in detail["regions"]:
        strokes = detail["trajectory"]["pages"][r["page_no"] - 1]["strokes"][r["stroke_start"]:r["stroke_end"]]
        out[(r["page_no"], r["region_no"])] = [json.dumps(s, separators=(",", ":")) for s in strokes]
    return out


# ---- recovery: regions -------------------------------------------------------------------------------
def test_recovery_splits_the_page_into_word_regions_and_flags_faded_ink():
    page, st = recovery.recover_page(_scan(), paper_size="A4")
    assert len(st.regions) == 6 and [r.region_no for r in st.regions] == list(range(1, 7))
    assert st.regions[0].stroke_start == 0 and st.regions[-1].stroke_end == len(page.strokes)
    assert all(a.stroke_end == b.stroke_start for a, b in zip(st.regions, st.regions[1:]))   # contiguous, no gap
    assert all(r.label == "ORIGINAL" and r.confidence >= rg.UNCERTAIN_BELOW for r in st.regions)
    for r in st.regions:
        x0, y0, x1, y1 = r.bbox
        assert all(x0 - .01 <= x <= x1 + .01 and y0 - .01 <= y <= y1 + .01 for s in page.strokes[r.stroke_start:r.stroke_end] for x, y in s.points)
    _, faded = recovery.recover_page(_scan(faded_gray=140), paper_size="A4")
    labels = [r.label for r in faded.regions]
    assert labels[2] == "RESTORED" and labels.count("RESTORED") == 1           # only the washed-out word
    assert faded.regions[2].metrics["contrast"] < rg.UNCERTAIN_BELOW


def test_washed_out_ink_is_kept_and_flagged_instead_of_vanishing():
    """U3 finding: Otsu alone dropped washed-out words silently (no strokes, so no region, so no warning). The faint-ink
    pass keeps them, and their low contrast makes them RESTORED."""
    for gray in (165, 180):
        page, st = recovery.recover_page(_scan(faded_gray=gray), paper_size="A4")
        nam = [r for r in st.regions if r.bbox[0] > 90 and r.bbox[1] < 105]      # first line, right of "Viet"
        assert nam and all(r.label == "RESTORED" for r in nam), (gray, [(r.bbox, r.label) for r in st.regions])
    page, st = recovery.recover_page(_scan(), paper_size="A4")
    assert [r.label for r in st.regions].count("RESTORED") == 0                    # clean page: nothing added


def test_text_is_written_inside_the_region_box():
    box = (20.0, 30.0, 80.0, 45.0)
    strokes = rg.text_in_box("Nam", box, "A4")
    x0, y0, x1, y1 = rg.bbox_of(strokes)
    assert box[0] - 0.01 <= x0 and x1 <= box[2] + 0.01 and box[1] - 0.01 <= y0 and y1 <= box[3] + 0.01
    assert x1 - x0 > 0.9 * (box[2] - box[0]) or y1 - y0 > 0.9 * (box[3] - box[1])          # scaled to fill the box
    page = Page("A4")
    for bad in ([], [[[1, 1]]], [[[1, 1], [999, 1]]]):
        try:
            rg.strokes_from_points(bad, page)
            raise AssertionError("accepted")
        except Exception as e:                                                               # noqa: BLE001
            assert getattr(e, "code", None) == "INVALID_REGION_STROKES"


# ---- API: Staff edit one region ------------------------------------------------------------------------
def test_editing_region_3_keeps_every_other_region_byte_for_byte(client, cust, staff, wcat, store):
    sh, staff_id = staff
    oid, s1 = _ot1(client, cust, staff, wcat, store)
    assert s1["region_counts"] == {"ORIGINAL": 6}
    d1 = _detail(client, sh, oid, 1)
    before = _region_strokes(d1)
    r3 = next(r for r in d1["regions"] if r["region_no"] == 3)
    new = [[[r3["x0"], r3["y0"]], [r3["x1"], r3["y1"]]], [[r3["x0"], r3["y1"]], [r3["x1"], r3["y0"]]]]
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{r3['id']}/edit", headers=sh,
                    json={"action": "REPLACE_STROKES", "strokes": [[[float(x), float(y)] for x, y in s] for s in new],
                          "note": "Nét chữ N bị nhoè, vẽ lại theo ảnh"})
    assert r.status_code == 201, r.text
    s2 = r.json()
    assert s2["version"] == 2 and s2["region_counts"] == {"ORIGINAL": 5, "RESTORED": 1} and s2["is_final"] is False
    d2 = _detail(client, sh, oid, 2)
    after = _region_strokes(d2)
    assert set(after) == set(before)                                       # numbers are stable
    for key in before:
        if key[1] != 3:
            assert after[key] == before[key], key                          # same bytes for every other region
    assert len(after[(1, 3)]) == 2 and after[(1, 3)] != before[(1, 3)]
    e3 = next(x for x in d2["regions"] if x["region_no"] == 3)
    assert (e3["label"], e3["source"], e3["edited_by"], e3["confidence"]) == ("RESTORED", "STAFF", staff_id, None)
    assert e3["note"] == "Nét chữ N bị nhoè, vẽ lại theo ảnh"
    assert d2["trajectory"]["engine"]["region_edits"] == [
        {"from_version": 1, "page": 1, "region": 3, "action": "REPLACE_STROKES", "label": "RESTORED"}]
    assert _sql("select count(*) from audit_logs where action='SKETCH_REGION_EDIT' and entity_id=:s", s=s2["id"]) == 1

    # a second Staff still on v1 is refused instead of silently forking the sketch
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{r3['id']}/edit", headers=sh,
                    json={"action": "REMOVE", "note": "x"})
    assert r.status_code == 409 and _err(r) == "SKETCH_VERSION_CONFLICT" and r.json()["error"]["details"]["latest_version"] == 2

    # removing region 2 shifts the stroke ranges after it and keeps their bytes
    r2 = next(x for x in d2["regions"] if x["region_no"] == 2)
    r = client.post(f"{W}/orders/{oid}/sketches/2/regions/{r2['id']}/edit", headers=sh,
                    json={"action": "REMOVE", "note": "Vết bẩn, không phải chữ"})
    assert r.status_code == 201, r.text
    d3 = _detail(client, sh, oid, 3)
    after3 = _region_strokes(d3)
    assert (1, 2) not in after3 and all(after3[k] == after[k] for k in after3)
    total = len(d3["trajectory"]["pages"][0]["strokes"])
    assert total == len(d2["trajectory"]["pages"][0]["strokes"]) - (r2["stroke_end"] - r2["stroke_start"])
    assert client.post(f"{W}/orders/{oid}/sketches/3/regions/999999999/edit", headers=sh,
                       json={"action": "REMOVE", "note": "x"}).status_code == 404


def test_faithful_mode_never_accepts_inferred_strokes(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, _ = _ot1(client, cust, staff, wcat, store)                       # no choice = FAITHFUL
    reg = _detail(client, sh, oid, 1)["regions"][0]
    for body in ({"action": "TEXT", "text": "Nam", "note": "đoán"},
                 {"action": "REPLACE_STROKES", "label": "INFERRED", "strokes": [[[20, 20], [30, 30]]], "note": "đoán"}):
        r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{reg['id']}/edit", headers=sh, json=body)
        assert r.status_code == 409 and _err(r) == "INFERRED_NOT_ALLOWED"
    _sql("update sketch_regions set label='INFERRED' where id=:r returning 1", r=reg["id"])     # defence in depth
    r = client.post(f"{W}/orders/{oid}/sketches/1/finalize", headers=sh)
    assert r.status_code == 409 and _err(r) == "INFERRED_NOT_ALLOWED" and r.json()["error"]["details"]["regions"] == [1]


def test_assisted_mode_writes_text_into_a_region_and_the_customer_sees_the_labels(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, s1 = _ot1(client, cust, staff, wcat, store, mode="ASSISTED", faded_gray=140)
    assert s1["region_counts"] == {"ORIGINAL": 5, "RESTORED": 1} and "UNCERTAIN_REGIONS" in s1["warnings"]
    reg = next(x for x in _detail(client, sh, oid, 1)["regions"] if x["region_no"] == 1)
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{reg['id']}/edit", headers=sh,
                    json={"action": "TEXT", "text": "Nét", "note": "Khách xác nhận chữ đầu là 'Nét'"})
    assert r.status_code == 201, r.text
    assert r.json()["region_counts"] == {"INFERRED": 1, "ORIGINAL": 4, "RESTORED": 1}
    assert client.post(f"{W}/orders/{oid}/sketches/2/finalize", headers=sh).status_code == 200
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"char_count": 20})
    assert q.status_code == 201, q.text
    assert client.post(f"{W}/quotations/{q.json()['id']}/send", headers=sh).status_code == 200
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    view = client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]
    assert view["restoration_mode"] == "ASSISTED"
    assert view["region_counts"] == {"INFERRED": 1, "ORIGINAL": 4, "RESTORED": 1}
    shown = {(x["region_no"], x["label"]) for x in view["regions"]}
    assert shown == {(1, "INFERRED"), (3, "RESTORED")}                      # ORIGINAL regions are not listed
    assert next(x for x in view["regions"] if x["region_no"] == 1)["text"] == "Nét"


def test_restoration_mode_is_only_for_ot1(client, cust):
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT3_TEMPLATE"}).json()["id"]
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"restoration_mode": "ASSISTED"})
    assert r.status_code == 422 and _err(r) == "RESTORATION_MODE_OT1_ONLY"
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"restoration_mode": "MAGIC"})
    assert r.status_code == 422
