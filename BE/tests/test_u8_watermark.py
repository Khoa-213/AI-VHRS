"""Upgrade U8: physical watermark line, verification code, certificate card, public verification page (Q3 = A).

The line is part of the trajectory (kind "watermark"), regenerated on every saved sketch version, declared in the signed
snapshot (schema 2) and checked again when the package is downloaded; OT-1 cannot be produced without it.
"""
import copy
import json

import cv2
import pytest

from app.core import production_signing as ps
from app.core.config import get_settings
from app.models.order import OrderType
from app.services import certificates as cert_mod
from app.services.stroke_ai import physical_mark as pm
from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.trajectory import Page, Stroke
from tests.test_api_orders import API, _png, _sql, _upload, issue_paper
from tests.test_api_scheduling import _at, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import W, _err, _ot3, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_api_technician import CAL, _robot_wrote
from tests.test_production_snapshot import _forge, _package, _refused, _snap

T = f"{API}/technician"


# ---- the module ---------------------------------------------------------------------------------------
def test_code_format_and_normalisation():
    codes = {pm.new_code() for _ in range(200)}
    assert len(codes) == 200 and all(pm.is_code(c) for c in codes)
    assert not any(ch in c for c in codes for ch in "01ILO")
    assert pm.normalise_code(" abcd efgh ") == "ABCD-EFGH" and pm.normalise_code("abcd-efgh") == "ABCD-EFGH"
    assert not pm.is_code("ABCD-EFG0") and not pm.is_code("ABCDEFGH")


@pytest.mark.parametrize("size", ["A6", "A5", "A4"])
def test_the_line_fits_the_ot1_margin_and_moves_up_when_the_bottom_is_taken(size):
    page = Page(size)
    w, h = page.width_mm, page.height_mm
    page.strokes = [Stroke([(10, 10), (w - 10, h - 10)]), Stroke([(10, h - 10), (w - 10, h - 10)])]   # OT-1 fills to 10 mm
    info = pm.apply([page], "ABCD-EFGH")
    marks = [s for s in page.strokes if s.kind == pm.KIND]
    ys = [y for s in marks for _, y in s.points]
    xs = [x for s in marks for x, _ in s.points]
    assert info["pages"][0]["placement"] == "BOTTOM" and info["text"] == "Tái tạo bằng AI-VHRS - Mã ABCD-EFGH"
    assert max(ys) == pytest.approx(h - pm.EDGE_MM, abs=0.01) and min(ys) > h - 10 + pm.CLEAR_MM
    assert min(xs) >= pm.EDGE_MM and max(xs) <= w - pm.EDGE_MM
    assert page.strokes[-1].kind == pm.KIND                       # written last
    # content reaching the bottom margin: the line goes to the top
    low = Page(size, [Stroke([(5, h - 6), (w - 5, h - 6)])])
    assert pm.apply([low], "ABCD-EFGH")["pages"][0]["placement"] == "TOP"
    assert min(y for s in low.strokes if s.kind == pm.KIND for _, y in s.points) == pytest.approx(pm.EDGE_MM, abs=0.01)
    # both margins taken: refused with a clear reason
    full = Page(size, [Stroke([(5, 7), (w - 5, 7)]), Stroke([(5, h - 7), (w - 5, h - 7)])])
    with pytest.raises(Exception) as e:
        pm.apply([full], "ABCD-EFGH")
    assert getattr(e.value, "code", None) == "WATERMARK_NO_SPACE"


def test_apply_replaces_any_uploaded_watermark_and_is_deterministic():
    page = Page("A5", [Stroke([(20, 20), (60, 40)]), Stroke([(1, 205), (140, 205)], pm.KIND)])   # a fake one
    first = pm.apply([page], "ABCD-EFGH")
    again = copy.deepcopy(page)
    assert pm.apply([again], "ABCD-EFGH") == first and again.strokes == page.strokes
    assert [s.points for s in page.strokes if s.kind == pm.KIND][0][0] != (1, 205)
    assert pm.strip([page]) == first["pages"][0]["strokes"] and all(s.kind != pm.KIND for s in page.strokes)


def _payload(otype, wm, schema=ps.SCHEMA):
    return {"schema": schema, "order": {"type": otype}, "watermark": wm}


def test_check_refuses_a_missing_or_altered_line_and_accepts_legacy_packages():
    page = Page("A5", [Stroke([(20, 20), (60, 40)])])
    bare = copy.deepcopy(page)
    info = pm.apply([page], "ABCD-EFGH")
    pages = tj.parse(json.loads(tj.dumps(tj.to_dict([page], {}))))     # through the file: coordinates rounded
    pm.check(_payload("OT1_COPY_RESTORE", {"required": True, **info}), pages)

    def code(payload, pp):
        with pytest.raises(ps.SignatureError) as e:
            pm.check(payload, pp)
        return e.value.code

    assert code(_payload("OT1_COPY_RESTORE", None), [bare]) == "WATERMARK_REQUIRED"
    assert code(_payload("OT1_COPY_RESTORE", {"required": True, **info}), [bare]) == "WATERMARK_MISMATCH"
    other = copy.deepcopy(info) | {"code": "ZZZZ-ZZZZ"}
    assert code(_payload("OT1_COPY_RESTORE", {"required": True, **other}), pages) == "WATERMARK_MISMATCH"
    moved = copy.deepcopy(pages)
    moved[0].strokes[-1].points[0] = (moved[0].strokes[-1].points[0][0] + 0.5, moved[0].strokes[-1].points[0][1])
    assert code(_payload("OT1_COPY_RESTORE", {"required": True, **info}), moved) == "WATERMARK_MISMATCH"
    assert code(_payload("OT3_TEMPLATE", None), pages) == "WATERMARK_MISMATCH"          # strokes the payload does not declare
    pm.check(_payload("OT3_TEMPLATE", None), [bare])                                     # OT-3 without the option
    pm.check(_payload("OT1_COPY_RESTORE", None, schema=ps.SCHEMA_V1), [bare])            # issued before U8: its job finishes


def test_the_card_qr_code_decodes_to_the_verification_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "public_verify_url", "https://ai-vhrs.vercel.app/verify/")
    url = cert_mod.verify_url("ABCD-EFGH")
    assert url == "https://ai-vhrs.vercel.app/verify/ABCD-EFGH"
    modules = cert_mod._qr_modules(url)
    import numpy as np
    img = np.array([[0 if d else 255 for d in row] for row in modules], np.uint8)
    img = cv2.copyMakeBorder(cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST), 32, 32, 32, 32,
                             cv2.BORDER_CONSTANT, value=255)
    assert cv2.QRCodeDetector().detectAndDecode(img)[0] == url
    pdf = cert_mod.render_card("ABCD-EFGH", order_type=OrderType.OT1_COPY_RESTORE, paper_size="A5", pages=1, quantity=2,
                               written_at=None, watermark_text=pm.line_text("ABCD-EFGH"))
    assert pdf.startswith(b"%PDF")


# ---- through the API -------------------------------------------------------------------------------------
def _marked_ot3(client, cust, staff_h, wcat):
    """OT-3 order with the watermark option, accepted, sketch generated and finalized."""
    oid = _ot3(client, cust, wcat, submit=False)
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"physical_watermark": True})
    assert r.status_code == 200 and r.json()["physical_watermark"] is True and r.json()["watermark_required"] is True
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=staff_h, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=staff_h, json={})
    assert r.status_code == 201, r.text
    assert client.post(f"{W}/orders/{oid}/sketches/{r.json()['version']}/finalize", headers=staff_h).status_code == 200
    return oid


def _pay(client, cust, staff_h, oid):
    q = client.post(f"{W}/orders/{oid}/quotations", headers=staff_h, json={})
    assert q.status_code == 201, q.text
    assert client.post(f"{W}/quotations/{q.json()['id']}/send", headers=staff_h).status_code == 200
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    p = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"}).json()
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200 and r.json()["order_status"] == "CONFIRMED", r.text


def test_ot3_without_the_option_has_no_line_and_no_certificate(client, cust, staff, wcat):
    sh, _ = staff
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    s = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={}).json()
    assert s["watermark"] is None
    d = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert all(st["kind"] != pm.KIND for p in d["trajectory"]["pages"] for st in p["strokes"])
    assert _sql("select count(*) from product_certificates where order_id=:o", o=oid) == 0
    r = client.get(f"{W}/orders/{oid}/certificate", headers=sh)
    assert r.status_code == 409 and _err(r) == "CERTIFICATE_NOT_READY"


def test_ot1_always_carries_the_line(client, cust, staff, store, wcat):
    sh, _ = staff
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"physical_watermark": False})
    assert r.status_code == 422 and _err(r) == "WATERMARK_MANDATORY_OT1"
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"],
                                                               "ink_color_id": wcat["gel_ink"]})
    assert r.json()["watermark_required"] is True and r.json()["physical_watermark"] is False
    assert _upload(client, cust, oid, store, _png())[0].status_code == 200
    client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201, r.text
    wm = r.json()["watermark"]
    code = _sql("select code from product_certificates where order_id=:o", o=oid)
    assert wm["code"] == code and wm["pages"][0]["placement"] == "BOTTOM" and wm["pages"][0]["strokes"] > 10
    traj = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["trajectory"]
    pages = tj.parse(traj)
    pm.check(_payload("OT1_COPY_RESTORE", {"required": True, **wm}), pages)
    # a region edit keeps exactly the same line (same code, regenerated)
    region = client.get(f"{W}/orders/{oid}/sketches/1/regions", headers=sh).json()[0]
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{region['id']}/edit", headers=sh,
                    json={"action": "REMOVE", "note": "pytest"})
    assert r.status_code == 201, r.text
    assert r.json()["watermark"]["code"] == code


def test_a_manual_upload_can_neither_drop_nor_fake_the_line(client, cust, staff, wcat):
    sh, _ = staff
    oid = _marked_ot3(client, cust, sh, wcat)
    code = _sql("select code from product_certificates where order_id=:o", o=oid)
    upload = {"format": tj.FORMAT, "pages": [{"paper": {"size": "A5"}, "strokes": [
        {"kind": "manual", "points": [[20, 20], [60, 30]]},
        {"kind": "watermark", "points": [[10, 200], [120, 200]]}]}]}           # a fake line
    r = client.post(f"{W}/orders/{oid}/sketches", headers=sh, json={"trajectory": upload})
    assert r.status_code == 201, r.text
    assert r.json()["watermark"]["code"] == code
    traj = client.get(f"{W}/orders/{oid}/sketches/{r.json()['version']}", headers=sh).json()["trajectory"]
    marks = [s for s in traj["pages"][0]["strokes"] if s["kind"] == pm.KIND]
    assert [[10, 200], [120, 200]] not in [s["points"] for s in marks] and len(marks) == r.json()["watermark"]["pages"][0]["strokes"]


def test_the_signed_snapshot_declares_the_line_and_the_package_is_checked(client, cust, staff, mgr, wcat, robot, tech, store):
    sh, _ = staff
    oid = _marked_ot3(client, cust, sh, wcat)
    code = _sql("select code from product_certificates where order_id=:o", o=oid)
    _pay(client, cust, sh, oid)
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    pkg = _package(client, tech, jid)
    assert pkg.status_code == 200, pkg.text
    payload = json.loads(pkg.json()["snapshot"]["payload"])
    assert payload["schema"] == ps.SCHEMA == "vhrs-production/2"
    assert payload["watermark"]["required"] is True and payload["watermark"]["code"] == code
    # a forged v2 package that drops the line of an OT-1 order is refused and recorded
    _forge(oid, jid, get_settings().production_signing_key, key_id=get_settings().production_signing_key_id,
           order={**payload["order"], "type": "OT1_COPY_RESTORE"}, watermark=None)
    _refused(client, tech, jid, "WATERMARK_REQUIRED")
    assert _sql("select count(*) from audit_logs where action='JOB_SIGNATURE_INVALID' and entity_id=:j", j=jid) == 1


def test_scheduling_refuses_a_required_line_missing_from_the_sketch(client, cust, staff, mgr, wcat, robot, tech):
    sh, _ = staff
    oid = _marked_ot3(client, cust, sh, wcat)
    _sql("update sketches set watermark = null where order_id=:o returning 1", o=oid)   # as a sketch saved before U8
    _pay(client, cust, sh, oid)
    assert _sql("select count(*) from production_snapshots where order_id=:o", o=oid) == 0   # the webhook stayed PROCESSED
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 409 and _err(r) == "WATERMARK_MISSING", r.text


def test_public_verification_and_the_certificate_card(client, cust, staff, mgr, wcat, robot, tech):
    sh, _ = staff
    oid = _marked_ot3(client, cust, sh, wcat)
    code = _sql("select code from product_certificates where order_id=:o", o=oid)
    r = client.get(f"{W}/orders/{oid}/certificate", headers=sh)
    assert r.status_code == 409 and _err(r) == "CERTIFICATE_NOT_READY"           # not locked yet
    view = client.get(f"{API}/verify/{code.lower().replace('-', '')}")         # typed from the sheet
    assert view.status_code == 200, view.text
    v = view.json()
    assert v["code"] == code and v["status"] == "NOT_PRODUCED" and v["written_at"] is None
    assert v["order_type"] == "OT3_TEMPLATE" and v["pages"] == 1 and v["watermark_text"].endswith(code)
    assert "không phải bản gốc" in v["statement"]
    assert not ({"customer_name", "customer_id", "order_id", "code_order", "phone", "address", "text"} & v.keys())
    r = client.get(f"{API}/verify/ZZZZ-ZZZZ")
    assert r.status_code == 404 and _err(r) == "CERTIFICATE_NOT_FOUND"

    _pay(client, cust, sh, oid)
    jid = _sched(client, mgr, oid, robot, tech[1], _at(1, 9)).json()["id"]
    r = client.get(f"{W}/orders/{oid}/certificate", headers=sh)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert code in r.headers["content-disposition"]
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200            # the real path to WRITTEN
    issue_paper(client, tech[0], jid)
    for path, body in (("prepare", None), ("calibration", CAL), ("simulation", {"passed": True}), ("start", None)):
        assert client.post(f"{T}/jobs/{jid}/{path}", headers=tech[0], json=body).status_code in (200, 201), path
    _robot_wrote(client, tech, jid)                                                               # D06: the robot's run ended DONE
    assert client.post(f"{T}/jobs/{jid}/finish", headers=tech[0]).status_code == 200
    v = client.get(f"{API}/verify/{code}").json()
    assert v["status"] == "VALID" and v["written_at"] is not None and v["production_locked_at"] is not None
