"""The agent as a network service: login through the backend, roles, loading a job, checks, dry run, run, pause/stop, and the REAL gate.

The backend is a fake (httpx.MockTransport); robots are software robots; the REAL robot is a labelled test double. Nothing moves a real robot.
"""
import json
import os
import time

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core import production_signing as ps
from app.services.stroke_ai import text_to_stroke as tts
from app.services.stroke_ai import trajectory as tj

from vhrs_agent.cli import DEMO_CFG, DEMO_LIMITS, DEMO_PROBES, DEMO_START, DEMO_WS
from vhrs_agent.port import Mode, RobotInfo
from vhrs_agent.server import AgentService, ServerConfig, create_server_app
from vhrs_agent.sim import SimRobot

USERS = {"tech-token": {"id": 5, "role": "TECHNICAL_STAFF", "full_name": "Ky Thuat", "email": "Tech@X.vn"},
         "other-token": {"id": 6, "role": "TECHNICAL_STAFF", "full_name": "Ky Thuat 2", "email": "tech2@x.vn"},
         "mgr-token": {"id": 7, "role": "MANAGER", "full_name": "Quan Ly"},
         "cust-token": {"id": 8, "role": "CUSTOMER", "full_name": "Khach"}}
PAGES = tts.compose_text("Xin chào", font_name="futural", paper_size="A5", font_size_mm=7.0, seed=1)
RAW = tj.dumps(tj.to_dict(PAGES, {"name": "test"}))
HASH = tj.content_hash(RAW)
PEN = {"name": "Gel 0.5", "f_target_n": 1.0, "f_min_n": 0.6, "f_max_n": 1.6, "f_hard_n": 4.0, "v_max_mm_s": 40.0}
MOTION = {k: v for k, v in DEMO_CFG.__dict__.items() if k not in ("f_target_n", "v_max_mm_s")}
# A08: the REAL robot writes only a package that carries the backend's production signature (checked with the station's public key)
SIGNING_KEY = ps.generate_private_key()
KEY_RING = {"k1": ps.public_key_of(SIGNING_KEY)}
_SIGNED = ps.canonical({"schema": ps.SCHEMA, "order": {"id": 5, "type": "OT3_TEMPLATE"}, "sketch": {"id": 6, "trajectory_sha256": HASH},
                        "materials": {"pen": {k: str(PEN[k]) for k in ("f_target_n", "f_min_n", "f_max_n", "f_hard_n", "v_max_mm_s")}}})
SNAPSHOT = {"snapshot_id": 1, "package_id": "x", "schema": ps.SCHEMA, "payload": _SIGNED, "payload_sha256": ps.sha256_hex(_SIGNED),
            "signature": ps.sign(_SIGNED, SIGNING_KEY), "key_id": "k1"}
WSD = {"box_min_mm": list(DEMO_WS.box_min_mm), "box_max_mm": list(DEMO_WS.box_max_mm)}


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.calibration = {"probe_points": DEMO_PROBES, "frame_transform": {"schema": "vhrs-motion/1", "motion": MOTION, "workspace": WSD}}
        self.signed = True                                       # False: a job scheduled before the packages were signed

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/api/v1")
        body = json.loads(req.content) if req.content else None
        tok = req.headers.get("authorization", "")[7:]
        self.calls.append((req.method, path, body))
        if path == "/auth/login":
            role = "CUSTOMER" if body["email"].startswith("cust") else "TECHNICAL_STAFF"
            return httpx.Response(200, json={"access_token": "tech-token", "refresh_token": "r1", "account": {"role": role, "full_name": "Ky Thuat"}})
        if path == "/auth/refresh":
            return httpx.Response(200, json={"access_token": "tech-token", "refresh_token": "r2"})
        if tok not in USERS:
            return httpx.Response(401, json={"error": {"code": "UNAUTHENTICATED", "message": "x", "details": None}})
        if path == "/me":
            return httpx.Response(200, json=USERS[tok])
        if path.endswith("/package"):
            return httpx.Response(200, json={"job_id": 12, "order_code": "VHRS-T", "package_hash": HASH, "trajectory_url": "https://store/x", "pen": PEN,
                                             "snapshot": SNAPSHOT if self.signed else None})
        if path == "/technician/jobs/12":
            return httpx.Response(200, json={"id": 12, "robot_id": 3, "status": "PREPARING", "calibration": self.calibration})
        if path.endswith("/runs") or path.startswith("/technician/runs/") or path.endswith("/events") or path.endswith("/alerts"):
            return httpx.Response(201, json={"id": 1, "level": 3, "title_vi": "t", "action_vi": "a", "estop_advised": False})
        if path.endswith("/heartbeat"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": path, "details": None}})


def make(tmp_path, *, modes=("mock", "sim"), robot_factory=None, speed=None, watchdogs=None, backend=None, gripper_factory=None, unsensed=False):
    backend = backend or FakeBackend()
    cfg = ServerConfig(backend_url="https://be.test", modes=modes, run_dir=tmp_path,
                       sim={"tool_offset_mm": 250.0, "table_z_mm": 19.0, "start_mm": list(DEMO_START), "speed_factor": speed, "yaw_deg": 0.0},
                       watchdogs=watchdogs, unsensed_gripper=unsensed, production_public_keys=KEY_RING,
                       station_limits={"z_floor_mm": 15.0, "max_press_mm": 4.0} if "real" in modes else None)
    svc = AgentService(cfg, transport=httpx.MockTransport(backend), downloader=lambda url: RAW,
                       robot_factory=robot_factory or (lambda mode: SimRobot(DEMO_START, speed_factor=None)),
                       gripper_factory=gripper_factory)
    # the tests act as a person at the workstation (D03 / 1a: REAL is switched on and started from this computer only)
    return svc, TestClient(create_server_app(svc), client=("127.0.0.1", 50000)), backend


def auth(tok="tech-token"):
    return {"Authorization": f"Bearer {tok}"}


def wait_idle(c, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        a = c.get("/api/agent", headers=auth()).json()
        if not a["busy"]:
            return a
        time.sleep(0.05)
    raise AssertionError("agent stayed busy")


# ---------------------------------------------------------------- identity and roles
def test_nothing_works_without_a_valid_login_and_each_role_gets_only_its_rights(tmp_path):
    svc, c, _ = make(tmp_path)
    assert c.get("/api/state").status_code == 401 and c.get("/api/agent").status_code == 200       # the agent's own info is public
    assert c.get("/api/state", headers=auth("nope")).status_code == 401
    assert c.get("/api/state", headers=auth("cust-token")).status_code == 403
    assert c.get("/api/state", headers=auth("mgr-token")).status_code == 200
    assert c.post("/api/jobs/12/load", headers=auth("mgr-token")).status_code == 403              # a Manager watches and stops, never runs
    assert c.post("/api/stop", headers=auth("cust-token")).status_code == 403
    assert c.post("/api/paper-changed", headers=auth("mgr-token")).status_code == 403
    e = c.post("/api/jobs/12/load").json()["error"]
    assert e["code"] == "UNAUTHENTICATED"
    assert c.get("/api/model").status_code == 200                                                 # public static data only


def test_login_goes_through_the_backend_and_refuses_customers(tmp_path):
    svc, c, be = make(tmp_path)
    ok = c.post("/api/login", json={"email": "tech@x.vn", "password": "pw"})
    assert ok.status_code == 200 and ok.json()["role"] == "TECHNICAL_STAFF" and ok.json()["access_token"] == "tech-token"
    assert "refresh" not in json.dumps(ok.json())                                                 # the refresh token stays on the server
    assert c.post("/api/login", json={"email": "cust@x.vn", "password": "pw"}).status_code == 403


def test_the_desktop_app_signs_the_screen_in_with_its_code_only(tmp_path):
    svc, c, be = make(tmp_path)
    code = "a" * 32
    assert c.post("/api/screen-login", json={"code": code}).json()["error"]["code"] == "SCREEN_CODE_INVALID"   # not started by the app
    svc.screen_login = (code, "tech@x.vn", "pw")
    assert c.post("/api/screen-login", json={"code": "b" * 32}).status_code == 401
    ok = c.post("/api/screen-login", json={"code": code})
    assert ok.status_code == 200 and ok.json()["access_token"] == "tech-token" and ok.json()["role"] == "TECHNICAL_STAFF"
    assert "pw" not in json.dumps(ok.json())


def test_the_app_technician_turns_real_on_for_a_job_loaded_from_the_app_and_nobody_else(tmp_path):
    from vhrs_agent.link import LINK_WHO
    svc, c, be = make(tmp_path, modes=("mock", "sim", "real"))
    svc.check_real_robot = lambda: {"ok": True}
    h = {"Authorization": "Bearer tech-token"}
    tech = svc.identify("tech-token")
    svc.load_job(12, "tech-token", LINK_WHO)                                  # LOAD sent from the app, run through the link
    r = c.post("/api/jobs/12/real-enable", json={"minutes": 5}, headers=h)
    assert r.json()["error"]["code"] == "JOB_NOT_LOADED"                       # the agent was not started by the app
    svc.link_owner = "someone.else@x.vn"
    assert c.post("/api/jobs/12/real-enable", json={"minutes": 5}, headers=h).status_code == 409
    assert tech["email"] == "tech@x.vn"
    svc.link_owner = "tech@x.vn"
    ok = c.post("/api/jobs/12/real-enable", json={"minutes": 5}, headers=h)
    assert ok.status_code == 200 and ok.json()["real_enabled"]["job_id"] == 12
    assert ok.json()["real_enabled"]["waive_dry_run"] is False
    # the app may skip the pen-up dry run (owner 2026-11-27), only with the literal confirmation
    bad = c.post("/api/jobs/12/real-enable", json={"minutes": 5, "waive_dry_run": True}, headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "CONFIRM_REQUIRED"
    waived = c.post("/api/jobs/12/real-enable", json={"minutes": 5, "waive_dry_run": True, "confirm_waive": "SKIP-DRY-RUN"}, headers=h)
    assert waived.status_code == 200 and waived.json()["real_enabled"]["waive_dry_run"] is True


def test_websocket_needs_a_token(tmp_path):
    svc, c, _ = make(tmp_path)
    with pytest.raises(Exception):
        with c.websocket_connect("/ws"):
            pass
    with c.websocket_connect("/ws?token=mgr-token") as ws:
        assert "state" in ws.receive_json()


# ---------------------------------------------------------------- jobs
def test_load_summarises_the_job_validates_it_and_binds_it_to_its_owner(tmp_path):
    svc, c, _ = make(tmp_path)
    r = c.post("/api/jobs/12/load", headers=auth())
    assert r.status_code == 200
    s = r.json()
    assert s["job_id"] == 12 and s["package_hash"] == HASH and s["validation"]["passed"] is True and s["strokes"] > 0
    assert s["authorization_token"].startswith("AUTHORIZE-12-") and s["pen"] == "Gel 0.5"
    assert c.get("/api/jobs/12", headers=auth()).status_code == 200
    assert c.get("/api/jobs/12", headers=auth("other-token")).json()["error"]["code"] == "JOB_NOT_LOADED"      # someone else's loaded job
    assert c.post("/api/jobs/12/dry-run", headers=auth("other-token"), json={"mode": "sim"}).status_code == 409


def test_a_job_without_calibration_is_refused_at_load(tmp_path):
    be = FakeBackend()
    be.calibration = None
    svc, c, _ = make(tmp_path, backend=be)
    r = c.post("/api/jobs/12/load", headers=auth())
    assert r.status_code == 409 and r.json()["error"]["code"] == "CALIBRATION_REQUIRED"


def test_preflight_reports_ok_or_the_reason_without_moving_anything(tmp_path):
    svc, c, _ = make(tmp_path)
    c.post("/api/jobs/12/load", headers=auth())
    r = c.post("/api/jobs/12/preflight", headers=auth(), json={"mode": "sim"})
    assert r.status_code == 200 and r.json()["ok"] is True
    svc.robot_factory = lambda mode: SimRobot((150.0, 0.0, 19.0), speed_factor=None)               # the pen would rest pressed into the paper
    svc.gripper_factory = None
    r2 = c.post("/api/jobs/12/preflight", headers=auth(), json={"mode": "sim"})
    assert r2.json()["ok"] is False and r2.json()["code"] == "GRIPPER_ZERO_DRIFT"


# ---------------------------------------------------------------- running
def test_dry_run_then_run_in_the_background_with_the_backend_recording_both(tmp_path):
    svc, c, be = make(tmp_path)
    c.post("/api/jobs/12/load", headers=auth())
    d = c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "sim"})
    assert d.status_code == 202
    a = wait_idle(c)
    assert a["last"]["result"]["state"] == "DRY_RUN_DONE" and a["last"]["dry_run"] is True
    r = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"})
    assert r.status_code == 202 and r.json()["started"] in (True, False)
    a = wait_idle(c)
    assert a["last"]["result"]["state"] == "DONE" and a["last"]["result"]["completed_strokes"] == a["last"]["result"]["total_strokes"] > 0
    progress = c.get("/api/jobs/12", headers=auth()).json()["progress"]
    assert progress["state"] == "DONE"
    kinds = [(m, p) for m, p, _ in be.calls]
    assert ("POST", "/technician/jobs/12/runs") in kinds and any(p.startswith("/technician/runs/") for _, p in kinds)
    assert any(p == "/technician/jobs/12/events" for _, p in kinds)
    log = c.get("/api/jobs/12/log", headers=auth("mgr-token")).json()
    assert log["file"].startswith("run-") and any(x["kind"] == "run_end" for x in log["lines"])


def test_a_second_run_is_refused_while_one_is_active_and_stop_works_for_a_manager(tmp_path):
    svc, c, _ = make(tmp_path, robot_factory=lambda mode: SimRobot(DEMO_START, speed_factor=20.0))
    c.post("/api/jobs/12/load", headers=auth())
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "sim"}).status_code == 202
    wait_idle(c, 30)
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"}).status_code == 202
    busy = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"})
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "AGENT_BUSY"
    assert c.post("/api/pause", headers=auth("mgr-token")).status_code == 200
    assert c.post("/api/resume", headers=auth("mgr-token")).status_code == 403                   # a Manager halts, never puts the arm back in motion (TP-03)
    assert c.post("/api/resume", headers=auth()).status_code == 200                               # the technician does
    assert c.post("/api/stop", headers=auth("mgr-token")).status_code == 200
    a = wait_idle(c, 30)
    assert a["last"]["result"]["state"] == "STOPPED"
    again = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"})                       # no explicit resume point: refused
    assert again.status_code == 409 and again.json()["error"]["code"] == "PARTIAL_JOB_EXISTS"


def test_mode_must_be_enabled_on_the_agent(tmp_path):
    svc, c, _ = make(tmp_path, modes=("sim",))
    c.post("/api/jobs/12/load", headers=auth())
    r = c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "mock"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MODE_DISABLED"


# ---------------------------------------------------------------- the REAL gate
class FakeReal(SimRobot):
    mode = Mode.REAL

    def connect(self):
        self._alive = True
        return RobotInfo(Mode.REAL, "TEST DOUBLE posing as REAL (nothing moves)")


WD = {"stop_settle_s": 0.01, "stop_window_s": 0.02, "stop_tolerance_mm": 1.0, "tracking_tolerance_mm": 2.0, "tracking_grace_s": 0.5}


def model_gripper(mode, ctx, frame):
    """Stands in for the serial gripper: the spring model fed by the planned pen height."""
    import numpy as np
    from vhrs_agent.gripper import SimGripper

    def depth(p):
        rel = np.asarray(p) - frame.origin
        return -(float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis)))

    return SimGripper(depth, 0.4, ctx.limits.f_hard, 6.0)


def real_service(tmp_path, modes=("sim", "real")):
    svc, c, be = make(tmp_path, modes=modes, watchdogs=WD, gripper_factory=model_gripper,
                      robot_factory=lambda mode: FakeReal(DEMO_START, speed_factor=None) if mode == "real" else SimRobot(DEMO_START, speed_factor=None))
    return svc, c, be


def enable(tmp_path, job_id=12, minutes=30):
    (tmp_path / "REAL_ENABLED.json").write_text(json.dumps({"job_id": job_id, "expires_at": time.time() + minutes * 60, "enabled_by": "op"}))


def test_real_is_impossible_unless_enabled_on_the_agent_and_by_a_person_at_the_workstation(tmp_path):
    svc, c, _ = real_service(tmp_path, modes=("sim",))
    c.post("/api/jobs/12/load", headers=auth())
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real"}).json()["error"]["code"] == "MODE_DISABLED"
    svc2, c2, _ = real_service(tmp_path / "b")
    c2.post("/api/jobs/12/load", headers=auth())
    r = c2.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAL_NOT_ENABLED_ON_SITE" and "real-enable" in r.json()["error"]["message"]
    enable(tmp_path / "b", job_id=99)                                                                # enabled for another job
    assert c2.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real"}).json()["error"]["code"] == "REAL_NOT_ENABLED_ON_SITE"
    (tmp_path / "b" / "REAL_ENABLED.json").write_text(json.dumps({"job_id": 12, "expires_at": time.time() - 5}))
    assert c2.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real"}).json()["error"]["code"] == "REAL_NOT_ENABLED_ON_SITE"


def test_real_with_the_site_switch_still_needs_the_plan_bound_authorization_and_a_dry_run(tmp_path):
    svc, c, _ = real_service(tmp_path)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path)
    no_auth = c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real"})
    assert no_auth.status_code == 409 and no_auth.json()["error"]["code"] == "AUTHORIZATION_REQUIRED"
    wrong = c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": "AUTHORIZE-12-deadbeef"})
    assert wrong.json()["error"]["code"] == "AUTHORIZATION_REQUIRED"
    skip = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token})
    assert skip.status_code == 409 and skip.json()["error"]["code"] == "DRY_RUN_REQUIRED"
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"


def test_the_job_summary_does_not_leak_to_a_customer_and_the_log_needs_a_staff_role(tmp_path):
    svc, c, _ = make(tmp_path)
    assert c.get("/api/jobs/12/log", headers=auth("cust-token")).status_code == 403
    assert c.get("/api/my-jobs", headers=auth("cust-token")).status_code == 403


def test_a_plain_gripper_writes_only_when_the_owner_says_so_and_it_is_recorded(tmp_path):
    robots = lambda mode: FakeReal(DEMO_START, speed_factor=None) if mode == "real" else SimRobot(DEMO_START, speed_factor=None)   # noqa: E731
    # default: REAL without a force sensor is refused, even for a pen-up rehearsal
    svc, c, _ = make(tmp_path / "a", modes=("sim", "real"), watchdogs=WD, robot_factory=robots)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path / "a")
    r = c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token})
    assert r.status_code == 409 and r.json()["error"]["code"] == "GRIPPER_NOT_CONFIGURED" and "unsensed_gripper" in r.json()["error"]["message"]
    # the owner's explicit choice: all the OTHER gates stay (site switch, plan-bound token, finished dry run, watchdogs)
    svc, c, be = make(tmp_path / "b", modes=("sim", "real"), watchdogs=WD, robot_factory=robots, unsensed=True)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "REAL_NOT_ENABLED_ON_SITE"
    enable(tmp_path / "b")
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "DRY_RUN_REQUIRED"
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"
    closes = [b for m, p, b in be.calls if m == "PATCH" and p.startswith("/technician/runs/") and b.get("result") == "DONE"]
    assert closes and closes[-1]["summary"]["force_sensing"] is False                                  # the run record says it had no force sensor
    log = c.get("/api/jobs/12/log", headers=auth()).json()["lines"]
    assert any(x["kind"] == "no_force_sensing" for x in log)
    # watchdogs are still mandatory
    svc, c, _ = make(tmp_path / "c", modes=("sim", "real"), watchdogs=None, robot_factory=robots, unsensed=True)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path / "c")
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "WATCHDOG_UNCONFIGURED"


def test_a_simulator_rehearsal_does_not_qualify_a_real_run(tmp_path):
    svc, c, _ = real_service(tmp_path)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path)
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "sim"}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"
    skip = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token})
    assert skip.status_code == 409 and skip.json()["error"]["code"] == "DRY_RUN_REQUIRED"          # SIM rehearsal is not a REAL one
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "sim"}).status_code == 202       # a later SIM rehearsal does not undo it
    wait_idle(c)
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"


def test_latest_run_log_is_not_chosen_by_random_filename_suffix(tmp_path):
    _, c, _ = make(tmp_path)
    job_dir = tmp_path / "job12"
    job_dir.mkdir()
    older = job_dir / "run-20261024-201552-j12-zzzzzz.jsonl"
    newer = job_dir / "run-20261024-201552-j12-aaaaaa.jsonl"
    older.write_text('{"kind":"older"}\n', encoding="utf-8")
    newer.write_text('{"kind":"newer"}\n', encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (1001, 1001))
    result = c.get("/api/jobs/12/log", headers=auth()).json()
    assert result["file"] == newer.name and result["lines"] == [{"kind": "newer"}]


def test_after_a_finished_run_the_pen_goes_back_to_the_fixed_start(tmp_path):
    robots = []

    def factory(mode):
        r = SimRobot(DEMO_START, speed_factor=None)
        robots.append(r)
        return r

    svc, c, _ = make(tmp_path, robot_factory=factory)
    c.post("/api/jobs/12/load", headers=auth())
    for kind in ("dry-run", "run"):
        assert c.post(f"/api/jobs/12/{kind}", headers=auth(), json={"mode": "sim"}).status_code == 202
        last = wait_idle(c, 30)["last"]
        assert last["result"]["state"] in ("DRY_RUN_DONE", "DONE")
        back = last["return_to_start"]
        assert back["ok"] is True and robots[-1].commands[-1] == "align_to"
        start = svc.start_point(svc.jobs[12])
        assert np.allclose(robots[-1].read_tcp(), start)                    # it really is at the fixed start
    # a stopped run does not move on its own afterwards
    robots.clear()
    svc2, c2, _ = make(tmp_path / "b", robot_factory=lambda mode: (robots.append(SimRobot(DEMO_START, speed_factor=20.0)) or robots[-1]))
    c2.post("/api/jobs/12/load", headers=auth())
    c2.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "sim"})
    wait_idle(c2, 30)
    c2.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"})
    c2.post("/api/stop", headers=auth("mgr-token"))
    last = wait_idle(c2, 30)["last"]
    assert last["result"]["state"] == "STOPPED" and "return_to_start" not in last


def test_the_operator_at_the_workstation_can_waive_the_real_rehearsal_for_one_job_and_it_is_recorded(tmp_path):
    svc, c, be = real_service(tmp_path)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path)                                                                       # a normal enable: no waiver
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "DRY_RUN_REQUIRED"
    (tmp_path / "REAL_ENABLED.json").write_text(json.dumps({"job_id": 12, "expires_at": time.time() + 600, "waive_dry_run": True}))
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"
    closes = [b for m, p, b in be.calls if m == "PATCH" and p.startswith("/technician/runs/") and b.get("result") == "DONE"]
    assert closes and closes[-1]["summary"]["dry_run_waived"] is True
    assert any(x["kind"] == "dry_run_waived" for x in c.get("/api/jobs/12/log", headers=auth()).json()["lines"])
    # the waiver covers one job: the same file does not open another job's rehearsal gate, and a rehearsal never counts as waived
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code in (202, 409)


# ---------------------------------------------------------------- the desktop is the technician's workspace (owner 2026-11-26)
def test_real_is_switched_on_by_the_desktop_button_only_on_a_wired_agent_for_a_loaded_job(tmp_path):
    svc, c, _ = make(tmp_path)                                                         # no "real": not wired to the robot
    c.post("/api/jobs/12/load", headers=auth())
    r = c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 30})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MODE_DISABLED"
    assert c.get("/api/real", headers=auth()).json() == {"real_enabled": None, "real_available": False, "max_minutes": 120}

    svc, c, _ = real_service(tmp_path / "b")
    assert c.post("/api/jobs/12/real-enable", headers=auth(), json={}).json()["error"]["code"] == "JOB_NOT_LOADED"
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    assert c.post("/api/jobs/12/real-enable", headers=auth("other-token"), json={}).json()["error"]["code"] == "JOB_NOT_LOADED"
    assert c.post("/api/jobs/12/real-enable", headers=auth("mgr-token"), json={}).status_code == 403
    assert c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 500}).status_code == 422
    assert c.post("/api/jobs/12/real-enable", headers=auth(), json={"waive_dry_run": True}).json()["error"]["code"] == "CONFIRM_REQUIRED"
    on = c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 30})
    assert on.status_code == 200 and on.json()["real_enabled"]["enabled_by"] == "desktop:Ky Thuat"
    assert c.get("/api/agent", headers=auth()).json()["real_enabled"]["job_id"] == 12
    # the switch replaces typing at the console; the plan-bound token and the dry run are still required
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "DRY_RUN_REQUIRED"
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"
    assert c.delete("/api/real-enable", headers=auth("mgr-token")).json() == {"real_enabled": None}       # a Manager may switch it off
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token}).json()["error"]["code"] == "REAL_NOT_ENABLED_ON_SITE"


class DeadReal(FakeReal):
    """A real robot that is switched off or unplugged: the SDK connection fails."""

    def connect(self):
        raise ConnectionError("controller 192.168.58.2 did not answer")


class WrongToolReal(FakeReal):
    """Answers, but the controller has another tool slot active than agent.json asks for."""

    def connect(self):
        from vhrs_agent.port import RobotError
        raise RobotError("TOOL_MISMATCH", "Robot đang dùng tool 0, cấu hình yêu cầu tool 2.")


class MuteReal(FakeReal):
    """Connects, but the controller does not answer the heartbeat."""

    def heartbeat(self, deadline=None):
        return False


def test_real_switch_checks_the_robot_first_and_stays_off_when_it_does_not_answer(tmp_path):
    """Owner 2026-11-26: pressing 'Bật REAL' first checks the connection to the real robot; no answer, no REAL."""
    svc, c, _ = real_service(tmp_path)
    c.post("/api/jobs/12/load", headers=auth())
    for dead in (DeadReal, MuteReal):
        svc.robot_factory = lambda mode, cls=dead: cls(DEMO_START, speed_factor=None) if mode == "real" else SimRobot(DEMO_START, speed_factor=None)
        r = c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 30})
        assert r.status_code == 502 and r.json()["error"]["code"] == "ROBOT_UNREACHABLE", dead
        assert not (tmp_path / "REAL_ENABLED.json").exists()
        assert c.get("/api/real", headers=auth()).json()["real_enabled"] is None
    # it answers but the tool slot differs: a setup problem, not a lost connection, and REAL still stays off
    svc.robot_factory = lambda mode: WrongToolReal(DEMO_START, speed_factor=None) if mode == "real" else SimRobot(DEMO_START, speed_factor=None)
    r = c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 30})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ROBOT_CONFIG_MISMATCH"
    assert r.json()["error"]["details"]["reason"] == "TOOL_MISMATCH" and "tool 0" in r.json()["error"]["message"]
    assert not (tmp_path / "REAL_ENABLED.json").exists()
    r = c.post("/api/robot/identify", headers=auth(), json={"mode": "real"})
    assert r.json()["error"]["code"] == "ROBOT_CONFIG_MISMATCH"
    svc.robot_factory = lambda mode: FakeReal(DEMO_START, speed_factor=None) if mode == "real" else SimRobot(DEMO_START, speed_factor=None)
    on = c.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 30}).json()
    assert on["real_enabled"]["job_id"] == 12
    assert on["robot_check"]["ok"] is True and on["robot_check"]["controller"]["mode"] in ("real", "REAL") and len(on["robot_check"]["tcp_mm"]) == 3


def test_reset_progress_needs_a_new_sheet_confirmation(tmp_path):
    svc, c, _ = make(tmp_path)
    c.post("/api/jobs/12/load", headers=auth())
    assert c.post("/api/jobs/12/reset-progress", headers=auth(), json={"confirm": "NEW_SHEET"}).json() == {"reset": False, "reason": "NO_PROGRESS"}
    d = tmp_path / "job12"
    d.mkdir(exist_ok=True)
    (d / "progress.json").write_text(json.dumps({"state": "INTERRUPTED", "completed": 7, "interrupted": 7, "resume_at": 7}))
    assert c.post("/api/jobs/12/reset-progress", headers=auth(), json={"confirm": "yes"}).json()["error"]["code"] == "CONFIRM_REQUIRED"
    r = c.post("/api/jobs/12/reset-progress", headers=auth(), json={"confirm": "NEW_SHEET"}).json()
    assert r["reset"] is True and r["before"] == {"state": "INTERRUPTED", "completed": 7} and (d / r["backup"]).exists()
    assert json.loads((d / "progress.json").read_text())["completed"] == 0


def test_the_desktop_reaches_the_technician_api_through_the_agent_with_the_persons_token(tmp_path):
    svc, c, be = make(tmp_path)
    r = c.get("/api/technician/jobs/12", headers=auth())
    assert r.status_code == 200 and r.json()["id"] == 12
    assert be.calls[-1][:2] == ("GET", "/technician/jobs/12")
    r = c.put("/api/technician/jobs/99/robot", headers=auth(), json={"robot_id": 3})
    assert r.status_code == 404 and be.calls[-1] == ("PUT", "/technician/jobs/99/robot", {"robot_id": 3})   # the backend's answer, as is
    assert c.get("/api/technician/jobs/12").status_code == 401                                              # no token: refused here


def test_the_desktop_workspace_page_and_its_assets_are_served_and_the_agent_says_which_robot_it_drives(tmp_path):
    svc, c, _ = make(tmp_path)
    page = c.get("/")
    assert page.status_code == 200 and "/assets/app.js" in page.text and "/assets/app.css" in page.text
    js = c.get("/assets/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"] and "/api/technician/" in js.text
    assert c.get("/assets/app.css").status_code == 200
    assert c.get("/assets/../server.py").status_code == 404                     # the mount stays inside static/assets
    assert c.get("/api/agent").json()["robot_id"] is None                       # not configured: the page learns it from a loaded job
    svc.cfg.robot_id = 46
    assert c.get("/api/agent").json()["robot_id"] == 46


# ---------------------------------------------------------------- started by the desktop app (owner 2026-11-26)
def _running(tmp_path):
    svc, c, _ = make(tmp_path, robot_factory=lambda mode: SimRobot(DEMO_START, speed_factor=1.0))
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim", "authorization": token}).status_code == 202
    assert svc._busy
    return svc, c


class _Silent:
    """stdin that never ends (a pipe end kept open by another process)."""

    def readline(self):
        import threading as th
        th.Event().wait()


def test_the_agent_still_exits_when_the_app_took_its_stdout_with_it(tmp_path, monkeypatch):
    """Seen on the workstation 2026-11-26: the app closed, printing 'stopping safely' raised on the broken pipe and the agent stayed."""
    import io
    import sys
    import threading as th
    from vhrs_agent.server import watch_parent

    class Broken(io.TextIOBase):
        def write(self, s):
            raise OSError(22, "Invalid argument")

    svc, c, _ = make(tmp_path)
    monkeypatch.setattr(sys, "stdout", Broken())
    released, codes, done = [], [], th.Event()
    watch_parent(svc, lambda: released.append(True), stream=io.StringIO(""), exit_fn=lambda code: (codes.append(code), done.set()))
    assert done.wait(10)
    assert released == [True] and codes == [0]


def test_waiting_for_a_process_returns_when_it_ends():
    import subprocess
    import sys
    from vhrs_agent.server import wait_for_process_exit
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    t0 = time.monotonic()
    wait_for_process_exit(p.pid)
    assert p.wait(5) == 0 and time.monotonic() - t0 < 5


def test_the_desktop_app_stops_the_agent_safely_by_a_stop_line_or_by_going_away(tmp_path):
    """STOP on stdin, stdin closing, or the app's process ending: a run in progress is stopped the normal way, the robot session is
    released once, then the agent exits. Other lines are ignored."""
    import io
    import threading as th
    from vhrs_agent.server import watch_parent

    def watch(svc, **kw):
        released, codes, done = [], [], th.Event()
        watch_parent(svc, lambda: released.append(True), exit_fn=lambda code: (codes.append(code), done.set()), **kw)
        assert done.wait(40)
        return released, codes

    for i, kw in enumerate([
        {"stream": io.StringIO("hello\nSTOP\n")},
        {"stream": io.StringIO("")},
        {"stream": _Silent(), "parent_pid": 999999, "wait_exit": lambda pid: None},          # stdin stays open: only the pid tells
    ]):
        svc, c = _running(tmp_path / str(i))
        released, codes = watch(svc, **kw)
        assert released == [True] and codes == [0] and not svc._busy, kw
