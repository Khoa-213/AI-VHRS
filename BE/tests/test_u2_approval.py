"""Upgrade U2 (docs/UPGRADE_AI_ROBOT_PLAN.md): AI mark on customer-facing sketch images, an append-only record of what the
customer approved, and a mandatory reason on every re-quote after a change request (owner decision Q4).
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import cv2
import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_engine

from app.services import quotation_pdf
from app.services.stroke_ai import trajectory as tj, watermark
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _paid, _quoted as _privacy_ok
from tests.test_api_workshop import _err, cust, policy, staff, store, wcat  # noqa: F401


def _blank(h=400, w=600, fmt="png"):
    ok, buf = cv2.imencode("." + fmt, np.full((h, w, 3), 255, np.uint8))
    return buf.tobytes()


def _img(data):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)


# ---- the mark itself -----------------------------------------------------------------------------------
def test_the_mark_has_a_bottom_band_and_a_faint_tile_and_keeps_the_size():
    out = _img(watermark.apply_bytes(_blank(), "AI-00042", fmt="png"))
    assert out.shape == (400, 600)
    band = out[-14:, :]
    assert band.min() < 140                                     # readable text in the band
    body = out[:300, :]
    assert 200 < body.min() < 255                               # the diagonal tile is there but faint
    assert (body < 255).mean() > 0.01
    assert "AI-00042" in watermark.band_text("AI-00042") and watermark.band_text(None) == watermark.BAND_TEXT
    jpg = watermark.apply_bytes(_blank(fmt="jpg"), None, fmt="jpg")
    assert jpg[:2] == b"\xff\xd8"
    with pytest.raises(ValueError):
        watermark.apply_bytes(b"not an image", None, fmt="png")


def test_saved_sketch_images_carry_the_mark_but_the_trajectory_does_not(client, cust, staff, wcat, store):
    oid, _ = _privacy_ok(client, cust, staff[0], wcat)
    code = _sql("select code from orders where id=:o", o=oid)
    sid = _sql("select max(id) from sketches where order_id=:o", o=oid)
    traj_uri = _sql("select trajectory_uri from sketches where id=:s", s=sid)
    jpgs = _sql("select image_urls from sketches where id=:s", s=sid)
    page = tj.parse(json.loads(store.read(traj_uri)))[0]
    plain = tj.render_preview(page)
    stored = store.read(json.loads(store.read(traj_uri))["pages"][0]["preview_path"])
    assert stored != plain
    again = _img(watermark.apply_bytes(plain, code, fmt="png")).astype(int)      # the plain render + the mark
    assert np.abs(_img(stored).astype(int) - again).mean() < 1.0                   # (re-parsed strokes round slightly)
    assert np.abs(_img(stored).astype(int) - _img(plain).astype(int)).mean() > 1.0
    assert _img(store.read(jpgs[0]))[-10:, :].min() < 160                 # the customer JPEG has the band too
    raw = json.dumps(json.loads(store.read(traj_uri)))
    assert "AI-VHRS" not in raw                                           # nothing added to the strokes


def test_the_quotation_pdf_still_renders_with_a_revision_block():
    doc = quotation_pdf.QuotationDoc(
        order_code="AI-1", version=2, customer_name="Khách", issued_at=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc), eta=None, options=[], min_deposit_pct=Decimal("30"), adjusted=False,
        multi_option=False, revision_reason="Thêm một trang", previous_version=1, previous_total=Decimal("150000"))
    pdf = quotation_pdf.render(doc)
    assert pdf[:5] == b"%PDF-"
    assert "AI-VHRS" in quotation_pdf.AI_NOTICE


# ---- the approval record ------------------------------------------------------------------------------
def test_approval_records_what_the_customer_saw_and_cannot_be_edited(client, cust, staff, wcat, store):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    with get_engine().connect() as c:
        r = c.execute(text("select sketch_id, sketch_version, sketch_content_hash, image_paths, chosen_option, total "
                           "from sketch_approvals where quotation_id=:q"), {"q": q["id"]}).one()
        s = c.execute(text("select id, version, content_hash, image_urls from sketches where id=:s"),
                      {"s": q["sketch_id"]}).one()
    assert tuple(r[:4]) == tuple(s) and s[2] and s[3]
    assert r[4] == 1 and r[5] == Decimal(q["final_total"])
    with pytest.raises(DBAPIError):
        _sql("update sketch_approvals set total = 1 where quotation_id=:q returning 1", q=q["id"])


def test_a_stale_sketch_id_is_refused_and_the_current_one_approves(client, cust, staff, wcat, store):
    oid, q = _privacy_ok(client, cust, staff[0], wcat)
    view = client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()
    assert view["sketch"]["id"] == q["sketch_id"] and "AI-VHRS" in view["ai_notice"] and view["revision"] is None
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"sketch_id": q["sketch_id"] + 99999})
    assert r.status_code == 409 and _err(r) == "SKETCH_VERSION_STALE"
    assert r.json()["error"]["details"]["sketch_id"] == q["sketch_id"]
    assert _sql("select count(*) from sketch_approvals where quotation_id=:q", q=q["id"]) == 0
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"sketch_id": q["sketch_id"]})
    assert r.status_code == 200, r.text
    assert _sql("select count(*) from sketch_approvals where quotation_id=:q", q=q["id"]) == 1


def test_the_signed_snapshot_carries_the_approval(client, cust, staff, wcat, store):
    oid, q, _ = _paid(client, cust, staff[0], wcat)
    payload = json.loads(_sql("select payload from production_snapshots where order_id=:o and revoked_at is null", o=oid))
    appr = payload["approval"]
    assert appr["id"] == _sql("select id from sketch_approvals where quotation_id=:q", q=q["id"])
    assert appr["sketch_version"] == payload["sketch"]["version"]
    assert appr["sketch_content_hash"] == payload["sketch"]["trajectory_sha256"]
