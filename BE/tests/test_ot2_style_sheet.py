"""OT-2 Phase O2 (owner approved 2026-11-20): the handwriting sample sheet and the customer / Manager style flow.

The sheet photos here are synthetic: the sheet is drawn at its own millimetres (corner squares, page slot, box borders), each
box gets the Hershey glyph of its character at the printed baseline / x-height, then the page is warped as by a hand-held
camera, blurred and JPEG-compressed. That checks the geometry of the reader (right character in the right box, coordinates
in x-height units from the printed baseline), not how real handwriting reads; real sheets are measured separately (O2).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import cv2
import numpy as np
import pytest

from app.core.errors import AppError
from app.integrations.storage import InMemoryStorage
from app.main import app
from app.api.v1.orders import optional_storage
from app.services import background_jobs as bj
from app.services.stroke_ai import sample_sheet as ss
from app.services.stroke_ai.text_to_stroke import HersheySource
from tests.conftest import auth
from tests.test_api_orders import API, _sql

SKIP, OVER = "p1c05", "p1c10"
HU = ss.XH_MM / 14.0                    # Hershey futural: x-height 14 units, baseline at y = 9


def _drawn(ch: str) -> list[list[tuple[float, float]]]:
    """The Hershey glyph of a box in Hershey units; marks lifted clear of the letter (a writer's gap)."""
    g = HersheySource("futural").char(ch)
    lift = lambda s: [(x, y - (2.5 if min(v for _, v in s) < 0 else -1.0)) for x, y in s]   # noqa: E731
    return g.base + [lift(m) for m in g.marks]


def _x_offset(cell, polys, shift=0.0) -> float:
    xs = [x for s in polys for x, _ in s]
    return cell.x + (ss.BOX - (max(xs) - min(xs)) * HU) / 2 - min(xs) * HU + shift


def _draw_page(page: int, skip=(), overflow=()) -> np.ndarray:
    P = ss.PX_PER_MM
    img = np.full((int(ss.PAGE_H * P), int(ss.PAGE_W * P)), 250, np.uint8)
    for x, y in ss.MARK_AT:
        cv2.rectangle(img, (int(x * P), int(y * P)), (int((x + ss.MARK) * P), int((y + ss.MARK) * P)), 0, -1)
    for i, (x, y) in enumerate(ss.SLOTS_AT):
        cv2.rectangle(img, (int(x * P), int(y * P)), (int((x + ss.SLOT) * P), int((y + ss.SLOT) * P)), 0,
                      -1 if i + 1 == page else 3)
    for c in (c for c in ss.layout() if c.page == page):
        cv2.rectangle(img, (int(c.x * P), int(c.y * P)), (int((c.x + ss.BOX) * P), int((c.y + ss.BOX) * P)), 150, 2)
        cv2.putText(img, "x", (int(c.x * P) + 80, int((c.y - 1) * P)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
        if c.id in skip:
            continue
        polys = _drawn(c.char)
        ox = _x_offset(c, polys, 8.0 if c.id in overflow else 0.0)
        for s in polys:
            pts = np.array([[(ox + x * HU) * P, (c.y + ss.BASELINE + (y - 9) * HU) * P] for x, y in s], np.int32)
            cv2.polylines(img, [pts], False, 20, 5)
    return img


def _photo(img: np.ndarray) -> bytes:
    h, w = img.shape
    d = 0.03 * w
    src = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    dst = np.float32([[d, d * 1.5], [w - d * 0.5, d], [d * 0.3, h - d], [w - d, h - d * 0.4]]) + 200
    out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w + 400, h + 400), borderValue=90)  # dark desk
    out = cv2.resize(cv2.GaussianBlur(out, (3, 3), 0), None, fx=0.75, fy=0.75)
    return cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


@lru_cache(maxsize=None)
def photo(page: int, flawed: bool = True) -> bytes:
    return _photo(_draw_page(page, skip={SKIP} if flawed else set(), overflow={OVER} if flawed else set()))


@lru_cache(maxsize=None)
def read(page: int, flawed: bool = True) -> dict:
    return ss.read_page(photo(page, flawed), page)


def _cloud(strokes, step=0.03) -> np.ndarray:
    pts = []
    for s in strokes:
        s = np.asarray(s, float)
        seg = np.linalg.norm(np.diff(s, axis=0), axis=1) if len(s) > 1 else np.zeros(0)
        cum = np.concatenate([[0], np.cumsum(seg)])
        t = np.linspace(0, cum[-1], max(2, int(cum[-1] / step) + 1))
        pts.append(np.stack([np.interp(t, cum, s[:, 0]), np.interp(t, cum, s[:, 1])], 1))
    return np.concatenate(pts)


def _chamfer(a, b) -> float:
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return float(max(d.min(1).mean(), d.min(0).mean()))


# ---------------------------------------------------------------------------------------------------------------------
def test_the_sheet_layout_and_pdf():
    cells = ss.layout()
    assert ss.pages() == 3 and len(cells) == 194 and len({c.id for c in cells}) == 194
    for c in cells:                                   # every box on the paper, clear of the corner squares and the header
        assert 10 < c.x and c.x + ss.BOX < ss.PAGE_W - 10 and 30 < c.y and c.y + ss.BOX < ss.PAGE_H - 17
    t = ss.targets()
    assert len(t) == 86 and "ơ" in t and "Đ" in t and "acute" in t and "á" not in t
    pdf = ss.sheet_pdf()
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r") + pdf.count(b"/Type /Page ") \
        + pdf.count(b"/Type /Page>") >= 3


def test_a_photographed_page_puts_each_box_s_strokes_in_x_height_units_from_its_baseline():
    r = read(1)
    by = {c["cell"]: c for c in r["cells"]}
    assert by[SKIP]["status"] == "EMPTY" and by[OVER]["status"] == "OVERFLOW"
    assert all(c["status"] == "OK" for c in r["cells"] if c["cell"] not in (SKIP, OVER))
    worst = 0.0
    for cell in (c for c in ss.layout() if c.page == 1 and c.id not in (SKIP, OVER)):
        polys = _drawn(cell.char)
        ox = _x_offset(cell, polys)
        truth = [[((ox + x * HU - cell.x) / ss.XH_MM, (y - 9) * HU / ss.XH_MM) for x, y in s] for s in polys]
        worst = max(worst, _chamfer(_cloud(by[cell.id]["strokes"]), _cloud(truth)))
    assert worst < 0.12, worst                        # < 0.7 mm after a hand-held warp, blur and JPEG


def test_carrier_boxes_give_the_marks_alone():
    r = read(3)
    marks = {}
    for c in r["cells"]:
        assert c["status"] == "OK", c
        if c["char"] in ss.CARRIERS:
            assert [m["mark"] for m in c["marks"]] == ss.marks_of(c["char"])
            for m in c["marks"]:
                marks.setdefault(m["mark"], []).append(m)
    assert set(marks) == set(ss.MARK_NAMES)
    assert all(m["dy"] < 0 for k, ms in marks.items() if k != "dot_below" for m in ms)        # above the letter's top
    assert all(m["dy"] > 0.9 for m in marks["dot_below"])                                      # under the letter


def test_a_page_that_cannot_be_located_or_is_another_page_is_refused():
    with pytest.raises(AppError) as e:
        ss.read_page(photo(2), 1)
    assert e.value.code == "SHEET_PAGE_MISMATCH"
    blank = cv2.imencode(".png", np.full((1200, 900), 245, np.uint8))[1].tobytes()
    with pytest.raises(AppError) as e:
        ss.read_page(blank, 1)
    assert e.value.code == "SHEET_CORNERS_NOT_FOUND"
    with pytest.raises(AppError) as e:
        ss.read_page(photo(1), 4)
    assert e.value.code == "SHEET_PAGE_INVALID"


def test_coverage_and_glyph_set_follow_the_samples_kept():
    pages = [read(1, False), read(2, False), read(3, False)]
    s = ss.summary(pages)
    assert s["coverage_pct"] == 100.0 and s["missing"] == [] and s["issues"] == []
    b_cells = [c["cell"] for p in pages for c in p["cells"] if c["char"] == "b"]
    acute = [f"{c['cell']}:acute" for p in pages for c in p["cells"] if c["char"] == "á"]
    s2 = ss.summary(pages, set(b_cells + acute))
    assert s2["missing"] == ["b", "acute"] and s2["coverage_pct"] == round(100 * 84 / 86, 2)
    gs = ss.glyph_set(pages, {b_cells[0]})
    assert gs["format"] == "ot2-glyphs/1" and len(gs["glyphs"]["b"]) == 2 and len(gs["glyphs"]["a"]) == 3
    assert len(gs["marks"]["acute"]) == 2 and "á" not in gs["glyphs"]


# ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def store():
    mem = InMemoryStorage()
    app.dependency_overrides[optional_storage] = lambda: mem
    yield mem
    app.dependency_overrides.pop(optional_storage, None)


def _upload(client, h, sid, page, data, store, *, as_page=None):
    r = client.post(f"{API}/styles/{sid}/pages/{as_page or page}/upload-url", headers=h,
                    json={"mime_type": "image/jpeg", "size_bytes": len(data)})
    assert r.status_code == 201, r.text
    up = r.json()
    store.put(up["upload_url"].removeprefix("memory://"), data)
    return client.post(f"{API}/styles/{sid}/pages/{as_page or page}/confirm", headers=h,
                       json={"upload_id": up["upload_id"], "mime_type": "image/jpeg"})


def _err(r) -> str:
    return r.json()["error"]["code"]


def test_a_customer_builds_a_style_from_the_sheet_and_the_manager_approves_it(client, store):
    cust, other, mgr = auth(client, "CUSTOMER"), auth(client, "CUSTOMER"), auth(client, "MANAGER")
    r = client.post(f"{API}/styles", headers=cust, json={"name": "Nét của tôi", "right_to_use_confirmed": False})
    assert r.status_code == 422 and _err(r) == "RIGHT_TO_USE_REQUIRED"
    r = client.post(f"{API}/styles", headers=cust, json={"name": "Nét của tôi", "right_to_use_confirmed": True})
    assert r.status_code == 201, r.text
    st = r.json()
    sid = st["id"]
    assert st["status"] == "DRAFT" and st["sheet_version"] == "SHEET_V1" and st["pages_total"] == 3 and st["coverage_pct"] == 0
    pdf = client.get(f"{API}/styles/sheet.pdf", headers=cust)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    assert client.get(f"{API}/styles/{sid}", headers=other).status_code == 404               # another customer's style
    r = _upload(client, cust, sid, 2, photo(2), store, as_page=1)                            # page 2 sent as page 1
    assert r.status_code == 422 and _err(r) == "SHEET_PAGE_MISMATCH"
    assert not [k for k in store.objects if k.startswith(f"styles/{sid}/")]                 # refused photo not kept
    r = _upload(client, cust, sid, 1, photo(1), store)
    assert r.status_code == 200, r.text
    assert {c["cell"]: c["status"] for c in r.json()["cells"]}[SKIP] == "EMPTY"
    r = client.post(f"{API}/styles/{sid}/submit", headers=cust)
    assert r.status_code == 422 and _err(r) == "SHEET_PAGES_MISSING" and r.json()["error"]["details"] == {"missing_pages": [2, 3]}
    first = [k for k in store.objects if k.startswith(f"styles/{sid}/p1-")]
    assert _upload(client, cust, sid, 1, photo(1, False), store).status_code == 200          # page 1 photographed again
    assert all(k not in store.objects for k in first) and _sql(
        "select count(*) from handwriting_style_pages where style_id=:s", s=sid) == 1
    assert _upload(client, cust, sid, 2, photo(2), store).status_code == 200
    assert _upload(client, cust, sid, 3, photo(3), store).status_code == 200
    d = client.get(f"{API}/styles/{sid}", headers=cust).json()
    assert d["coverage_pct"] == 100.0 and d["issues"] == [] and [p["page_no"] for p in d["pages"]] == [1, 2, 3]

    r = client.post(f"{API}/styles/{sid}/submit", headers=cust)
    assert r.status_code == 200 and r.json()["status"] == "PENDING_REVIEW"
    r = client.post(f"{API}/styles/{sid}/pages/1/upload-url", headers=cust, json={"mime_type": "image/jpeg", "size_bytes": 9})
    assert r.status_code == 409 and _err(r) == "STYLE_NOT_DRAFT"

    m = client.get(f"{API}/manager/styles/{sid}", headers=mgr).json()
    assert len(m["cells"]) == 194 and all(c["strokes"] for c in m["cells"] if c["status"] == "OK")
    png = client.get(f"{API}/manager/styles/{sid}/cells/p1c00.png", headers=mgr)
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    b_cells = [c["cell"] for c in m["cells"] if c["char"] == "b"]
    for cid in b_cells:
        assert client.put(f"{API}/manager/styles/{sid}/samples/{cid}", headers=mgr, json={"rejected": True}).status_code == 200
    r = client.put(f"{API}/manager/styles/{sid}/samples/p3c32:acute", headers=mgr, json={"rejected": True})
    assert r.status_code == 200 and r.json()["missing"] == ["b"] and "p3c32:acute" in r.json()["rejected_samples"]
    assert client.put(f"{API}/manager/styles/{sid}/samples/p9c99", headers=mgr, json={"rejected": True}).status_code == 404
    assert client.put(f"{API}/manager/styles/{sid}/samples/{b_cells[0]}", headers=mgr,
                      json={"rejected": False}).json()["missing"] == []

    r = client.post(f"{API}/manager/styles/{sid}/approve", headers=mgr)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED", r.text
    uri = _sql("select glyph_set_uri from handwriting_styles where id=:s", s=sid)
    gs = json.loads(store.objects[uri])
    assert gs["coverage_pct"] == 100.0 and len(gs["glyphs"]["b"]) == 1 and len(gs["marks"]["acute"]) == 1
    assert sid in [s["id"] for s in client.get(f"{API}/catalog/my-styles", headers=cust).json()]

    assert client.delete(f"{API}/styles/{sid}", headers=cust).status_code == 204
    assert not [k for k in store.objects if k.startswith(f"styles/{sid}/")]
    assert client.get(f"{API}/styles/{sid}", headers=cust).status_code == 404
    assert sid not in [s["id"] for s in client.get(f"{API}/catalog/my-styles", headers=cust).json()]


def test_the_manager_rejects_with_a_reason_and_a_draft_is_not_reviewable(client, store):
    cust, mgr = auth(client, "CUSTOMER"), auth(client, "MANAGER")
    sid = client.post(f"{API}/styles", headers=cust, json={"name": "x", "right_to_use_confirmed": True}).json()["id"]
    assert client.get(f"{API}/manager/styles/{sid}", headers=mgr).status_code == 404            # still DRAFT
    assert client.post(f"{API}/manager/styles/{sid}/approve", headers=mgr).status_code == 409
    for p in (1, 2, 3):
        assert _upload(client, cust, sid, p, photo(p), store).status_code == 200
    assert client.post(f"{API}/styles/{sid}/submit", headers=cust).status_code == 200
    r = client.post(f"{API}/manager/styles/{sid}/reject", headers=mgr, json={"reason": "Chữ quá nhỏ"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    d = client.get(f"{API}/styles/{sid}", headers=cust).json()
    assert d["review_note"] == "Chữ quá nhỏ" and d["status"] == "REJECTED"


def test_sheet_photos_of_styles_not_kept_are_purged_after_the_retention_but_the_strokes_stay(client, store, monkeypatch):
    cust = auth(client, "CUSTOMER")
    keep = client.post(f"{API}/styles", headers=cust, json={"name": "k", "right_to_use_confirmed": True,
                                                             "keep_consent": True}).json()["id"]
    drop = client.post(f"{API}/styles", headers=cust, json={"name": "d", "right_to_use_confirmed": True}).json()["id"]
    for sid in (keep, drop):
        assert _upload(client, cust, sid, 1, photo(1), store).status_code == 200
    # updated_at is set by a trigger on every UPDATE, so the job's clock moves a day ahead instead
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(bj, "_now", lambda: tomorrow)
    monkeypatch.setattr(bj, "PURGE_AFTER_DAYS", 0)
    from app.db.session import _factory
    with _factory()() as s:
        out = bj.photo_purge(s, order_ids=[-1], style_ids=[keep, drop], storage=store)
    assert out.get("style_pages_would_delete") == 1 and out["dry_run"] is True, out
    with _factory()() as s:
        out = bj.photo_purge(s, order_ids=[-1], style_ids=[keep, drop], storage=store, enabled=True)
    assert out["style_pages_deleted"] == 1
    assert [k for k in store.objects if k.startswith(f"styles/{keep}/")] and not [
        k for k in store.objects if k.startswith(f"styles/{drop}/")]
    assert _sql("select read_result->'cells'->0->>'cell' from handwriting_style_pages where style_id=:s", s=drop) == "p1c00"
    with _factory()() as s:
        assert bj.photo_purge(s, order_ids=[-1], style_ids=[keep, drop], storage=store, enabled=True)[
            "style_pages_deleted"] == 0
    with _factory()() as s:                          # an order-scoped run (other tests) never looks at styles
        assert "style_pages_would_delete" not in bj.photo_purge(s, order_ids=[-1], storage=store)
