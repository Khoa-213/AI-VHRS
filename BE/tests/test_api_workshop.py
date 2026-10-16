"""Phase 2 on the real database: Staff / Manager queue, intake, AI sketches, quotations, privacy, messages.

Catalog rows use codes starting 'pytest_' and every account is 'pytest_*@example.com'; conftest removes them.
Storage is the in-memory double; the AI pipelines, Pricing Engine, PDF renderer and DB triggers are real.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.api.v1.orders import optional_storage
from app.db.session import get_engine
from app.integrations.storage import InMemoryStorage
from app.main import app
from app.services import pricing as pr
from app.services import quotations as qsvc
from app.services.stroke_ai import trajectory as tj
from tests.conftest import auth, login, make_account
from tests.test_api_orders import API, _png, _sql, _upload

W = f"{API}/workshop"
M = f"{API}/manager"


# ---- fixtures ----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def wcat():
    tag = "pytest_" + uuid.uuid4().hex[:6]
    ids = {}
    ids["paper"] = _sql("""insert into paper_types (code,name,gsm,surface,size,unit_price,stock_qty)
                           values (:c,'Giay test A5',120,'ART','A5',9000,100) returning id""", c=tag + "_p")
    ids["gloss"] = _sql("""insert into paper_types (code,name,gsm,surface,size,unit_price,stock_qty)
                           values (:c,'Giay test bong',150,'GLOSSY','A5',6000,100) returning id""", c=tag + "_g")
    for key, cat, name, f, v, sur in (("gel", "GEL", "But gel test", (0.6, 0.3, 1.0, 3.0), 30, 5000),
                                      ("fountain", "FOUNTAIN", "But may test", (0.3, 0.15, 0.6, 2.0), 20, 10000)):
        ids[key] = _sql("""insert into pen_types (code,name,category,stroke_width_mm,f_target_n,f_min_n,f_max_n,f_hard_n,
                           v_max_mm_s,surcharge,stock_qty) values (:c,:n,:cat,0.5,:a,:b,:d,:e,:v,:s,50) returning id""",
                        c=f"{tag}_{key}", n=name, cat=cat, a=f[0], b=f[1], d=f[2], e=f[3], v=v, s=sur)
        ids[key + "_ink"] = _sql("""insert into ink_colors (pen_type_id,name,hex_code,unit_price,stock_qty)
                                    values (:p,'Den','#000000',0,50) returning id""", p=ids[key])
    for paper, pen, ok in (("paper", "gel", True), ("paper", "fountain", True), ("gloss", "gel", True),
                           ("gloss", "fountain", False)):
        _sql("insert into paper_pen_compats (paper_type_id,pen_type_id,is_compatible) values (:a,:b,:c) returning 1",
             a=ids[paper], b=ids[pen], c=ok)
    ids["tpl"] = _sql("""insert into templates (code,name,kind,font_uri) values (:c,'Mau test','SINGLE_LINE_FONT',
                         'hershey:scripts') returning id""", c=tag + "_t")
    ids["tpl_bad"] = _sql("""insert into templates (code,name,kind,font_uri) values (:c,'Mau thu phap','CALLIGRAPHY',
                             'fonts/x.json') returning id""", c=tag + "_tb")
    ids["tpl_off"] = _sql("""insert into templates (code,name,kind,font_uri,is_active) values (:c,'Mau tat','SINGLE_LINE_FONT',
                             'hershey:futural',false) returning id""", c=tag + "_to")
    return ids


@pytest.fixture(scope="module", autouse=True)
def policy():
    """The privacy policy lives in system_settings (seeded). Provide a test one when the seed was not run."""
    had = _sql("select 1 from system_settings where key='privacy_policy'")
    if not had:
        _sql("""insert into system_settings (key,value) values ('privacy_policy',
                '{"version":"t1","title":"Chinh sach test","body":"Noi dung test"}'::jsonb) returning 1""")
    yield
    if not had:
        _sql("delete from system_settings where key='privacy_policy' returning 1")


@pytest.fixture(autouse=True)
def store():
    mem = InMemoryStorage()
    app.dependency_overrides[optional_storage] = lambda: mem
    yield mem
    app.dependency_overrides.pop(optional_storage, None)


def _user(client, role):
    email = make_account(role)
    h = {"Authorization": f"Bearer {login(client, email)['access_token']}"}
    return h, client.get(f"{API}/me", headers=h).json()["id"]


@pytest.fixture
def cust(client):
    return auth(client, "CUSTOMER")


@pytest.fixture
def staff(client):
    return _user(client, "STAFF")


@pytest.fixture
def manager(client):
    return _user(client, "MANAGER")


# ---- helpers -----------------------------------------------------------------------------------------
def _ot3(client, cust, cat, text_="Kính gửi quý khách", qty=1, paper="paper", pen="gel", submit=True, suggest=False,
         canvas=None):
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT3_TEMPLATE", "quantity": qty}).json()["id"]
    body = {"workshop_suggest_materials": True} if suggest else {
        "paper_type_id": cat[paper], "pen_type_id": cat[pen], "ink_color_id": cat[pen + "_ink"]}
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json=body).status_code == 200
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
                   json={"text_content": text_, "template_id": cat["tpl"], "font_size_mm": 8, "alignment": "LEFT"})
    assert r.status_code == 200, r.text
    if canvas:
        assert client.put(f"{API}/orders/{oid}/inputs/canvas", headers=cust, json={"canvas_data": canvas}).status_code == 200
    if submit:
        r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
        assert r.status_code == 200, r.text
    return oid


def _accepted(client, cust, staff_h, cat, **kw):
    oid = _ot3(client, cust, cat, **kw)
    r = client.post(f"{W}/orders/{oid}/accept", headers=staff_h, json={})
    assert r.status_code == 200 and r.json()["order_status"] == "ACCEPTED", r.text
    return oid


def _with_sketch(client, cust, staff_h, cat, **kw):
    oid = _accepted(client, cust, staff_h, cat, **kw)
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=staff_h, json={})
    assert r.status_code == 201, r.text
    assert client.post(f"{W}/orders/{oid}/sketches/{r.json()['version']}/finalize", headers=staff_h).status_code == 200
    return oid


def _quoted(client, cust, staff_h, cat, **kw):
    oid = _with_sketch(client, cust, staff_h, cat, **kw)
    q = client.post(f"{W}/orders/{oid}/quotations", headers=staff_h, json={})
    assert q.status_code == 201, q.text
    return oid, q.json()


def _sent(client, cust, staff_h, cat, **kw):
    oid, q = _quoted(client, cust, staff_h, cat, **kw)
    r = client.post(f"{W}/quotations/{q['id']}/send", headers=staff_h)
    assert r.status_code == 200, r.text
    return oid, r.json()


def _order_status(oid):
    return _sql("select order_status::text from orders where id=:o", o=oid)


def _err(r):
    return r.json()["error"]["code"]


# ---- access control ----------------------------------------------------------------------------------
def test_workshop_requires_login_and_staff_or_manager(client, cust):
    for url in (f"{W}/orders", f"{M}/staff", f"{API}/orders/1/messages"):
        assert client.get(url).status_code == 401
    for role in ("CUSTOMER", "TECHNICAL_STAFF", "ADMIN"):
        h = auth(client, role)
        assert client.get(f"{W}/orders", headers=h).status_code == 403
        assert client.post(f"{W}/orders/1/accept", headers=h, json={}).status_code == 403
        assert client.post(f"{W}/orders/1/sketches/generate", headers=h, json={}).status_code == 403
        assert client.post(f"{W}/orders/1/quotations", headers=h, json={}).status_code == 403
        assert client.get(f"{M}/staff", headers=h).status_code == 403


def test_staff_cannot_use_manager_endpoints(client, staff):
    h, _ = staff
    assert client.get(f"{M}/staff", headers=h).status_code == 403
    assert client.put(f"{M}/orders/1/assignment", headers=h, json={"staff_id": 1}).status_code == 403
    assert client.get(f"{M}/quotations/pending-approval", headers=h).status_code == 403
    assert client.post(f"{M}/quotations/1/approve-adjustment", headers=h).status_code == 403


def test_drafts_are_invisible_to_the_workshop(client, cust, staff, manager, wcat):
    oid = _ot3(client, cust, wcat, submit=False)
    for h in (staff[0], manager[0]):
        assert client.get(f"{W}/orders/{oid}", headers=h).status_code == 404
    ids = [o["id"] for o in client.get(f"{W}/orders", headers=manager[0], params={"page_size": 100}).json()["items"]]
    assert oid not in ids


# ---- queue, claim, assign ----------------------------------------------------------------------------
def test_pool_claim_and_scoping(client, cust, wcat):
    s1, s2 = _user(client, "STAFF")[0], _user(client, "STAFF")[0]
    oid = _ot3(client, cust, wcat)
    for h in (s1, s2):                                            # unassigned SUBMITTED orders are in the pool
        assert oid in [o["id"] for o in client.get(f"{W}/orders", headers=h, params={"unassigned": True,
                                                                                   "page_size": 100}).json()["items"]]
        assert client.get(f"{W}/orders/{oid}", headers=h).status_code == 200
    r = client.post(f"{W}/orders/{oid}/claim", headers=s1)
    assert r.status_code == 200 and r.json()["assigned_staff_id"]
    assert client.post(f"{W}/orders/{oid}/claim", headers=s1).status_code == 200      # idempotent for the owner
    assert client.post(f"{W}/orders/{oid}/claim", headers=s2).status_code == 404       # no longer visible to others
    assert client.get(f"{W}/orders/{oid}", headers=s2).status_code == 404
    assert oid not in [o["id"] for o in client.get(f"{W}/orders", headers=s2, params={"page_size": 100}).json()["items"]]
    assert oid in [o["id"] for o in client.get(f"{W}/orders", headers=s1, params={"page_size": 100}).json()["items"]]


def test_two_staff_claim_the_same_order_only_one_wins(client, cust, wcat):
    """The atomic UPDATE: the loser gets 409/404, never a second owner."""
    s1, s2 = _user(client, "STAFF")[0], _user(client, "STAFF")[0]
    oid = _ot3(client, cust, wcat)
    codes = sorted([client.post(f"{W}/orders/{oid}/claim", headers=s1).status_code,
                    client.post(f"{W}/orders/{oid}/claim", headers=s2).status_code])
    assert codes[0] == 200 and codes[1] in (404, 409)
    assert _sql("select count(*) from orders where id=:o and assigned_staff_id is not null", o=oid) == 1


def test_manager_sees_everything_filters_and_cannot_claim(client, cust, manager, wcat):
    mh, _ = manager
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/claim", headers=mh).status_code == 403
    items = client.get(f"{W}/orders", headers=mh, params={"status": "SUBMITTED", "order_type": "OT3_TEMPLATE",
                                                          "page_size": 100}).json()["items"]
    row = next(o for o in items if o["id"] == oid)
    assert row["customer_name"] and row["order_type"] == "OT3_TEMPLATE"
    code = row["code"]
    assert [o["id"] for o in client.get(f"{W}/orders", headers=mh, params={"q": code}).json()["items"]] == [oid]
    assert client.get(f"{W}/orders", headers=mh, params={"status": "COMPLETED", "q": code}).json()["total"] == 0


def test_manager_assigns_and_reassigns_staff(client, cust, manager, wcat):
    mh, _ = manager
    (s1, s1id), (s2, s2id) = _user(client, "STAFF"), _user(client, "STAFF")
    oid = _ot3(client, cust, wcat)
    r = client.put(f"{M}/orders/{oid}/assignment", headers=mh, json={"staff_id": s1id})
    assert r.status_code == 200 and r.json()["assigned_staff_id"] == s1id
    assert client.get(f"{W}/orders/{oid}", headers=s1).status_code == 200
    r = client.put(f"{M}/orders/{oid}/assignment", headers=mh, json={"staff_id": s2id})
    assert r.json()["assigned_staff_id"] == s2id
    assert client.get(f"{W}/orders/{oid}", headers=s1).status_code == 404            # moved away from s1
    assert _sql("select count(*) from audit_logs where action='ORDER_ASSIGN' and entity_id=:o", o=oid) == 2
    # staff directory shows the load
    directory = {s["id"]: s for s in client.get(f"{M}/staff", headers=mh).json()}
    assert directory[s2id]["open_orders"] == 1 and directory[s1id]["open_orders"] == 0


def test_assignment_rejects_non_staff_and_closed_orders(client, cust, manager, wcat):
    mh, mid = manager
    oid = _ot3(client, cust, wcat)
    for bad in (mid, _user(client, "CUSTOMER")[1], 99999999):
        assert client.put(f"{M}/orders/{oid}/assignment", headers=mh, json={"staff_id": bad}).status_code == 422
    client.post(f"{W}/orders/{oid}/reject", headers=mh, json={"reason": "TOO_OLD", "staff_id": _user(client, "STAFF")[1]})
    r = client.put(f"{M}/orders/{oid}/assignment", headers=mh, json={"staff_id": _user(client, "STAFF")[1]})
    assert r.status_code == 409 and _err(r) == "ORDER_CLOSED"


# ---- intake ------------------------------------------------------------------------------------------
def test_accept_claims_records_history_and_blocks_other_staff(client, cust, staff, wcat):
    sh, sid = staff
    oid = _accepted(client, cust, sh, wcat)
    row = _sql("select assigned_staff_id from orders where id=:o", o=oid)
    assert row == sid
    hist = _sql("select count(*) from status_histories where order_id=:o and state_type='ORDER' and to_status='ACCEPTED' "
                "and actor_id=:a and reason='Tiếp nhận đơn'", o=oid, a=sid)
    assert hist == 1
    other = _user(client, "STAFF")[0]
    assert client.post(f"{W}/orders/{oid}/accept", headers=other, json={}).status_code == 404
    r = client.post(f"{W}/orders/{oid}/accept", headers=sh, json={})
    assert r.status_code == 409 and _err(r) == "STATE_CONFLICT"                       # trigger: ACCEPTED -> ACCEPTED


def test_manager_accept_needs_a_staff_for_a_pool_order(client, cust, manager, wcat):
    mh, _ = manager
    oid = _ot3(client, cust, wcat)
    r = client.post(f"{W}/orders/{oid}/accept", headers=mh, json={})
    assert r.status_code == 422 and _err(r) == "STAFF_REQUIRED"
    assert _order_status(oid) == "SUBMITTED"
    sid = _user(client, "STAFF")[1]
    r = client.post(f"{W}/orders/{oid}/accept", headers=mh, json={"staff_id": sid})
    assert r.status_code == 200 and r.json()["assigned_staff_id"] == sid


def test_reject_with_reason_and_customer_sees_it(client, cust, staff, wcat):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/reject", headers=sh, json={"reason": "NOPE"}).status_code == 422
    r = client.post(f"{W}/orders/{oid}/reject", headers=sh, json={"reason": "OTHER"})
    assert r.status_code == 422 and _err(r) == "NOTE_REQUIRED"
    assert _order_status(oid) == "SUBMITTED"
    r = client.post(f"{W}/orders/{oid}/reject", headers=sh, json={"reason": "DAMAGED", "note": "Rách nát"})
    assert r.status_code == 200 and r.json()["order_status"] == "REJECTED"
    mine = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert mine["order_status"] == "REJECTED" and mine["reject_reason"] == "DAMAGED" and mine["reject_note"] == "Rách nát"
    r = client.post(f"{W}/orders/{oid}/accept", headers=sh, json={})
    assert r.status_code == 409                                                       # REJECTED is final


def test_accepted_order_cannot_be_rejected_or_sent_back(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    assert client.post(f"{W}/orders/{oid}/reject", headers=sh, json={"reason": "TOO_OLD"}).status_code == 409
    assert client.post(f"{W}/orders/{oid}/request-info", headers=sh, json={"note": "x"}).status_code == 409


def test_request_info_then_customer_resubmits(client, cust, staff, wcat):
    sh, sid = staff
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/request-info", headers=sh, json={"note": "  "}).status_code in (422,)
    r = client.post(f"{W}/orders/{oid}/request-info", headers=sh, json={"note": "Chụp lại rõ hơn"})
    assert r.status_code == 200 and r.json()["order_status"] == "NEED_INFO"
    mine = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert mine["info_request_note"] == "Chụp lại rõ hơn"
    r = client.post(f"{API}/orders/{oid}/provide-info", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200 and r.json()["order_status"] == "SUBMITTED"
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200  # same staff continues
    assert _sql("select assigned_staff_id from orders where id=:o", o=oid) == sid


def test_order_detail_shows_inputs_and_signed_image_links(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"],
                                                           "ink_color_id": wcat["gel_ink"]})
    r, iid = _upload(client, cust, oid, store, _png())
    assert r.status_code == 200
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    d = client.get(f"{W}/orders/{oid}", headers=sh).json()
    assert d["customer_name"] and d["inputs"][0]["id"] == iid and d["inputs"][0]["file_url"].startswith("memory://")
    assert d["inputs"][0]["quality_result"]["analysed"] is True


# ---- sketches ----------------------------------------------------------------------------------------
def test_generate_sketch_for_template_order_end_to_end(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat, text_="Chúc mừng năm mới", qty=2)
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"approach_note": "Viết bằng bút gel"})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["version"] == 1 and s["is_final"] is False and s["similarity_score"] is None
    assert s["pen_lift_count"] > 10 and float(s["total_stroke_mm"]) > 100 and s["estimated_writing_sec"] > 5
    assert s["suggested_complexity"] in ("SIMPLE", "MEDIUM", "COMPLEX") and s["approach_note"] == "Viết bằng bút gel"
    assert len(s["content_hash"]) == 64 and s["preview_urls"]
    d = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert d["trajectory"]["format"] == tj.FORMAT and d["trajectory"]["pages"][0]["paper"]["size"] == "A5"   # order paper
    path = f"orders/{oid}/sketches/v1/trajectory.json"
    assert tj.content_hash(store.objects[path]) == s["content_hash"]
    assert any(p.endswith("preview_p1.png") for p in store.objects)
    r2 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"paper_size": "A4", "seed": 5})
    assert r2.json()["version"] == 2
    assert [x["version"] for x in client.get(f"{W}/orders/{oid}/sketches", headers=sh).json()] == [2, 1]
    assert _sql("select count(*) from audit_logs where action='SKETCH_CREATE' and actor_id is not null "
                "and entity_id in (select id from sketches where order_id=:o)", o=oid) == 2


def test_generate_sketch_from_uploaded_image_recovers_strokes(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"],
                                                           "ink_color_id": wcat["gel_ink"]})
    assert _upload(client, cust, oid, store, _png())[0].status_code == 200
    client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["similarity_score"] is not None and float(s["similarity_score"]) > 50
    d = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert d["trajectory"]["engine"]["name"] == "zhang-suen-skeleton" and len(d["trajectory"]["pages"][0]["strokes"]) > 3


def test_ot1_generate_requires_an_image_and_rejects_pdf(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"],
                                                           "ink_color_id": wcat["gel_ink"]})
    pdf = b"%PDF-1.4\n" + b"0" * 200
    assert _upload(client, cust, oid, store, pdf, mime="application/pdf")[0].status_code == 200
    client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    client.post(f"{W}/orders/{oid}/accept", headers=sh, json={})
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 422 and _err(r) == "PDF_NOT_SUPPORTED_AI"


def test_learned_style_orders_have_no_auto_sketch(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT2_LEARNED_STYLE"}).json()["id"]
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"],
                                                           "ink_color_id": wcat["gel_ink"]})
    _upload(client, cust, oid, store, _png(), kind="HANDWRITING_SAMPLE")
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust, json={"text_content": "Gửi mẹ"})
    client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True, "confirm_right_to_use": True})
    client.post(f"{W}/orders/{oid}/accept", headers=sh, json={})
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 422 and _err(r) == "AI_TYPE_UNSUPPORTED"
    # ... but Staff can still save a hand-made trajectory for it
    traj = {"format": tj.FORMAT, "pages": [{"paper": {"size": "A5"}, "strokes": [{"kind": "manual",
                                                                                 "points": [[20, 20], [100, 40]]}]}]}
    assert client.post(f"{W}/orders/{oid}/sketches", headers=sh, json={"trajectory": traj}).status_code == 201


def test_sketch_only_while_order_is_accepted(client, cust, staff, wcat):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    client.post(f"{W}/orders/{oid}/claim", headers=sh)
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_ACCEPTED"


def test_unsupported_characters_and_templates_are_reported(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat, text_="Xin 漢字 chào")
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 422 and _err(r) == "UNSUPPORTED_CHARS"
    assert {d["char"] for d in r.json()["error"]["details"]} == {"漢", "字"}
    assert client.get(f"{W}/orders/{oid}/sketches", headers=sh).json() == []             # nothing half-saved
    # a template that is not a single-line font
    oid2 = _accepted(client, cust, sh, wcat)
    _sql("update order_inputs set template_id=:t where order_id=:o returning 1", t=wcat["tpl_bad"], o=oid2)
    r = client.post(f"{W}/orders/{oid2}/sketches/generate", headers=sh, json={})
    assert r.status_code == 422 and _err(r) == "UNSUPPORTED_TEMPLATE"


def test_canvas_drawing_is_added_to_the_sketch(client, cust, staff, wcat):
    sh, _ = staff
    canvas = {"strokes": [{"points": [{"x": 20, "y": 150}, {"x": 60, "y": 170}, {"x": 100, "y": 150}]}]}
    oid = _accepted(client, cust, sh, wcat, canvas=canvas)
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201 and r.json()["suggested_complexity"] == "COMPLEX"          # a drawing is "complex" (SRS)
    d = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert d["trajectory"]["pages"][0]["strokes"][-1]["kind"] == "canvas"


def test_manual_trajectory_validation_and_finalize_switches_version(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    bad = {"format": tj.FORMAT, "pages": [{"paper": {"size": "A5"}, "strokes": [{"kind": "manual",
                                                                                "points": [[0, 0], [999, 0]]}]}]}
    r = client.post(f"{W}/orders/{oid}/sketches", headers=sh, json={"trajectory": bad})
    assert r.status_code == 422 and _err(r) == "INVALID_TRAJECTORY"
    good = {"format": tj.FORMAT, "pages": [{"paper": {"size": "A5"}, "strokes": [
        {"kind": "manual", "points": [[10, 10], [60, 10], [60, 60]]}]}]}
    v1 = client.post(f"{W}/orders/{oid}/sketches", headers=sh, json={"trajectory": good, "approach_note": "tay"}).json()
    v2 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={}).json()
    assert (v1["version"], v2["version"]) == (1, 2)
    assert float(v1["total_stroke_mm"]) == 100.0 and v1["pen_lift_count"] == 1
    assert client.post(f"{W}/orders/{oid}/sketches/1/finalize", headers=sh).json()["is_final"] is True
    assert client.post(f"{W}/orders/{oid}/sketches/2/finalize", headers=sh).json()["is_final"] is True
    flags = {s["version"]: s["is_final"] for s in client.get(f"{W}/orders/{oid}/sketches", headers=sh).json()}
    assert flags == {1: False, 2: True}                                                # exactly one final
    r = client.patch(f"{W}/orders/{oid}/sketches/2", headers=sh, json={"approach_note": "mới", "suggested_complexity": "MEDIUM"})
    assert r.json()["approach_note"] == "mới" and r.json()["suggested_complexity"] == "MEDIUM"
    assert client.get(f"{W}/orders/{oid}/sketches/9", headers=sh).status_code == 404


def test_other_staff_cannot_touch_sketches(client, cust, staff, wcat):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat)
    other = _user(client, "STAFF")[0]
    assert client.get(f"{W}/orders/{oid}/sketches", headers=other).status_code == 404
    assert client.post(f"{W}/orders/{oid}/sketches/generate", headers=other, json={}).status_code == 404
    assert client.post(f"{W}/orders/{oid}/sketches/1/finalize", headers=other).status_code == 404


def test_sketch_without_storage_is_503(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    app.dependency_overrides[optional_storage] = lambda: None
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 503 and _err(r) == "STORAGE_NOT_CONFIGURED"


# ---- quotations --------------------------------------------------------------------------------------
def _expected_total(chars: int, qty: int, level: str, paper=9000, pen=5000, ink=0) -> Decimal:
    with get_engine().begin() as c:
        cfg = c.execute(text("select * from pricing_configs where is_active")).mappings().one()
    params = pr.PricingParams(u_per_char=cfg["u_ot3"], w_min=cfg["w_min"], setup_fee=cfg["s_ot3"],
                              k_by_complexity={"SIMPLE": cfg["k_simple"], "MEDIUM": cfg["k_medium"],
                                               "COMPLEX": cfg["k_complex"]},
                              discount_tiers=pr.parse_tiers(cfg["discount_tiers"]), p_min_pct=cfg["p_min_pct"])
    return pr.compute_price(params, chars=chars, quantity=qty, complexity=level,
                            materials=pr.MaterialPrices(Decimal(paper), Decimal(pen), Decimal(ink))).total


def test_quotation_needs_accepted_order_and_final_sketch_br22(client, cust, staff, wcat):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    client.post(f"{W}/orders/{oid}/claim", headers=sh)
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_ACCEPTED"
    client.post(f"{W}/orders/{oid}/accept", headers=sh, json={})
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert r.status_code == 409 and _err(r) == "SKETCH_REQUIRED"
    client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})              # saved but not final
    assert _err(client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})) == "SKETCH_REQUIRED"


def test_quotation_price_matches_the_pricing_engine(client, cust, staff, wcat):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat, text_="Xin chào", qty=2)          # 7 non-space characters
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"complexity": "MEDIUM"})
    assert r.status_code == 201, r.text
    q = r.json()
    expected = _expected_total(7, 2, "MEDIUM")
    assert Decimal(q["computed_total"]) == expected == Decimal(q["final_total"])
    assert q["status"] == "DRAFT" and q["adjustment_status"] == "NONE" and q["version"] == 1 and q["char_count"] == 7
    assert q["quantity"] == 2 and q["complexity"] == "MEDIUM"
    assert Decimal(q["min_deposit_pct"]) == Decimal(
        _sql("select p_min_pct from pricing_configs where is_active"))
    assert q["options"][0]["total"] == int(expected)
    assert q["options"][0]["min_deposit"] >= int(expected) * Decimal(q["min_deposit_pct"]) / 100          # BR-10
    assert q["line_items"][-1]["amount"] == int(expected) and q["line_items"][-1]["item"].startswith("Tổng")
    snap = _sql("select price_snapshot::text from quotations where id=:q", q=q["id"])
    assert '"pricing_config"' in snap and '"adjust_threshold_pct"' in snap


def test_quotation_complexity_defaults_to_the_sketch_suggestion(client, cust, staff, wcat):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat)
    suggested = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["suggested_complexity"]
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={}).json()
    assert q["complexity"] == suggested


def test_only_one_open_quotation_and_cancel_allows_a_new_one(client, cust, staff, wcat):
    sh, _ = staff
    oid, q = _quoted(client, cust, sh, wcat)
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert r.status_code == 409 and _err(r) == "QUOTATION_ALREADY_OPEN"
    assert client.post(f"{W}/quotations/{q['id']}/cancel", headers=sh).json()["status"] == "CANCELLED"
    q2 = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert q2.status_code == 201 and q2.json()["version"] == 2


def test_adjustment_within_threshold_staff_alone_and_boundary(client, cust, staff, wcat):
    sh, _ = staff
    oid, q = _quoted(client, cust, sh, wcat, qty=3)
    computed = Decimal(q["computed_total"])
    edge = (computed * Decimal("1.15") / 100).to_integral_value(rounding="ROUND_FLOOR") * 100      # <= +15%
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(edge), "reason": "Khách quen"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["adjustment_status"] == "WITHIN_THRESHOLD" and a["status"] == "DRAFT"
    assert Decimal(a["final_total"]) == edge and abs(Decimal(a["adjustment_pct"])) <= 15
    assert _sql("select count(*) from audit_logs where action='PRICE_ADJUST' and entity_id=:q and reason='Khách quen'",
                q=q["id"]) == 1
    over = edge + 100
    while Decimal(over - computed) * 100 / computed <= Decimal("15.00"):
        over += 100
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(over), "reason": "Quá tay"})
    assert r.json()["adjustment_status"] == "PENDING_MANAGER" and r.json()["status"] == "PENDING_APPROVAL"
    down = (computed * Decimal("0.80") / 100).to_integral_value(rounding="ROUND_FLOOR") * 100                     # -20%
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(down), "reason": "Giảm"})
    assert r.json()["adjustment_status"] == "PENDING_MANAGER"


def test_adjustment_input_validation(client, cust, staff, wcat):
    sh, _ = staff
    _, q = _quoted(client, cust, sh, wcat)
    url = f"{W}/quotations/{q['id']}/adjustment"
    assert client.put(url, headers=sh, json={"adjusted_total": "150050", "reason": "x"}).status_code == 422   # not x100
    assert client.put(url, headers=sh, json={"adjusted_total": "-100", "reason": "x"}).status_code == 422
    assert client.put(url, headers=sh, json={"adjusted_total": "150000", "reason": "   "}).status_code == 422
    assert client.put(url, headers=sh, json={"adjusted_total": "150000"}).status_code == 422                    # reason missing
    same = client.put(url, headers=sh, json={"adjusted_total": q["computed_total"], "reason": "giữ nguyên"})
    assert same.status_code == 200 and same.json()["adjustment_status"] == "NONE" and same.json()["adjusted_total"] is None


def test_manager_approval_flow_blocks_sending_until_decided(client, cust, staff, manager, wcat):
    sh, _ = staff
    mh, mid = manager
    oid, q = _quoted(client, cust, sh, wcat, qty=2)
    big = int(Decimal(q["computed_total"]) * 2 / 100) * 100
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(big), "reason": "Đơn lớn"})
    assert r.json()["status"] == "PENDING_APPROVAL"
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 409           # blocked while pending
    assert client.post(f"{M}/quotations/{q['id']}/approve-adjustment", headers=sh).status_code == 403
    pending = client.get(f"{M}/quotations/pending-approval", headers=mh, params={"page_size": 100}).json()
    assert q["id"] in [p["id"] for p in pending["items"]]
    ok = client.post(f"{M}/quotations/{q['id']}/approve-adjustment", headers=mh).json()
    assert ok["adjustment_status"] == "APPROVED" and ok["status"] == "DRAFT" and ok["approved_by"] == mid
    assert Decimal(ok["final_total"]) == big
    assert client.post(f"{M}/quotations/{q['id']}/approve-adjustment", headers=mh).status_code == 409   # nothing pending
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 200
    assert _sql("select count(*) from audit_logs where action='PRICE_ADJUST_APPROVE' and entity_id=:q", q=q["id"]) == 1


def test_manager_rejection_restores_the_computed_price(client, cust, staff, manager, wcat):
    sh, _ = staff
    mh, _ = manager
    _, q = _quoted(client, cust, sh, wcat)
    big = int(Decimal(q["computed_total"]) * 3 / 100) * 100
    client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(big), "reason": "Đắt"})
    assert client.post(f"{M}/quotations/{q['id']}/reject-adjustment", headers=mh, json={"reason": " "}).status_code == 422
    r = client.post(f"{M}/quotations/{q['id']}/reject-adjustment", headers=mh, json={"reason": "Quá cao"})
    d = r.json()
    assert d["adjustment_status"] == "REJECTED" and d["adjusted_total"] is None and d["status"] == "DRAFT"
    assert Decimal(d["final_total"]) == Decimal(q["computed_total"])
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 200


def test_manager_own_big_adjustment_needs_no_second_approval(client, cust, manager, wcat):
    mh, mid = manager
    sid = _user(client, "STAFF")[1]
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/accept", headers=mh, json={"staff_id": sid}).status_code == 200
    v = client.post(f"{W}/orders/{oid}/sketches/generate", headers=mh, json={}).json()["version"]
    client.post(f"{W}/orders/{oid}/sketches/{v}/finalize", headers=mh)
    q = client.post(f"{W}/orders/{oid}/quotations", headers=mh, json={}).json()
    big = int(Decimal(q["computed_total"]) * 2 / 100) * 100
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=mh, json={"adjusted_total": str(big), "reason": "Ưu đãi"})
    assert r.json()["adjustment_status"] == "APPROVED" and r.json()["approved_by"] == mid


def test_clear_adjustment(client, cust, staff, wcat):
    sh, _ = staff
    _, q = _quoted(client, cust, sh, wcat, qty=2)
    small = int(Decimal(q["computed_total"]) * Decimal("1.05") / 100) * 100
    client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": str(small), "reason": "x"})
    r = client.delete(f"{W}/quotations/{q['id']}/adjustment", headers=sh).json()
    assert r["adjusted_total"] is None and r["adjustment_status"] == "NONE" and Decimal(r["final_total"]) == Decimal(q["computed_total"])


def test_send_quotation_creates_pdf_and_waits_for_privacy_consent(client, cust, staff, store, wcat):
    sh, _ = staff
    oid, q = _quoted(client, cust, sh, wcat)
    r = client.post(f"{W}/quotations/{q['id']}/send", headers=sh)
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "SENT" and s["has_pdf"] and s["sent_at"] and s["valid_until"]
    sent, valid = (datetime.fromisoformat(s[k]) for k in ("sent_at", "valid_until"))
    assert timedelta(days=6, hours=23) < valid - sent < timedelta(days=7, hours=1)           # BR-08: 7 days
    assert store.objects[f"orders/{oid}/quotations/v1.pdf"].startswith(b"%PDF")
    assert _order_status(oid) == "AWAITING_PRIVACY"
    assert client.get(f"{W}/quotations/{q['id']}/pdf", headers=sh).json()["url"].endswith("v1.pdf")
    assert _err(client.get(f"{API}/orders/{oid}/quotation", headers=cust)) == "PRIVACY_REQUIRED"   # hidden until consent
    # no second send, no edits after sending
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 409
    assert client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh,
                      json={"adjusted_total": "100000", "reason": "x"}).status_code == 409
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='AWAITING_PRIVACY'", o=oid) == 1


def test_send_is_refused_when_the_sketch_changed(client, cust, staff, wcat):
    sh, _ = staff
    oid, q = _quoted(client, cust, sh, wcat)
    v2 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"seed": 9}).json()["version"]
    client.post(f"{W}/orders/{oid}/sketches/{v2}/finalize", headers=sh)
    r = client.post(f"{W}/quotations/{q['id']}/send", headers=sh)
    assert r.status_code == 409 and _err(r) == "SKETCH_CHANGED"
    assert _order_status(oid) == "ACCEPTED"


def test_privacy_accept_unlocks_sketch_and_quote_for_the_customer(client, cust, staff, wcat):
    sh, _ = staff
    oid, _s = _sent(client, cust, staff[0], wcat, text_="Chúc mừng")
    pol = client.get(f"{API}/privacy-policy").json()                           # public
    assert pol["version"] and pol["body"]
    other = auth(client, "CUSTOMER")
    assert client.post(f"{API}/orders/{oid}/privacy", headers=other, json={"accept": True}).status_code == 404
    r = client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    assert r.status_code == 200 and r.json()["order_status"] == "QUOTED"
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 409
    v = client.get(f"{API}/orders/{oid}/quotation", headers=cust)
    assert v.status_code == 200, v.text
    d = v.json()
    assert d["status"] == "SENT" and d["sketch"]["preview_urls"] and d["pdf_url"] and d["note"].startswith("Giá chưa")
    assert "adjustment_reason" not in d and "computed_total" not in d                  # internal fields stay hidden
    assert d["options"][0]["total"] == int(d["final_total"])
    assert client.get(f"{API}/orders/{oid}/quotation", headers=other).status_code == 404
    row = _sql("select policy_version from audit_logs where action='PRIVACY_ACCEPT' and entity_id=:o", o=oid)
    assert row == pol["version"]
    assert _sql("select privacy_policy_version from orders where id=:o", o=oid) == pol["version"]


def test_privacy_decline_cancels_the_order(client, cust, staff, wcat):
    oid, s = _sent(client, cust, staff[0], wcat)
    r = client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": False})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED"
    assert _sql("select status::text from quotations where id=:q", q=s["id"]) == "CANCELLED"
    assert _sql("select count(*) from audit_logs where action='PRIVACY_DECLINE' and entity_id=:o and policy_version is not null",
                o=oid) == 1
    assert _sql("select privacy_declined_at is not null from orders where id=:o", o=oid) is True


def test_customer_cannot_see_a_quote_before_one_exists(client, cust, staff, wcat):
    oid = _accepted(client, cust, staff[0], wcat)
    assert client.get(f"{API}/orders/{oid}/quotation", headers=cust).status_code == 404
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 409


def test_request_changes_then_requote_skips_the_second_privacy_prompt(client, cust, staff, wcat):
    sh, _ = staff
    oid, q1 = _sent(client, cust, sh, wcat)
    client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    assert client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust, json={"note": " "}).status_code == 422
    r = client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust, json={"note": "Chữ to hơn"})
    assert r.status_code == 200 and r.json()["order_status"] == "ACCEPTED"
    assert _sql("select status::text from quotations where id=:q", q=q1["id"]) == "CHANGES_REQUESTED"
    assert _sql("select customer_note from quotations where id=:q", q=q1["id"]) == "Chữ to hơn"
    assert client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust, json={"note": "lại"}).status_code == 409
    v2 = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"seed": 3}).json()["version"]
    client.post(f"{W}/orders/{oid}/sketches/{v2}/finalize", headers=sh)
    q2 = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={}).json()
    assert q2["version"] == 2
    assert _sql("select status::text from quotations where id=:q", q=q1["id"]) == "SUPERSEDED"
    assert client.post(f"{W}/quotations/{q2['id']}/send", headers=sh).status_code == 200
    assert _order_status(oid) == "QUOTED"                      # consent already given for this policy version
    assert client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["version"] == 2


def test_quotation_expires_after_its_validity(client, cust, staff, wcat):
    oid, s = _sent(client, cust, staff[0], wcat)
    client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    _sql("""update quotations set sent_at = now() - interval '9 days', valid_until = now() - interval '2 days'
            where id=:q returning 1""", q=s["id"])
    d = client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()                 # lazy expiry (BR-08)
    assert d["status"] == "EXPIRED"
    assert _order_status(oid) == "CANCELLED"
    assert _sql("select cancel_reason from orders where id=:o", o=oid) == "Báo giá hết hạn"
    assert _sql("select count(*) from audit_logs where action='QUOTATION_EXPIRE' and entity_id=:q", q=s["id"]) == 1
    assert client.post(f"{API}/orders/{oid}/quotation/request-changes", headers=cust, json={"note": "x"}).status_code == 409


def test_expire_all_cancels_orders_waiting_for_privacy(client, cust, staff, wcat):
    oid, s = _sent(client, cust, staff[0], wcat)
    _sql("update quotations set sent_at = now() - interval '9 days', valid_until = now() - interval '2 days' where id=:q returning 1",
         q=s["id"])
    with get_engine().begin() as conn:
        from sqlalchemy.orm import Session
        with Session(conn) as session:
            assert qsvc.expire_all(session) >= 1
            session.flush()
    assert _order_status(oid) == "CANCELLED"
    assert _sql("select status::text from quotations where id=:q", q=s["id"]) == "EXPIRED"


def test_multi_option_quotation_for_workshop_suggested_materials(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat, suggest=True)
    v = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"paper_size": "A5"}).json()["version"]
    client.post(f"{W}/orders/{oid}/sketches/{v}/finalize", headers=sh)
    assert _err(client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})) == "OPTIONS_REQUIRED"
    bad = [{"paper_type_id": wcat["gloss"], "pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": bad})
    assert r.status_code == 422 and _err(r) == "INVALID_MATERIALS" and r.json()["error"]["details"] == {"option": 1}
    mismatch = [{"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["fountain_ink"]}]
    assert _err(client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": mismatch})) == "INVALID_MATERIALS"
    opts = [{"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]},
            {"paper_type_id": wcat["paper"], "pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]
    r = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": opts, "complexity": "MEDIUM"})
    assert r.status_code == 201, r.text
    q = r.json()
    assert [o["option"] for o in q["options"]] == [1, 2] and q["chosen_option"] is None
    assert q["options"][1]["total"] > q["options"][0]["total"]                      # fountain pen costs more
    assert {li["option"] for li in q["line_items"]} == {1, 2}
    r = client.put(f"{W}/quotations/{q['id']}/adjustment", headers=sh, json={"adjusted_total": "500000", "reason": "x"})
    assert r.status_code == 422 and _err(r) == "ADJUST_NOT_ALLOWED_MULTI_OPTION"
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 200


def test_too_many_options_and_manual_char_count(client, cust, staff, wcat):
    sh, _ = staff
    oid = _with_sketch(client, cust, sh, wcat, text_="Xin chào")
    o = {"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}
    assert client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": [o] * 4}).status_code == 422
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"char_count": 400, "complexity": "COMPLEX"}).json()
    assert q["char_count"] == 400 and Decimal(q["computed_total"]) == _expected_total(400, 1, "COMPLEX")


def test_other_staff_cannot_touch_quotations(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    other = _user(client, "STAFF")[0]
    assert client.get(f"{W}/quotations/{q['id']}", headers=other).status_code == 404
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=other).status_code == 404
    assert client.put(f"{W}/quotations/{q['id']}/adjustment", headers=other,
                      json={"adjusted_total": "100000", "reason": "x"}).status_code == 404
    assert client.get(f"{W}/orders/{oid}/quotations", headers=other).status_code == 404


def test_quotation_pdf_unavailable_before_sending(client, cust, staff, wcat):
    _, q = _quoted(client, cust, staff[0], wcat)
    assert client.get(f"{W}/quotations/{q['id']}/pdf", headers=staff[0]).status_code == 404


# ---- messages ----------------------------------------------------------------------------------------
def test_chat_between_customer_and_staff_with_unread_counts(client, cust, staff, wcat):
    sh, sid = staff
    oid = _accepted(client, cust, sh, wcat)
    url = f"{API}/orders/{oid}/messages"
    assert client.post(url, headers=cust, json={"body": "Chào xưởng"}).status_code == 201
    assert client.post(url, headers=sh, json={"body": "Chào bạn, đơn đã nhận"}).status_code == 201
    mine = client.get(url, headers=cust).json()
    assert [m["body"] for m in mine["items"]] == ["Chào xưởng", "Chào bạn, đơn đã nhận"]
    assert [m["mine"] for m in mine["items"]] == [True, False] and mine["unread"] == 1
    assert client.get(url, headers=sh).json()["unread"] == 1
    assert client.post(f"{url}/read", headers=cust).json() == {"marked": 1}
    assert client.get(url, headers=cust).json()["unread"] == 0
    assert client.get(url, headers=sh).json()["unread"] == 1            # staff has not read the customer's message yet


def test_chat_permissions(client, cust, staff, manager, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    url = f"{API}/orders/{oid}/messages"
    other_c, other_s = auth(client, "CUSTOMER"), _user(client, "STAFF")[0]
    for h in (other_c, other_s):
        assert client.get(url, headers=h).status_code == 404
        assert client.post(url, headers=h, json={"body": "x"}).status_code == 404
    for role in ("ADMIN", "TECHNICAL_STAFF"):
        assert client.get(url, headers=auth(client, role)).status_code == 403
    assert client.post(url, headers=manager[0], json={"body": "Manager đây"}).status_code == 201
    assert client.get(url).status_code == 401


def test_staff_in_pool_can_read_but_not_post_until_claimed(client, cust, staff, wcat):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    url = f"{API}/orders/{oid}/messages"
    client.post(url, headers=cust, json={"body": "Khi nào xong?"})
    assert client.get(url, headers=sh).status_code == 200
    r = client.post(url, headers=sh, json={"body": "x"})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_CLAIMED"
    client.post(f"{W}/orders/{oid}/claim", headers=sh)
    assert client.post(url, headers=sh, json={"body": "Đã nhận"}).status_code == 201


def test_chat_rules_draft_empty_long_and_closed(client, cust, staff, wcat):
    sh, _ = staff
    draft = _ot3(client, cust, wcat, submit=False)
    assert _err(client.post(f"{API}/orders/{draft}/messages", headers=cust, json={"body": "hi"})) == "ORDER_NOT_SUBMITTED"
    oid = _accepted(client, cust, sh, wcat)
    url = f"{API}/orders/{oid}/messages"
    assert _err(client.post(url, headers=cust, json={"body": "   "})) == "EMPTY_MESSAGE"
    assert client.post(url, headers=cust, json={"body": "x" * 2001}).status_code == 422
    rejected = _ot3(client, cust, wcat)
    client.post(f"{W}/orders/{rejected}/reject", headers=sh, json={"reason": "TOO_OLD"})
    r = client.post(f"{API}/orders/{rejected}/messages", headers=cust, json={"body": "Vì sao?"})
    assert r.status_code == 409 and _err(r) == "ORDER_CLOSED"
    assert client.get(f"{API}/orders/{rejected}/messages", headers=cust).status_code == 200       # history stays readable


def test_chat_image_attachment_flow(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    url = f"{API}/orders/{oid}/messages"
    png = _png()
    up = client.post(f"{url}/upload-url", headers=cust, json={"mime_type": "image/png", "size_bytes": len(png)})
    assert up.status_code == 201
    path = up.json()["path"]
    assert path.startswith(f"orders/{oid}/messages/")
    assert _err(client.post(url, headers=cust, json={"attachments": [{"path": path}]})) == "ATTACHMENT_NOT_UPLOADED"
    store.put(path, png)
    r = client.post(url, headers=cust, json={"body": "Ảnh mẫu", "attachments": [{"path": path}]})
    assert r.status_code == 201 and r.json()["attachments"][0]["mime"] == "image/png"
    seen = client.get(url, headers=sh).json()["items"][0]
    assert seen["attachments"][0]["url"].startswith("memory://") and seen["body"] == "Ảnh mẫu"
    # someone else's path, a path traversal and non-image content are refused
    assert _err(client.post(url, headers=sh, json={"attachments": [{"path": path}]})) == "INVALID_ATTACHMENT"
    assert _err(client.post(url, headers=cust, json={"attachments": [{"path": f"orders/{oid}/x.png"}]})) == "INVALID_ATTACHMENT"
    cust_id = client.get(f"{API}/me", headers=cust).json()["id"]
    fake = f"orders/{oid}/messages/{cust_id}/f.png"
    store.put(fake, b"not an image at all")
    assert _err(client.post(url, headers=cust, json={"attachments": [{"path": fake}]})) == "INVALID_ATTACHMENT"
    assert fake not in store.objects
    assert client.post(f"{url}/upload-url", headers=cust, json={"mime_type": "image/png", "size_bytes": 6_000_000}).status_code == 422
    assert client.post(f"{url}/upload-url", headers=cust, json={"mime_type": "image/gif", "size_bytes": 10}).status_code == 422


# ---- template preview --------------------------------------------------------------------------------
def test_template_preview_is_a_public_png(client, wcat):
    r = client.get(f"{API}/catalog/templates/{wcat['tpl']}/preview", params={"text": "Nét Việt ắ ở ộ"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(f"{API}/catalog/templates/{wcat['tpl_off']}/preview").status_code == 404
    assert client.get(f"{API}/catalog/templates/{wcat['tpl_bad']}/preview").status_code == 422
    assert client.get(f"{API}/catalog/templates/99999999/preview").status_code == 404
    assert client.get(f"{API}/catalog/templates/{wcat['tpl']}/preview", params={"text": "x" * 201}).status_code == 422
    assert client.get(f"{API}/catalog/templates/{wcat['tpl']}/preview", params={"text": "漢"}).status_code == 422
