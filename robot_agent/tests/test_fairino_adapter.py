"""Fairino adapter against a FAKE SDK object (no network, no robot). Checks call discipline, not robot behaviour."""
import threading
import time

import numpy as np
import pytest

from vhrs_agent.fairino_robot import FairinoConfig, FairinoRobot, _SDKWorker
from vhrs_agent.port import CommunicationLost, Control, RobotError, StopRequested

MOTION_CALLS = {"ServoCart", "ServoMoveStart", "ServoMoveEnd", "MoveL", "MoveJ", "MoveCart", "RobotEnable", "Mode",
                "SetSpeed", "SetDO", "SetToolDO", "ResetAllError", "DragTeachSwitch"}


class FakeRPC:
    def __init__(self, controller="V3.8.25-QX", model="FR3 V6.0", tool=1, stuck=None, ik_code=0, errors=(0, 0)):
        self.calls, self.controller, self.model, self.tool = [], controller, model, tool
        self.stuck, self.ik_code, self.errors = stuck, ik_code, errors
        self.release = threading.Event()

    def _log(self, n, *a):
        self.calls.append((n, a))
        if self.stuck == n:
            self.release.wait(3)

    def GetSoftwareVersion(self):
        self._log("GetSoftwareVersion")
        return 0, self.model, "v3.8.5.1", self.controller

    def GetSDKVersion(self):
        self._log("GetSDKVersion")
        return 0, ["SDK:V2.1.7", "Robot:V3.8.7"]

    def GetActualTCPNum(self, flag=1):
        self._log("GetActualTCPNum")
        return 0, self.tool

    def GetActualTCPPose(self, flag=1):
        self._log("GetActualTCPPose")
        return 0, getattr(self, "tcp_pose", [300.0, 0.0, 25.0, 180.0, 0.0, 0.0])

    def GetActualToolFlangePose(self, flag=1):
        self._log("GetActualToolFlangePose")
        return 0, [300.0, 0.0, 125.0, 180.0, 0.0, 0.0]

    def GetJointSoftLimitDeg(self, flag=1):
        self._log("GetJointSoftLimitDeg")
        return 0, [-170, 170] * 6

    def GetRobotErrorCode(self):
        return 0, list(self.errors)

    def GetRobotEmergencyStopState(self):
        return 0, 0

    def GetInverseKin(self, t, pose, cfg=-1):
        self._log("GetInverseKin", t, pose)
        return (self.ik_code, [0, -30, 90, 0, 60, 0]) if self.ik_code == 0 else (self.ik_code, None)

    def ServoMoveStart(self):
        self._log("ServoMoveStart")
        return 0

    def ServoMoveEnd(self):
        self._log("ServoMoveEnd")
        return 0

    def ServoCart(self, mode, pose, gain, acc, vel, cmdT, filterT, g):
        self._log("ServoCart", pose)
        self.tcp_pose = list(pose)
        return 0

    def StopMotion(self):
        self.calls.append(("StopMotion", ()))
        return 0

    def CloseRPC(self):
        self.calls.append(("CloseRPC", ()))


def make(rpc, **kw):
    cfg = FairinoConfig(ip="192.168.58.2", tool_id=1, orientation_deg=(180.0, 0.0, 0.0), servo_cmd_period_s=0.004, **kw)
    return FairinoRobot(cfg, sdk_factory=lambda ip: rpc, stop_sender=rpc.StopMotion)


def test_connect_only_reads_and_never_calls_a_motion_or_enable_function():
    rpc = FakeRPC()
    info = make(rpc).connect()
    assert info.controller_version == "V3.8.25-QX" and "FR3" in info.model and info.mode.value == "REAL"
    assert not ({n for n, _ in rpc.calls} & MOTION_CALLS)


@pytest.mark.parametrize("rpc,code", [(FakeRPC(model="Franka Research 3"), "WRONG_ROBOT"),
                                      (FakeRPC(controller="V4.0.0"), "CONTROLLER_UNSUPPORTED"),
                                      (FakeRPC(tool=0), "TOOL_MISMATCH")])
def test_wrong_robot_controller_or_tool_is_refused(rpc, code):
    with pytest.raises(RobotError) as e:
        make(rpc).connect()
    assert e.value.code == code


def test_unconfigured_servo_period_refuses_to_connect():
    cfg = FairinoConfig(ip="1.2.3.4", tool_id=1, orientation_deg=(0, 0, 0), servo_cmd_period_s=0.0)
    with pytest.raises(RobotError) as e:
        FairinoRobot(cfg, sdk_factory=lambda ip: FakeRPC()).connect()
    assert e.value.code == "UNCONFIGURED"


def test_tcp_offset_is_checked_against_the_measured_pen_length():
    make(FakeRPC(), tcp_offset_mm=100.0).connect()
    with pytest.raises(RobotError) as e:
        make(FakeRPC(), tcp_offset_mm=140.0).connect()
    assert e.value.code == "TCP_OFFSET_MISMATCH"


def test_reachability_uses_the_controllers_inverse_kinematics_without_moving():
    rpc = FakeRPC()
    r = make(rpc)
    r.connect()
    assert r.check_reachable(np.array([[300.0, 0, 25], [310.0, 0, 25]])) == []
    assert not ({n for n, _ in rpc.calls} & MOTION_CALLS)
    bad = FakeRPC(ik_code=14)
    r2 = make(bad)
    r2.connect()
    assert "no inverse-kinematics solution" in r2.check_reachable(np.array([[300.0, 0, 25]]))[0]


def test_heartbeat_reflects_controller_errors():
    ok = make(FakeRPC())
    ok.connect()
    assert ok.heartbeat()
    err = make(FakeRPC(errors=(112, 3)))
    err.connect()
    assert not err.heartbeat()


def test_execute_streams_targets_at_the_requested_spacing_and_pairs_start_with_end():
    rpc = FakeRPC()
    r = make(rpc)
    r.connect()
    seen = []
    pts = np.array([[300.0, 0.0, 25.0], [300.0, 10.0, 25.0]])
    r.execute(pts, np.array([200.0, 200.0]), Control(), lambda p, t: seen.append(p.copy()))
    names = [n for n, _ in rpc.calls]
    assert names.index("ServoMoveStart") < names.index("ServoCart") < names.index("ServoMoveEnd")
    assert all(name == "GetActualTCPPose" for name in names[names.index("ServoMoveEnd") + 1:])
    ys = [p[1] for p in seen]
    assert ys[-1] == pytest.approx(10.0) and all(b >= a for a, b in zip(ys, ys[1:]))
    assert max(np.diff(ys)) == pytest.approx(200.0 * 0.004, abs=1e-6)      # v * period
    sent = [a[0] for n, a in rpc.calls if n == "ServoCart"]
    assert all(p[3:] == [180.0, 0.0, 0.0] for p in sent)                    # orientation held, never converted


def test_a_stuck_sdk_call_is_a_lost_link_stops_the_robot_and_is_never_repeated():
    rpc = FakeRPC(stuck="ServoCart")
    r = make(rpc, call_deadline_s=0.2)
    r.connect()
    with pytest.raises(CommunicationLost):
        r.execute(np.array([[300.0, 0.0, 25.0], [300.0, 10.0, 25.0]]), np.array([50.0, 50.0]), Control(), lambda p, t: None)
    time.sleep(0.1)
    rpc.release.set()
    names = [n for n, _ in rpc.calls]
    assert names.count("ServoCart") == 1 and "StopMotion" in names
    assert not r.heartbeat()                                                # and the link stays down until reconnected


@pytest.mark.parametrize("cap", [0.1, 10.0])
def test_real_speed_cap_limits_every_streamed_target_including_the_first(cap):
    rpc = FakeRPC()
    robot = make(rpc, speed_cap_mm_s=cap)
    robot.connect()
    length = cap * 0.012
    robot.execute(np.array([[300.0, 0, 25], [300.0, length, 25]]), np.array([200.0, 200.0]),
                  Control(), lambda p, t: None)
    ys = [0.0] + [args[0][1] for name, args in rpc.calls if name == "ServoCart"]
    assert ys[-1] == pytest.approx(length)
    assert len(ys) >= 4
    assert max(np.diff(ys)) <= cap * robot.cfg.servo_cmd_period_s + 1e-9


@pytest.mark.parametrize("cap", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_speed_cap_is_refused_before_connecting_to_the_controller(cap):
    rpc = FakeRPC()
    with pytest.raises(RobotError) as err:
        make(rpc, speed_cap_mm_s=cap).connect()
    assert err.value.code == "INVALID_CONFIG" and not rpc.calls


def test_stop_request_sends_stop_motion():
    rpc = FakeRPC()
    r = make(rpc)
    r.connect()
    ctl = Control()
    ctl.request_stop("test")
    with pytest.raises(StopRequested):
        r.execute(np.array([[300.0, 0.0, 25.0], [300.0, 10.0, 25.0]]), np.array([50.0, 50.0]), ctl, lambda p, t: None)
    time.sleep(0.05)
    assert any(n == "StopMotion" for n, _ in rpc.calls)


def test_wrong_start_orientation_is_refused_before_any_servo_command():
    rpc = FakeRPC()
    rpc.GetActualTCPPose = lambda: (0, [300, 0, 25, 180, 0, -13.0])
    robot = make(rpc)
    robot.connect()
    with pytest.raises(RobotError) as readiness:
        robot.check_start_ready()
    assert readiness.value.code == "START_ORIENTATION_MISMATCH"
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert err.value.code == "START_ORIENTATION_MISMATCH"
    assert not ({name for name, _ in rpc.calls} & MOTION_CALLS)


def test_equivalent_wrapped_angles_do_not_cause_a_false_start_refusal():
    rpc = FakeRPC()
    rpc.GetActualTCPPose = lambda: (0, [300, 0, 25, -180, 0, 0])
    robot = make(rpc)
    robot.connect()
    robot.execute(np.array([[300, 0, 25], [300, .01, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert any(name == "ServoCart" for name, _ in rpc.calls)


def test_stale_start_position_is_refused_before_any_servo_command():
    rpc = FakeRPC()
    robot = make(rpc)
    robot.connect()
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[310, 0, 25], [311, 0, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert err.value.code == "START_POSITION_MISMATCH"
    assert not ({name for name, _ in rpc.calls} & MOTION_CALLS)


def test_rejected_servo_is_not_retried_and_reports_controller_fault_codes():
    rpc = FakeRPC(errors=(1, 28))
    def reject(*args):
        rpc._log("ServoCart", args[1])
        return 14
    rpc.ServoCart = reject
    robot = make(rpc)
    robot.connect()
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert "14" in err.value.message and "[1, 28]" in err.value.message
    assert err.value.details == {"code": 14, "controller_errors": [1, 28]}
    names = [name for name, _ in rpc.calls]
    assert names.count("ServoCart") == 1 and names[-1] == "ServoMoveEnd"
    time.sleep(.02)
    assert "StopMotion" in [name for name, _ in rpc.calls]


def test_connection_reuses_one_sdk_worker_and_closes_it():
    rpc, thread_ids = FakeRPC(), []
    original = rpc._log
    def log(name, *args):
        thread_ids.append(threading.get_ident())
        original(name, *args)
    rpc._log = log
    robot = make(rpc)
    robot.connect()
    robot.execute(np.array([[300, 0, 25], [300, .01, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    robot.read_tcp()
    worker = robot._worker
    robot.disconnect()
    worker.thread.join(1)
    assert len(set(thread_ids)) == 1 and thread_ids[0] != threading.get_ident()
    assert not worker.thread.is_alive()


def test_expired_queued_call_is_never_executed():
    worker = _SDKWorker()
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    sent = []
    def blocking():
        entered.set()
        release.wait(1)
    def first():
        try:
            worker.call(blocking, (), 2)
        finally:
            finished.set()
    threading.Thread(target=first, daemon=True).start()
    try:
        assert entered.wait(1)
        with pytest.raises(TimeoutError):
            worker.call(lambda: sent.append("expired motion"), (), .02)
        release.set()
        assert finished.wait(1)
        worker.call(lambda: None, (), 1)  # the expired request has now been skipped
        assert sent == []
    finally:
        release.set()
        worker.close()


class FakeClock:
    def __init__(self, oversleep=0):
        self.now, self.oversleep = 0.0, oversleep
    def counter(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds + self.oversleep
        self.oversleep = 0


def test_late_wakeup_stops_before_sending_another_target(monkeypatch):
    clock = FakeClock(oversleep=.020)
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = FakeRPC()
    robot = make(rpc)
    robot.connect()
    with pytest.raises(CommunicationLost) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert err.value.code == "STREAM_OVERRUN" and err.value.details["phase"] == "before_send"
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 1
    robot.disconnect()


def test_minor_delay_does_not_trigger_a_burst_of_catchup_targets(monkeypatch):
    clock, sent = FakeClock(), []
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = FakeRPC()
    def servo(*args):
        sent.append(clock.now)
        return 0
    rpc.ServoCart = servo
    def callback(p, t):
        if len(sent) == 1:
            clock.now += .006  # slower than one 4 ms period, below the stop threshold
    robot = make(rpc)
    robot.connect()
    robot.execute(np.array([[300, 0, 25], [300, .20, 25]]), np.array([10, 10]), Control(), callback)
    assert len(sent) >= 4 and min(np.diff(sent)) >= .004 - 1e-9
    robot.disconnect()


def test_slow_callback_keeps_the_existing_stop_threshold_and_records_phase(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = FakeRPC()
    robot = make(rpc)
    robot.connect()
    def callback(p, t):
        clock.now += .050
    with pytest.raises(CommunicationLost) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([10, 10]), Control(), callback)
    assert err.value.code == "STREAM_OVERRUN" and err.value.details["phase"] == "after_send"
    assert err.value.details["callback_ms"] == pytest.approx(50)
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 1
    robot.disconnect()


def test_next_segment_waits_for_delayed_tcp_feedback_without_resending_targets(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)

    class LaggingRPC(FakeRPC):
        def __init__(self):
            super().__init__()
            self.feedback = [300., 0., 25., 180., 0., 0.]
            self.ready_at = float("inf")
        def ServoMoveEnd(self):
            self.ready_at = clock.now + .08
            return super().ServoMoveEnd()
        def GetActualTCPPose(self, flag=1):
            self._log("GetActualTCPPose")
            if clock.now >= self.ready_at:
                self.feedback = self.tcp_pose.copy()
            return 0, self.feedback.copy()

    rpc = LaggingRPC()
    robot = make(rpc)
    robot.connect()
    for y in (0, 1):
        started = clock.now
        robot.execute(np.array([[300, y, 25], [300, y + 1, 25]]), np.array([200, 200]), Control(), lambda p, t: None)
        assert clock.now - started >= .18
        assert rpc.feedback[1] == y + 1
    commands = [args[0] for name, args in rpc.calls if name == "ServoCart"]
    assert [round(p[1], 3) for p in commands] == [.8, 1., 1.8, 2.]
    robot.disconnect()


def test_endpoint_that_never_arrives_times_out_without_resending_or_relaxing_start_guard(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = FakeRPC()
    rpc.GetActualTCPPose = lambda: (0, [300, 0, 25, 180, 0, 0])
    robot = make(rpc)
    robot.connect()
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([200, 200]), Control(), lambda p, t: None)
    assert err.value.code == "ENDPOINT_NOT_SETTLED"
    assert err.value.details["target_mm"] == [300, 1, 25] and clock.now < 2.1
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 2
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 1, 25], [300, 2, 25]]), np.array([200, 200]), Control(), lambda p, t: None)
    assert err.value.code == "START_POSITION_MISMATCH"
    assert err.value.details["distance_mm"] == 1
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 2
    robot.disconnect()


def test_endpoint_wait_honors_operator_stop_without_new_motion(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc, ctl = FakeRPC(), Control()
    def end():
        rpc._log("ServoMoveEnd")
        ctl.request_stop("operator stop while settling")
        return 0
    rpc.ServoMoveEnd = end
    robot = make(rpc)
    robot.connect()
    with pytest.raises(StopRequested):
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([200, 200]), ctl, lambda p, t: None)
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 2
    robot.disconnect()


def test_servo_end_error_does_not_report_success():
    rpc = FakeRPC()
    rpc.ServoMoveEnd = lambda: 14
    robot = make(rpc)
    robot.connect()
    with pytest.raises(RobotError, match="ServoMoveEnd"):
        robot.execute(np.array([[300, 0, 25], [300, .01, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    robot.disconnect()


def test_slow_sdk_records_execution_time_without_counting_emergency_stop_as_callback(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = FakeRPC()
    original = rpc.ServoCart
    def slow_servo(*args):
        clock.now += .028
        return original(*args)
    rpc.ServoCart = slow_servo
    robot = make(rpc)
    robot.connect()
    def stop_cost():
        clock.now += .007
    robot._best_effort_stop = stop_cost
    with pytest.raises(CommunicationLost) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([10, 10]), Control(), lambda p, t: None)
    assert err.value.code == "STREAM_OVERRUN"
    assert err.value.details["sdk_execution_ms"] == pytest.approx(28)
    assert err.value.details["lag_ms"] == pytest.approx(24)
    assert err.value.details["callback_ms"] == 0
    assert sum(name == "ServoCart" for name, _ in rpc.calls) == 1
    robot.disconnect()


def test_timing_probe_calls_only_read_methods():
    from scripts.inspect_robot_timing import probe
    rpc = FakeRPC()
    report = probe(rpc, iterations=3)
    assert report["ok"] and report["iterations"] == 3
    assert {name for name, _ in rpc.calls} == {"GetActualTCPPose", "GetSoftwareVersion"}
    assert report["controller_errors"] == (0, [0, 0])
    assert report["timing"]["total_ms"]["max"] >= report["timing"]["sdk_execution_ms"]["max"]


def test_stop_uses_independent_proxy_while_sdk_connection_is_busy(monkeypatch):
    import xmlrpc.client
    rpc = FakeRPC(stuck="ServoCart")
    robot = make(rpc)
    robot.connect()
    stopped, closed = threading.Event(), threading.Event()
    seen = []
    class StopProxy:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.set()
        def StopMotion(self):
            stopped.set()
            return 0
    def factory(url, *, transport):
        seen.append((url, transport.timeout))
        return StopProxy()
    monkeypatch.setattr(xmlrpc.client, "ServerProxy", factory)
    robot._stop_sender = robot._send_stop_rpc
    done = threading.Event()
    def blocked_call():
        try:
            robot._worker.call(lambda: rpc._log("ServoCart"), (), 2)
        finally:
            done.set()
    threading.Thread(target=blocked_call, daemon=True).start()
    try:
        robot.stop()
        assert stopped.wait(.5) and closed.wait(.5)
        assert not done.is_set()
        assert seen == [("http://192.168.58.2:20003/RPC2", robot.cfg.call_deadline_s)]
        assert not any(name == "StopMotion" for name, _ in rpc.calls)
    finally:
        rpc.release.set()
        assert done.wait(1)
        robot.disconnect()


def test_simultaneous_stops_are_coalesced_and_failures_are_recorded():
    entered, release = threading.Event(), threading.Event()
    calls = []
    robot = make(FakeRPC())
    robot.connect()
    def stop():
        calls.append(1)
        entered.set()
        release.wait(1)
        raise TimeoutError("stop timeout")
    robot._stop_sender = stop
    try:
        robot.stop()
        assert entered.wait(.5)
        robot.stop()
        robot.stop()
        assert len(calls) == 1
        release.set()
        assert robot._stop_lock.acquire(timeout=1)
        robot._stop_lock.release()
        assert robot.last_stop_error == "TimeoutError: stop timeout"
    finally:
        release.set()
        robot.disconnect()


def test_stop_transport_never_retries_disconnected_request(monkeypatch):
    from http.client import RemoteDisconnected
    from vhrs_agent.fairino_robot import _StopTransport
    transport = _StopTransport(.5)
    calls = []
    def fail(*args):
        calls.append(args)
        raise RemoteDisconnected("response lost")
    monkeypatch.setattr(transport, "single_request", fail)
    with pytest.raises(RemoteDisconnected):
        transport.request("example", "/RPC2", b"request")
    assert len(calls) == 1


def test_release_rpc_leaves_nothing_that_could_reconnect_later():
    from vhrs_agent.fairino_robot import release_rpc

    class Sock:
        closed = False

        def close(self):
            self.closed = True

    class Orphan:
        closeRPC_state = False
        robot_realstate_exit = False

        def __init__(self):
            self.stop_event = __import__("threading").Event()
            self.sock_cli_state = Sock()
            self.connect_to_robot = lambda: True               # what the vendor's reconnect loop would call

        def CloseRPC(self):
            raise RuntimeError("close failed halfway")        # even a failing close must not leave the connection hook alive

    rpc, sock = Orphan(), None
    sock = rpc.sock_cli_state
    release_rpc(rpc)
    assert rpc.closeRPC_state and rpc.robot_realstate_exit and rpc.stop_event.is_set()
    assert rpc.connect_to_robot() is False and sock.closed and rpc.sock_cli_state is None


def test_a_slow_probe_in_the_sdk_constructor_does_not_poison_later_connections(monkeypatch):
    """The vendor's RPC() sets the class-wide RPC.is_conect = False after one slow probe and never resets it: every later call returns -4."""
    import types

    from vhrs_agent import fairino_robot as fr

    class PoisonedRPC(FakeRPC):
        is_conect = True

        def __init__(self, ip):
            super().__init__()
            PoisonedRPC.is_conect = False                      # what the vendor's constructor does on one 1 s timeout

    fake_sdk = types.SimpleNamespace(RPC=PoisonedRPC)
    monkeypatch.setattr(fr, "load_sdk", lambda: fake_sdk)
    PoisonedRPC.is_conect = False                              # left over from an earlier failed probe in this process
    rpc = fr._open_sdk_connection("192.168.58.2")
    assert isinstance(rpc, PoisonedRPC) and PoisonedRPC.is_conect is True
