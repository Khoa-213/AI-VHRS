"""Phase 1 order API: catalog, estimate, drafts, uploads, submit, ownership. Runs on the real DB.

Catalog rows are created with codes starting 'pytest_' and removed by conftest._cleanup.
"""
import uuid
from decimal import Decimal

import cv2
import numpy as np
import pytest
from sqlalchemy import text

from app.api.v1.orders import optional_storage
from app.db.session import get_engine
from app.integrations.storage import InMemoryStorage
from app.main import app
from app.services import pricing as pr
from tests.conftest import auth

API = "/api/v1"


def _sql(stmt: str, **params):
    with get_engine().begin() as c:
        return c.execute(text(stmt), params).scalar()


@pytest.fixture(scope="module")
def catalog():
    tag = "pytest_" + uuid.uuid4().hex[:6]
    ids = {}
    ids["paper"] = _sql("""insert into paper_types (code,name,gsm,surface,size,unit_price,stock_qty)
                           values (:c,'Giay test A4',100,'ART','A4',15000,100) returning id""", c=tag + "_p")
    ids["paper2"] = _sql("""insert into paper_types (code,name,gsm,surface,size,unit_price,stock_qty)
                            values (:c,'Giay test A5 bong',80,'GLOSSY','A5',9000,100) returning id""", c=tag + "_p2")
    ids["pen"] = _sql("""insert into pen_types (code,name,category,stroke_width_mm,f_target_n,f_min_n,f_max_n,f_hard_n,
                         v_max_mm_s,surcharge,stock_qty) values (:c,'But test gel','GEL',0.5,0.6,0.3,1.0,3.0,30,10000,50)
                         returning id""", c=tag + "_g")
    ids["pen2"] = _sql("""insert into pen_types (code,name,category,stroke_width_mm,f_target_n,f_min_n,f_max_n,f_hard_n,
                          v_max_mm_s,surcharge,stock_qty) values (:c,'But test may','FOUNTAIN',0.6,0.3,0.15,0.6,2.0,20,0,50)
                          returning id""", c=tag + "_f")
    ids["ink"] = _sql("insert into ink_colors (pen_type_id,name,hex_code,unit_price,stock_qty) values (:p,'Den','#000000',0,50) returning id",
                      p=ids["pen"])
    ids["ink2"] = _sql("insert into ink_colors (pen_type_id,name,hex_code,unit_price,stock_qty) values (:p,'Xanh','#0000ff',0,50) returning id",
                       p=ids["pen2"])
    _sql("insert into paper_pen_compats (paper_type_id,pen_type_id,is_compatible) values (:a,:b,true) returning 1",
         a=ids["paper"], b=ids["pen"])
    _sql("insert into paper_pen_compats (paper_type_id,pen_type_id,is_compatible) values (:a,:b,false) returning 1",
         a=ids["paper2"], b=ids["pen2"])
    _sql("insert into paper_pen_compats (paper_type_id,pen_type_id,is_compatible) values (:a,:b,true) returning 1",
         a=ids["paper2"], b=ids["pen"])
    ids["tpl"] = _sql("""insert into templates (code,name,kind,font_uri) values (:c,'Mau test','SINGLE_LINE_FONT','x.json')
                         returning id""", c=tag + "_t")
    return ids


@pytest.fixture
def storage():
    mem = InMemoryStorage()
    app.dependency_overrides[optional_storage] = lambda: mem
    yield mem
    app.dependency_overrides.pop(optional_storage, None)


@pytest.fixture
def cust(client):
    return auth(client, "CUSTOMER")


def _png(lines=("Net Viet Nam", "xuong viet tay")) -> bytes:
    img = np.full((900, 1200), 245, np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (60, 120 + i * 110), cv2.FONT_HERSHEY_SIMPLEX, 2.4, 20, 4, cv2.LINE_AA)
    return cv2.imencode(".png", img)[1].tobytes()


def _new(client, h, order_type="OT3_TEMPLATE", quantity=1):
    r = client.post(f"{API}/orders", json={"order_type": order_type, "quantity": quantity}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _materials(client, h, oid, cat):
    r = client.patch(f"{API}/orders/{oid}", headers=h, json={
        "paper_type_id": cat["paper"], "pen_type_id": cat["pen"], "ink_color_id": cat["ink"]})
    assert r.status_code == 200, r.text
    return r.json()


def _upload(client, h, oid, mem, data: bytes, kind="ORIGINAL_IMAGE", mime="image/png"):
    r = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=h,
                    json={"kind": kind, "mime_type": mime, "size_bytes": len(data)})
    assert r.status_code == 201, r.text
    body = r.json()
    path = body["upload_url"].removeprefix("memory://")
    mem.put(path, data)
    return client.post(f"{API}/orders/{oid}/inputs/{body['input_id']}/confirm", headers=h), body["input_id"]


# ---- access control ---------------------------------------------------------------------
def test_orders_require_login_and_customer_role(client):
    assert client.get(f"{API}/orders").status_code == 401
    for role in ("STAFF", "MANAGER", "ADMIN", "TECHNICAL_STAFF"):
        h = auth(client, role)
        assert client.get(f"{API}/orders", headers=h).status_code == 403
        assert client.post(f"{API}/orders", headers=h, json={"order_type": "OT3_TEMPLATE"}).status_code == 403


def test_customer_cannot_see_or_touch_another_customers_order(client, cust, catalog):
    order = _new(client, cust)
    other = auth(client, "CUSTOMER")
    oid = order["id"]
    assert client.get(f"{API}/orders/{oid}", headers=other).status_code == 404
    assert client.patch(f"{API}/orders/{oid}", headers=other, json={"quantity": 3}).status_code == 404
    assert client.delete(f"{API}/orders/{oid}", headers=other).status_code == 404
    assert client.post(f"{API}/orders/{oid}/submit", headers=other, json={"terms_accepted": True}).status_code == 404
    assert client.put(f"{API}/orders/{oid}/inputs/text", headers=other,
                      json={"text_content": "x", "template_id": catalog["tpl"]}).status_code == 404
    assert client.get(f"{API}/orders", headers=other).json()["total"] == 0


# ---- catalog + materials ------------------------------------------------------------------
def test_catalog_filters_pens_by_paper(client, cust, catalog):
    pens = client.get(f"{API}/catalog/pens", params={"paper_id": catalog["paper2"]}, headers=cust).json()
    assert [p["id"] for p in pens if p["id"] in (catalog["pen"], catalog["pen2"])] == [catalog["pen"]]
    inks = client.get(f"{API}/catalog/pens/{catalog['pen']}/inks", headers=cust).json()
    assert [i["id"] for i in inks] == [catalog["ink"]]


def test_incompatible_pen_rejected_msg05(client, cust, catalog):
    oid = _new(client, cust)["id"]
    r = client.patch(f"{API}/orders/{oid}", headers=cust,
                     json={"paper_type_id": catalog["paper2"], "pen_type_id": catalog["pen2"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PEN_INCOMPATIBLE"


def test_ink_must_belong_to_pen_and_pen_comes_first(client, cust, catalog):
    oid = _new(client, cust)["id"]
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"ink_color_id": catalog["ink"]})
    assert r.json()["error"]["code"] == "INK_REQUIRES_PEN"
    r = client.patch(f"{API}/orders/{oid}", headers=cust,
                     json={"paper_type_id": catalog["paper"], "pen_type_id": catalog["pen"],
                           "ink_color_id": catalog["ink2"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INK"


def test_changing_paper_resets_incompatible_pen_with_warning(client, cust, catalog):
    oid = _new(client, cust)["id"]
    _materials(client, cust, oid, catalog)
    # paper2 is compatible with pen -> kept; make pen2 the stored pen via compat paper? use paper2 + pen (ok)
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": catalog["paper2"]})
    assert r.status_code == 200 and r.json()["pen_type_id"] == catalog["pen"]
    _sql("update paper_pen_compats set is_compatible=false where paper_type_id=:a and pen_type_id=:b returning 1",
         a=catalog["paper2"], b=catalog["pen"])
    try:
        oid2 = _new(client, cust)["id"]
        _materials(client, cust, oid2, catalog)
        r = client.patch(f"{API}/orders/{oid2}", headers=cust, json={"paper_type_id": catalog["paper2"]})
        body = r.json()
        assert r.status_code == 200
        assert body["pen_type_id"] is None and body["ink_color_id"] is None
        assert "PEN_RESET" in body["warnings"]
    finally:
        _sql("update paper_pen_compats set is_compatible=true where paper_type_id=:a and pen_type_id=:b returning 1",
             a=catalog["paper2"], b=catalog["pen"])


# ---- estimate -----------------------------------------------------------------------------
def _active_params(order_type_n: int) -> pr.PricingParams:
    with get_engine().connect() as c:
        r = c.execute(text("select * from pricing_configs where is_active")).mappings().one()
    return pr.PricingParams(
        u_per_char=r[f"u_ot{order_type_n}"], w_min=r["w_min"], setup_fee=r[f"s_ot{order_type_n}"],
        k_by_complexity={"SIMPLE": r["k_simple"], "MEDIUM": r["k_medium"], "COMPLEX": r["k_complex"]},
        discount_tiers=pr.parse_tiers(r["discount_tiers"]), p_min_pct=r["p_min_pct"])


def test_estimate_from_typed_text_needs_no_manual_count(client, cust, catalog):
    text_in = "Xin chào các bạn, chúc một ngày tốt lành"
    r = client.post(f"{API}/pricing/estimate", headers=cust, json={
        "order_type": "OT3_TEMPLATE", "quantity": 2, "text": text_in,
        "paper_type_id": catalog["paper"], "pen_type_id": catalog["pen"], "ink_color_id": catalog["ink"]})
    assert r.status_code == 200, r.text
    body = r.json()
    n = pr.count_text_chars(text_in)
    expected = pr.compute_price(_active_params(3), chars=n, quantity=2, complexity="SIMPLE",
                                materials=pr.MaterialPrices(Decimal(15000), Decimal(10000), Decimal(0)))
    assert body["basis"] == "TEXT" and body["materials_priced"] is True
    assert body["chars_min"] == body["chars_max"] == n
    assert Decimal(body["price_min"]) == Decimal(body["price_max"]) == expected.total


def test_estimate_without_content_is_minimum_charge(client, cust):
    r = client.post(f"{API}/pricing/estimate", headers=cust, json={"order_type": "OT1_COPY_RESTORE"})
    assert r.status_code == 200 and r.json()["basis"] == "MINIMUM_CHARGE"


# ---- drafts + inputs ----------------------------------------------------------------------
def test_draft_lifecycle_text_order(client, cust, catalog):
    order = _new(client, cust, quantity=2)
    oid = order["id"]
    assert order["order_status"] == "DRAFT" and order["code"].startswith("VHRS-")
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
                   json={"text_content": "Chúc mừng năm mới", "template_id": catalog["tpl"], "alignment": "CENTER"})
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert d["char_count"] == pr.count_text_chars("Chúc mừng năm mới")
    assert len(d["inputs"]) == 1
    drafts = client.get(f"{API}/orders", params={"status": "DRAFT"}, headers=cust).json()
    assert drafts["total"] == 1 and drafts["items"][0]["id"] == oid
    assert client.delete(f"{API}/orders/{oid}", headers=cust).status_code == 204
    assert client.get(f"{API}/orders/{oid}", headers=cust).status_code == 404


def test_input_kind_must_match_order_type(client, cust, storage):
    oid = _new(client, cust, "OT3_TEMPLATE")["id"]
    r = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=cust,
                    json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/png", "size_bytes": 1000})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INPUT_KIND_NOT_ALLOWED"
    oid1 = _new(client, cust, "OT1_COPY_RESTORE")["id"]
    r = client.put(f"{API}/orders/{oid1}/inputs/text", headers=cust, json={"text_content": "x"})
    assert r.json()["error"]["code"] == "INPUT_KIND_NOT_ALLOWED"


def test_template_required_and_unknown_template_rejected(client, cust, catalog):
    oid = _new(client, cust)["id"]
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust, json={"text_content": "abc"})
    assert r.json()["error"]["code"] == "TEMPLATE_REQUIRED"
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust, json={"text_content": "abc", "template_id": 0})
    assert r.json()["error"]["code"] == "INVALID_TEMPLATE"


def test_canvas_counts_toward_chars(client, cust):
    oid = _new(client, cust)["id"]
    canvas = {"strokes": [{"points": [{"x": 0, "y": 0}, {"x": 400, "y": 0}]}]}   # 400 mm / 40 = 10 chars
    r = client.put(f"{API}/orders/{oid}/inputs/canvas", headers=cust, json={"canvas_data": canvas})
    assert r.status_code == 200
    assert client.get(f"{API}/orders/{oid}", headers=cust).json()["char_count"] == 10
    assert client.put(f"{API}/orders/{oid}/inputs/canvas", headers=cust,
                      json={"canvas_data": {"strokes": []}}).json()["error"]["code"] == "EMPTY_CANVAS"


def test_image_upload_estimates_characters_automatically(client, cust, storage):
    oid = _new(client, cust, "OT1_COPY_RESTORE")["id"]
    r, input_id = _upload(client, cust, oid, storage, _png())
    assert r.status_code == 200, r.text
    q = r.json()["quality_result"]
    assert q["analysed"] is True and q["chars_estimate"] > 0
    d = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert d["char_count"] > 0 and d["estimated_price_min"] is not None
    assert Decimal(d["estimated_price_min"]) <= Decimal(d["estimated_price_max"])
    est = client.post(f"{API}/pricing/estimate", headers=cust,
                      json={"order_type": "OT1_COPY_RESTORE", "order_id": oid}).json()
    assert est["basis"] == "IMAGE_ESTIMATE"
    # rotate -> analysis re-run, still confirmed
    r = client.patch(f"{API}/orders/{oid}/inputs/{input_id}", headers=cust, json={"rotation_deg": 90})
    assert r.status_code == 200 and r.json()["rotation_deg"] == 90


def test_upload_validation(client, cust, storage):
    oid = _new(client, cust, "OT1_COPY_RESTORE")["id"]
    big = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=cust,
                      json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/png", "size_bytes": 21 * 1024 * 1024})
    assert big.status_code == 422 and big.json()["error"]["code"] == "FILE_TOO_LARGE"
    bad = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=cust,
                      json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/gif", "size_bytes": 10})
    assert bad.status_code == 422
    # confirm before anything was uploaded
    r = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=cust,
                    json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/png", "size_bytes": 10})
    iid = r.json()["input_id"]
    assert client.post(f"{API}/orders/{oid}/inputs/{iid}/confirm", headers=cust).status_code == 409
    # an executable disguised as png is rejected by magic-byte sniffing and removed
    path = r.json()["upload_url"].removeprefix("memory://")
    storage.put(path, b"MZ\x90\x00" + b"\x00" * 100)
    r = client.post(f"{API}/orders/{oid}/inputs/{iid}/confirm", headers=cust)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_FILE"
    assert path not in storage.objects


def test_upload_without_storage_config_is_503(client, cust, monkeypatch):
    app.dependency_overrides[optional_storage] = lambda: None
    try:
        oid = _new(client, cust, "OT1_COPY_RESTORE")["id"]
        r = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=cust,
                        json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/png", "size_bytes": 10})
        assert r.status_code == 503 and r.json()["error"]["code"] == "STORAGE_NOT_CONFIGURED"
    finally:
        app.dependency_overrides.pop(optional_storage, None)


# ---- submit -------------------------------------------------------------------------------
def test_submit_rejects_incomplete_order(client, cust):
    oid = _new(client, cust)["id"]
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ORDER_INCOMPLETE"
    fields = {p["field"] for p in r.json()["error"]["details"]}
    assert fields == {"inputs", "materials"}
    assert client.get(f"{API}/orders/{oid}", headers=cust).json()["order_status"] == "DRAFT"


def test_submit_requires_terms(client, cust, catalog):
    oid = _new(client, cust)["id"]
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": False})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TERMS_NOT_ACCEPTED"


def test_submit_complete_ot3_order_and_lock(client, cust, catalog):
    oid = _new(client, cust)["id"]
    _materials(client, cust, oid, catalog)
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
               json={"text_content": "Cảm ơn", "template_id": catalog["tpl"]})
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200, r.text
    assert r.json()["order_status"] == "SUBMITTED" and r.json()["submitted_at"]
    # status history written by the DB trigger with the customer as actor
    rows = _sql("select count(*) from status_histories where order_id=:o and to_status='SUBMITTED' and actor_id is not null",
                o=oid)
    assert rows == 1
    # locked afterwards
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"quantity": 5}).json()["error"]["code"] == "ORDER_NOT_EDITABLE"
    assert client.delete(f"{API}/orders/{oid}", headers=cust).json()["error"]["code"] == "ORDER_NOT_DRAFT"
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust,
                       json={"terms_accepted": True}).status_code == 409


def test_workshop_suggest_materials_allows_submit_without_selection(client, cust, catalog):
    oid = _new(client, cust)["id"]
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"workshop_suggest_materials": True})
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
               json={"text_content": "Hello", "template_id": catalog["tpl"]})
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200


def test_ot2_requires_right_to_use_confirmation(client, cust, catalog, storage):
    oid = _new(client, cust, "OT2_LEARNED_STYLE")["id"]
    _materials(client, cust, oid, catalog)
    _upload(client, cust, oid, storage, _png(), kind="HANDWRITING_SAMPLE")
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust, json={"text_content": "Gửi mẹ"})
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 422
    assert any(p["field"] == "confirm_right_to_use" for p in r.json()["error"]["details"])
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust,
                    json={"terms_accepted": True, "confirm_right_to_use": True})
    assert r.status_code == 200


def test_need_info_flow_allows_edit_and_resubmit(client, cust, catalog):
    oid = _new(client, cust)["id"]
    _materials(client, cust, oid, catalog)
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
               json={"text_content": "Hello", "template_id": catalog["tpl"]})
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    # Staff would move the order to NEED_INFO (Phase 2 API); simulate that decision directly in the DB
    staff_id = _sql("select id from accounts where role_id = 2 order by id limit 1")
    _sql("update orders set order_status='NEED_INFO', info_request_note='Bổ sung ảnh' where id=:o returning 1", o=oid)
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"customer_note": "đã bổ sung"}).status_code == 200
    r = client.post(f"{API}/orders/{oid}/provide-info", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200 and r.json()["order_status"] == "SUBMITTED"
    assert staff_id  # seed staff exists


def test_provide_info_only_from_need_info(client, cust):
    oid = _new(client, cust)["id"]
    r = client.post(f"{API}/orders/{oid}/provide-info", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 409


def test_suspended_order_type_is_refused(client, cust):
    _sql("""insert into system_settings (key, value) values ('order_types_enabled', '["OT1_COPY_RESTORE","OT3_TEMPLATE"]'::jsonb)
            on conflict (key) do update set value = excluded.value returning 1""")
    try:
        r = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT2_LEARNED_STYLE"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_TYPE_SUSPENDED"
        assert client.post(f"{API}/orders", headers=cust, json={"order_type": "OT3_TEMPLATE"}).status_code == 201
    finally:
        _sql("delete from system_settings where key='order_types_enabled' returning 1")
