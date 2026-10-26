"""Controller-planned motion against fake feedback only. No hardware or network."""
import dataclasses

import numpy as np
import pytest

from test_fairino_adapter import FakeClock, FakeRPC
from vhrs_agent.fairino_robot import FairinoConfig, FairinoRobot
from vhrs_agent.linear_motion import payload, segments
from vhrs_agent.port import CommunicationLost, Control, RobotError, StopRequested


class LinearRPC(FakeRPC):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.robot_state_pkg = object()
        self.fresh, self.stalled, self.wobj = True, False, 0
        self.goal, self.origin, self.at, self.speed = None, None, 0, 0
        self.tcp_pose = [300., 0., 25., 180., 0., 0.]
        self.done = 1

    def GetActualTCPPose(self):
        if self.fresh:
            self.robot_state_pkg = object()
        if self.goal is not None and not self.stalled:
            length = np.linalg.norm(self.goal - self.origin)
            fraction = min(1., (self.clock.now - self.at) * self.speed / length)
            self.tcp_pose[:3] = (self.origin + fraction * (self.goal - self.origin)).tolist()
            self.done = int(fraction == 1.)
        return super().GetActualTCPPose()

    def GetActualJointPosDegree(self):
        return 0, [0., -30., 90., 0., 60., 0.]

    def GetInverseKinRef(self, mode, pose, joints):
        self._log("GetInverseKinRef", mode, pose, joints)
        return 0, joints

    def GetActualWObjNum(self):
        return 0, self.wobj

    def GetWObjOffset(self):
        return 0, [0.] * 6

    def GetSafetyCode(self):
        return 0

    def GetRobotMotionDone(self):
        return 0, self.done


class Wire:
    def __init__(self, rpc):
        self.rpc, self.calls, self.error, self.delay = rpc, [], None, 0

    def MoveL(self, values):
        self.calls.append(list(values))
        if self.error is not None:
            raise self.error
        r = self.rpc
        r.origin = np.array(r.tcp_pose[:3])
        r.goal, r.at, r.speed = np.array(values[6:9]), r.clock.now, values[16]
        r.done = 0
        r.clock.now += self.delay
        return 0

    def __exit__(self, *args):
        pass


@pytest.fixture
def rig(monkeypatch):
    import time
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = LinearRPC(clock)
    cfg = FairinoConfig("192.168.58.2", 1, (180., 0., 0.), .008,
                        speed_cap_mm_s=10, motion_method="movel")
    robot = FairinoRobot(cfg, sdk_factory=lambda ip: rpc, stop_sender=rpc.StopMotion)
    robot.connect()
    wire = Wire(rpc)
    robot._linear_proxy = wire
    yield robot, rpc, wire, clock
    robot.disconnect()


def test_merging_preserves_corners_reversals_and_lowest_speed():
    points = [[0, 0, 0], [1, 0, 0], [2, 0, 0], [2, 1, 0], [2, 0, 0]]
    result = list(segments(points, [10, 2, 10, 8, 10], 5, 5))
    assert len(result) == 3
    assert [b.tolist() for _, b, _ in result] == [[2, 0, 0], [2, 1, 0], [2, 0, 0]]
    assert [v for _, _, v in result] == [2, 5, 5]


def test_long_line_is_bounded_without_altering_geometry():
    points = np.column_stack([np.linspace(0, 21, 106), np.zeros((106, 2))])
    result = list(segments(points, np.full(106, 30), 10, 5))
    assert len(result) == 5
    assert all(np.linalg.norm(b - a) <= 5 and v == 10 for a, b, v in result)
    assert np.array_equal(result[-1][1], points[-1])


@pytest.mark.parametrize("speeds", [[0, 10], [10, float("nan")], [-1, 10], [10]])
def test_bad_plan_is_rejected_before_motion(rig, speeds):
    robot, rpc, wire, _ = rig
    with pytest.raises(RobotError, match="INVALID_LINEAR_PLAN|không hợp lệ"):
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array(speeds), Control(), lambda p, t: None)
    assert not wire.calls


def test_wire_layout_uses_physical_speed_in_ovl_not_percentage_vel():
    values = payload([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12], 1, 5, 20)
    assert len(values) == 33
    assert values[:14] == [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 1, 0]
    assert values[14:19] == [100, 100, 5, 0, 0]
    assert values[19:31] == [0] * 12
    assert values[31:] == [20, 1]


def test_slow_rpc_no_longer_requires_8ms_stream_and_next_move_waits(rig):
    robot, rpc, wire, clock = rig
    wire.delay = .047  # observed on hardware; valid for controller-planned movement
    seen = []
    robot.execute(np.array([[300, 0, 25], [300, 1, 25], [301, 1, 25]]), np.array([5, 5, 5]),
                  Control(), lambda p, t: seen.append(p.copy()))
    assert len(wire.calls) == 2
    assert clock.now >= .6
    assert np.allclose(rpc.tcp_pose[:3], [301, 1, 25])
    assert not any(name.startswith("Servo") for name, _ in rpc.calls)
    assert len(seen) > 4 and wire.calls[0][16] == 5


def test_stale_state_stops_without_queuing_next_command(rig):
    robot, rpc, wire, _ = rig
    rpc.fresh = False
    with pytest.raises(CommunicationLost) as err:
        robot.execute(np.array([[300, 0, 25], [300, 5, 25], [301, 5, 25]]), np.array([5, 5, 5]),
                      Control(), lambda p, t: None)
    assert err.value.code == "STALE_ROBOT_STATE" and len(wire.calls) == 1


def test_stalled_motion_times_out_without_next_command(rig):
    robot, rpc, wire, _ = rig
    rpc.stalled = True
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25], [301, 1, 25]]), np.array([5, 5, 5]),
                      Control(), lambda p, t: None)
    assert err.value.code == "LINEAR_MOVE_TIMEOUT" and len(wire.calls) == 1
    d = err.value.details                                                # the report says where the pen was, not only that it timed out
    assert {"target_mm", "last_pose_mm", "distance_to_target_mm", "last_motion_done_flag", "arrival_tolerance_mm",
            "controller_errors", "segment_length_mm"} <= set(d) and d["arrival_tolerance_mm"] == 0.05


@pytest.mark.parametrize("action", ["stop", "pause"])
def test_stop_and_pause_during_motion_do_not_send_next_line(rig, action):
    robot, rpc, wire, _ = rig
    ctl = Control()
    def callback(p, t):
        ctl.request_stop("test") if action == "stop" else ctl.paused.set()
    with pytest.raises(StopRequested):
        robot.execute(np.array([[300, 0, 25], [300, 1, 25], [301, 1, 25]]), np.array([5, 5, 5]), ctl, callback)
    assert len(wire.calls) == 1 and ctl.stop.is_set()


def test_failed_request_is_unknown_and_is_never_repeated(rig):
    robot, rpc, wire, _ = rig
    wire.error = OSError("lost response")
    with pytest.raises(CommunicationLost) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([5, 5]), Control(), lambda p, t: None)
    assert err.value.code == "LINEAR_RPC_FAILED" and len(wire.calls) == 1 and robot._lost


def test_branch_change_is_refused_before_motion(rig):
    robot, rpc, wire, _ = rig
    rpc.GetInverseKinRef = lambda *args: (0, [0, -30, 90, 0, 60, 180])
    with pytest.raises(RobotError) as err:
        robot.execute(np.array([[300, 0, 25], [300, 1, 25]]), np.array([5, 5]), Control(), lambda p, t: None)
    assert err.value.code == "JOINT_BRANCH_CHANGE" and not wire.calls


def test_signature_changes_with_motion_method_and_speed(rig):
    robot, _, _, _ = rig
    before = robot.execution_signature()
    robot.cfg = dataclasses.replace(robot.cfg, motion_method="servo")
    assert before != robot.execution_signature()
    robot.cfg = dataclasses.replace(robot.cfg, motion_method="movel", speed_cap_mm_s=5)
    assert before != robot.execution_signature()


def test_a_completed_move_leaves_smoothness_statistics(rig):
    robot, rpc, wire, _ = rig
    robot.execute(np.array([[300, 0, 25], [300, 1, 25], [301, 1, 25]]), np.array([5, 5, 5]), Control(), lambda p, t: None)
    st = robot.motion_stats
    assert st["segments"] >= 2 and st["path_mm"] == pytest.approx(2.0, abs=0.01) and st["wall_s"] > 0
    assert st["effective_mm_s"] > 0 and st["slowdown_factor"] >= 0 and st["gap_mean_s"] is not None
    assert st["end_error_z_max_mm"] is not None and st["end_error_z_max_mm"] < 0.2 and st["end_error_xy_max_mm"] < 0.2    # the fake robot arrives where told


# ---------------------------------------------------------------- align to the fixed start
class AlignWire(Wire):
    """Like Wire, and the fake controller also rotates the pen to the commanded orientation on arrival."""

    def MoveL(self, values):
        out = super().MoveL(values)
        self.rpc.target_orientation = list(values[9:12])
        return out


class AlignRPC(LinearRPC):
    def GetActualTCPPose(self, flag=1):
        out = super().GetActualTCPPose()
        if self.done == 1 and getattr(self, "target_orientation", None):
            self.tcp_pose[3:] = self.target_orientation
        return out


@pytest.fixture
def arig(monkeypatch):
    import time
    clock = FakeClock()
    monkeypatch.setattr(time, "perf_counter", clock.counter)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    rpc = AlignRPC(clock)
    rpc.tcp_pose = [300., 0., 40., 175., 0., 0.]                  # 5 degrees off the writing orientation
    cfg = FairinoConfig("192.168.58.2", 1, (180., 0., 0.), .008, speed_cap_mm_s=10, motion_method="movel")
    robot = FairinoRobot(cfg, sdk_factory=lambda ip: rpc, stop_sender=rpc.StopMotion)
    robot.connect() if False else None
    yield robot, rpc, clock


def _connected(robot, rpc):
    rpc.tcp_pose, saved = [300., 0., 40., 180., 0., 0.], rpc.tcp_pose     # connect() demands the writing orientation? no: it only reads
    robot.connect()
    rpc.tcp_pose = saved
    wire = AlignWire(rpc)
    robot._linear_proxy = wire
    return wire


def test_align_moves_to_the_start_with_the_exact_writing_orientation(arig):
    robot, rpc, clock = arig
    wire = _connected(robot, rpc)
    out = robot.align_to(np.array([310., 0., 40.]), Control())
    assert out["moved"] is True and len(wire.calls) == 1
    assert wire.calls[0][9:12] == [180., 0., 0.]                       # the commanded pose carries the fixed orientation
    assert np.allclose(rpc.tcp_pose, [310., 0., 40., 180., 0., 0.], atol=.3)
    robot.disconnect()


def test_align_does_nothing_when_the_arm_is_already_there(arig):
    robot, rpc, clock = arig
    wire = _connected(robot, rpc)
    rpc.tcp_pose = [310., 0., 40., 180., 0., 0.]
    assert robot.align_to(np.array([310., 0., 40.]), Control())["moved"] is False and wire.calls == []
    robot.disconnect()


@pytest.mark.parametrize("pose", [[2000., 0., 40., 180., 0., 0.], [310., 0., 40., 60., 0., 0.]])
def test_align_refuses_a_big_jump_or_a_big_turn(arig, pose):
    robot, rpc, clock = arig
    wire = _connected(robot, rpc)
    rpc.tcp_pose = pose
    with pytest.raises(RobotError) as err:
        robot.align_to(np.array([310., 0., 40.]), Control())
    assert err.value.code == "ALIGN_TOO_FAR" and wire.calls == []       # nothing was sent
    robot.disconnect()


def test_align_stop_and_pause_stop_the_arm(arig):
    robot, rpc, clock = arig
    _connected(robot, rpc)
    rpc.stalled = True
    ctl = Control()
    ctl.paused.set()
    with pytest.raises(StopRequested):
        robot.align_to(np.array([310., 0., 40.]), ctl)
    assert ("StopMotion", ()) in rpc.calls
    robot.disconnect()


def test_align_goes_from_a_far_point_with_a_large_but_plausible_joint_change(arig):
    robot, rpc, clock = arig
    _connected(robot, rpc)
    rpc.tcp_pose = [300., 0., 40., 180., 0., 0.]
    assert robot.align_to(np.array([550., 150., 40.]), Control())["moved"] is True            # 290 mm away, no box needed
    robot.disconnect()


def test_align_refuses_only_a_joint_flip_and_reports_the_joints(arig):
    robot, rpc, clock = arig
    wire = _connected(robot, rpc)
    rpc.tcp_pose = [300., 0., 40., 180., 0., 0.]
    rpc.GetInverseKinRef = lambda mode, pose, joints: (0, [j + 150 for j in joints])     # a wrist/elbow flip
    with pytest.raises(RobotError) as err:
        robot.align_to(np.array([310., 0., 40.]), Control())
    assert err.value.code == "JOINT_BRANCH_CHANGE" and err.value.details["max_delta_deg"] == 150 and wire.calls == []
    robot.disconnect()
