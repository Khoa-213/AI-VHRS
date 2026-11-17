"""Upgrade U2 (rest): comparing two sketch versions, for the Staff (any two versions) and for the customer (the current
quote's sketch against one that was sent before)."""
import cv2
import numpy as np

from app.services import sketch_compare
from app.services.stroke_ai.trajectory import Page, Stroke
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _err, _sent, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_u4_regions import _detail, _ot1


def test_the_page_diff_matches_strokes_one_for_one_and_draws_an_overlay():
    a = Page("A5", [Stroke([(10, 10), (20, 20)]), Stroke([(30, 30), (40, 40)]), Stroke([(10, 10), (20, 20)])])
    b = Page("A5", [Stroke([(10, 10), (20, 20)]), Stroke([(30, 30), (41, 40)]), Stroke([(50, 50), (60, 60)])])
    kept, removed, added = sketch_compare._page_diff(a, b)
    assert (len(kept), len(removed), len(added)) == (1, 2, 2)             # a moved stroke = removed + added
    assert sketch_compare._page_diff(a, None)[1] == a.strokes             # a dropped page: every stroke removed
    img = cv2.imdecode(np.frombuffer(sketch_compare.overlay_jpeg(b, kept, removed, added, "AI-1"), np.uint8),
                       cv2.IMREAD_COLOR)
    assert img.shape[:2] == (round(b.height_mm * 2), round(b.width_mm * 2))
    reds = (img[:, :, 2] > 150) & (img[:, :, 0] < 120) & (img[:, :, 1] < 120)
    blues = (img[:, :, 0] > 150) & (img[:, :, 2] < 120)
    assert reds.any() and blues.any()
    assert img[-10:, :].min() < 160                                       # the AI band (U2) is on the image


def test_staff_compare_two_versions_with_strokes_metrics_and_regions(client, cust, staff, wcat, store):
    sh, _ = staff
    oid, _ = _ot1(client, cust, staff, wcat, store)
    d1 = _detail(client, sh, oid, 1)
    r3 = next(r for r in d1["regions"] if r["region_no"] == 3)
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{r3['id']}/edit", headers=sh,
                    json={"action": "REPLACE_STROKES", "strokes": [[[float(r3["x0"]), float(r3["y0"])],
                                                                    [float(r3["x1"]), float(r3["y1"])]]],
                          "note": "vẽ lại"})
    assert r.status_code == 201, r.text
    r = client.get(f"{W}/orders/{oid}/sketches/compare", headers=sh, params={"from_version": 1, "to_version": 2})
    assert r.status_code == 200, r.text
    c = r.json()
    assert (c["from_version"], c["to_version"], c["identical"]) == (1, 2, False)
    p1 = c["pages"][0]
    old_n = r3["stroke_end"] - r3["stroke_start"]
    assert p1["changed"] and p1["removed"] == old_n and p1["added"] == 1
    assert p1["kept"] == len(d1["trajectory"]["pages"][0]["strokes"]) - old_n     # every other stroke kept as is
    assert p1["image_url"]
    assert c["regions"] == [{"page_no": 1, "region_no": 3, "change": "LABEL_CHANGED", "from_label": "ORIGINAL",
                             "to_label": "RESTORED", "text": None, "note": "vẽ lại"}]
    m = c["metrics"]
    assert m["pen_lift_count"]["from"] == d1["pen_lift_count"] and m["pages"] == {"from": 1, "to": 1, "delta": 0}
    assert store.read(f"orders/{oid}/sketches/compare_v1_v2_p1.jpg")[:2] == b"\xff\xd8"
    # same version / unknown version / customer has no access to the Staff route
    r = client.get(f"{W}/orders/{oid}/sketches/compare", headers=sh, params={"from_version": 2, "to_version": 2})
    assert r.status_code == 422 and _err(r) == "SAME_VERSION"
    r = client.get(f"{W}/orders/{oid}/sketches/compare", headers=sh, params={"from_version": 1, "to_version": 9})
    assert r.status_code == 404 and _err(r) == "SKETCH_NOT_FOUND"
    assert client.get(f"{W}/orders/{oid}/sketches/compare", headers=cust,
                      params={"from_version": 1, "to_version": 2}).status_code == 403


def test_the_customer_compares_the_requote_with_the_sketch_sent_before(client, cust, staff, wcat):
    sh, _ = staff
    oid, q1 = _sent(client, cust, sh, wcat)
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    r = client.get(f"{API}/orders/{oid}/quotation/compare", headers=cust)
    assert r.status_code == 404 and _err(r) == "NO_PREVIOUS_VERSION"
    assert client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust,
                       json={"note": "Chữ khác đi"}).status_code == 200
    v2 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"seed": 3}).json()["version"]
    v3 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"seed": 5}).json()["version"]
    assert client.post(f"{W}/orders/{oid}/sketches/{v3}/finalize", headers=sh).status_code == 200
    q2 = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"revision_reason": "Đổi nét theo yêu cầu"}).json()
    assert client.post(f"{W}/quotations/{q2['id']}/send", headers=sh).status_code == 200

    r = client.get(f"{API}/orders/{oid}/quotation/compare", headers=cust)
    assert r.status_code == 200, r.text
    c = r.json()
    v1 = _sql("select version from sketches where id=:s", s=q1["sketch_id"])
    assert (c["from_version"], c["to_version"]) == (v1, v3)
    assert c["versions_available"] == [v1]                                 # v2 was never sent: not comparable
    assert c["quote"] == {"from_quotation_version": 1, "to_quotation_version": 2, "from_total": int(float(q1["final_total"])),
                          "to_total": int(float(q2["final_total"])), "revision_reason": "Đổi nét theo yêu cầu"}
    assert any(p["changed"] for p in c["pages"]) and all(p["image_url"] for p in c["pages"] if p["changed"])
    r = client.get(f"{API}/orders/{oid}/quotation/compare", headers=cust, params={"against_version": v2})
    assert r.status_code == 404 and _err(r) == "SKETCH_NOT_FOUND"          # a Staff draft stays private
