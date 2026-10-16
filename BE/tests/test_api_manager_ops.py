"""Phase 3, Manager side: materials, stock, compatibility, templates, handwriting styles, robots, versioned prices.

Runs on the real database. Everything created here carries a 'pytest_' code and is removed by conftest; a saved
PricingConfig version is rolled back (the previously active version is made active again) after each test.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db.session import get_engine
from tests.conftest import auth
from tests.test_api_orders import API, _png, _sql  # noqa: F401
from tests.test_api_workshop import (W, _err, _quoted as _draft_quote, _user, cust, manager, policy,  # noqa: F401
                                     staff, store, wcat)

M = f"{API}/manager"


def _tag() -> str:
    return "pytest_" + uuid.uuid4().hex[:8]


@pytest.fixture
def mgr(client):
    return _user(client, "MANAGER")[0]


def _paper(client, mgr, **kw):
    body = {"code": _tag() + "_p", "name": "Giay thu", "gsm": 100, "surface": "ART", "size": "A5", "unit_price": 9000,
            "stock_qty": 10, **kw}
    r = client.post(f"{M}/papers", headers=mgr, json=body)
    assert r.status_code == 201, r.text
    return r.json()


GEL = {"category": "GEL", "stroke_width_mm": 0.5, "f_target_n": 0.6, "f_min_n": 0.36, "f_max_n": 0.84, "f_hard_n": 3.0,
       "v_max_mm_s": 30, "surcharge": 5000, "stock_qty": 20}


def _pen(client, mgr, **kw):
    r = client.post(f"{M}/pens", headers=mgr, json={"code": _tag() + "_n", "name": "But thu", **GEL, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _audit(action, entity_id):
    return _sql("select count(*) from audit_logs where action=:a and entity_id=:i", a=action, i=entity_id)


# ---- access -----------------------------------------------------------------------------------------
READS = ["/manager/papers", "/manager/pens", "/manager/inks", "/manager/compatibility", "/manager/templates",
         "/manager/styles", "/manager/robots", "/manager/pricing-config", "/manager/pricing-config/versions",
         "/manager/schedule/queue", "/manager/jobs", "/manager/technicians"]


def test_manager_endpoints_reject_everyone_else(client):
    for path in READS:
        assert client.get(f"{API}{path}").status_code == 401, path
    for role in ("CUSTOMER", "STAFF", "TECHNICAL_STAFF", "ADMIN"):       # Admin runs the system, not the workshop (BR-02)
        h = auth(client, role)
        for path in READS:
            assert client.get(f"{API}{path}", headers=h).status_code == 403, (role, path)
        assert client.post(f"{M}/pricing-config", headers=h, json={"adjust_threshold_pct": 10}).status_code == 403
        assert client.post(f"{M}/robots", headers=h, json={"code": "pytest_x"}).status_code == 403
        assert client.post(f"{M}/papers/1/stock", headers=h, json={"mode": "ADD", "quantity": 1, "reason": "x"}).status_code == 403


# ---- papers -----------------------------------------------------------------------------------------
def test_paper_lifecycle_audit_and_public_visibility(client, mgr):
    p = _paper(client, mgr)
    assert p["is_active"] is True and p["stock_qty"] == 10 and p["surface"] == "ART"
    dup = client.post(f"{M}/papers", headers=mgr, json={"code": p["code"], "name": "x", "gsm": 80, "surface": "PLAIN",
                                                         "size": "A4", "unit_price": 1})
    assert dup.status_code == 409 and _err(dup) == "CODE_TAKEN"
    base = {"name": "x", "gsm": 80, "surface": "PLAIN", "size": "A4", "unit_price": 1}
    for bad in ({"code": "bad code!"}, {"code": "pytest_zz", "gsm": 0}, {"code": "pytest_zz", "size": "A3"},
                {"code": "pytest_zz", "surface": "VELVET"}, {"code": "pytest_zz", "unit_price": -1}, {"code": "x"}):
        assert client.post(f"{M}/papers", headers=mgr, json={**base, **bad}).status_code == 422, bad
    assert p["id"] in [x["id"] for x in client.get(f"{API}/catalog/papers").json()]
    r = client.patch(f"{M}/papers/{p['id']}", headers=mgr, json={"unit_price": 12000, "name": "Giay thu moi"})
    assert r.status_code == 200 and r.json()["unit_price"] == "12000" and r.json()["name"] == "Giay thu moi"
    assert _sql("select old_value->>'unit_price' from audit_logs where action='CATALOG_PAPER_UPDATE' and entity_id=:i", i=p["id"]) == "9000"
    for same in ({}, {"unit_price": 12000}, {"name": None}):
        r = client.patch(f"{M}/papers/{p['id']}", headers=mgr, json=same)
        assert r.status_code == 422 and _err(r) == "NO_CHANGES", same
    assert client.patch(f"{M}/papers/{p['id']}", headers=mgr, json={"is_active": False}).status_code == 200
    assert p["id"] not in [x["id"] for x in client.get(f"{API}/catalog/papers").json()]      # hidden from customers
    assert p["id"] in [x["id"] for x in client.get(f"{M}/papers", headers=mgr).json()]       # still managed
    assert client.patch(f"{M}/papers/999999999", headers=mgr, json={"unit_price": 1}).status_code == 404
    assert _audit("CATALOG_PAPER_CREATE", p["id"]) == 1


def test_stock_adjustments_are_audited_and_never_negative(client, mgr):
    p = _paper(client, mgr, stock_qty=10)
    url = f"{M}/papers/{p['id']}/stock"
    assert client.post(url, headers=mgr, json={"mode": "ADD", "quantity": 5, "reason": "Nhập kho"}).json()["stock_qty"] == 15
    r = client.post(url, headers=mgr, json={"mode": "ADD", "quantity": -20, "reason": "Hỏng"})
    assert r.status_code == 422 and _err(r) == "STOCK_NEGATIVE" and r.json()["error"]["details"] == {"current": 15}
    assert client.post(url, headers=mgr, json={"mode": "SET", "quantity": 3, "reason": "Kiểm kê"}).json()["stock_qty"] == 3
    for bad in ({"mode": "SET", "quantity": -1, "reason": "x"}, {"mode": "ADD", "quantity": 1, "reason": ""},
                {"mode": "ADD", "quantity": 1}, {"mode": "MUL", "quantity": 2, "reason": "x"}):
        assert client.post(url, headers=mgr, json=bad).status_code == 422, bad
    assert _audit("STOCK_ADJUST", p["id"]) == 2
    assert _sql("select reason from audit_logs where action='STOCK_ADJUST' and entity_id=:i order by id desc limit 1", i=p["id"]) == "Kiểm kê"
    assert _sql("select old_value->>'stock_qty' from audit_logs where action='STOCK_ADJUST' and entity_id=:i order by id desc limit 1", i=p["id"]) == "15"
    assert client.post(f"{M}/papers/999999999/stock", headers=mgr, json={"mode": "ADD", "quantity": 1, "reason": "x"}).status_code == 404


# ---- pens and inks ----------------------------------------------------------------------------------
def test_pen_force_profile_is_validated_on_create_and_update(client, mgr):
    bad = client.post(f"{M}/pens", headers=mgr, json={"code": _tag() + "_n", "name": "x", **{**GEL, "f_min_n": 0.7}})
    assert bad.status_code == 422                                           # F_min must be below F_target
    assert client.post(f"{M}/pens", headers=mgr, json={"code": _tag() + "_n", "name": "x", **{**GEL, "f_target_n": 0.2}}).status_code == 422
    pen = _pen(client, mgr)
    r = client.patch(f"{M}/pens/{pen['id']}", headers=mgr, json={"f_hard_n": 0.5})          # below F_max
    assert r.status_code == 422 and _err(r) == "INVALID_FORCE_PROFILE"
    r = client.patch(f"{M}/pens/{pen['id']}", headers=mgr, json={"surcharge": 8000, "f_hard_n": 2.5})
    assert r.status_code == 200 and r.json()["surcharge"] == "8000" and r.json()["f_hard_n"] == "2.50"
    assert _audit("CATALOG_PEN_UPDATE", pen["id"]) == 1
    dup = client.post(f"{M}/pens", headers=mgr, json={"code": pen["code"], "name": "x", **GEL})
    assert dup.status_code == 409 and _err(dup) == "CODE_TAKEN"
    assert client.post(f"{M}/pens/{pen['id']}/stock", headers=mgr, json={"mode": "ADD", "quantity": 4, "reason": "r"}).json()["stock_qty"] == 24


def test_inks_belong_to_a_pen_and_can_be_switched_off(client, mgr):
    pen = _pen(client, mgr)
    r = client.post(f"{M}/pens/{pen['id']}/inks", headers=mgr, json={"name": "Đen", "hex_code": "#000000", "unit_price": 0, "stock_qty": 5})
    assert r.status_code == 201, r.text
    ink = r.json()
    assert ink["pen_type_id"] == pen["id"]
    dup = client.post(f"{M}/pens/{pen['id']}/inks", headers=mgr, json={"name": "đen"})
    assert dup.status_code == 409 and _err(dup) == "NAME_TAKEN"
    assert client.post(f"{M}/pens/{pen['id']}/inks", headers=mgr, json={"name": "Đỏ", "hex_code": "red"}).status_code == 422
    assert client.post(f"{M}/pens/999999999/inks", headers=mgr, json={"name": "Xanh"}).status_code == 404
    assert [i["id"] for i in client.get(f"{M}/inks", headers=mgr, params={"pen_id": pen["id"]}).json()] == [ink["id"]]
    assert ink["id"] in [i["id"] for i in client.get(f"{API}/catalog/pens/{pen['id']}/inks").json()]
    assert client.patch(f"{M}/inks/{ink['id']}", headers=mgr, json={"unit_price": 1500}).json()["unit_price"] == "1500"
    assert client.patch(f"{M}/inks/{ink['id']}", headers=mgr, json={"is_active": False}).status_code == 200
    assert client.get(f"{API}/catalog/pens/{pen['id']}/inks").json() == []
    assert client.post(f"{M}/inks/{ink['id']}/stock", headers=mgr, json={"mode": "SET", "quantity": 0, "reason": "hết"}).json()["stock_qty"] == 0


def test_compatibility_matrix_drives_the_public_catalog(client, mgr):
    paper, pen = _paper(client, mgr), _pen(client, mgr)
    listed = lambda: [p["id"] for p in client.get(f"{API}/catalog/pens", params={"paper_id": paper["id"]}).json()]  # noqa: E731
    assert pen["id"] not in listed()                                        # no row = not compatible (BR-05)
    r = client.put(f"{M}/compatibility/{paper['id']}/{pen['id']}", headers=mgr, json={"is_compatible": True})
    assert r.status_code == 200 and r.json()["is_compatible"] is True
    assert pen["id"] in listed()
    r = client.put(f"{M}/compatibility/{paper['id']}/{pen['id']}", headers=mgr,
                   json={"is_compatible": False, "note": "Mực loang"})
    assert r.json()["note"] == "Mực loang" and pen["id"] not in listed()
    rows = [c for c in client.get(f"{M}/compatibility", headers=mgr).json() if c["paper_type_id"] == paper["id"]]
    assert rows == [{"paper_type_id": paper["id"], "pen_type_id": pen["id"], "is_compatible": False, "note": "Mực loang"}]
    assert client.put(f"{M}/compatibility/999999999/{pen['id']}", headers=mgr, json={"is_compatible": True}).status_code == 404
    assert _audit("CATALOG_COMPAT_SET", paper["id"]) == 2


# ---- templates and handwriting styles ---------------------------------------------------------------
def test_template_management_and_visibility(client, mgr):
    code = _tag() + "_t"
    r = client.post(f"{M}/templates", headers=mgr, json={"code": code, "name": "Mẫu thử", "kind": "SINGLE_LINE_FONT",
                                                          "font_uri": "hershey:scripts"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert client.post(f"{M}/templates", headers=mgr, json={"code": code, "name": "x", "kind": "CALLIGRAPHY",
                                                            "font_uri": "hershey:futural"}).status_code == 409
    for uri in ("fonts/x.json", "hershey:nonexistent", "hershey:", "scripts"):
        r = client.post(f"{M}/templates", headers=mgr, json={"code": _tag() + "_t", "name": "x", "kind": "CALLIGRAPHY", "font_uri": uri})
        assert r.status_code == 422 and _err(r) == "UNSUPPORTED_FONT", uri
    assert t["id"] in [x["id"] for x in client.get(f"{API}/catalog/templates").json()]
    assert client.get(f"{API}/catalog/templates/{t['id']}/preview").status_code == 200          # the engine can draw it
    assert client.patch(f"{M}/templates/{t['id']}", headers=mgr, json={"font_uri": "hershey:rowmans", "name": "Mẫu La Mã"}).status_code == 200
    assert client.patch(f"{M}/templates/{t['id']}", headers=mgr, json={"font_uri": "oops"}).status_code == 422
    assert client.patch(f"{M}/templates/{t['id']}", headers=mgr, json={"is_active": False}).status_code == 200
    assert t["id"] not in [x["id"] for x in client.get(f"{API}/catalog/templates").json()]      # FR-42: inactive is hidden
    assert t["id"] in [x["id"] for x in client.get(f"{M}/templates", headers=mgr).json()]
    assert client.patch(f"{M}/templates/{t['id']}", headers=mgr, json={}).status_code == 422
    assert _sql("select created_by from templates where id=:i", i=t["id"]) is not None


def _style(owner_id, status="PENDING_REVIEW", right=True):
    return _sql("""insert into handwriting_styles (owner_id,name,status,right_to_use_confirmed)
                   values (:o,'Bộ nét thử',cast(:s as style_status),:r) returning id""", o=owner_id, s=status, r=right)


def test_handwriting_style_review(client, mgr):
    owner_h, owner_id = _user(client, "CUSTOMER")
    ok, no_right, to_reject = _style(owner_id), _style(owner_id, right=False), _style(owner_id)
    pending = {s["id"] for s in client.get(f"{M}/styles", headers=mgr).json()}
    assert {ok, no_right, to_reject} <= pending
    assert client.get(f"{API}/catalog/my-styles", headers=owner_h).json() == []             # nothing approved yet
    r = client.post(f"{M}/styles/{ok}/approve", headers=mgr)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED" and r.json()["approved_by"] and r.json()["approved_at"]
    assert [s["id"] for s in client.get(f"{API}/catalog/my-styles", headers=owner_h).json()] == [ok]
    again = client.post(f"{M}/styles/{ok}/approve", headers=mgr)
    assert again.status_code == 409 and _err(again) == "STYLE_NOT_PENDING"
    r = client.post(f"{M}/styles/{no_right}/approve", headers=mgr)
    assert r.status_code == 409 and _err(r) == "RIGHT_TO_USE_NOT_CONFIRMED"                 # FR-07 / BR-23
    assert client.post(f"{M}/styles/{to_reject}/reject", headers=mgr, json={"reason": ""}).status_code == 422
    r = client.post(f"{M}/styles/{to_reject}/reject", headers=mgr, json={"reason": "Ảnh mờ"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert _sql("select reason from audit_logs where action='STYLE_REJECT' and entity_id=:i", i=to_reject) == "Ảnh mờ"
    assert client.post(f"{M}/styles/999999999/approve", headers=mgr).status_code == 404
    done = {s["id"] for s in client.get(f"{M}/styles", headers=mgr, params={"status": "APPROVED"}).json()}
    assert ok in done and to_reject not in done


# ---- robots -----------------------------------------------------------------------------------------
def test_robot_management(client, mgr):
    code = _tag() + "_r"
    r = client.post(f"{M}/robots", headers=mgr, json={"code": code, "station": "Bàn 9", "supported_pen_categories": ["GEL", "FOUNTAIN"]})
    assert r.status_code == 201, r.text
    robot = r.json()
    assert robot["status"] == "AVAILABLE" and robot["robot_type"] == "FAIRINO_FR3" and robot["is_simulated"] is False
    assert client.post(f"{M}/robots", headers=mgr, json={"code": code}).status_code == 409
    assert client.post(f"{M}/robots", headers=mgr, json={"code": _tag() + "_r", "status": "BUSY"}).json()["error"]["code"] == "STATUS_NOT_SETTABLE"
    assert client.post(f"{M}/robots", headers=mgr, json={"code": _tag() + "_r", "supported_pen_categories": ["CRAYON"]}).status_code == 422
    r = client.patch(f"{M}/robots/{robot['id']}", headers=mgr, json={"station": "Bàn 10", "note": "Đã hiệu chỉnh"})
    assert r.status_code == 200 and r.json()["station"] == "Bàn 10" and r.json()["affected_job_ids"] == []
    assert client.patch(f"{M}/robots/{robot['id']}", headers=mgr, json={"status": "BUSY"}).json()["error"]["code"] == "STATUS_NOT_SETTABLE"
    r = client.patch(f"{M}/robots/{robot['id']}", headers=mgr, json={"status": "MAINTENANCE"})
    assert r.status_code == 200 and r.json()["status"] == "MAINTENANCE"
    ids = lambda **p: [x["id"] for x in client.get(f"{M}/robots", headers=mgr, params=p).json()]  # noqa: E731
    assert robot["id"] in ids() and robot["id"] in ids(status="MAINTENANCE") and robot["id"] not in ids(status="AVAILABLE")
    assert client.patch(f"{M}/robots/{robot['id']}", headers=mgr, json={}).status_code == 422
    assert client.patch(f"{M}/robots/999999999", headers=mgr, json={"station": "x"}).status_code == 404
    assert _audit("ROBOT_UPDATE", robot["id"]) == 2


# ---- versioned prices (FR-30) -----------------------------------------------------------------------
@pytest.fixture
def pricing_guard():
    """Saving a price version deactivates the real one. Put the real one back after the test."""
    real = _sql("select version from pricing_configs where is_active")
    yield real
    with get_engine().begin() as c:
        c.execute(text("update pricing_configs set is_active=false where is_active and version<>:v"), {"v": real})
        c.execute(text("update pricing_configs set is_active=true where version=:v"), {"v": real})


def test_pricing_config_versions(client, mgr, pricing_guard):
    cur = client.get(f"{M}/pricing-config", headers=mgr).json()
    assert cur["version"] == pricing_guard and cur["is_active"] is True
    r = client.post(f"{M}/pricing-config", headers=mgr, json={"adjust_threshold_pct": 10, "note": "Ngưỡng thận trọng hơn"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["version"] == max(v["version"] for v in client.get(f"{M}/pricing-config/versions", headers=mgr).json()) > cur["version"]
    assert new["is_active"] is True and Decimal(new["adjust_threshold_pct"]) == 10 and new["note"] == "Ngưỡng thận trọng hơn"
    assert new["created_by"]
    for f in ("u_ot1", "u_ot3", "w_min", "s_ot1", "k_simple", "k_complex", "p_min_pct", "canvas_mm_per_char"):
        assert new[f] == cur[f], f                                          # untouched fields are copied
    assert new["discount_tiers"] == cur["discount_tiers"]
    versions = client.get(f"{M}/pricing-config/versions", headers=mgr).json()
    assert [v["is_active"] for v in versions].count(True) == 1 and versions[0]["version"] == new["version"]
    assert client.get(f"{M}/pricing-config", headers=mgr).json()["version"] == new["version"]
    assert _sql("select is_active from pricing_configs where version=:v", v=cur["version"]) is False         # old one kept, inactive
    row = _sql("select new_value::text from audit_logs where action='PRICING_CONFIG_SAVE' and entity_id=:i", i=new["id"])
    assert '"adjust_threshold_pct"' in row and '"u_ot1"' not in row                                        # diff, not the whole row
    assert _sql("select reason from audit_logs where action='PRICING_CONFIG_SAVE' and entity_id=:i", i=new["id"]) == "Ngưỡng thận trọng hơn"


def test_pricing_config_rejects_bad_or_empty_changes(client, mgr, pricing_guard):
    before = client.get(f"{M}/pricing-config/versions", headers=mgr).json()
    for body, code in (({}, "NO_CHANGES"), ({"adjust_threshold_pct": 15}, "NO_CHANGES"),
                       ({"k_medium": 0.5}, "INVALID_PRICING"), ({"u_ot1": 250}, "INVALID_PRICING"),
                       ({"discount_tiers": [{"min_qty": 10, "pct": 10}, {"min_qty": 20, "pct": 5}]}, "INVALID_PRICING")):
        cur = client.get(f"{M}/pricing-config", headers=mgr).json()
        if code == "NO_CHANGES" and body:
            body = {"adjust_threshold_pct": float(cur["adjust_threshold_pct"])}
        r = client.post(f"{M}/pricing-config", headers=mgr, json=body)
        assert r.status_code == 422 and _err(r) == code, (body, r.text)
    assert client.post(f"{M}/pricing-config", headers=mgr, json={"p_min_pct": 0}).status_code == 422
    assert client.post(f"{M}/pricing-config", headers=mgr, json={"adjust_threshold_pct": 101}).status_code == 422
    assert client.post(f"{M}/pricing-config", headers=mgr, json={"u_ot1": -100}).status_code == 422
    bad = client.post(f"{M}/pricing-config", headers=mgr, json={"u_ot1": 250}).json()["error"]
    assert bad["details"][0]["field"] == "u_ot1"
    assert client.get(f"{M}/pricing-config/versions", headers=mgr).json() == before         # nothing was saved


def test_discount_tiers_can_be_replaced(client, mgr, pricing_guard):
    tiers = [{"min_qty": 5, "pct": 3}, {"min_qty": 20, "pct": 7.5}]
    r = client.post(f"{M}/pricing-config", headers=mgr, json={"discount_tiers": tiers})
    assert r.status_code == 201, r.text
    assert [(t["min_qty"], float(t["pct"])) for t in r.json()["discount_tiers"]] == [(5, 3.0), (20, 7.5)]


def test_new_threshold_and_deposit_apply_to_new_quotations_only(client, cust, staff, mgr, wcat, pricing_guard):
    sh, _ = staff
    old_oid, old_q = _draft_quote(client, cust, sh, wcat)                          # priced with the real config
    r = client.post(f"{M}/pricing-config", headers=mgr, json={"adjust_threshold_pct": 5, "p_min_pct": 30, "note": "test"})
    assert r.status_code == 201, r.text
    version = r.json()["version"]
    new_oid, q = _draft_quote(client, cust, sh, wcat)
    assert Decimal(q["min_deposit_pct"]) == 30
    snap = _sql("select price_snapshot->'pricing_config'->>'version' from quotations where id=:q", q=q["id"])
    assert int(snap) == version
    assert _sql("select price_snapshot->>'adjust_threshold_pct' from quotations where id=:q", q=q["id"]) == "5.00"
    computed = Decimal(q["computed_total"])
    plus10 = int((computed * Decimal("1.10") / 100).to_integral_value(rounding="ROUND_CEILING") * 100)
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": plus10, "reason": "Khách quen"})
    assert r.status_code == 200 and r.json()["adjustment_status"] == "PENDING_MANAGER" and r.json()["status"] == "PENDING_APPROVAL"
    # the quotation drafted BEFORE the change keeps its own snapshot: +10% is still within the old 15%
    assert Decimal(old_q["min_deposit_pct"]) == Decimal(_sql("select min_deposit_pct from quotations where id=:q", q=old_q["id"]))
    assert Decimal(old_q["min_deposit_pct"]) != 30
    old_plus10 = int((Decimal(old_q["computed_total"]) * Decimal("1.10") / 100).to_integral_value(rounding="ROUND_CEILING") * 100)
    r = client.put(f"{W}/quotations/{old_q['id']}/adjustment", headers=sh, json={"adjusted_total": old_plus10, "reason": "Khách quen"})
    assert r.status_code == 200 and r.json()["adjustment_status"] == "WITHIN_THRESHOLD"
