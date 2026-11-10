"""NFR-01 (Report 3, SRS): price estimate <= 1 s; OT-3 sketch of one A4 page <= 5 s; OT-1 restoration of an A5 image <= 15 s;
job package <= 10 s.

Two layers:

* Always run (no network, a few seconds): the COMPUTE part of each requirement, i.e. the work the server does itself, on
  inputs at the size the SRS names. These are the numbers a slow CPU (Render's small instance) would break.
* Opt-in (`RUN_PERF=1`): estimate, OT-3 sketch and OT-1 restoration through the API, end to end, so the time includes
  the database and storage round trips. Run them against the database you want to measure (local Postgres ~ the server's
  own time; Supabase from a laptop adds the Internet round trips, which Render in the same region would not pay). The job
  package is only measured in its compute part: end to end it needs a scheduled job on a robot.

Timings use the best of a few runs (`perf_counter`), so a single hiccup of a shared machine does not fail the build; every
measurement is printed (`pytest -s`) to be copied into PROJECT_STATUS.
"""
import os
import time

import cv2
import numpy as np
import pytest

from app.services.stroke_ai import engine, trajectory as tj
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401  (fixtures for the opt-in API tests)

LIMITS = {"estimate": 1.0, "sketch_ot3_a4": 5.0, "restore_ot1_a5": 15.0, "package": 10.0}
perf_api = pytest.mark.skipif(os.environ.get("RUN_PERF") != "1", reason="end-to-end NFR-01 timing: set RUN_PERF=1")

# About one A4 page of handwriting at the default 8 mm letters (the text fills the page; extra lines go to page 2).
A4_TEXT = ("Kính gửi quý khách hàng thân mến, xưởng Nét Việt xin chân thành cảm ơn sự tin tưởng của quý vị. "
           "Chúc quý khách một năm mới an khang, thịnh vượng, vạn sự như ý và luôn tràn đầy niềm vui. ") * 4


def _best(fn, runs: int = 3) -> tuple[float, object]:
    best, out = float("inf"), None
    for _ in range(runs):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    return best, out


def _report(name: str, seconds: float) -> None:
    print(f"\nNFR-01 {name}: {seconds:.3f} s (limit {LIMITS[name]:.0f} s)")


def _a5_scan() -> bytes:
    """A5 page scanned at 300 dpi (1748 x 2480 px), filled with lines of cursive-like writing: the largest original the
    customer is expected to send for OT-1."""
    img = np.full((2480, 1748), 242, np.uint8)
    words = ("Net Viet Nam", "xuong viet tay", "chuc mung nam moi", "an khang thinh vuong", "van su nhu y")
    for i in range(16):
        cv2.putText(img, words[i % len(words)], (90, 200 + i * 140), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 2.4, 25, 5,
                    cv2.LINE_AA)
    return cv2.imencode(".png", img)[1].tobytes()


def _ot3_a4():
    g = engine.generate_ot3(A4_TEXT, None, font_uri="hershey:scripts", font_size_mm=8, alignment="LEFT", paper_size="A4",
                            seed=1, v_max_mm_s=30, pen_category="GEL", chars=len(A4_TEXT))
    raw = tj.dumps(tj.to_dict(g.pages, g.engine))
    previews = [tj.render_preview(p) for p in g.pages]
    return g, raw, previews


# ---- compute part: always run --------------------------------------------------------------------------------------------
def test_ot3_sketch_of_a_full_a4_page_is_within_5_seconds():
    seconds, (g, raw, previews) = _best(_ot3_a4)
    _report("sketch_ot3_a4", seconds)
    assert g.pages and len(g.pages[0].strokes) > 200 and previews[0][:4] == b"\x89PNG"     # really a full page of writing
    assert seconds <= LIMITS["sketch_ot3_a4"]


def test_ot1_restoration_of_an_a5_scan_is_within_15_seconds():
    scan = _a5_scan()

    def run():
        g = engine.generate_ot1([engine.ImageSource(scan)], paper_size="A5", v_max_mm_s=30, pen_category="GEL", chars=200)
        return g, tj.dumps(tj.to_dict(g.pages, g.engine)), tj.render_preview(g.pages[0])
    seconds, (g, _, _) = _best(run, runs=2)
    _report("restore_ot1_a5", seconds)
    assert len(g.pages[0].strokes) > 50
    assert seconds <= LIMITS["restore_ot1_a5"]


def test_a_job_package_of_the_largest_sketch_is_checked_within_10_seconds():
    """What the package step does with the stored file: hash it (FR-38), parse and validate every page. Ten A4 pages
    (the most a sketch may have) of dense writing."""
    g, _, _ = _ot3_a4()
    pages = (g.pages * tj.MAX_PAGES)[:tj.MAX_PAGES]
    raw = tj.dumps(tj.to_dict(pages, g.engine))

    def run():
        import json
        h = tj.content_hash(raw)
        return h, tj.parse(json.loads(raw))
    seconds, (h, parsed) = _best(run)
    _report("package", seconds)
    assert len(h) == 64 and len(parsed) == tj.MAX_PAGES
    assert seconds <= LIMITS["package"]


# ---- end to end through the API: opt-in ----------------------------------------------------------------------------------
@perf_api
def test_api_price_estimate_is_within_1_second(client):
    from tests.conftest import auth
    cust = auth(client, "CUSTOMER")
    body = {"order_type": "OT3_TEMPLATE", "quantity": 20, "text": A4_TEXT}
    assert client.post("/api/v1/pricing/estimate", headers=cust, json=body).status_code == 200          # warm up
    seconds, r = _best(lambda: client.post("/api/v1/pricing/estimate", headers=cust, json=body))
    _report("estimate", seconds)
    assert r.status_code == 200, r.text
    assert seconds <= LIMITS["estimate"]


@perf_api
def test_api_ot3_sketch_generation_of_an_a4_page_is_within_5_seconds(client, cust, staff, wcat):
    from tests.test_api_workshop import W, _accepted
    oid = _accepted(client, cust, staff[0], wcat, text_=A4_TEXT)
    seconds, r = _best(lambda: client.post(f"{W}/orders/{oid}/sketches/generate", headers=staff[0], json={}), runs=2)
    _report("sketch_ot3_a4", seconds)
    assert r.status_code == 201, r.text
    assert seconds <= LIMITS["sketch_ot3_a4"]


@perf_api
def test_api_ot1_restoration_of_an_a5_scan_is_within_15_seconds(client, store, staff, wcat):
    from tests.conftest import auth
    from tests.test_api_orders import API, _upload
    from tests.test_api_workshop import W
    cust = auth(client, "CUSTOMER")
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE", "quantity": 1}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    _upload(client, cust, oid, store, _a5_scan())
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=staff[0], json={}).status_code == 200
    seconds, r = _best(lambda: client.post(f"{W}/orders/{oid}/sketches/generate", headers=staff[0], json={}), runs=1)
    _report("restore_ot1_a5", seconds)
    assert r.status_code == 201, r.text
    assert seconds <= LIMITS["restore_ot1_a5"]
