"""The onsite discovery tool must never use the motion adapter or setters."""
import threading

import pytest

from scripts.inspect_robot import READ_METHODS, bounded_call, inspect


class ReadOnlyRPC:
    robot_state_pkg = object()

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        # Reject ANY unexpected operation, including motion, enable, setters and StopMotion.
        if name not in READ_METHODS:
            raise AssertionError(f"Unexpected SDK operation: {name}")

        def read():
            self.calls.append(name)
            if name == "GetActualTCPPose":
                return 0, [0, 0, 100, 180, 0, 0]
            if name == "GetActualToolFlangePose":
                return 0, [0, 0, 365, 180, 0, 0]
            return 0, 1

        return read


def test_inspection_only_reads_and_does_not_require_a_configured_tool_id():
    rpc, reads = ReadOnlyRPC(), {}
    result = inspect(rpc, reads, 1)
    assert rpc.calls == list(READ_METHODS)
    assert result["flange_to_active_tcp_mm"] == 265


def test_undecoded_state_does_not_report_a_tool_or_pose():
    rpc = ReadOnlyRPC()
    rpc.robot_state_pkg = type("UninitialisedState", (), {})
    with pytest.raises(RuntimeError, match="No decoded realtime state"):
        inspect(rpc, {}, 1)
    assert rpc.calls == ["GetSoftwareVersion", "GetSDKVersion"]


def test_sdk_error_stops_inspection_and_keeps_partial_report():
    rpc, reads = ReadOnlyRPC(), {}
    rpc.GetTCPOffset = lambda: -4
    with pytest.raises(RuntimeError, match="GetTCPOffset returned SDK error"):
        inspect(rpc, reads, 1)
    assert reads["GetTCPOffset"] == -4
    assert "GetActualTCPPose" not in rpc.calls


def test_blocked_read_times_out_without_retry_or_stop_command():
    release = threading.Event()
    calls = []

    def blocked():
        calls.append("read")
        release.wait(1)

    try:
        with pytest.raises(TimeoutError):
            bounded_call(blocked, 0.02)
        assert calls == ["read"]
    finally:
        release.set()
