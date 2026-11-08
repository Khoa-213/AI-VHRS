"""Phase 5c on the real database: customer reviews (FR-58, UC-20/59) and the workshop showcase (FR-54, UC-55).

A COMPLETED order is reached through the real flow (production, photos, acceptance, final payment MOCK, hand-over at the
workshop), reusing the helpers of the delivery tests. The public lists also show real reviews and posts, so the tests look for
their own rows by id.
"""
import json

from app.services.reviews import short_name
from tests.test_api_orders import API, _sql
from tests.test_api_delivery_final import W, _final, _final_stage, _pickup, _put
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, manager, policy, staff, store, wcat  # noqa: F401

O = f"{API}/orders"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

def _complete(client, cust, staff, oid):
    """From AWAITING_FINAL_PAYMENT: pick up at the workshop, pay the rest (MOCK), the Staff hands it over -> COMPLETED."""
    _put(client, cust, oid, _pickup())
    p = _final(client, cust, oid).json()["payments"][0]
    assert client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0901234567"})
    assert r.status_code == 200 and r.json()["order_status"] == "COMPLETED", r.text


def _completed(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    _complete(client, cust, staff, oid)
    return oid


def _photo(client, cust, store, oid, data=JPEG, mime="image/jpeg"):
    r = client.post(f"{O}/{oid}/review/photos/upload-url", headers=cust, json={"mime_type": mime, "size_bytes": len(data)})
    assert r.status_code == 201, r.text
    store.put(r.json()["path"], data)
    return r.json()["path"]


def test_short_names_hide_who_wrote_it():
    assert short_name("Nguyễn Văn An") == "Nguyễn V. A." and short_name("An") == "An"
    assert short_name("") == short_name(None) == "Khách hàng"


def test_the_customer_reviews_a_completed_order_once_and_may_edit_it(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    r = client.post(f"{O}/{oid}/review", headers=cust, json={"rating": 5})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_COMPLETED"              # accepted but not paid nor handed over
    r = client.post(f"{O}/{oid}/review/photos/upload-url", headers=cust, json={"mime_type": "image/jpeg", "size_bytes": 10})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_COMPLETED"
    _complete(client, cust, staff, oid)
    assert client.get(f"{O}/{oid}/review", headers=cust).status_code == 404

    # bad photos and values are refused, nothing is stored
    for body, code in (({"rating": 6}, "VALIDATION_ERROR"), ({"rating": 0}, "VALIDATION_ERROR"),
                       ({"rating": 5, "photos": [f"orders/{oid}/review/1/x.jpg"]}, "INVALID_PHOTO"),
                       ({"rating": 5, "photos": [f"orders/{oid}/review/{_sql('select customer_id from orders where id=:o', o=oid)}/none.jpg"]},
                        "PHOTO_NOT_UPLOADED"),
                       ({"rating": 5, "photos": ["x"] * 6}, "VALIDATION_ERROR"),
                       ({"rating": 5, "comment": "a" * 2001}, "VALIDATION_ERROR")):
        r = client.post(f"{O}/{oid}/review", headers=cust, json=body)
        assert r.status_code == 422 and _err(r) == code, (body, r.text)
    fake = _photo(client, cust, store, oid, data=b"not an image")
    r = client.post(f"{O}/{oid}/review", headers=cust, json={"rating": 5, "photos": [fake]})
    assert r.status_code == 422 and _err(r) == "INVALID_PHOTO" and store.read(fake) is None   # a non-image leaves storage
    for mime, size in (("image/gif", 10), ("image/jpeg", 6 * 1024 * 1024)):
        r = client.post(f"{O}/{oid}/review/photos/upload-url", headers=cust, json={"mime_type": mime, "size_bytes": size})
        assert r.status_code == 422, r.text
    assert _sql("select count(*) from reviews where order_id=:o", o=oid) == 0

    a, b = _photo(client, cust, store, oid), _photo(client, cust, store, oid, PNG, "image/png")
    r = client.post(f"{O}/{oid}/review", headers=cust, json={"rating": 5, "comment": "  Chữ đẹp, giao nhanh  ", "photos": [a, b]})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["rating"] == 5 and rev["comment"] == "Chữ đẹp, giao nhanh" and rev["hidden"] is False
    assert [p["path"] for p in rev["photos"]] == [a, b] and all(p["url"] for p in rev["photos"])
    staff_id = staff[1]
    assert _sql("""select count(*) from notifications where account_id=:s and order_id=:o and title like 'Khách đánh giá%'""",
                s=staff_id, o=oid) == 1                                              # the Staff of the order is told
    assert _sql("select count(*) from audit_logs where action='REVIEW_CREATE' and entity_id=:r", r=rev["id"]) == 1
    r = client.post(f"{O}/{oid}/review", headers=cust, json={"rating": 1})
    assert r.status_code == 409 and _err(r) == "REVIEW_EXISTS"
    other, _ = _user(client, "CUSTOMER")
    assert client.get(f"{O}/{oid}/review", headers=other).status_code == 404       # not their order
    assert client.post(f"{O}/{oid}/review", headers=staff[0], json={"rating": 5}).status_code == 403

    # a PUT replaces everything; a photo no longer used leaves storage
    r = client.put(f"{O}/{oid}/review", headers=cust, json={"rating": 3, "photos": [b]})
    assert r.status_code == 200 and r.json()["rating"] == 3 and r.json()["comment"] is None
    assert [p["path"] for p in r.json()["photos"]] == [b] and store.read(a) is None and store.read(b) is not None
    assert client.get(f"{O}/{oid}/review", headers=cust).json()["rating"] == 3

    _sql("update reviews set created_at = now() - interval '31 days' where order_id=:o returning 1", o=oid)
    r = client.put(f"{O}/{oid}/review", headers=cust, json={"rating": 4})
    assert r.status_code == 409 and _err(r) == "REVIEW_EDIT_CLOSED"


def test_the_manager_hides_a_review_from_the_public_list(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _completed(client, cust, staff, mgr, wcat, robot, tech, store)
    photo = _photo(client, cust, store, oid)
    rid = client.post(f"{O}/{oid}/review", headers=cust, json={"rating": 2, "comment": "Giao chậm", "photos": [photo]}).json()["id"]
    boss, boss_id = _user(client, "MANAGER")

    def public():
        r = client.get(f"{API}/catalog/reviews", params={"limit": 50})
        assert r.status_code == 200, r.text
        return r.json()

    pub = public()
    mine = next(i for i in pub["items"] if i["id"] == rid)
    name = _sql("select full_name from accounts where id=(select customer_id from orders where id=:o)", o=oid)
    assert mine["customer_name"] == short_name(name) and mine["photos"] == [f"memory://{photo}"]
    assert "@" not in json.dumps(pub) and pub["count"] >= 1 and pub["by_star"]["2"] >= 1 and pub["average"] is not None
    assert client.get(f"{API}/catalog/reviews", params={"order_type": "OT3_TEMPLATE", "limit": 50}).status_code == 200

    assert client.post(f"{API}/manager/reviews/{rid}/hide", headers=staff[0], json={"reason": "spam spam"}).status_code == 403
    assert client.post(f"{API}/manager/reviews/{rid}/hide", headers=boss, json={"reason": "x"}).status_code == 422
    r = client.post(f"{API}/manager/reviews/{rid}/hide", headers=boss, json={"reason": "Có số điện thoại riêng"})
    assert r.status_code == 200 and r.json()["hidden"] is True
    assert all(i["id"] != rid for i in public()["items"])
    assert client.get(f"{O}/{oid}/review", headers=cust).json()["hidden"] is True       # the author still sees it, marked
    r = client.put(f"{O}/{oid}/review", headers=cust, json={"rating": 5})
    assert r.status_code == 409 and _err(r) == "REVIEW_HIDDEN"
    listed = client.get(f"{API}/manager/reviews", headers=boss, params={"hidden": True, "page_size": 100}).json()
    row = next(i for i in listed["items"] if i["id"] == rid)
    assert row["hidden_at"] and row["customer_name"] == name and row["order_code"]
    assert _sql("select reason from audit_logs where action='REVIEW_HIDE' and entity_id=:r and actor_id=:a",
                r=rid, a=boss_id) == "Có số điện thoại riêng"
    assert client.post(f"{API}/manager/reviews/{rid}/unhide", headers=boss, json={"reason": "Đã xem lại"}).json()["hidden"] is False
    assert any(i["id"] == rid for i in public()["items"])
    assert client.post(f"{API}/manager/reviews/999999999/hide", headers=boss, json={"reason": "không có"}).status_code == 404


def test_staff_post_sample_products_for_the_home_page(client, store, cust):
    sh, sid = _user(client, "STAFF")
    mgr, _ = _user(client, "MANAGER")

    def upload(h, data=JPEG):
        r = client.post(f"{API}/workshop/showcase/upload-url", headers=h, json={"mime_type": "image/jpeg", "size_bytes": len(data)})
        assert r.status_code == 201, r.text
        store.put(r.json()["path"], data)
        return r.json()["path"]

    def public():
        r = client.get(f"{API}/catalog/showcase", params={"limit": 50})
        assert r.status_code == 200
        return {p["id"]: p for p in r.json()}

    assert client.post(f"{API}/workshop/showcase/upload-url", headers=cust,
                       json={"mime_type": "image/jpeg", "size_bytes": 10}).status_code == 403
    img = upload(sh)
    r = client.post(f"{API}/workshop/showcase", headers=sh,
                    json={"image_path": img, "title": "Thiệp cưới viết tay", "description": "Mẫu chữ thư pháp",
                          "order_type": "OT3_TEMPLATE", "sort_order": 1})
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["posted_by"] == sid and post["is_visible"] is True and post["image_url"] == f"memory://{img}"
    shown = public()[post["id"]]
    assert shown["title"] == "Thiệp cưới viết tay" and "posted_by" not in shown and "image_path" not in shown

    other = upload(mgr)                                                        # an image in someone else's folder
    r = client.post(f"{API}/workshop/showcase", headers=sh, json={"image_path": other, "title": "x"})
    assert r.status_code == 422 and _err(r) == "INVALID_PHOTO"
    r = client.post(f"{API}/workshop/showcase", headers=sh, json={"image_path": f"showcase/{sid}/none.jpg", "title": "x"})
    assert r.status_code == 422 and _err(r) == "PHOTO_NOT_UPLOADED"

    r = client.patch(f"{API}/workshop/showcase/{post['id']}", headers=mgr, json={"is_visible": False})
    assert r.status_code == 200 and r.json()["is_visible"] is False
    assert post["id"] not in public()
    assert any(p["id"] == post["id"] for p in client.get(f"{API}/workshop/showcase", headers=sh).json())
    new_img = upload(sh)
    r = client.patch(f"{API}/workshop/showcase/{post['id']}", headers=sh,
                     json={"image_path": new_img, "is_visible": True, "title": "Thiệp cưới"})
    assert r.status_code == 200 and r.json()["image_path"] == new_img and store.read(img) is None    # the old image is gone
    assert public()[post["id"]]["title"] == "Thiệp cưới"

    assert client.delete(f"{API}/workshop/showcase/{post['id']}", headers=sh).status_code == 204
    assert post["id"] not in public() and store.read(new_img) is None
    assert client.delete(f"{API}/workshop/showcase/{post['id']}", headers=sh).status_code == 404
    assert _sql("""select count(*) from audit_logs where entity_type='showcase_post' and entity_id=:p
                   and action in ('SHOWCASE_CREATE', 'SHOWCASE_UPDATE', 'SHOWCASE_DELETE')""", p=post["id"]) == 4
