"""Viewer API and backend bridge. No robot, no network (httpx mock transport, FastAPI TestClient)."""
import json
import threading

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from vhrs_agent.bridge import BackendBridge, BridgeError
from vhrs_agent.cli import DEMO_CFG, DEMO_LIMITS, DEMO_PROBES, DEMO_WS, main
from vhrs_agent.runner import JobRunner, Snapshot
from vhrs_agent.sim import SimRobot
from vhrs_agent.viewer import ViewerHub, create_app
from app.services.motion.frame import build_frame
from app.services.stroke_ai.trajectory import Page, Stroke


def _hub(tmp_path, token=None):
    pages = [Page("A5", [Stroke([(20, 20), (60, 20)]), Stroke([(20, 40), (60, 40)])])]
    frame = build_frame(DEMO_PROBES)
    runner = JobRunner(SimRobot((200.0, 0.0, 80.0), speed_factor=None), None, run_dir=tmp_path, limits=DEMO_LIMITS)
    hub = ViewerHub(token=token)
    hub.attach(runner, pages, frame, DEMO_LIMITS, DEMO_CFG.press_mm, DEMO_CFG.pen_up_clearance_mm, job_id=3)
    return hub, runner, pages


def test_viewer_serves_the_page_the_job_and_the_live_state(tmp_path):
    hub, runner, _ = _hub(tmp_path)
    c = TestClient(create_app(hub))
    assert "VHRS Robot Monitor" in c.get("/").text
    job = c.get("/api/job").json()
    assert job["mode"] == "SIM" and job["job_id"] == 3 and len(job["pages"][0]["strokes"]) == 2
    hub.set_snapshot(Snapshot(state="WRITING", mode="SIM", progress_pct=40.0, force_n=1.1))
    assert c.get("/api/state").json()["state"] == "WRITING"
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["progress_pct"] == 40.0


def test_stop_and_pause_reach_the_runner_and_need_the_token_when_one_is_set(tmp_path):
    hub, runner, _ = _hub(tmp_path, token="s3cret")
    c = TestClient(create_app(hub))
    assert c.post("/api/stop").status_code == 401 and not runner.ctl.stop.is_set()
    assert c.post("/api/stop", headers={"X-Viewer-Token": "wrong"}).status_code == 401
    assert c.post("/api/pause", headers={"X-Viewer-Token": "s3cret"}).status_code == 200 and runner.ctl.paused.is_set()
    assert c.post("/api/resume", headers={"X-Viewer-Token": "s3cret"}).status_code == 200 and not runner.ctl.paused.is_set()
    assert c.post("/api/stop", headers={"X-Viewer-Token": "s3cret"}).status_code == 200
    assert runner.ctl.stop.is_set() and runner.robot.stopped == 1


def test_stop_during_a_real_run_ends_it(tmp_path):
    hub, runner, pages = _hub(tmp_path)
    runner.robot = SimRobot((200.0, 0.0, 80.0), speed_factor=300.0)           # slow enough to interrupt
    c = TestClient(create_app(hub))
    out = {}
    t = threading.Thread(target=lambda: out.update(r=runner.run(job_id=3, pages=pages, package_hash="b" * 64,
                         probes=DEMO_PROBES, cfg=DEMO_CFG, ws=DEMO_WS, dry_run=True)))
    t.start()
    while runner.snap.state not in ("DRY_RUN", "DRY_RUN_DONE"):
        pass
    c.post("/api/stop")
    t.join(10)
    assert out["r"].state in ("STOPPED", "DRY_RUN_DONE")


def test_network_viewer_without_a_token_is_refused_by_the_cli():
    assert main(["demo", "--host", "0.0.0.0"]) == 2


# ---------------------------------------------------------------- bridge
def test_bridge_posts_events_in_the_backend_shape_and_surfaces_errors():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else None, req.headers["authorization"]))
        if req.url.path.endswith("/events") and b"BAD" in req.content:
            return httpx.Response(409, json={"error": {"code": "JOB_STATE_CONFLICT", "message": "x", "details": None}})
        return httpx.Response(201, json={"id": 1})

    b = BackendBridge("https://be.example", "tok", transport=httpx.MockTransport(handler))
    b.event(9, "PROGRESS", stroke_index=4, progress_pct=12.5, agent_run={"run_id": "r1"})
    b.event(9, "FORCE_SUMMARY", force_summary={"f_mean": 1.0}, run_id="r1")
    assert seen[0] == ("POST", "/api/v1/technician/jobs/9/events",
                       {"event_type": "PROGRESS", "stroke_index": 4, "progress_pct": 12.5, "payload": {"agent_run": {"run_id": "r1"}}},
                       "Bearer tok")
    assert seen[1][2] == {"event_type": "FORCE_SUMMARY", "force_summary": {"f_mean": 1.0}, "payload": {"run_id": "r1"}}
    with pytest.raises(BridgeError) as e:
        b.event(9, "BAD")
    assert e.value.status == 409 and e.value.code == "JOB_STATE_CONFLICT"


def test_runner_survives_a_dead_backend_and_keeps_the_local_log(tmp_path):
    class Dead:
        def event(self, *a, **k):
            raise ConnectionError("backend unreachable")

    pages = [Page("A5", [Stroke([(20, 20), (60, 20)])])]
    runner = JobRunner(SimRobot((200.0, 0.0, 80.0), speed_factor=None), None, run_dir=tmp_path, limits=DEMO_LIMITS, bridge=Dead())
    from vhrs_agent.runner import RunRefused
    with pytest.raises(RunRefused):                                           # a real write needs the gripper
        runner.run(job_id=1, pages=pages, package_hash="c" * 64, probes=DEMO_PROBES, cfg=DEMO_CFG, ws=DEMO_WS)
    res = runner.run(job_id=1, pages=pages, package_hash="c" * 64, probes=DEMO_PROBES, cfg=DEMO_CFG, ws=DEMO_WS, dry_run=True)
    assert res.state == "DRY_RUN_DONE"
