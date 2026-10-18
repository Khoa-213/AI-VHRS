"""Phase 4a, the workshop floor: the Technical Staff's jobs (UC-31..39, FR-43..49, BR-17, BR-19, BR-20).

Real database, real DB triggers, the in-memory storage double. Every test gets its own 'pytest_' robot and technician,
so the workshop's real robot and people are never touched. Nothing here talks to a robot: the workstation's reports
(simulation result, progress, safety stops) are posted by the test the way the Flutter app / Robot Agent would.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.api.v1.orders import optional_storage
from app.main import app
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid
from tests.test_api_scheduling import _at, _prod, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401

T = f"{API}/technician"
M = f"{API}/manager"
POINTS = [{"x": 0, "y": 0, "z": 10.0}, {"x": 100, "y": 0, "z": 10.1}, {"x": 0, "y": 100, "z": 10.2}]
CHECKLIST = {"frame_mounted": True, "paper_clamped": True, "pen_installed": True, "force_zeroed": True}
CAL = {"checklist": CHECKLIST, "force_zero_offset": 0.02, "probe_points": POINTS}
SUMMARY = {"f_mean": 0.61, "f_max": 0.98, "rms_err_pct": 4.5, "in_band_pct": 97.2, "samples": 5000}


# ---- helpers ----------------------------------------------------------------------------------------
def _job(client, cust, staff, mgr, wcat, robot, tech, **kw):
    """A paid order scheduled for `tech` on `robot`. Returns (order id, job id)."""
    oid, _, _ = _paid(client, cust, staff[0], wcat, **kw)
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 201, r.text
    return oid, r.json()["id"]


def _post(client, tech, jid, path, body=None, status=None):
    r = client.post(f"{T}/jobs/{jid}/{path}", headers=tech[0], json=body)
    if status is not None:
        assert r.status_code == status, (path, r.status_code, r.text)
    return r


def _ready(client, cust, staff, mgr, wcat, robot, tech, **kw):
    """Downloaded, preparing, calibrated and simulated (passed): one call from START."""
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, **kw)
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _post(client, tech, jid, "prepare", status=200)
    _post(client, tech, jid, "calibration", CAL, status=201)
    _post(client, tech, jid, "simulation", {"passed": True}, status=200)
    return oid, jid


def _running(client, cust, staff, mgr, wcat, robot, tech, **kw):
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech, **kw)
    _post(client, tech, jid, "start", status=200)
    return oid, jid


def _status(jid):
    return _sql("select status::text from production_jobs where id=:j", j=jid)


def _event_types(client, h, jid, base=T):
    items = client.get(f"{base}/jobs/{jid}/events", headers=h, params={"page_size": 500}).json()["items"]
    return [e["event_type"] for e in items]


# ---- access: BR-19 -----------------------------------------------------------------------------------
def test_only_the_assigned_technician_can_see_or_touch_a_job(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=2)
    other = _user(client, "TECHNICAL_STAFF")
    calls = [("get", f"/jobs/{jid}", None), ("get", f"/jobs/{jid}/package", None), ("post", f"/jobs/{jid}/prepare", None),
             ("post", f"/jobs/{jid}/calibration", CAL), ("post", f"/jobs/{jid}/simulation", {"passed": True}),
             ("post", f"/jobs/{jid}/start", None), ("post", f"/jobs/{jid}/events", {"event_type": "PROGRESS", "progress_pct": 5}),
             ("get", f"/jobs/{jid}/events", None), ("post", f"/jobs/{jid}/finish", None),
             ("post", f"/jobs/{jid}/incidents", {"type": "ROBOT", "description": "x"})]
    for method, path, body in calls:                                  # someone else's job is simply not found
        r = client.request(method.upper(), f"{T}{path}", headers=other[0], json=body)
        assert r.status_code == 404 and _err(r) == "JOB_NOT_FOUND", path
    assert client.get(f"{T}/jobs", headers=other[0]).json()["total"] == 0
    assert client.get(f"{T}/jobs/999999999", headers=tech[0]).status_code == 404
    assert _status(jid) == "SCHEDULED" and _prod(oid) == "SCHEDULED"      # none of that changed anything

    mine = client.get(f"{T}/jobs", headers=tech[0]).json()
    assert [j["id"] for j in mine["items"]] == [jid] and mine["items"][0]["order_code"] and mine["total"] == 1
    assert client.get(f"{T}/jobs", headers=tech[0], params={"status": "SCHEDULED"}).json()["total"] == 1
    assert client.get(f"{T}/jobs", headers=tech[0], params={"status": "DONE"}).json()["total"] == 0
    assert client.get(f"{T}/jobs", headers=tech[0], params={"from": "2999-01-01T00:00:00+00:00"}).json()["total"] == 0

    d = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()
    assert d["status"] == "SCHEDULED" and d["can_start"] is False and d["calibration"] is None and d["incidents"] == []
    assert d["quantity"] == 2 and d["paper_name"] == "Giay test A5" and d["pen_name"] == "But gel test" and d["ink_name"] == "Den"
    assert d["order_type"] == "OT3_TEMPLATE" and d["simulation_passed"] is None and d["downloaded_at"] is None
    assert not {"customer_id", "customer_name", "customer_note", "delivery_address"} & set(d)   # no customer data on the floor
    # the Manager's scheduling step already packaged the job (FR-38)
    assert _sql("""select package_uri is not null and packaged_at is not null and package_hash is not null
                   from production_jobs where id=:j""", j=jid)


# ---- UC-32: the package and its hash ----------------------------------------------------------------
def test_package_download_verifies_the_hash(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    uri = _sql("select package_uri from production_jobs where id=:j", j=jid)
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    assert r.status_code == 200, r.text
    pkg = r.json()
    assert pkg["package_hash"] == hashlib.sha256(store.objects[uri]).hexdigest() == _sql(
        "select package_hash from production_jobs where id=:j", j=jid)
    assert pkg["hash_algorithm"] == "SHA-256" and pkg["trajectory_url"].endswith(uri) and pkg["pages"] >= 1
    assert pkg["trajectory_format"] == "vhrs-trajectory/1" and pkg["trajectory_url_expires_in"] > 0
    assert pkg["preview_url"] and pkg["order_code"] and pkg["is_rewrite"] is False
    assert pkg["paper"] == {"name": "Giay test A5", "gsm": 120, "surface": "ART", "size": "A5"}
    assert pkg["pen"]["category"] == "GEL" and pkg["pen"]["f_hard_n"] == 3.0 and pkg["pen"]["v_max_mm_s"] == 30.0   # BR-20
    assert (pkg["pen"]["f_min_n"], pkg["pen"]["f_target_n"], pkg["pen"]["f_max_n"]) == (0.3, 0.6, 1.0)
    assert pkg["ink_name"] == "Den" and pkg["ink_hex"] == "#000000"
    assert _sql("select downloaded_at is not null from production_jobs where id=:j", j=jid)
    assert _event_types(client, tech[0], jid) == ["DOWNLOADED"]

    good = store.objects[uri]
    store.objects[uri] = good + b" "                                        # the stored file no longer matches the hash
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    assert r.status_code == 409 and _err(r) == "JOB_HASH_MISMATCH"          # MSG14
    assert _event_types(client, tech[0], jid) == ["DOWNLOADED", "HASH_MISMATCH"]      # kept although the request failed
    assert _sql("select count(*) from audit_logs where action='JOB_HASH_MISMATCH' and entity_id=:j", j=jid) == 1
    store.objects.pop(uri)
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    assert r.status_code == 409 and _err(r) == "FILE_MISSING"
    store.objects[uri] = good
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200

    app.dependency_overrides[optional_storage] = lambda: None
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    assert r.status_code == 503 and _err(r) == "STORAGE_NOT_CONFIGURED"
    app.dependency_overrides[optional_storage] = lambda: store
    # the job can no longer be changed through the order once the approved sketch differs from the package hash
    _sql("update production_jobs set package_hash=:h where id=:j returning 1", h="0" * 64, j=jid)
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    assert r.status_code == 409 and _err(r) == "JOB_HASH_MISMATCH"


# ---- the whole floor flow ---------------------------------------------------------------------------
def test_job_lifecycle_from_download_to_written(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=3)
    paper0, pen0, ink0 = (_sql(f"select stock_qty from {t} where id=:i", i=i) for t, i in (
        ("paper_types", wcat["paper"]), ("pen_types", wcat["gel"]), ("ink_colors", wcat["gel_ink"])))

    # nothing can start before the package is downloaded and the job prepared
    assert _err(_post(client, tech, jid, "prepare", status=409)) == "JOB_NOT_DOWNLOADED"
    for path, body in (("calibration", CAL), ("simulation", {"passed": True}), ("start", None)):
        assert _err(_post(client, tech, jid, path, body, status=409)) == "JOB_STATE_CONFLICT", path
    pkg = client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).json()

    r = _post(client, tech, jid, "prepare", status=200)
    assert r.json()["status"] == "PREPARING" and _prod(oid) == "PREPARING"
    assert _err(_post(client, tech, jid, "prepare", status=409)) == "JOB_STATE_CONFLICT"      # not twice

    # BR-19: no run without a calibration; FR-45: none without a passed simulation
    assert _err(_post(client, tech, jid, "start", status=409)) == "CALIBRATION_REQUIRED"
    assert _err(_post(client, tech, jid, "simulation", {"passed": True}, status=409)) == "CALIBRATION_REQUIRED"
    bad = [({**CAL, "checklist": {**CHECKLIST, "paper_clamped": False}}, "CHECKLIST_INCOMPLETE"),
           ({**CAL, "probe_points": POINTS[:2]}, "INVALID_PROBE_POINTS"),
           ({**CAL, "probe_points": [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 1}, {"x": 2, "y": 2, "z": 2}]}, "INVALID_PROBE_POINTS")]
    for body, code in bad:
        r = _post(client, tech, jid, "calibration", body, status=422)
        assert _err(r) == code
    for body in ({**CAL, "force_zero_offset": 5000}, {**CAL, "probe_points": "x"}, {"checklist": CHECKLIST}):
        assert _err(_post(client, tech, jid, "calibration", body, status=422)) == "VALIDATION_ERROR"
    assert _sql("select count(*) from calibrations where job_id=:j", j=jid) == 0

    cal1 = _post(client, tech, jid, "calibration", {**CAL, "height_map": {"grid": [[0, 0.1]]}}, status=201).json()
    assert cal1["is_valid"] is True and cal1["robot_id"] == robot and cal1["technician_id"] == tech[1]
    assert cal1["probe_points"] == POINTS and cal1["force_zero_offset"] == 0.02 and cal1["height_map"] == {"grid": [[0, 0.1]]}
    assert _sql("select paper_type_id from calibrations where id=:c", c=cal1["id"]) == wcat["paper"]
    assert _err(_post(client, tech, jid, "start", status=409)) == "SIMULATION_REQUIRED"
    r = _post(client, tech, jid, "simulation", {"passed": True, "errors": ["singularity"]}, status=422)
    assert _err(r) == "SIMULATION_INCONSISTENT"
    r = _post(client, tech, jid, "simulation", {"passed": False, "errors": ["Tầm với vượt 0,9 x 622 mm"],
                                                "report": {"max_reach_mm": 640}}, status=200)
    assert r.json()["simulation_passed"] is False
    assert _err(_post(client, tech, jid, "start", status=409)) == "SIMULATION_FAILED"           # blocked while errors remain

    cal2 = _post(client, tech, jid, "calibration", CAL, status=201).json()                      # re-calibrate: new plane
    assert cal2["id"] != cal1["id"]
    assert [x[0] for x in [(_sql("select is_valid from calibrations where id=:c", c=c["id"]),) for c in (cal1, cal2)]] == [False, True]
    d = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()
    assert d["simulation_passed"] is None and d["can_start"] is False and d["calibration"]["id"] == cal2["id"]
    assert _err(_post(client, tech, jid, "start", status=409)) == "SIMULATION_REQUIRED"         # old simulation is void
    _post(client, tech, jid, "simulation", {"passed": True, "report": {"est_min": 12}}, status=200)
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["can_start"] is True
    assert _sql("select simulation_report->'report'->>'est_min' from production_jobs where id=:j", j=jid) == "12"

    r = _post(client, tech, jid, "start", status=200)
    assert r.json()["status"] == "WRITING" and r.json()["started_at"] and _prod(oid) == "WRITING"
    # DB backstop: the constraint chk_job_run_requires_sim is satisfied because the simulation passed
    assert _sql("select simulation_passed from production_jobs where id=:j", j=jid) is True

    def ev(kind, expect=201, **kw):
        r = _post(client, tech, jid, "events", {"event_type": kind, **kw}, status=expect)
        return r

    for body, code in (({"event_type": "START"}, "EVENT_NOT_ALLOWED"), ({"event_type": "WRITTEN"}, "EVENT_NOT_ALLOWED"),
                       ({"event_type": "INCIDENT"}, "EVENT_NOT_ALLOWED"), ({"event_type": "PROGRESS"}, "PROGRESS_REQUIRED"),
                       ({"event_type": "PROGRESS", "progress_pct": 101}, "VALIDATION_ERROR"),
                       ({"event_type": "NOPE"}, "VALIDATION_ERROR"), ({"event_type": "FORCE_SUMMARY"}, "INVALID_FORCE_SUMMARY"),
                       ({"event_type": "FORCE_SUMMARY", "force_summary": {"in_band_pct": 150}}, "INVALID_FORCE_SUMMARY")):
        assert _err(_post(client, tech, jid, "events", body, status=422)) == code, body
    assert _err(ev("RESUME", 409)) == "JOB_STATE_CONFLICT"                                      # not paused

    ev("PROGRESS", stroke_index=3, progress_pct=10)
    ev("PROGRESS", progress_pct=5)                                                               # late message: never goes back
    assert float(_sql("select progress_pct from production_jobs where id=:j", j=jid)) == 10.0
    e = ev("PROGRESS", stroke_index=40, progress_pct=40.5).json()
    assert e["event_type"] == "PROGRESS" and e["stroke_index"] == 40 and e["actor_id"] == tech[1]

    ev("PAUSE")
    assert _status(jid) == "PAUSED" and _prod(oid) == "PAUSED"
    assert _err(ev("PROGRESS", 409, progress_pct=50)) == "JOB_STATE_CONFLICT"                    # nothing is being written
    ev("RESUME")
    assert _status(jid) == "WRITING" and _prod(oid) == "WRITING"
    ev("OVER_FORCE", payload={"f": 3.4})                                                         # arm lifted the pen (NFR-03)
    assert _status(jid) == "PAUSED" and _prod(oid) == "PAUSED"
    ev("ESTOP")                                                                                  # a second stop is logged only
    assert _status(jid) == "PAUSED"
    ev("RESUME")
    ev("SENSOR_LOST")
    assert _status(jid) == "PAUSED"
    ev("RESUME")
    assert _sql("select count(*) from audit_logs where action in ('JOB_OVER_FORCE','JOB_ESTOP') and entity_id=:j", j=jid) == 2
    ev("FORCE_SUMMARY", force_summary=SUMMARY)
    assert _sql("select force_summary->>'in_band_pct' from job_events where job_id=:j and event_type='FORCE_SUMMARY'", j=jid) == "97.2"
    assert _err(_post(client, tech, jid, "start", status=409)) == "JOB_STATE_CONFLICT"            # already writing

    r = _post(client, tech, jid, "finish", status=200)
    assert r.json()["status"] == "WRITTEN" and float(r.json()["progress_pct"]) == 100.0 and r.json()["finished_at"]
    assert _status(jid) == "WRITTEN" and _prod(oid) == "WRITTEN"
    assert _sql("select order_status::text from orders where id=:o", o=oid) == "CONFIRMED"
    # FR-41: stock is deducted when writing is done (3 copies x sheets per copy; 1 pen; 1 ink)
    paper1, pen1, ink1 = (_sql(f"select stock_qty from {t} where id=:i", i=i) for t, i in (
        ("paper_types", wcat["paper"]), ("pen_types", wcat["gel"]), ("ink_colors", wcat["gel_ink"])))
    assert (paper0 - paper1, pen0 - pen1, ink0 - ink1) == (3 * pkg["pages"], 1, 1)
    written = _sql("select payload->'stock'->'paper'->>'used' from job_events where job_id=:j and event_type='WRITTEN'", j=jid)
    assert written == str(3 * pkg["pages"])

    # after WRITTEN the job is closed to everything but a closing force summary
    assert _err(ev("PROGRESS", 409, progress_pct=99)) == "JOB_STATE_CONFLICT"
    ev("FORCE_SUMMARY", force_summary=SUMMARY)
    for path in ("finish", "start", "prepare"):
        assert _err(_post(client, tech, jid, path, status=409)) == "JOB_NOT_ACTIVE", path
    assert _err(_post(client, tech, jid, "incidents", {"type": "ROBOT", "description": "x"}, status=409)) == "JOB_NOT_ACTIVE"
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 409

    # BR-24 / FR-25: every production transition is on record with the technician as the actor
    chain = _sql("""select string_agg(from_status || '>' || to_status, ',' order by id) from status_histories
                    where order_id=:o and state_type='PRODUCTION' and actor_id=:t""", o=oid, t=tech[1])
    assert chain == ("SCHEDULED>PREPARING,PREPARING>WRITING,WRITING>PAUSED,PAUSED>WRITING,WRITING>PAUSED,PAUSED>WRITING,"
                     "WRITING>PAUSED,PAUSED>WRITING,WRITING>WRITTEN")
    types = _event_types(client, tech[0], jid)
    assert types[0] == "DOWNLOADED" and types.count("CALIBRATED") == 2 and types.count("SIMULATED") == 2
    assert types.count("START") == 1 and types.count("WRITTEN") == 1 and types.count("FORCE_SUMMARY") == 2
    # the Manager sees the same job and the same timeline, read-only
    mj = client.get(f"{M}/jobs/{jid}", headers=mgr).json()
    assert mj["status"] == "WRITTEN" and mj["progress_pct"] == 100.0 and mj["downloaded_at"] and mj["simulation_passed"] is True
    assert _event_types(client, mgr, jid, M) == types
    assert client.get(f"{M}/jobs/999999999/events", headers=mgr).status_code == 404


# ---- stock, concurrency -----------------------------------------------------------------------------
def test_finish_is_idempotent_under_concurrency_and_never_blocked_by_stale_stock(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=3)
    pages = _sql("select (payload->>'pages')::int from job_events where job_id=:j and event_type='DOWNLOADED'", j=jid)
    need = 3 * pages
    _sql("update paper_types set stock_qty=:n where id=:i returning 1", n=need - 1, i=wcat["paper"])   # count is 1 sheet short
    pen0 = _sql("select stock_qty from pen_types where id=:i", i=wcat["gel"])

    def finish(_):
        with TestClient(app) as c:
            return c.post(f"{T}/jobs/{jid}/finish", headers=tech[0]).status_code

    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(finish, range(2)))
    assert codes == [200, 409], codes                                                            # exactly one wins
    assert _status(jid) == "WRITTEN" and _prod(oid) == "WRITTEN"
    assert _sql("select stock_qty from paper_types where id=:i", i=wcat["paper"]) == 0           # floor at 0, no violation
    assert pen0 - _sql("select stock_qty from pen_types where id=:i", i=wcat["gel"]) == 1         # deducted once, not twice
    assert _sql("select count(*) from job_events where job_id=:j and event_type='WRITTEN'", j=jid) == 1
    assert int(_sql("select payload->'stock'->'paper'->>'shortfall' from job_events where job_id=:j and event_type='WRITTEN'",
                    j=jid)) == 1                                                                 # the gap is reported, not hidden


# ---- UC-37: incidents -------------------------------------------------------------------------------
def test_incident_stops_the_job_and_returns_the_order_to_the_manager(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    for body in ({"type": "ROBOT"}, {"type": "ROBOT", "description": "   "}, {"type": "BOOM", "description": "x"},
                 {"type": "ROBOT", "description": "x", "robot_status_after": "AVAILABLE"}):
        assert _post(client, tech, jid, "incidents", body).status_code == 422, body
    assert _status(jid) == "WRITING"

    r = _post(client, tech, jid, "incidents", {"type": "ROBOT", "description": "Servo khớp 3 báo lỗi",
                                               "robot_status_after": "MAINTENANCE"}, status=201)
    inc = r.json()
    assert inc["job_id"] == jid and inc["robot_id"] == robot and inc["reported_by"] == tech[1]
    assert inc["type"] == "ROBOT" and inc["robot_status_after"] == "MAINTENANCE" and inc["resolved_at"] is None
    assert _status(jid) == "FAILED" and _prod(oid) == "FAILED"                                    # FR-48
    assert _sql("select status::text from robots where id=:r", r=robot) == "MAINTENANCE"
    assert _sql("select order_status::text from orders where id=:o", o=oid) == "CONFIRMED"
    assert "INCIDENT" in _event_types(client, tech[0], jid)
    assert _sql("select incident_id from job_events where job_id=:j and event_type='INCIDENT'", j=jid) == inc["id"]
    assert _sql("select count(*) from audit_logs where action='INCIDENT_REPORT' and entity_id=:i", i=inc["id"]) == 1
    assert _sql("""select count(*) from status_histories where order_id=:o and to_status='FAILED' and actor_id=:t
                   and reason like 'Sự cố:%'""", o=oid, t=tech[1]) == 1
    d = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()
    assert [i["id"] for i in d["incidents"]] == [inc["id"]] and d["status"] == "FAILED" and d["finished_at"]
    for path, body in (("incidents", {"type": "ROBOT", "description": "x"}), ("start", None), ("finish", None)):
        assert _err(_post(client, tech, jid, path, body, status=409)) == "JOB_NOT_ACTIVE"          # a failed job is closed

    # the Manager sees it, and the order is waiting in the scheduling queue again
    listed = client.get(f"{M}/incidents", headers=mgr, params={"resolved": False, "robot_id": robot}).json()
    assert [i["id"] for i in listed["items"]] == [inc["id"]] and listed["total"] == 1
    assert client.get(f"{M}/incidents", headers=mgr, params={"resolved": True, "robot_id": robot}).json()["total"] == 0
    mine, page = [], 1
    while not mine:                                          # the shared DB may hold more than one page of waiting orders
        d = client.get(f"{M}/schedule/queue", headers=mgr, params={"page": page, "page_size": 100}).json()
        mine = [q for q in d["items"] if q["order_id"] == oid]
        if not d["items"] or page * 100 >= d["total"]:
            break
        page += 1
    assert len(mine) == 1 and mine[0]["production_status"] == "FAILED"
    assert _sched(client, mgr, oid, robot, tech[1], _at(2, 9)).status_code == 409                 # robot is in maintenance
    assert _event_types(client, mgr, jid, M)[-1] == "INCIDENT"

    resolved = client.post(f"{M}/incidents/{inc['id']}/resolve", headers=mgr, json={"note": "Đã thay servo"})
    assert resolved.status_code == 200 and resolved.json()["resolved_at"] and resolved.json()["resolution_note"] == "Đã thay servo"
    again = client.post(f"{M}/incidents/{inc['id']}/resolve", headers=mgr, json={"note": "x"})
    assert again.status_code == 409 and _err(again) == "INCIDENT_ALREADY_RESOLVED"
    assert client.post(f"{M}/incidents/999999999/resolve", headers=mgr, json={"note": "x"}).status_code == 404
    assert client.post(f"{M}/incidents/{inc['id']}/resolve", headers=mgr, json={}).status_code == 422
    assert client.get(f"{M}/incidents", headers=mgr, params={"resolved": False, "robot_id": robot}).json()["total"] == 0

    # robot repaired: the order is planned again on a new job, the old one stays as history
    _sql("update robots set status='AVAILABLE' where id=:r returning 1", r=robot)
    r = _sched(client, mgr, oid, robot, tech[1], _at(2, 9))
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["id"] != jid and new["status"] == "SCHEDULED" and new["is_rewrite"] is False and _prod(oid) == "SCHEDULED"
    assert _status(jid) == "FAILED"
    assert client.get(f"{T}/jobs/{new['id']}/package", headers=tech[0]).status_code == 200


def test_incident_needs_a_started_job(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    r = _post(client, tech, jid, "incidents", {"type": "MATERIAL", "description": "Hết giấy"}, status=409)
    assert _err(r) == "JOB_STATE_CONFLICT"
    assert _status(jid) == "SCHEDULED" and _prod(oid) == "SCHEDULED"
    assert _sql("select count(*) from incidents where job_id=:j", j=jid) == 0


# ---- guards from outside the job ------------------------------------------------------------------------
def test_robot_out_of_service_or_cancelled_order_stops_the_technician(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _sql("update robots set status='MAINTENANCE' where id=:r returning 1", r=robot)                # Manager took it out meanwhile
    r = _post(client, tech, jid, "prepare", status=409)
    assert _err(r) == "ROBOT_UNAVAILABLE" and _status(jid) == "SCHEDULED" and _prod(oid) == "SCHEDULED"
    _sql("update robots set status='AVAILABLE' where id=:r returning 1", r=robot)

    _sql("update orders set order_status='CANCELLED', cancel_reason='test' where id=:o returning 1", o=oid)   # BR-17
    for method, path in (("post", "prepare"), ("get", "package")):
        r = client.request(method.upper(), f"{T}/jobs/{jid}/{path}", headers=tech[0])
        assert r.status_code == 409 and _err(r) == "ORDER_NOT_ACTIVE", path
    assert _status(jid) == "SCHEDULED"


def test_technician_endpoints_need_login_and_the_technician_role(client, cust):
    for role in (None, "CUSTOMER", "STAFF", "MANAGER", "ADMIN"):
        h = auth(client, role) if role else {}
        for method, path in (("get", "/technician/jobs"), ("get", "/technician/jobs/1"), ("post", "/technician/jobs/1/start")):
            r = client.request(method.upper(), f"{API}{path}", headers=h)
            assert r.status_code == (403 if role else 401), (role, path)
        for method, path in (("get", "/manager/incidents"), ("post", "/manager/incidents/1/resolve"),
                             ("get", "/manager/jobs/1/events")):
            r = client.request(method.upper(), f"{API}{path}", headers=auth(client, "TECHNICAL_STAFF"), json={})
            assert r.status_code == 403, path                                                     # the Manager's reads stay Manager-only
