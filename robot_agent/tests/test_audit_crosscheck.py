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
