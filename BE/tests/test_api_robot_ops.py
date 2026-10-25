"""Robot operations: runs, alerts (4 levels, red = press the E-Stop, e-mailed), heartbeat, status, health, compliance, catalogue.

Real database and triggers. The agent is simulated by the test; no robot is involved and no e-mail leaves the machine
(the console mailer keeps messages in `outbox`).
"""
import json
import time
import uuid

import pytest

from app.integrations.mailer import ConsoleMailer
from tests.test_api_orders import API, _sql
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL, T, _err, _job, _post, _ready, _running
from tests.test_api_workshop import _user, cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"


def rid() -> str:
    return "run-" + uuid.uuid4().hex[:10]


def open_run(client, tech, jid, **kw):
    body = {"run_id": rid(), "mode": "SIM", "dry_run": False, "total_strokes": 10, **kw}
    return client.post(f"{T}/jobs/{jid}/runs", headers=tech[0], json=body), body["run_id"]


def raise_alert(client, tech, robot_id, code, **kw):
    return client.post(f"{T}/alerts", headers=tech[0], json={"robot_id": robot_id, "code": code, **kw})


@pytest.fixture
def catalog_guard():
    """Tests that edit the shared catalogue put it back."""
    rows = _sql("select json_agg(c) from alert_catalog c")
    yield
    for r in rows:
        _sql("""update alert_catalog set title_vi=:t, action_vi=:a, notify_roles=:n, send_email=:e, threshold=cast(:th as jsonb), is_active=:i
                where code=:c returning 1""", t=r["title_vi"], a=r["action_vi"], n=r["notify_roles"], e=r["send_email"],
             th=json.dumps(r["threshold"]) if r["threshold"] is not None else None, i=r["is_active"], c=r["code"])


def wait_mail(n=1, timeout=3.0):
    end = time.time() + timeout
    while len(ConsoleMailer.outbox) < n and time.time() < end:
        time.sleep(0.05)
    return list(ConsoleMailer.outbox)


# ---------------------------------------------------------------- runs
def test_run_lifecycle_and_the_rules_around_it(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    r, key = open_run(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "JOB_STATE_CONFLICT"                # a write run needs WRITING
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _post(client, tech, jid, "prepare", status=200)
    _post(client, tech, jid, "calibration", CAL, status=201)
    _post(client, tech, jid, "simulation", {"passed": True}, status=200)

    r, dry_key = open_run(client, tech, jid, dry_run=True)
    assert r.status_code == 201 and r.json()["dry_run"] is True and r.json()["result"] is None
    r2, _ = open_run(client, tech, jid, dry_run=True)
    assert r2.status_code == 409 and _err(r2) == "ROBOT_BUSY"                      # one controller per robot (DB unique index)
    assert client.patch(f"{T}/runs/{dry_key}", headers=tech[0], json={"result": "DONE"}).status_code == 422
    ok = client.patch(f"{T}/runs/{dry_key}", headers=tech[0], json={"result": "DRY_RUN_DONE", "completed_strokes": 10, "total_strokes": 10})
    assert ok.status_code == 200 and ok.json()["ended_at"]
    again = client.patch(f"{T}/runs/{dry_key}", headers=tech[0], json={"result": "DRY_RUN_DONE"})
    assert again.status_code == 200                                                # a retried close is idempotent
    clash = client.patch(f"{T}/runs/{dry_key}", headers=tech[0], json={"result": "FAULT"})
    assert clash.status_code == 409 and _err(clash) == "RUN_ALREADY_CLOSED"

    _post(client, tech, jid, "start", status=200)
    real, real_key = open_run(client, tech, jid, mode="REAL")
    assert real.status_code == 422 and _err(real) == "AUTHORIZATION_REQUIRED"      # REAL needs the operator's authorization
    real, real_key = open_run(client, tech, jid, mode="REAL", authorized=True, plan_digest="a" * 64)
    assert real.status_code == 201 and real.json()["authorized_by"] == tech[1] and real.json()["authorized_at"]
    assert client.patch(f"{T}/runs/{real_key}", headers=tech[0],
                        json={"result": "DONE", "completed_strokes": 11, "total_strokes": 10}).status_code == 422
    done = client.patch(f"{T}/runs/{real_key}", headers=tech[0],
                        json={"result": "DONE", "completed_strokes": 10, "total_strokes": 10, "summary": {"in_band_pct": 97.5}})
    assert done.json()["summary"]["in_band_pct"] == 97.5
    dup = client.post(f"{T}/jobs/{jid}/runs", headers=tech[0], json={"run_id": real_key, "mode": "SIM"})
    assert dup.status_code == 409 and _err(dup) == "RUN_EXISTS"


def test_database_refuses_a_real_run_without_an_authorizer(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        _sql("""insert into robot_runs (run_id, job_id, robot_id, mode, created_by) values (:r,:j,:b,'REAL',:u) returning id""",
             r=rid(), j=jid, b=robot, u=tech[1])
    assert _sql("select count(*) from robot_runs where job_id=:j", j=jid) == 0


def test_a_refused_attempt_is_recorded_closed(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    r, key = open_run(client, tech, jid, mode="REAL", refused_reason="Hiệu chuẩn chưa có")
    assert r.status_code == 201 and r.json()["result"] == "REFUSED" and r.json()["ended_at"]
    r2, _ = open_run(client, tech, jid)                                            # and it does not block the robot
    assert r2.status_code == 409 and _err(r2) == "JOB_STATE_CONFLICT"


def test_another_technician_cannot_touch_runs_or_robots(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, key = open_run(client, tech, jid)
    assert r.status_code == 201
    other = _user(client, "TECHNICAL_STAFF")
    assert client.post(f"{T}/jobs/{jid}/runs", headers=other[0], json={"run_id": rid(), "mode": "SIM"}).status_code == 404
    assert client.patch(f"{T}/runs/{key}", headers=other[0], json={"result": "STOPPED"}).status_code == 404
    assert client.put(f"{T}/robots/{robot}/heartbeat", headers=other[0], json={"mode": "SIM"}).status_code == 404
    assert raise_alert(client, other, robot, "OVER_FORCE").status_code == 404
    assert client.get(f"{T}/robot-status", headers=other[0]).json() == []
    assert client.get(f"{T}/alerts", headers=other[0]).json()["total"] == 0


# ---------------------------------------------------------------- alerts
def test_the_agent_names_the_alert_the_catalogue_decides_level_and_wording(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r = raise_alert(client, tech, robot, "OVER_FORCE", job_id=jid, details={"force_n": 4.3})
    assert r.status_code == 201
    a = r.json()
    assert a["level"] == 3 and a["estop_advised"] is False and "tự dừng" in a["title_vi"] and a["robot_code"]
    assert raise_alert(client, tech, robot, "NOPE").status_code == 422
    assert _err(raise_alert(client, tech, robot, "NOPE")) == "UNKNOWN_ALERT"
    body = {"robot_id": robot, "code": "OVER_FORCE", "job_id": jid, "level": 1}      # a level in the request is simply ignored
    assert client.post(f"{T}/alerts", headers=tech[0], json=body).json()["level"] == 3
    again = client.post(f"{T}/alerts", headers=tech[0], json=body).json()
    assert again["id"] == a["id"] and again["occurrences"] == 3                      # one open alert, counted, not flooded
    assert _sql("select count(*) from robot_alerts where robot_id=:r and code='OVER_FORCE'", r=robot) == 1


def test_a_red_alert_is_e_mailed_to_the_technician_and_the_managers_and_says_press_estop(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    ConsoleMailer.outbox.clear()
    r = raise_alert(client, tech, robot, "STOP_NOT_EFFECTIVE", job_id=jid)
    assert r.status_code == 201 and r.json()["level"] == 4 and r.json()["estop_advised"] is True
    assert "E-STOP" in r.json()["action_vi"]
    tech_email = _sql("select email from accounts where id=:i", i=tech[1])
    mails = wait_mail()
    to = {m[0] for m in mails}
    assert tech_email in to and len(to) >= 2                                         # the technician and at least one Manager
    assert all("E-STOP" in m[1] and "KHẨN" in m[1] for m in mails)
    assert all("không thể bấm nút E-Stop" in m[2] for m in mails)
    n = len(ConsoleMailer.outbox)
    raise_alert(client, tech, robot, "STOP_NOT_EFFECTIVE", job_id=jid)               # still open: not e-mailed again within 5 minutes
    time.sleep(0.3)
    assert len(ConsoleMailer.outbox) == n
    # an orange alert does not e-mail
    ConsoleMailer.outbox.clear()
    raise_alert(client, tech, robot, "SENSOR_LOST", job_id=jid)
    time.sleep(0.3)
    assert ConsoleMailer.outbox == []


def test_acknowledge_resolve_and_who_may_close_a_red_alert(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    orange = raise_alert(client, tech, robot, "STROKE_LOST", job_id=jid).json()
    red = raise_alert(client, tech, robot, "TRACKING_ERROR", job_id=jid).json()
    ack = client.post(f"{T}/alerts/{orange['id']}/ack", headers=tech[0]).json()
    assert ack["acknowledged_by"] == tech[1] and ack["resolved_at"] is None
    res = client.post(f"{T}/alerts/{orange['id']}/resolve", headers=tech[0], json={"note": "Giấy bị cong, đã kẹp lại"})
    assert res.status_code == 200 and res.json()["resolved_at"]
    no = client.post(f"{T}/alerts/{red['id']}/resolve", headers=tech[0], json={"note": "đã xong"})
    assert no.status_code == 403 and _err(no) == "RED_ALERT_NEEDS_MANAGER"
    assert client.post(f"{T}/alerts/{red['id']}/resolve", headers=tech[0], json={"note": "x"}).status_code in (403, 422)
    yes = client.post(f"{M}/alerts/{red['id']}/resolve", headers=mgr, json={"note": "Đã kiểm tra robot, an toàn"})
    assert yes.status_code == 200 and yes.json()["resolved_by"] and yes.json()["acknowledged_at"]
    open_now = client.get(f"{T}/alerts", headers=tech[0]).json()
    assert open_now["total"] == 0
    assert client.get(f"{T}/alerts", headers=tech[0], params={"open": "false"}).json()["total"] == 2
    # after it was closed the same code opens a NEW alert
    assert raise_alert(client, tech, robot, "STROKE_LOST", job_id=jid).json()["id"] != orange["id"]


# ---------------------------------------------------------------- heartbeat and status
def test_status_in_plain_words_follows_the_alerts_and_the_heartbeat(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    hb = client.put(f"{T}/robots/{robot}/heartbeat", headers=tech[0],
                    json={"mode": "SIM", "controller_version": "V3.8.25-QX", "sdk_version": "SDK:V2.1.7", "agent_version": "0.1.0"})
    assert hb.status_code == 200 and hb.json()["offline_after_seconds"] == 15
    st = client.get(f"{T}/robot-status", headers=tech[0]).json()
    assert len(st) == 1 and st[0]["robot_id"] == robot
    assert st[0]["state"] == "WRITING" and st[0]["headline_vi"] == "Đang viết" and st[0]["level"] == 1
    assert st[0]["controller_version"] == "V3.8.25-QX" and st[0]["connection_state"] == "ONLINE" and st[0]["mode"] == "SIM"
    assert st[0]["calibration_age_minutes"] is not None

    raise_alert(client, tech, robot, "SENSOR_LOST", job_id=jid)
    s2 = client.get(f"{T}/robot-status", headers=tech[0]).json()[0]
    assert s2["state"] == "PAUSED_SAFE" and s2["level"] == 3 and s2["open_alerts"][0]["code"] == "SENSOR_LOST"
    raise_alert(client, tech, robot, "LINK_LOST_MOVING", job_id=jid)
    s3 = client.get(f"{T}/robot-status", headers=tech[0]).json()[0]
    assert s3["state"] == "DANGER" and s3["level"] == 4 and "E-STOP" in s3["headline_vi"]
    assert [a["level"] for a in s3["open_alerts"]] == [4, 3]                         # worst first
    mgr_view = {r["robot_id"]: r for r in client.get(f"{M}/robot-status", headers=mgr).json()}
    assert mgr_view[robot]["state"] == "DANGER"


def test_a_silent_agent_during_a_run_is_raised_by_the_server(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, key = open_run(client, tech, jid)
    assert r.status_code == 201
    client.put(f"{T}/robots/{robot}/heartbeat", headers=tech[0], json={"mode": "SIM"})
    _sql("update robots set last_seen_at = now() - interval '2 minutes' where id=:r returning 1", r=robot)
    st = client.get(f"{T}/robot-status", headers=tech[0]).json()[0]
    assert st["connection_state"] == "OFFLINE" and st["state"] == "PAUSED_SAFE"       # the level-3 "outcome unknown" alert
    codes = {a["code"] for a in st["open_alerts"]}
    assert {"AGENT_OFFLINE", "RUN_OUTCOME_UNKNOWN"} <= codes
    again = client.get(f"{T}/robot-status", headers=tech[0]).json()[0]
    assert all(a["occurrences"] == 1 for a in again["open_alerts"] if a["code"] in codes)   # not re-raised on every read


# ---------------------------------------------------------------- catalogue
def test_manager_edits_wording_but_not_the_level_and_red_alerts_stay_on(client, mgr, catalog_guard):
    rows = client.get(f"{M}/alert-catalog", headers=mgr).json()
    assert len(rows) == 17 and {r["level"] for r in rows} == {1, 2, 3, 4}
    assert all((r["level"] == 4) == r["estop_advised"] for r in rows)
    p = client.patch(f"{M}/alert-catalog/OVER_FORCE", headers=mgr, json={"title_vi": "Bút ép quá mạnh (đã dừng)", "level": 1})
    assert p.status_code == 200 and p.json()["level"] == 3 and p.json()["title_vi"].endswith("(đã dừng)")
    for body in ({"is_active": False}, {"send_email": False}, {"notify_roles": ["MANAGER"]}):
        r = client.patch(f"{M}/alert-catalog/STOP_NOT_EFFECTIVE", headers=mgr, json=body)
        assert r.status_code == 422 and _err(r) == "RED_ALERT_PROTECTED"
    assert client.patch(f"{M}/alert-catalog/NOPE", headers=mgr, json={"send_email": True}).status_code == 404
    assert client.patch(f"{M}/alert-catalog/OVER_FORCE", headers=mgr, json={"is_active": False}).status_code == 200


def test_an_old_alert_keeps_the_wording_it_was_raised_with(client, cust, staff, mgr, wcat, robot, tech, catalog_guard):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    a = raise_alert(client, tech, robot, "STROKE_LOST", job_id=jid).json()
    client.patch(f"{M}/alert-catalog/STROKE_LOST", headers=mgr, json={"title_vi": "Câu chữ mới"})
    seen = client.get(f"{T}/alerts", headers=tech[0]).json()["items"][0]
    assert seen["id"] == a["id"] and seen["title_vi"] == a["title_vi"] != "Câu chữ mới"
    client.post(f"{T}/alerts/{a['id']}/resolve", headers=tech[0], json={"note": "xong rồi"})
    assert raise_alert(client, tech, robot, "STROKE_LOST", job_id=jid).json()["title_vi"] == "Câu chữ mới"


# ---------------------------------------------------------------- manager views
def test_compliance_follows_the_real_steps_and_flags_a_job_without_a_real_run(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech)
    c0 = client.get(f"{M}/jobs/{jid}/compliance", headers=mgr).json()
    st = {s["key"]: s["status"] for s in c0["steps"]}
    assert st["package"] == "PASS" and st["calibration"] == "PASS" and st["simulation"] == "PASS"
    assert st["dry_run"] == "PENDING" and st["authorized"] == "PENDING" and st["written"] == "PENDING"
    _post(client, tech, jid, "start", status=200)
    _post(client, tech, jid, "finish", status=200)                                    # recorded as written with NO real run
    c1 = client.get(f"{M}/jobs/{jid}/compliance", headers=mgr).json()
    st1 = {s["key"]: s for s in c1["steps"]}
    assert st1["written"]["status"] == "PASS" and st1["real_run"]["status"] == "FAIL"
    assert "không có lần chạy robot thật" in st1["real_run"]["detail"] and c1["followed_process"] is False
    assert client.get(f"{M}/jobs/999999999/compliance", headers=mgr).status_code == 404


def test_compliance_passes_after_dry_run_authorization_and_a_real_run(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech)
    d, dk = open_run(client, tech, jid, dry_run=True)
    assert d.status_code == 201
    client.patch(f"{T}/runs/{dk}", headers=tech[0], json={"result": "DRY_RUN_DONE"})
    _post(client, tech, jid, "start", status=200)
    r, k = open_run(client, tech, jid, mode="REAL", authorized=True)
    client.patch(f"{T}/runs/{k}", headers=tech[0], json={"result": "DONE", "completed_strokes": 10, "total_strokes": 10})
    _post(client, tech, jid, "finish", status=200)
    c = client.get(f"{M}/jobs/{jid}/compliance", headers=mgr).json()
    st = {s["key"]: s for s in c["steps"]}
    assert st["dry_run"]["status"] == st["authorized"]["status"] == st["real_run"]["status"] == "PASS"
    assert st["authorized"]["detail"] == "Test TECHNICAL_STAFF" and c["exceptions"] == [] and c["followed_process"] is True


def test_health_counts_runs_stops_and_alerts(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, k = open_run(client, tech, jid)
    client.patch(f"{T}/runs/{k}", headers=tech[0], json={"result": "STOPPED", "completed_strokes": 4, "summary": {"in_band_pct": 90}})
    _post(client, tech, jid, "events", {"event_type": "OVER_FORCE"}, status=201)
    raise_alert(client, tech, robot, "OVER_FORCE", job_id=jid)
    raise_alert(client, tech, robot, "STOP_NOT_EFFECTIVE", job_id=jid)
    h = client.get(f"{M}/robots/{robot}/health", headers=mgr, params={"days": 7}).json()
    assert h["runs_by_result"] == {"STOPPED": 1} and h["runs_by_mode"] == {"SIM": 1}
    assert h["safety_stops"] == 1 and h["alerts_by_level"] == {"3": 1, "4": 1} and h["unresolved_red"] == 1
    assert h["in_band_pct_avg"] == 90.0 and h["robot"]["state"] == "DANGER"
    runs = client.get(f"{M}/runs", headers=mgr, params={"robot_id": robot}).json()
    assert runs["total"] == 1 and runs["items"][0]["run_id"] == k
    assert client.get(f"{M}/robots/999999999/health", headers=mgr).status_code == 404
    al = client.get(f"{M}/alerts", headers=mgr, params={"robot_id": robot, "min_level": 4}).json()
    assert al["total"] == 1 and al["items"][0]["code"] == "STOP_NOT_EFFECTIVE"
