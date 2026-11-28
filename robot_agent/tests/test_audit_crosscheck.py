"""Cross-check of the two audits, 2026-11-28 (A06): a run's result is kept until the backend has it.

Before, a failed "run closed" call was only written to the run log, so the backend held the run open for ever.
No robot and no backend here: the bridge is a stand-in.
"""
import json

from vhrs_agent.bridge import BridgeError
from vhrs_agent.ops import CloseOutbox, OpsReporter


class Bridge:
    """Records what reaches the backend. `fail` is raised by every call while it is set."""

    def __init__(self):
        self.fail: Exception | None = None
        self.opened: list[str] = []
        self.closed: list[tuple[str, dict]] = []

    def open_run(self, job_id, **fields):
        if self.fail:
            raise self.fail
        self.opened.append(fields["run_id"])

    def close_run(self, run_id, **fields):
        if self.fail:
            raise self.fail
        self.closed.append((run_id, fields))


def _reporter(tmp_path, bridge):
    box = CloseOutbox(tmp_path / "pending_closes.json")
    return OpsReporter(bridge, robot_id=1, outbox=box), box


def _open(ops, run_id):
    return ops.open_run(7, run_id=run_id, mode="SIM", dry_run=False, authorized=False, digest="d", total=10, robot_info=None,
                        agent_version="t")


def test_a_result_that_could_not_be_sent_waits_and_is_sent_when_the_link_works(tmp_path):
    bridge = Bridge()
    ops, box = _reporter(tmp_path, bridge)
    assert _open(ops, "run-1") and box.pending() == []                     # open, nothing to send yet
    bridge.fail = ConnectionError("network is down")
    ops.close_run("run-1", result="DONE", completed=10, total=10, summary={"duration_s": 3})
    waiting = box.pending()
    assert [r["run_id"] for r in waiting] == ["run-1"] and waiting[0]["fields"]["result"] == "DONE"
    assert box.flush(bridge.close_run) == 0 and len(box.pending()) == 1     # still down: it stays

    bridge.fail = None
    again = CloseOutbox(tmp_path / "pending_closes.json")                   # the agent was restarted in between
    assert again.flush(bridge.close_run) == 1 and again.pending() == []
    assert bridge.closed == [("run-1", {"result": "DONE", "completed_strokes": 10, "total_strokes": 10, "summary": {"duration_s": 3}})]


def test_a_result_that_was_sent_leaves_nothing_behind(tmp_path):
    bridge = Bridge()
    ops, box = _reporter(tmp_path, bridge)
    _open(ops, "run-2")
    ops.close_run("run-2", result="STOPPED", completed=4, total=10, summary=None)
    assert box.pending() == [] and json.loads((tmp_path / "pending_closes.json").read_text()) == []
    assert box.recover() == 0


def test_an_answer_the_backend_already_has_is_not_sent_for_ever(tmp_path):
    bridge = Bridge()
    ops, box = _reporter(tmp_path, bridge)
    _open(ops, "run-3")
    bridge.fail = BridgeError(409, "RUN_ALREADY_CLOSED", "closed by a person as UNKNOWN, then as something else")
    ops.close_run("run-3", result="DONE", completed=10, total=10, summary=None)
    assert box.pending() == []                                              # a retry could not change it: dropped at once

    box.add("run-4", {"result": "FAULT", "completed_strokes": 1, "total_strokes": 10, "summary": None})
    assert box.flush(bridge.close_run) == 1 and box.pending() == []


def test_a_run_the_previous_process_left_open_is_reported_as_unknown(tmp_path):
    bridge = Bridge()
    ops, box = _reporter(tmp_path, bridge)
    _open(ops, "run-5")                                                     # ... and the agent is killed here
    restarted = CloseOutbox(tmp_path / "pending_closes.json")
    assert restarted.pending() == [] and restarted.recover() == 1
    assert restarted.flush(bridge.close_run) == 1
    run_id, fields = bridge.closed[0]
    assert run_id == "run-5" and fields["result"] == "UNKNOWN" and fields["completed_strokes"] == 0
    assert "restarted" in fields["summary"]["reason"]


def test_a_refused_run_is_closed_by_the_backend_and_is_not_tracked(tmp_path):
    bridge = Bridge()
    ops, box = _reporter(tmp_path, bridge)
    ops.open_run(7, run_id="run-6", mode="REAL", dry_run=False, authorized=False, digest=None, total=0, robot_info=None,
                 agent_version="t", refused_reason="DRY_RUN_REQUIRED: no rehearsal")
    assert CloseOutbox(tmp_path / "pending_closes.json").recover() == 0


# ---------------------------------------------------------------------------------------------- A08
def test_the_real_robot_writes_only_a_signed_package_whatever_the_station_setting(tmp_path):
    """`require_signed_packages` is off by default (jobs older than the signing still load and can be simulated). It must not
    decide for the REAL robot: an unsigned package is rehearsed pen-up at most, never written."""
    from test_server_api import auth, enable, real_service, wait_idle

    svc, c, be = real_service(tmp_path)
    be.signed = False                                                       # a job scheduled before packages were signed
    assert svc.cfg.require_signed_packages is False
    loaded = c.post("/api/jobs/12/load", headers=auth()).json()
    assert loaded["signed"] is False
    token = loaded["authorization_token"]
    enable(tmp_path)
    assert c.post("/api/jobs/12/dry-run", headers=auth(), json={"mode": "real", "authorization": token}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DRY_RUN_DONE"        # pen-up rehearsal: nothing is written
    r = c.post("/api/jobs/12/run", headers=auth(), json={"mode": "real", "authorization": token})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PACKAGE_NOT_SIGNED", r.text
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"}).status_code == 202   # the simulator is not held back
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"


# ---------------------------------------------------------------------------------------------- pen-mount move (new on main)
def test_the_real_pen_mount_descent_obeys_the_station_locks(tmp_path):
    """The pen-mount move brings the tool point DOWN onto the paper at a height computed from the hand-typed probe points,
    outside a run. It must pass the same station locks as a REAL run's preflight."""
    import pytest
    from test_server_api import auth, enable, real_service
    from vhrs_agent.server import ApiError

    svc, c, _ = real_service(tmp_path)
    token = c.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    enable(tmp_path)
    ctx = svc.jobs[12]

    def code(**change):
        saved = (list(ctx.probes), svc.cfg.station_limits)
        try:
            if "probes" in change:
                ctx.probes = change["probes"]
            if "limits" in change:
                svc.cfg.station_limits = change["limits"]
            with pytest.raises(ApiError) as e:
                svc.do_align(ctx, "real", token, corner="TL")
            return e.value.code
        finally:
            ctx.probes, svc.cfg.station_limits = saved

    p = list(ctx.probes)
    assert code(limits=None) == "STATION_LIMITS_UNCONFIGURED"
    assert code(probes=p[:3]) == "PROBE_CHECK_POINT_REQUIRED"
    assert code(probes=[p[0], p[2], p[1], p[3]]) == "PROBE_ORDER_MIRRORED"
    assert code(limits={"z_floor_mm": 60.0, "max_press_mm": 4.0}) == "BELOW_Z_FLOOR"     # the "paper" is under the station's floor
    assert svc._busy is False                                                            # refused before anything was claimed or moved

    ok = svc.do_align(ctx, "real", token, corner="TL")                                   # with the locks satisfied it works as before
    assert ok["on_paper"] is True and ok["corner"] == "TL"
    svc.cfg.station_limits = None
    sim = svc.do_align(ctx, "sim", None, corner="TL")                                    # the simulator is not held back
    assert sim["on_paper"] is True


# ---------------------------------------------------------------------------------------------- D03 / 1a
def test_the_real_robot_is_switched_on_and_started_from_the_workstation_only(tmp_path):
    """Owner decision 2026-11-28. Even when the agent is started for the LAN, another computer may watch, simulate and stop,
    but it cannot switch REAL on, start the real arm, or even see the confirmation code."""
    from fastapi.testclient import TestClient
    from test_server_api import auth, enable, real_service, wait_idle
    from vhrs_agent.server import create_server_app

    svc, here, _ = real_service(tmp_path)
    far = TestClient(create_server_app(svc), client=("192.168.1.50", 50000))            # another computer on the LAN

    loaded_far = far.post("/api/jobs/12/load", headers=auth()).json()
    assert "authorization_token" not in loaded_far and loaded_far["plan_digest"]       # everything but the code
    assert "authorization_token" not in far.get("/api/jobs/12", headers=auth()).json()
    token = here.post("/api/jobs/12/load", headers=auth()).json()["authorization_token"]
    assert token.startswith("AUTHORIZE-12-")

    def code(r):
        return r.status_code, r.json()["error"]["code"]

    assert code(far.post("/api/jobs/12/real-enable", headers=auth(), json={"minutes": 5})) == (403, "REAL_ONLY_AT_WORKSTATION")
    enable(tmp_path)                                                                    # switched on at the workstation
    body = {"mode": "real", "authorization": token}
    for path in ("dry-run", "run", "align-start"):
        assert code(far.post(f"/api/jobs/12/{path}", headers=auth(), json=body)) == (403, "REAL_ONLY_AT_WORKSTATION"), path
    assert svc._busy is False

    assert far.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"}).status_code == 202   # simulating from afar is fine
    assert wait_idle(far)["last"]["result"]["state"] == "DONE"
    aligned = here.post("/api/jobs/12/align-start", headers=auth(), json={"mode": "sim"})          # the local route the page uses
    assert aligned.status_code == 200 and aligned.json()["mode"] == "sim", aligned.text
    assert here.post("/api/jobs/12/dry-run", headers=auth(), json=body).status_code == 202         # and REAL at the workstation works
    assert wait_idle(here)["last"]["result"]["state"] == "DRY_RUN_DONE"


def test_a_waiting_run_result_is_also_sent_when_a_job_is_loaded(tmp_path):
    """Loading a job is one more moment to send a run result that is still waiting, with the agent's own key."""
    from test_server_api import auth, make

    svc, c, be = make(tmp_path)
    svc.run_key = lambda: "other-token"                                                 # the agent's own key (the link sets it)
    svc.closes.add("run-old-1", {"result": "STOPPED", "completed_strokes": 3, "total_strokes": 10, "summary": None})
    assert c.post("/api/jobs/12/load", headers=auth()).status_code == 200
    assert svc.closes.pending() == []
    assert ("PATCH", "/technician/runs/run-old-1", {"result": "STOPPED", "completed_strokes": 3, "total_strokes": 10}) in be.calls


def test_resuming_a_real_run_is_for_the_technician_at_the_workstation(tmp_path):
    """Resume and "paper changed" put the arm back in motion. For a REAL run they are taken from this computer only, never
    through a reverse proxy, and never from a Manager (who may watch and halt, as on the backend)."""
    from fastapi.testclient import TestClient
    from test_server_api import auth, real_service
    from vhrs_agent.server import create_server_app

    svc, here, _ = real_service(tmp_path)
    far = TestClient(create_server_app(svc), client=("192.168.1.50", 50000))
    svc.current = {"job_id": 12, "mode": "real", "dry_run": False}                     # a REAL run is going on

    for path in ("/api/resume", "/api/paper-changed"):
        r = far.post(path, headers=auth())
        assert r.status_code == 403 and r.json()["error"]["code"] == "REAL_ONLY_AT_WORKSTATION", path
        proxied = here.post(path, headers={**auth(), "X-Forwarded-For": "192.168.1.50"})
        assert proxied.status_code == 403 and proxied.json()["error"]["code"] == "REAL_ONLY_AT_WORKSTATION", path
    assert here.post("/api/paper-changed", headers=auth()).status_code == 200            # at the workstation
    assert here.post("/api/resume", headers=auth("mgr-token")).status_code == 403        # a Manager does not resume
    for path in ("/api/pause", "/api/stop"):                                             # halting is never tied to a place
        r = far.post(path, headers=auth("mgr-token"))
        assert r.status_code != 403, (path, r.status_code)

    svc.current = {"job_id": 12, "mode": "sim", "dry_run": False}                       # a simulated run may be resumed from afar
    assert far.post("/api/paper-changed", headers=auth()).status_code == 200


# ---------------------------------------------------------------------------------------------- L2
def test_runs_are_reported_with_the_agents_key_whoever_pressed_the_button(tmp_path):
    """The backend takes the opening and closing of a run from the agent's key only. A person starts the run on the page with
    their own login; the record of it still goes out under the agent's key."""
    from test_server_api import auth, make, wait_idle

    svc, c, be = make(tmp_path)
    svc.run_key = lambda: "other-token"                                                 # stands for the agent key
    c.post("/api/jobs/12/load", headers=auth())                                         # the person: tech-token
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"}).status_code == 202
    assert wait_idle(c)["last"]["result"]["state"] == "DONE"
    run_calls = [(path, tok) for path, tok in be.tokens if path.endswith("/runs") or path.startswith("/technician/runs/")]
    assert len(run_calls) >= 2 and {tok for _, tok in run_calls} == {"other-token"}, run_calls
    assert ("/technician/jobs/12/package", "tech-token") in be.tokens                   # everything else stays the person's


def test_without_an_agent_key_the_persons_login_is_all_there_is(tmp_path):
    """No backend link, no key: the run record is sent with what the agent has (the backend refuses it since L2, so the
    simulator runs unrecorded and the REAL robot does not start)."""
    from test_server_api import auth, make, wait_idle

    svc, c, be = make(tmp_path)
    assert svc.run_key is None
    c.post("/api/jobs/12/load", headers=auth())
    assert c.post("/api/jobs/12/run", headers=auth(), json={"mode": "sim"}).status_code == 202
    wait_idle(c)
    assert {tok for path, tok in be.tokens if path.endswith("/runs")} == {"tech-token"}
