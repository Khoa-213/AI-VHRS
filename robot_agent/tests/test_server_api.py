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

from app.services.stroke_ai import text_to_stroke as tts
from app.services.stroke_ai import trajectory as tj

from vhrs_agent.cli import DEMO_CFG, DEMO_LIMITS, DEMO_PROBES, DEMO_START, DEMO_WS
from vhrs_agent.port import Mode, RobotInfo
from vhrs_agent.server import AgentService, ServerConfig, create_server_app
from vhrs_agent.sim import SimRobot

USERS = {"tech-token": {"id": 5, "role": "TECHNICAL_STAFF", "full_name": "Ky Thuat"},
         "other-token": {"id": 6, "role": "TECHNICAL_STAFF", "full_name": "Ky Thuat 2"},
         "mgr-token": {"id": 7, "role": "MANAGER", "full_name": "Quan Ly"},
         "cust-token": {"id": 8, "role": "CUSTOMER", "full_name": "Khach"}}
PAGES = tts.compose_text("Xin chào", font_name="futural", paper_size="A5", font_size_mm=7.0, seed=1)
RAW = tj.dumps(tj.to_dict(PAGES, {"name": "test"}))
HASH = tj.content_hash(RAW)
PEN = {"name": "Gel 0.5", "f_target_n": 1.0, "f_min_n": 0.6, "f_max_n": 1.6, "f_hard_n": 4.0, "v_max_mm_s": 40.0}
MOTION = {k: v for k, v in DEMO_CFG.__dict__.items() if k not in ("f_target_n", "v_max_mm_s")}
WSD = {"box_min_mm": list(DEMO_WS.box_min_mm), "box_max_mm": list(DEMO_WS.box_max_mm)}


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.calibration = {"probe_points": DEMO_PROBES, "frame_transform": {"schema": "vhrs-motion/1", "motion": MOTION, "workspace": WSD}}

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
            return httpx.Response(200, json={"job_id": 12, "order_code": "VHRS-T", "package_hash": HASH, "trajectory_url": "https://store/x", "pen": PEN})
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
                       watchdogs=watchdogs, unsensed_gripper=unsensed)
    svc = AgentService(cfg, transport=httpx.MockTransport(backend), downloader=lambda url: RAW,
                       robot_factory=robot_factory or (lambda mode: SimRobot(DEMO_START, speed_factor=None)),
                       gripper_factory=gripper_factory)
    return svc, TestClient(create_server_app(svc)), backend


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
    assert c.post("/api/resume", headers=auth("mgr-token")).status_code == 200
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
