"""Phase 4b: product photos + QC (UC-38, FR-49, BR-21) and the customer's acceptance / rewrite (UC-18, FR-28, BR-13).

Real database and triggers, the in-memory storage double. Every test builds its own paid and scheduled order with its own
'pytest_' robot and technician. Nothing talks to a robot or a camera: the test posts what the workstation would.
"""
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_engine
from app.domain import photo_rules as pr
from app.main import app
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_scheduling import _at, _prod, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL, T, _post, _running, _status  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, manager, policy, staff, store, wcat  # noqa: F401


# ---- helpers ----------------------------------------------------------------------------------------
def _jpeg(width=1400, height=1000, seed=0) -> bytes:
    """A real, decodable JPEG (smooth gradient, a few KB)."""
    x = np.linspace(0, 255, width, dtype=np.float32)[None, :]
    y = np.linspace(0, 255, height, dtype=np.float32)[:, None]
    img = np.stack([(x + seed * 17) % 256 + 0 * y, (y + seed * 31) % 256 + 0 * x, (x + y) / 2 + 0 * x], axis=-1)
    ok, buf = cv2.imencode(".jpg", img.astype(np.uint8))
    assert ok
    return buf.tobytes()


def _png(width=1400, height=1000) -> bytes:
    ok, buf = cv2.imencode(".png", np.zeros((height, width, 3), np.uint8))
    assert ok
    return buf.tobytes()


def _upload(client, tech, store, jid, data: bytes, mime="image/jpeg"):
    """upload-url, then the client's PUT (here: straight into the in-memory store). Returns (key, path)."""
    r = client.post(f"{T}/jobs/{jid}/photos/upload-url", headers=tech[0], json={"mime_type": mime, "size_bytes": len(data)})
    assert r.status_code == 201, r.text
    body = r.json()
    path = body["upload_url"].removeprefix("memory://")
    assert body["method"] == "PUT" and body["expires_in"] > 0
    store.objects[path] = data
    return body["photo_key"], path


def _add(client, tech, store, jid, kind, qc="PASS", note=None, seed=0, data=None, expect=201):
    key, path = _upload(client, tech, store, jid, data or _jpeg(seed=seed))
    body = {"photo_key": key, "kind": kind}
    if qc:
        body["qc_result"] = qc
    if note:
        body["qc_note"] = note
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json=body)
    assert r.status_code == expect, r.text
    return r.json(), path


def _written(client, cust, staff, mgr, wcat, robot, tech, **kw):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, **kw)
    _post(client, tech, jid, "finish", status=200)
    return oid, jid


def _awaiting(client, cust, staff, mgr, wcat, robot, tech, store, **kw):
    """Written, two QC-passed photos submitted: the order waits for the customer."""
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech, **kw)
    _add(client, tech, store, jid, "OVERALL", seed=1)
    _add(client, tech, store, jid, "CLOSE_UP", seed=2)
    _post(client, tech, jid, "photos/submit", status=200)
    return oid, jid


def _run_job(client, tech, jid):
    """The technician's whole path for one scheduled job, up to WRITTEN."""
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _post(client, tech, jid, "prepare", status=200)
    _post(client, tech, jid, "calibration", CAL, status=201)
    _post(client, tech, jid, "simulation", {"passed": True}, status=200)
    _post(client, tech, jid, "start", status=200)
    _post(client, tech, jid, "finish", status=200)


def _ost(oid) -> str:
    return _sql("select order_status::text from orders where id=:o", o=oid)


def _row(oid) -> dict:
    with get_engine().connect() as c:
        return dict(c.execute(text("""select order_status::text os, production_status::text ps, free_rewrite_used fr,
                  awaiting_acceptance_at aa, accepted_product_at ap from orders where id=:o"""), {"o": oid}).mappings().one())


def _reschedule(client, mgr, oid, robot, tech, days=2):
    r = _sched(client, mgr, oid, robot, tech[1], _at(days, 9))
    assert r.status_code == 201, r.text
    return r.json()["id"]


PHOTOS = f"{API}/orders"


# ---- access and the step guard ------------------------------------------------------------------------
def test_photo_routes_belong_to_the_assigned_technician_and_the_written_step(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)              # still WRITING
    up = {"mime_type": "image/jpeg", "size_bytes": 1000}
    for path, body in (("photos/upload-url", up), ("photos/submit", None), ("qc-fail", {"note": "mực loang"})):
        r = _post(client, tech, jid, path, body, status=409)
        assert _err(r) == "JOB_STATE_CONFLICT", path                               # photos only after the robot has written
    assert _post(client, tech, jid, "photos", {"photo_key": "a" * 32 + ".jpg", "kind": "OVERALL"}, status=409)
    _post(client, tech, jid, "finish", status=200)

    other = _user(client, "TECHNICAL_STAFF")
    calls = [("post", "/photos/upload-url", up), ("post", "/photos", {"photo_key": "a" * 32 + ".jpg", "kind": "OVERALL"}),
             ("get", "/photos", None), ("patch", "/photos/1", {"qc_result": "PASS"}), ("delete", "/photos/1", None),
             ("post", "/photos/submit", None), ("post", "/qc-fail", {"note": "mực loang"})]
    for method, path, body in calls:                                              # BR-19: someone else's job is not found
        r = client.request(method.upper(), f"{T}/jobs/{jid}{path}", headers=other[0], json=body)
        assert r.status_code == 404 and _err(r) == "JOB_NOT_FOUND", path
    assert _row(oid)["ps"] == "WRITTEN" and _status(jid) == "WRITTEN"             # none of that changed anything


# ---- upload, registration and QC ----------------------------------------------------------------------
def test_upload_validation_registration_and_qc(client, cust, staff, mgr, wcat, robot, tech, store, monkeypatch):
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech)

    for body, code in (({"mime_type": "image/gif", "size_bytes": 10}, "VALIDATION_ERROR"),
                       ({"mime_type": "application/pdf", "size_bytes": 10}, "VALIDATION_ERROR"),
                       ({"mime_type": "image/jpeg", "size_bytes": 0}, "VALIDATION_ERROR"),
                       ({"mime_type": "image/jpeg", "size_bytes": 21 * 1024 * 1024}, "FILE_TOO_LARGE")):
        r = client.post(f"{T}/jobs/{jid}/photos/upload-url", headers=tech[0], json=body)
        assert r.status_code == 422 and _err(r) == code, body

    # registering something that was never uploaded, or a key that is not ours
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": "a" * 32 + ".jpg", "kind": "OVERALL"})
    assert r.status_code == 409 and _err(r) == "UPLOAD_NOT_FOUND"
    for bad in ("z" * 36, "../../" + "a" * 30, "A" * 32 + ".jpg"):
        r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": bad, "kind": "OVERALL"})
        assert r.status_code in (422,) and _err(r) in ("INVALID_PHOTO_KEY", "VALIDATION_ERROR"), bad
    assert _sql("select count(*) from product_photos where job_id=:j", j=jid) == 0

    # the real content is checked, not the declared type
    key, path = _upload(client, tech, store, jid, b"%PDF-1.4 not a photo at all")
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": key, "kind": "OVERALL"})
    assert r.status_code == 422 and _err(r) == "INVALID_PHOTO" and path not in store.objects      # bad object removed
    key, path = _upload(client, tech, store, jid, b"\xff\xd8\xff" + b"garbage that does not decode")
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": key, "kind": "OVERALL"})
    assert r.status_code == 422 and _err(r) == "INVALID_PHOTO" and path not in store.objects
    key, path = _upload(client, tech, store, jid, _jpeg(800, 600))
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": key, "kind": "OVERALL"})
    assert r.status_code == 422 and _err(r) == "PHOTO_TOO_SMALL" and path not in store.objects
    assert _sql("select count(*) from product_photos where job_id=:j", j=jid) == 0               # nothing half-registered

    # FAIL needs a reason, everywhere
    key, _ = _upload(client, tech, store, jid, _jpeg(seed=3))
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": key, "kind": "OTHER", "qc_result": "FAIL"})
    assert r.status_code == 422 and _err(r) == "QC_NOTE_REQUIRED"

    # a good one
    p1, path1 = _add(client, tech, store, jid, "OVERALL", seed=1)
    assert p1["kind"] == "OVERALL" and p1["qc_result"] == "PASS" and p1["url"].endswith(path1) and p1["url_expires_in"] > 0
    assert path1 == f"orders/{oid}/product/{jid}/{path1.rsplit('/', 1)[1]}"                      # built by the server
    assert _sql("select uploaded_by from product_photos where id=:p", p=p1["id"]) == tech[1]
    again = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": path1.rsplit("/", 1)[1], "kind": "OVERALL"})
    assert again.json()["id"] == p1["id"]                                                         # same call twice is harmless
    assert _sql("select count(*) from product_photos where job_id=:j", j=jid) == 1
    png = _add(client, tech, store, jid, "CLOSE_UP", qc=None, data=_png())[0]                      # png is fine, QC left open
    assert png["qc_result"] is None

    # QC changes
    r = client.patch(f"{T}/jobs/{jid}/photos/{png['id']}", headers=tech[0], json={"qc_result": "FAIL"})
    assert r.status_code == 422 and _err(r) == "QC_NOTE_REQUIRED"
    r = client.patch(f"{T}/jobs/{jid}/photos/{png['id']}", headers=tech[0], json={"qc_result": "FAIL", "qc_note": "nét đứt"})
    assert r.status_code == 200 and r.json()["qc_result"] == "FAIL" and r.json()["qc_note"] == "nét đứt"
    r = client.patch(f"{T}/jobs/{jid}/photos/{png['id']}", headers=tech[0], json={"qc_result": "PASS"})
    assert r.json()["qc_result"] == "PASS"
    assert client.patch(f"{T}/jobs/{jid}/photos/999999999", headers=tech[0], json={"qc_result": "PASS"}).status_code == 404
    listing = client.get(f"{T}/jobs/{jid}/photos", headers=tech[0]).json()
    assert [p["id"] for p in listing] == [p1["id"], png["id"]]

    # removing keeps the row, drops the object, and the same key cannot be registered again
    assert client.delete(f"{T}/jobs/{jid}/photos/{png['id']}", headers=tech[0]).status_code == 204
    assert client.delete(f"{T}/jobs/{jid}/photos/{png['id']}", headers=tech[0]).status_code == 404
    assert _sql("select deleted_at is not null from product_photos where id=:p", p=png["id"]) is True
    assert [p["id"] for p in client.get(f"{T}/jobs/{jid}/photos", headers=tech[0]).json()] == [p1["id"]]
    key = _sql("select substring(url from '[^/]+$') from product_photos where id=:p", p=png["id"])
    r = client.post(f"{T}/jobs/{jid}/photos", headers=tech[0], json={"photo_key": key, "kind": "CLOSE_UP"})
    assert r.status_code == 409 and _err(r) == "PHOTO_REMOVED"

    # at most MAX_PHOTOS_PER_JOB live photos
    monkeypatch.setattr(pr, "MAX_PHOTOS_PER_JOB", 2)
    _add(client, tech, store, jid, "CLOSE_UP", seed=4)
    r = client.post(f"{T}/jobs/{jid}/photos/upload-url", headers=tech[0], json={"mime_type": "image/jpeg", "size_bytes": 1000})
    assert r.status_code == 422 and _err(r) == "TOO_MANY_PHOTOS"


# ---- BR-21 and the hand-over ---------------------------------------------------------------------------
def test_submit_needs_two_passing_photos_overall_and_close_up(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech)
    r = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust)
    assert r.status_code == 409 and _err(r) == "PHOTOS_NOT_AVAILABLE"                  # nothing to see yet

    def submit(expect_missing=None, **expect):
        r = _post(client, tech, jid, "photos/submit", status=409)
        assert _err(r) == "PHOTO_REQUIREMENTS_NOT_MET", r.text
        d = r.json()["error"]["details"]
        assert all(d[k] == v for k, v in expect.items()), d

    submit(photos=0)
    a, _ = _add(client, tech, store, jid, "OVERALL", seed=1)
    submit(photos=1)                                                                    # one photo is not enough
    b, _ = _add(client, tech, store, jid, "OVERALL", seed=2)
    submit(photos=2, missing_kinds=["CLOSE_UP"])                                        # two, but no close-up
    c, _ = _add(client, tech, store, jid, "CLOSE_UP", qc=None, seed=3)
    submit(unchecked=1)                                                                 # QC not done
    r = client.patch(f"{T}/jobs/{jid}/photos/{c['id']}", headers=tech[0], json={"qc_result": "FAIL", "qc_note": "ảnh bị mờ"})
    assert r.status_code == 200, r.text
    submit(failed=1)                                                                   # a failed photo blocks
    assert _row(oid)["ps"] == "WRITTEN" and _status(jid) == "WRITTEN"

    # DB backstop (trigger fn_photo_uploaded_guard): even a direct UPDATE cannot skip BR-21
    with pytest.raises(DBAPIError) as e:
        with get_engine().begin() as conn:
            conn.execute(text("update orders set production_status='PHOTO_UPLOADED' where id=:o"), {"o": oid})
    assert getattr(e.value.orig, "sqlstate", None) == "P0409"

    # a failed photo that was removed no longer counts (fix D2), neither for the API nor for the trigger
    assert client.delete(f"{T}/jobs/{jid}/photos/{c['id']}", headers=tech[0]).status_code == 204
    _add(client, tech, store, jid, "CLOSE_UP", seed=4)
    r = _post(client, tech, jid, "photos/submit", status=200)
    assert r.json()["status"] == "PHOTO_UPLOADED"

    row = _row(oid)
    assert (row["os"], row["ps"]) == ("AWAITING_ACCEPTANCE", "PHOTO_UPLOADED") and _status(jid) == "PHOTO_UPLOADED"
    assert row["aa"] is not None and row["ap"] is None                                  # the trigger stamped the waiting time
    chain = _sql("""select string_agg(state_type::text || ':' || from_status || '>' || to_status, ',' order by id)
                    from status_histories where order_id=:o and actor_id=:t and to_status in ('PHOTO_UPLOADED','AWAITING_ACCEPTANCE')""",
                 o=oid, t=tech[1])
    assert set(chain.split(",")) == {"PRODUCTION:WRITTEN>PHOTO_UPLOADED", "ORDER:CONFIRMED>AWAITING_ACCEPTANCE"}
    assert _sql("select count(*) from audit_logs where action='JOB_PHOTOS_SUBMIT' and entity_id=:j", j=jid) == 1

    # closed afterwards
    for path, body in (("photos/upload-url", {"mime_type": "image/jpeg", "size_bytes": 10}), ("photos/submit", None),
                       ("qc-fail", {"note": "mực loang"})):
        assert _err(_post(client, tech, jid, path, body, status=409)) in ("JOB_STATE_CONFLICT", "ORDER_NOT_ACTIVE"), path
    assert client.delete(f"{T}/jobs/{jid}/photos/{a['id']}", headers=tech[0]).status_code == 409


# ---- QC failed: back to the Manager, no free rewrite spent --------------------------------------------------
def test_qc_failure_sends_the_job_back_without_spending_the_free_rewrite(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech)
    for note in ("", "  ", "ab"):
        assert _post(client, tech, jid, "qc-fail", {"note": note}, status=422)
    r = _post(client, tech, jid, "qc-fail", {"note": "Nét bị đứt ở dòng 2"}, status=200)
    assert r.json()["status"] == "REWRITE_REQUIRED"
    row = _row(oid)
    assert (row["os"], row["ps"], row["fr"]) == ("CONFIRMED", "REWRITE_REQUIRED", False)      # the customer's free rewrite is intact
    assert _sql("select count(*) from audit_logs where action='JOB_QC_FAIL' and entity_id=:j", j=jid) == 1
    assert _err(_post(client, tech, jid, "qc-fail", {"note": "again"}, status=409)) == "JOB_STATE_CONFLICT"

    # the Manager schedules it again: a new job flagged as rewrite, and the whole path works a second time
    jid2 = _reschedule(client, mgr, oid, robot, tech)
    assert _sql("select is_rewrite from production_jobs where id=:j", j=jid2) is True and _prod(oid) == "SCHEDULED"
    _run_job(client, tech, jid2)
    _add(client, tech, store, jid2, "OVERALL", seed=1)
    _add(client, tech, store, jid2, "CLOSE_UP", seed=2)
    _post(client, tech, jid2, "photos/submit", status=200)
    assert _row(oid)["os"] == "AWAITING_ACCEPTANCE" and _status(jid2) == "PHOTO_UPLOADED"
    assert _status(jid) == "REWRITE_REQUIRED"


# ---- UC-18: the customer looks and accepts -------------------------------------------------------------------
def test_customer_sees_only_passing_photos_and_accepts(client, cust, staff, mgr, wcat, robot, tech, store, manager):
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech)
    _add(client, tech, store, jid, "OVERALL", seed=1)
    _add(client, tech, store, jid, "CLOSE_UP", seed=2)
    failed, _ = _add(client, tech, store, jid, "OTHER", qc="FAIL", note="bóng loá", seed=3)
    assert _post(client, tech, jid, "photos/submit", status=409)                       # the failed one still blocks
    client.delete(f"{T}/jobs/{jid}/photos/{failed['id']}", headers=tech[0])
    _post(client, tech, jid, "photos/submit", status=200)

    other = auth(client, "CUSTOMER")
    assert client.get(f"{PHOTOS}/{oid}/product-photos", headers=other).status_code == 404         # someone else's order
    for method, path, body in (("get", "product-photos", None), ("post", "accept", None),
                               ("post", "rewrite", {"reason_code": "WORKSHOP_ERROR", "note": "nét bị đứt"})):
        r = client.request(method.upper(), f"{PHOTOS}/{oid}/{path}", headers=other, json=body)
        assert r.status_code == 404 and _err(r) == "ORDER_NOT_FOUND", path

    d = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).json()
    assert d["order_status"] == "AWAITING_ACCEPTANCE" and sorted(p["kind"] for p in d["photos"]) == ["CLOSE_UP", "OVERALL"]
    assert all(p["url"] for p in d["photos"]) and d["sketch_preview_url"]
    assert d["can_accept"] is True and d["can_request_rewrite"] is True and d["free_rewrite_used"] is False
    assert d["acceptance_due_at"] is not None
    detail = client.get(f"{API}/orders/{oid}", headers=cust).json()
    assert detail["awaiting_acceptance_at"] and detail["accepted_product_at"] is None and detail["free_rewrite_used"] is False

    # the workshop reads the same photos (Staff of the order, Manager); another Staff does not see the order
    wh = client.get(f"{API}/workshop/orders/{oid}/product-photos", headers=staff[0]).json()
    assert len(wh) == 2 and {p["qc_result"] for p in wh} == {"PASS"} and all(p["job_status"] == "PHOTO_UPLOADED" for p in wh)
    assert client.get(f"{API}/workshop/orders/{oid}/product-photos", headers=manager[0]).status_code == 200
    stranger = _user(client, "STAFF")
    assert client.get(f"{API}/workshop/orders/{oid}/product-photos", headers=stranger[0]).status_code == 404

    # the customer may not cancel at this point (the trigger offers no way out)
    assert client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "x"}).status_code == 409

    r = client.post(f"{PHOTOS}/{oid}/accept", headers=cust)
    assert r.status_code == 200 and r.json()["order_status"] == "AWAITING_FINAL_PAYMENT", r.text
    assert r.json()["production_status"] == "FINISHED" and r.json()["accepted_product_at"]
    assert _status(jid) == "DONE"
    assert _sql("""select actor_id from status_histories where order_id=:o and to_status='AWAITING_FINAL_PAYMENT'""", o=oid) == _sql(
        "select customer_id from orders where id=:o", o=oid)
    assert _sql("select count(*) from audit_logs where action='ORDER_ACCEPT_PRODUCT' and entity_id=:o", o=oid) == 1

    again = client.post(f"{PHOTOS}/{oid}/accept", headers=cust)
    assert again.status_code == 409 and _err(again) == "ORDER_NOT_AWAITING_ACCEPTANCE"
    r = client.post(f"{PHOTOS}/{oid}/rewrite", headers=cust, json={"reason_code": "WORKSHOP_ERROR", "note": "nét bị đứt"})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_AWAITING_ACCEPTANCE"                  # too late for a rewrite
    after = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).json()
    assert after["can_accept"] is False and after["can_request_rewrite"] is False and len(after["photos"]) == 2


# ---- BR-13: ONE free rewrite, end to end ---------------------------------------------------------------------
def test_one_free_rewrite_runs_the_whole_cycle_and_the_second_is_refused(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store)
    base = f"{PHOTOS}/{oid}/rewrite"
    for body, code in (({"reason_code": "CHANGED_MY_MIND", "note": "tôi đổi ý rồi"}, "VALIDATION_ERROR"),
                       ({"reason_code": "WORKSHOP_ERROR", "note": "abc"}, "VALIDATION_ERROR"),
                       ({"reason_code": "WORKSHOP_ERROR"}, "VALIDATION_ERROR")):
        r = client.post(base, headers=cust, json=body)
        assert r.status_code == 422 and _err(r) == code, body
    assert _row(oid)["os"] == "AWAITING_ACCEPTANCE"                                          # refused requests changed nothing

    r = client.post(base, headers=cust, json={"reason_code": "DIFFERS_FROM_SKETCH", "note": "Chữ khác phác thảo ở dòng 3"})
    assert r.status_code == 200, r.text
    assert (r.json()["order_status"], r.json()["production_status"], r.json()["free_rewrite_used"]) == (
        "CONFIRMED", "REWRITE_REQUIRED", True)
    assert _status(jid) == "REWRITE_REQUIRED"
    assert _sql("select count(*) from audit_logs where action='ORDER_REWRITE_REQUEST' and entity_id=:o", o=oid) == 1
    assert _sql("select new_value->>'reason_code' from audit_logs where action='ORDER_REWRITE_REQUEST' and entity_id=:o",
                o=oid) == "DIFFERS_FROM_SKETCH"
    assert client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).status_code == 409        # nothing to judge while rewriting
    assert client.post(base, headers=cust, json={"reason_code": "WORKSHOP_ERROR", "note": "lần nữa nhé"}).status_code == 409

    # Manager schedules it again (assumption #10 of PROJECT_STATUS: the REWRITE_REQUIRED path, end to end)
    jid2 = _reschedule(client, mgr, oid, robot, tech)
    assert _sql("select is_rewrite from production_jobs where id=:j", j=jid2) is True
    assert _prod(oid) == "SCHEDULED" and _ost(oid) == "CONFIRMED"
    _run_job(client, tech, jid2)
    assert client.get(f"{T}/jobs/{jid2}/package", headers=tech[0]).status_code == 409           # WRITTEN: closed to download
    _add(client, tech, store, jid2, "OVERALL", seed=5)
    _add(client, tech, store, jid2, "CLOSE_UP", seed=6)
    _post(client, tech, jid2, "photos/submit", status=200)
    assert _row(oid)["os"] == "AWAITING_ACCEPTANCE"

    d = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).json()
    assert d["can_accept"] is True and d["can_request_rewrite"] is False and d["free_rewrite_used"] is True
    assert len(d["photos"]) == 2                                                                 # the NEW job's photos, not the old ones
    r = client.post(base, headers=cust, json={"reason_code": "WORKSHOP_ERROR", "note": "vẫn chưa đạt"})
    assert r.status_code == 409 and _err(r) == "REWRITE_LIMIT_REACHED"                          # "contact the workshop"
    assert _row(oid)["os"] == "AWAITING_ACCEPTANCE" and _status(jid2) == "PHOTO_UPLOADED"

    assert client.post(f"{PHOTOS}/{oid}/accept", headers=cust).status_code == 200
    assert (_ost(oid), _prod(oid), _status(jid2)) == ("AWAITING_FINAL_PAYMENT", "FINISHED", "DONE")
    assert _status(jid) == "REWRITE_REQUIRED"                                                    # the first job stays as history


# ---- FR-28: no answer means accepted ------------------------------------------------------------------------
def test_unanswered_order_is_accepted_after_the_deadline(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store)
    days = int(_sql("select value::text from system_settings where key='auto_accept_days'") or pr.DEFAULT_AUTO_ACCEPT_DAYS)

    _sql("update orders set awaiting_acceptance_at = now() - make_interval(days => :d) + interval '1 hour' where id=:o returning 1",
         d=days, o=oid)
    d = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).json()
    assert d["can_accept"] is True and _ost(oid) == "AWAITING_ACCEPTANCE"                        # one hour left: still the customer's

    _sql("update orders set awaiting_acceptance_at = now() - make_interval(days => :d) - interval '1 hour' where id=:o returning 1",
         d=days, o=oid)
    d = client.get(f"{PHOTOS}/{oid}/product-photos", headers=cust).json()                        # reading settles it
    assert d["order_status"] == "AWAITING_FINAL_PAYMENT" and d["can_accept"] is False and d["acceptance_due_at"] is None
    assert (_ost(oid), _prod(oid), _status(jid)) == ("AWAITING_FINAL_PAYMENT", "FINISHED", "DONE")
    assert _sql("select accepted_product_at is not null from orders where id=:o", o=oid) is True
    assert _sql("select actor_id is null from status_histories where order_id=:o and to_status='AWAITING_FINAL_PAYMENT'", o=oid) is True
    assert _sql("select count(*) from audit_logs where action='ORDER_AUTO_ACCEPT' and entity_id=:o and actor_id is null", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='ORDER_ACCEPT_PRODUCT' and entity_id=:o", o=oid) == 0


def test_acting_after_the_deadline_still_settles_the_order(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store)
    _sql("update orders set awaiting_acceptance_at = now() - interval '40 days' where id=:o returning 1", o=oid)
    r = client.post(f"{PHOTOS}/{oid}/rewrite", headers=cust, json={"reason_code": "WORKSHOP_ERROR", "note": "quá muộn rồi"})
    assert r.status_code == 409 and _err(r) == "ACCEPTANCE_CLOSED"
    # the 409 did not undo the acceptance (S03: committed before the error)
    assert (_ost(oid), _prod(oid), _status(jid)) == ("AWAITING_FINAL_PAYMENT", "FINISHED", "DONE")
    assert _row(oid)["fr"] is False                                                              # the free rewrite was never spent


# ---- concurrency -------------------------------------------------------------------------------------------
def test_accept_and_rewrite_at_the_same_time_leave_one_consistent_result(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store)

    def act(which):
        with TestClient(app) as c:
            if which == "accept":
                return c.post(f"{PHOTOS}/{oid}/accept", headers=cust).status_code
            return c.post(f"{PHOTOS}/{oid}/rewrite", headers=cust,
                          json={"reason_code": "WORKSHOP_ERROR", "note": "chưa đạt yêu cầu"}).status_code

    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(act, ["accept", "rewrite"]))
    assert codes in ([200, 409],), codes                                                         # exactly one wins
    row = _row(oid)
    if row["os"] == "AWAITING_FINAL_PAYMENT":
        assert (row["ps"], row["fr"], _status(jid)) == ("FINISHED", False, "DONE")
    else:
        assert (row["os"], row["ps"], row["fr"], _status(jid)) == ("CONFIRMED", "REWRITE_REQUIRED", True, "REWRITE_REQUIRED")
