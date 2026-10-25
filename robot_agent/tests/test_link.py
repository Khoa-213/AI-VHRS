"""The agent's outbound link: it pulls commands from the backend, executes them, answers each once, streams frames, and pauses
after the current stroke when the link is lost. The backend is a fake (httpx.MockTransport); robots are software robots.
Nothing moves a real robot."""
import json
import time
import uuid

import httpx
import pytest

from vhrs_agent.link import LinkClient
from vhrs_agent.port import Mode
from vhrs_agent.server import AgentService, ServerConfig
from vhrs_agent.sim import SimRobot
from test_server_api import DEMO_START, RAW, FakeBackend, USERS

KEY = "vhrs_ak_testkey"
USERS[KEY] = {"id": 5, "role": "TECHNICAL_STAFF", "full_name": "Ky Thuat"}      # the key acts as the job's technician on /technician/*


class LinkBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.queue: list[dict] = []
        self.results: dict[str, dict] = {}
        self.frames: list[dict] = []
        self.down = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/api/v1")
        if self.down:
            raise httpx.ConnectError("backend unreachable", request=req)
        if path == "/agent/sync":
            body = json.loads(req.content)
            self.frames += body.get("frames", [])
            self.last_status = body["status"]
            out, self.queue = self.queue, []
            return httpx.Response(200, json={"commands": out, "server_time": "2026-10-24T00:00:00Z", "robot_id": 3})
        if path.startswith("/agent/commands/") and path.endswith("/result"):
            cid = path.split("/")[3]
            self.results[cid] = json.loads(req.content)
            return httpx.Response(200, json={"id": cid})
        return super().__call__(req)

    def send(self, kind, job_id=12, **params):
        cid = str(uuid.uuid4())
        self.queue.append({"id": cid, "kind": kind, "job_id": job_id, "params": params, "expires_at": "2099-01-01T00:00:00Z"})
        return cid


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(tmp_path, *, speed=None, modes=("mock", "sim"), grace=6.0):
    be = LinkBackend()
    cfg = ServerConfig(backend_url="https://be.test", modes=modes, run_dir=tmp_path, link_loss_grace_s=grace,
                       sim={"tool_offset_mm": 250.0, "table_z_mm": 19.0, "start_mm": list(DEMO_START), "speed_factor": speed, "yaw_deg": 0.0})
    svc = AgentService(cfg, transport=httpx.MockTransport(be), downloader=lambda url: RAW,
                       robot_factory=lambda mode: SimRobot(DEMO_START, speed_factor=speed))
    clock = Clock()
    link = LinkClient(svc, key=KEY, transport=httpx.MockTransport(be), clock=clock)
    return svc, link, be, clock


def wait(pred, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    raise AssertionError("condition not reached")


def run_to_end(link, be, cid=None):
    wait(lambda: not link.svc._busy)


def test_load_and_preflight_are_answered_once_with_the_scene(tmp_path):
    svc, link, be, _ = make(tmp_path)
    load = be.send("LOAD")
    link.tick()
    r = be.results[load]
    assert r["ok"] is True and r["result"]["validation"]["passed"] is True and r["result"]["authorization_token"].startswith("AUTHORIZE-12-")
    assert r["result"]["scene"]["pages"][0]["strokes"] and r["result"]["scene"]["frame"]
    pre = be.send("PREFLIGHT", mode="SIM")
    link.tick()
    assert be.results[pre]["ok"] is True and be.results[pre]["result"]["ok"] is True
    bad = be.send("PREFLIGHT", job_id=99, mode="SIM")
    link.tick()
    assert be.results[bad]["ok"] is False and be.results[bad]["error_code"] == "JOB_NOT_LOADED"


def test_a_run_is_started_by_command_streams_frames_and_finishes(tmp_path):
    svc, link, be, _ = make(tmp_path)
    be.send("LOAD")
    link.tick()
    dry = be.send("DRY_RUN", mode="SIM")
    link.tick()
    assert be.results[dry]["ok"] is True
    run_to_end(link, be)
    run = be.send("RUN", mode="SIM")
    link.tick()
    assert be.results[run]["ok"] is True and be.results[run]["result"]["started"] in (True, False)
    link.tick()
    run_to_end(link, be)
    link.tick()
    assert svc.last["result"]["state"] == "DONE"
    assert be.last_status["mode"] in ("SIM", "MOCK") and be.last_status["busy"] is False
    assert any(f.get("joints_deg") is not None or f.get("tcp") for f in be.frames)


def test_control_commands_need_a_run_and_act_on_it(tmp_path):
    svc, link, be, _ = make(tmp_path, speed=20.0)
    stop = be.send("STOP")
    link.tick()
    assert be.results[stop]["ok"] is False and be.results[stop]["error_code"] == "NO_RUN_ACTIVE"
    be.send("LOAD")
    link.tick()
    be.send("DRY_RUN", mode="SIM")
    link.tick()
    run_to_end(link, be)
    be.send("RUN", mode="SIM")
    link.tick()
    pause, resume, stop2 = be.send("PAUSE"), be.send("RESUME"), be.send("STOP")
    link.tick()
    assert [be.results[c]["ok"] for c in (pause, resume, stop2)] == [True, True, True]
    run_to_end(link, be)
    assert svc.last["result"]["state"] == "STOPPED"


def test_real_mode_cannot_be_started_from_the_backend_alone(tmp_path):
    svc, link, be, _ = make(tmp_path, modes=("mock", "sim", "real"))
    be.send("LOAD")
    link.tick()
    run = be.send("RUN", mode="REAL", authorization="AUTHORIZE-12-deadbeef")
    link.tick()
    r = be.results[run]
    assert r["ok"] is False and r["error_code"] == "REAL_NOT_ENABLED_ON_SITE"        # no on-site real-enable file
    run2 = be.send("RUN", mode="REAL", authorization="AUTHORIZE-12-deadbeef")
    svc.cfg.modes = ("mock", "sim")
    link.tick()
    assert be.results[run2]["error_code"] == "MODE_DISABLED"
    assert svc._busy is False


def test_losing_the_link_while_writing_pauses_after_the_stroke_and_reports_when_back(tmp_path):
    svc, link, be, clock = make(tmp_path, speed=6.0, grace=6.0)
    be.send("LOAD")
    link.tick()
    be.send("DRY_RUN", mode="SIM")
    link.tick()
    run_to_end(link, be)
    be.send("RUN", mode="SIM")
    link.tick()
    wait(lambda: svc.hub.snapshot.state == "WRITING" and svc.hub.snapshot.stroke >= 1)
    be.down = True
    link.tick()                                                  # first failure, inside the grace period: nothing happens
    assert link.link_lost is False
    clock.t += 7.0                                               # quiet for longer than the grace period
    link.tick()
    assert link.link_lost is True
    wait(lambda: svc.hub.snapshot.state == "PAUSED")
    assert svc._busy is True                                     # paused, not abandoned: the job can be resumed
    stroke_at_pause = svc.hub.snapshot.stroke
    assert any(a["code"] == "BACKEND_LINK_LOST" and a["level"] == 3 for a in svc.hub.snapshot.alerts)   # orange, shown locally
    time.sleep(0.5)
    assert svc.hub.snapshot.stroke == stroke_at_pause            # no further strokes while the link is gone

    be.down = False
    be.calls.clear()
    link.tick()
    assert link.lost_reported is True
    assert any(m == "POST" and p.endswith("/alerts") and b["code"] == "BACKEND_LINK_LOST" for m, p, b in be.calls)   # now the backend knows
    assert svc.hub.snapshot.state == "PAUSED"                    # it does NOT resume by itself
    resume = be.send("RESUME")
    link.tick()
    assert be.results[resume]["ok"] is True
    run_to_end(link, be)
    assert svc.last["result"]["state"] == "DONE"


def test_align_start_moves_to_the_fixed_start_and_real_needs_the_site_switch(tmp_path):
    svc, link, be, _ = make(tmp_path, modes=("mock", "sim", "real"))
    be.send("LOAD")
    link.tick()
    ok = be.send("ALIGN_START", mode="SIM")
    link.tick()
    r = be.results[ok]
    assert r["ok"] is True and r["result"]["mode"] == "sim" and len(r["result"]["target_mm"]) == 3
    assert svc._busy is False and svc.align_ctl is None
    real = be.send("ALIGN_START", mode="REAL", authorization="AUTHORIZE-12-deadbeef")
    link.tick()
    assert be.results[real]["ok"] is False and be.results[real]["error_code"] == "REAL_NOT_ENABLED_ON_SITE"      # no on-site file
    assert svc._busy is False


def test_align_start_from_a_pen_that_rests_on_the_paper_lifts_straight_up_first(tmp_path):
    svc, link, be, _ = make(tmp_path)
    made = []

    def low(mode):
        r = SimRobot((-250.0, -74.0, 20.0), speed_factor=None)         # exactly on the sheet plane of the demo calibration
        made.append(r)
        return r

    svc.robot_factory = low
    be.send("LOAD")
    link.tick()
    cid = be.send("ALIGN_START", mode="SIM")
    link.tick()
    r = be.results[cid]
    assert r["ok"] is True and r["result"]["lifted_first"] is True and r["result"]["lift_mm"] == pytest.approx(5.5, abs=0.6)   # demo pen-up height 5 mm + 0.5
    assert made[0].commands.count("align_to") == 2                    # up, then to the start


def test_a_configured_start_point_is_used_for_align_and_the_return(tmp_path):
    svc, link, be, _ = make(tmp_path)
    svc.cfg.start_point_mm = [-300.0, 0.0, 60.0]                      # inside the demo box and above the demo sheet
    be.send("LOAD")
    link.tick()
    cid = be.send("ALIGN_START", mode="SIM")
    link.tick()
    assert be.results[cid]["ok"] is True and be.results[cid]["result"]["target_mm"] == [-300.0, 0.0, 60.0]
    svc.cfg.start_point_mm = [-300.0, 0.0]                             # a typo does not move anything
    cid = be.send("ALIGN_START", mode="SIM")
    link.tick()
    assert be.results[cid]["ok"] is False and be.results[cid]["error_code"] == "INVALID_CONFIG"
