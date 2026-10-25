"""Service G on synthetic photos: a rendered sheet is put on a dark table with perspective, rotation, uneven light and sensor noise.
These tests prove the measurement logic (alignment, orientation, mm metrics, honest failures); they say nothing about real phone photos."""
import cv2
import numpy as np
import pytest

from app.core.errors import AppError
from app.services import quality_eval as qe
from app.services.stroke_ai import render_image, text_to_stroke as tts
from app.services.stroke_ai.trajectory import Page, Stroke
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401

PAGE = tts.compose_text("Xin chào Việt Nam", font_name="futural", paper_size="A5", font_size_mm=9.0, seed=1)[0]


def photo(page: Page, *, rot90=0, shift_mm=(0.0, 0.0), skew=1.0, noise=6.0, ink="#14213d", seed=0, size=(1500, 1900)) -> bytes:
    """The sheet as a phone would see it."""
    shifted = Page(page.paper_size, [Stroke([(x + shift_mm[0], y + shift_mm[1]) for x, y in s.points], s.kind) for s in page.strokes])
    jpg = render_image.render_jpeg(shifted, ink_hex=ink, stroke_width_mm=0.6)
    sheet = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    sheet = np.rot90(sheet, rot90).copy()
    h, w = sheet.shape[:2]
    W, H = size
    canvas = np.full((H, W, 3), (38, 42, 46), np.uint8)
    scale = 0.8 * min(W / w, H / h)
    sw, sh = w * scale, h * scale
    x0, y0 = (W - sw) / 2, (H - sh) / 2
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[x0 + 40 * skew, y0 + 20], [x0 + sw - 10, y0 - 30 * skew], [x0 + sw + 30 * skew, y0 + sh - 20], [x0 - 20, y0 + sh + 40 * skew]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(sheet, M, (W, H), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (W, H))
    canvas[mask > 0] = warped[mask > 0]
    gx = np.linspace(0.75, 1.1, W, dtype=np.float32)[None, :, None]                      # uneven lighting
    rng = np.random.default_rng(seed)
    out = np.clip(canvas.astype(np.float32) * gx + rng.normal(0, noise, canvas.shape), 0, 255).astype(np.uint8)
    return cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def test_a_faithful_photo_passes_with_small_mm_errors_whatever_the_orientation():
    for rot in (0, 1, 2, 3):
        r = qe.evaluate(photo(PAGE, rot90=rot), PAGE, stroke_width_mm=0.6)
        m = r.metrics
        assert r.code == "PASS", (rot, m)
        assert m["coverage_pct"] >= 90 and m["chamfer_mm"] <= 1.0 and m["extra_ink_pct"] <= 10 and m["sheet_found"] == "quad"
        assert r.overlay_jpeg[:3] == bytes([0xFF, 0xD8, 0xFF])


def test_a_shifted_writing_is_aligned_and_the_shift_is_reported():
    r = qe.evaluate(photo(PAGE, shift_mm=(3.0, -2.0)), PAGE, stroke_width_mm=0.6)
    a = r.metrics["alignment"]
    assert a is not None and abs(abs(a["dx_mm"]) - 3.0) < 1.2 and abs(abs(a["dy_mm"]) - 2.0) < 1.2     # reported, never hidden
    assert r.metrics["coverage_pct"] >= 80


def test_missing_strokes_lower_coverage_and_the_overlay_marks_them():
    half = Page(PAGE.paper_size, PAGE.strokes[: len(PAGE.strokes) // 2])
    good = qe.evaluate(photo(PAGE), PAGE, stroke_width_mm=0.6)
    bad = qe.evaluate(photo(half), PAGE, stroke_width_mm=0.6)
    assert bad.metrics["coverage_pct"] < good.metrics["coverage_pct"] - 25
    assert bad.code in ("FAIL", "NEEDS_REVIEW") and bad.code != "PASS"
    assert bad.metrics["hausdorff_mm"] > 5.0


def test_extra_ink_is_detected():
    blot = Page(PAGE.paper_size, [*PAGE.strokes, Stroke([(20.0, 150.0), (120.0, 190.0), (30.0, 195.0), (110.0, 160.0)])])
    r = qe.evaluate(photo(blot), PAGE, stroke_width_mm=0.6)
    assert r.metrics["extra_ink_pct"] > 8 and r.metrics["hausdorff_mm"] > 8


def test_a_photo_without_a_sheet_is_refused_not_guessed():
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 255, (900, 1200, 3), dtype=np.uint8)
    with pytest.raises(AppError) as e:
        qe.evaluate(cv2.imencode(".jpg", noise)[1].tobytes(), PAGE)
    assert e.value.code == "PAPER_NOT_FOUND"
    with pytest.raises(AppError) as e2:
        qe.evaluate(b"not an image", PAGE)
    assert e2.value.code == "PHOTO_UNREADABLE"


def test_a_blank_sheet_and_the_wrong_text_are_not_a_match():
    blank = Page(PAGE.paper_size, [])
    with pytest.raises(AppError) as e:
        qe.evaluate(photo(blank), PAGE, stroke_width_mm=0.6)
    assert e.value.code in ("NO_INK", "NO_MATCH")
    other = tts.compose_text("Hà Nội mùa thu", font_name="futural", paper_size="A5", font_size_mm=9.0, seed=2)[0]
    r = qe.evaluate(photo(other), PAGE, stroke_width_mm=0.6)
    assert r.code != "PASS"


def test_the_result_states_its_limits():
    d = qe.evaluate(photo(PAGE), PAGE, stroke_width_mm=0.6).as_dict()
    assert d["thresholds"]["source"] == "DEFAULT_UNCALIBRATED" and d["scale_check"].startswith("NOT_CALIBRATED") and d["method"] == "service-g/1"


# ---------------------------------------------------------------- the API
def test_api_evaluates_a_job_photo_and_keeps_the_result(client, cust, staff, mgr, wcat, robot, tech, store):
    import json

    from tests.test_api_orders import _sql
    from tests.test_api_orders import API
    from tests.test_api_photos_acceptance import T, _add, _err, _written
    M = f"{API}/manager"
    oid, jid = _written(client, cust, staff, mgr, wcat, robot, tech)
    path = _sql("select package_uri from production_jobs where id=:j", j=jid)
    page = tts_pages(store.objects[path])[0]
    ph, _ = _add(client, tech, store, jid, "OVERALL", data=photo(page, rot90=1))
    r = client.post(f"{T}/jobs/{jid}/photos/{ph['id']}/evaluate", headers=tech[0], json={})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["verdict"] == "PASS" and d["metrics"]["coverage_pct"] >= 90 and d["overlay_url"] and "Chỉ để tham khảo" in d["advisory"]
    assert d["metrics"]["thresholds"]["source"] == "DEFAULT_UNCALIBRATED" and d["page"] == 1
    assert _sql("select overlay_url is not null from product_photos where id=:p", p=ph["id"])
    assert _sql("select count(*) from quality_evaluations where photo_id=:p", p=ph["id"]) == 1
    assert _sql("select count(*) from audit_logs where action='QUALITY_EVALUATE' and entity_id=:j", j=jid) == 1
    assert [x["id"] for x in client.get(f"{T}/jobs/{jid}/quality", headers=tech[0]).json()] == [d["id"]]
    assert client.get(f"{M}/jobs/{jid}/quality", headers=mgr[0] if isinstance(mgr, tuple) else mgr).status_code == 200
    # honest failures leave nothing behind
    blank, _ = _add(client, tech, store, jid, "CLOSE_UP", data=cv2.imencode(".jpg", np.full((1400, 1000, 3), 120, np.uint8))[1].tobytes())
    bad = client.post(f"{T}/jobs/{jid}/photos/{blank['id']}/evaluate", headers=tech[0], json={})
    assert bad.status_code == 422 and _err(bad) == "PAPER_NOT_FOUND"
    assert _sql("select count(*) from quality_evaluations where job_id=:j", j=jid) == 1
    assert _err(client.post(f"{T}/jobs/{jid}/photos/{ph['id']}/evaluate", headers=tech[0], json={"page": 3})) == "PAGE_OUT_OF_RANGE"
    assert client.post(f"{T}/jobs/{jid}/photos/99999999/evaluate", headers=tech[0], json={}).status_code == 404
    other = _user_tech(client)
    assert client.post(f"{T}/jobs/{jid}/photos/{ph['id']}/evaluate", headers=other[0], json={}).status_code == 404   # BR-19


def tts_pages(raw: bytes):
    import json

    from app.services.stroke_ai import trajectory as tj
    return tj.parse(json.loads(raw))


def _user_tech(client):
    from tests.test_api_workshop import _user
    return _user(client, "TECHNICAL_STAFF")
