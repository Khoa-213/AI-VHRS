"""Controller-planned line segments, with one outstanding command at a time.

The wire layout follows the pinned FAIRINO SDK's MoveL implementation.
velAccParamMode=1 makes ovl physical mm/s and oacc physical mm/s²:
https://manual.fairino.support/latest/SDKManual/CPPRobotMovement.html#cartesian-space-linear-motion
No servo scheduling, path blending, automatic retries, or percentage-speed fallback.
"""
from __future__ import annotations

import math
import time

import numpy as np

from vhrs_agent.port import CommunicationLost, RobotError, StopRequested

SETTLE_JITTER_MM = 0.1      # reading noise allowed while "standing still": with the pen pressed on the paper the pose flickers by more than 0.02 mm
SEGMENT_TIMEOUT_BASE_S = 5.0
PRE_MOVE_DEADLINE_S = 2.0   # between segments the robot stands still: a slow answer from the controller is not a reason to abandon the pen mid-page


def segments(points, speeds, cap, max_length):
    """Merge only collinear forward points; retain every bend and minimum speed.

    Split long lines to bound the distance covered by a single accepted command.
    The speed never exceeds any original speed on the merged interval.
    """
    points, speeds = np.asarray(points, float), np.asarray(speeds, float)
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 2
            or speeds.shape != (len(points),) or not np.isfinite(points).all()
            or not np.isfinite(speeds).all() or np.any(speeds <= 0)
            or not math.isfinite(cap) or cap <= 0 or not math.isfinite(max_length) or max_length <= 0):
        raise RobotError("INVALID_LINEAR_PLAN", "Điểm hoặc tốc độ MoveL không hợp lệ.")
    start = 0
    while start < len(points) - 1:
        end = start + 1
        vector = points[end] - points[start]
        length = float(np.linalg.norm(vector))
        if length < 1e-9:
            start += 1
            continue
        unit = vector / length
        while end + 1 < len(points):
            candidate = points[end + 1] - points[start]
            along = float(candidate @ unit)
            if along < length - 1e-9 or np.linalg.norm(candidate - along * unit) > 1e-8:
                break
            end += 1
            length = along
        speed = min(float(np.min(speeds[start:end + 1])), cap)
        count = max(1, math.ceil(length / max_length))
        for i in range(count):
            a = points[start] + (points[end] - points[start]) * (i / count)
            b = points[start] + (points[end] - points[start]) * ((i + 1) / count)
            yield a, b, speed
        start = end


def payload(pose, joints, tool, speed, acceleration):
    # 32 fields, identical to vendor/fairino/Robot.py MoveL's XML-RPC list.
    return [*map(float, joints), *map(float, pose), int(tool), 0,
            100.0, 100.0, float(speed), 0.0, 0,  # vel/acc %, ovl mm/s, blendR=0 (nonblocking)
            *([0.0] * 4), 0, 0, *([0.0] * 6), float(acceleration), 1]


class LinearExecutor:
    def __init__(self, robot):
        self.robot = robot

    def execute(self, points, speeds, ctl, on_tcp):
        robot = self.robot
        # Materialize/validate all segments before any motion.
        moves = list(segments(points, speeds, robot.cfg.speed_cap_mm_s, robot.cfg.linear_max_segment_mm))
        # How smooth was it? Every segment ends with the robot standing still (one command at a time), so the wall time is longer than
        # length/speed. These numbers let a person judge "stop and go" without watching: logged by the runner as `motion_stats`.
        t_begin = time.perf_counter()
        move_s, gap_s, last_return, ideal_s, path_mm = [], [], None, 0.0, 0.0
        try:
            for start, target, speed in moves:
                ctl.checkpoint()
                actual = robot._read_aligned_pose()
                if np.linalg.norm(actual[:3] - start) > .5:
                    raise RobotError("START_POSITION_MISMATCH", "TCP lệch đầu đoạn MoveL quá 0.5 mm.")
                if not robot.heartbeat(deadline=PRE_MOVE_DEADLINE_S):
                    raise RobotError("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi trước MoveL.")
                robot._ok(robot._call("GetSafetyCode", deadline=PRE_MOVE_DEADLINE_S), "GetSafetyCode")
                current_joints = robot.read_joints()
                if current_joints is None or np.asarray(current_joints).shape != (6,) or not np.isfinite(current_joints).all():
                    raise RobotError("INVALID_JOINT_FEEDBACK", "Không đọc được góc khớp trước MoveL.")
                joints = robot._ok(robot._call("GetInverseKinRef", 0, robot._pose(target), current_joints,
                                           deadline=PRE_MOVE_DEADLINE_S),
                                   "GetInverseKinRef")[1]
                joints = np.asarray(joints, float)
                if joints.shape != (6,) or not np.isfinite(joints).all():
                    raise RobotError("INVALID_IK", "Nghiệm khớp MoveL không hợp lệ.")
                # Each segment is short. Never accept a different wrist branch.
                if np.max(np.abs(joints - np.asarray(current_joints))) > 30:
                    raise RobotError("JOINT_BRANCH_CHANGE", "Nghiệm MoveL đổi nhánh khớp; không di chuyển.")
                limits = robot._joint_limits
                if limits is None or len(limits) != 12 or any(
                        q < limits[2 * j] + 5 or q > limits[2 * j + 1] - 5 for j, q in enumerate(joints)):
                    raise RobotError("JOINT_LIMIT", "Nghiệm MoveL gần giới hạn khớp; không di chuyển.")
                previous_packet = robot._rpc.robot_state_pkg
                sent = time.perf_counter()
                if last_return is not None:
                    gap_s.append(sent - last_return)                 # dead time between segments: checks, inverse kinematics, state reads
                robot._send_linear(payload(robot._pose(target), joints, robot.cfg.tool_id, speed,
                                           robot.cfg.linear_accel_mm_s2))
                self.wait(start, target, speed, previous_packet, ctl, on_tcp)
                last_return = time.perf_counter()
                move_s.append(last_return - sent)
                seg = float(np.linalg.norm(target - start))
                path_mm += seg
                ideal_s += seg / speed
            total = time.perf_counter() - t_begin
            robot.motion_stats = {"segments": len(moves), "path_mm": round(path_mm, 2), "wall_s": round(total, 2),
                                  "ideal_s_at_commanded_speed": round(ideal_s, 2),
                                  "effective_mm_s": round(path_mm / total, 2) if total > 0 else None,
                                  "slowdown_factor": round(total / ideal_s, 2) if ideal_s > 0 else None,
                                  "gap_mean_s": round(float(np.mean(gap_s)), 3) if gap_s else None,
                                  "gap_max_s": round(float(np.max(gap_s)), 3) if gap_s else None,
                                  "segment_wall_mean_s": round(float(np.mean(move_s)), 3) if move_s else None}
        except (RobotError, StopRequested):
            robot.stop()
            raise

    def wait(self, start, target, speed, previous_packet, ctl, on_tcp):
        robot = self.robot
        vector = target - start
        length = float(np.linalg.norm(vector))
        started = time.perf_counter()
        timeout = SEGMENT_TIMEOUT_BASE_S + 3 * length / speed
        packet_at, packet = started, previous_packet
        stable_at, anchor = None, None
        fresh_seen = False
        tol = float(getattr(robot.cfg, "linear_arrival_tol_mm", 0.05))
        stale_s = float(getattr(robot.cfg, "linear_stale_state_s", 0.2))
        seen: dict = {}                                         # what the last look at the robot said, for the timeout report
        while True:
            # Blocking on a pause flag would leave a controller-planned move
            # running without supervision. Stop it; never resume automatically.
            if ctl.paused.is_set():
                ctl.request_stop("Tạm dừng trong MoveL; cần kiểm tra vị trí trước khi chạy lại.")
            ctl.checkpoint()
            now = time.perf_counter()
            if now - started > timeout:
                details = {"target_mm": target.tolist(), "timeout_s": timeout, "segment_length_mm": length, "speed_mm_s": speed,
                           "arrival_tolerance_mm": tol, "fresh_packet_seen": fresh_seen, **seen}
                try:                                            # why the robot did not arrive: its own fault codes, read once
                    details["controller_errors"] = robot._call("GetRobotErrorCode", deadline=1.0)[1]
                except Exception:                               # noqa: BLE001 - the report must not hide the original timeout
                    details["controller_errors"] = "unreadable"
                raise RobotError("LINEAR_MOVE_TIMEOUT", "MoveL chưa hoàn tất trong thời gian cho phép.", details)
            # SDK replaces this structure on each decoded realtime packet.
            current_packet = robot._rpc.robot_state_pkg
            if current_packet is not packet:
                packet, packet_at, fresh_seen = current_packet, now, True
            elif now - packet_at > stale_s:
                raise CommunicationLost("STALE_ROBOT_STATE", f"Không nhận phản hồi robot mới trong {stale_s * 1000:.0f} ms.")
            pose = robot._read_aligned_pose()
            if not robot.heartbeat():
                raise RobotError("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi trong MoveL.")
            robot._ok(robot._call("GetSafetyCode"), "GetSafetyCode")
            # Preserve the runner's cross-track watchdog and force monitoring.
            # Progress along the line is controller-timed, bounded by timeout.
            fraction = float(np.clip((pose[:3] - start) @ vector / (length * length), 0, 1))
            on_tcp(start + fraction * vector, time.perf_counter())
            if ctl.paused.is_set():
                ctl.request_stop("Tạm dừng trong MoveL; cần kiểm tra vị trí trước khi chạy lại.")
            ctl.checkpoint()
            done = robot._ok(robot._call("GetRobotMotionDone"), "GetRobotMotionDone")[1]
            now = time.perf_counter()
            dist = float(np.linalg.norm(pose[:3] - target))
            seen = {"last_pose_mm": [round(float(v), 3) for v in pose[:3]], "distance_to_target_mm": round(dist, 4),
                    "last_motion_done_flag": done, "elapsed_s": round(now - started, 3)}
            if fresh_seen and done == 1 and dist <= tol:
                if anchor is None or np.linalg.norm(pose[:3] - anchor) > SETTLE_JITTER_MM:
                    anchor, stable_at = pose[:3].copy(), now
                elif now - stable_at >= .1:
                    return
            else:
                anchor, stable_at = None, None
            time.sleep(.02)


ALIGN_MAX_DISTANCE_MM = 1000.0    # effectively no distance limit: from wherever the pen is (above the paper) to the start; the operator watches with the E-Stop
ALIGN_MAX_DISTANCE_IN_BOX_MM = 1000.0
ALIGN_MAX_ANGLE_DEG = 90.0
ALIGN_MAX_JOINT_DELTA_DEG = 100.0  # a long move legitimately turns joints by tens of degrees; only a wrist/elbow flip is refused
ALIGN_ARRIVE_MM = 0.3
ALIGN_ARRIVE_DEG = 0.1            # same tolerance the writing moves demand at their start (START_ANGLE_TOL_DEG)


def align_to_start(robot, target, ctl, box=None):
    """One controller-planned straight MoveL from where the arm is to `target` WITH the fixed writing orientation.

    For the operator who has put the arm near the start by hand: it removes the few-degree orientation error that makes the writing
    moves refuse to begin. It never starts from or goes through a pose closer to the paper than the pen-up height (the caller checks the
    target and the current height), moves at the configured speed cap, and refuses large jumps. One command, no retry, stop on any
    doubt; pausing is treated as a stop."""
    cfg = robot.cfg
    if cfg.motion_method != "movel" or cfg.speed_cap_mm_s is None:
        raise RobotError("INVALID_CONFIG", "Đưa về điểm bắt đầu cần motion_method=movel và speed_cap_mm_s.")
    target = np.asarray(target, float)
    raw = np.asarray(robot._ok(robot._call("GetActualTCPPose"), "GetActualTCPPose")[1], float)
    if raw.shape != (6,) or not np.isfinite(raw).all():
        raise RobotError("INVALID_START_POSE", "Không đọc được tư thế TCP hợp lệ.")
    want = np.asarray(cfg.orientation_deg, float)

    def angle_error(pose):
        return float(np.max(np.abs((pose[3:] - want + 180.0) % 360.0 - 180.0)))

    distance, angle = float(np.linalg.norm(raw[:3] - target)), angle_error(raw)
    inside = False
    if box is not None:
        lo, hi = np.asarray(box[0], float), np.asarray(box[1], float)
        inside = bool(np.all(raw[:3] >= lo - 0.5) and np.all(raw[:3] <= hi + 0.5) and np.all(target >= lo - 0.5) and np.all(target <= hi + 0.5))
    limit = ALIGN_MAX_DISTANCE_IN_BOX_MM if inside else ALIGN_MAX_DISTANCE_MM
    if distance > limit or angle > ALIGN_MAX_ANGLE_DEG:
        raise RobotError("ALIGN_TOO_FAR", f"Đầu bút cách điểm bắt đầu {distance:.0f} mm và lệch góc {angle:.1f} độ: gần hơn bằng tay "
                         f"(tối đa {limit:g} mm{'' if inside else ' khi đang ở ngoài hộp an toàn'}, {ALIGN_MAX_ANGLE_DEG:g} độ) rồi thử lại.",
                         {"distance_mm": distance, "angle_deg": angle, "inside_safe_box": inside})
    if distance <= ALIGN_ARRIVE_MM and angle <= ALIGN_ARRIVE_DEG:
        return {"moved": False, "distance_mm": distance, "angle_deg": angle}
    if not robot.heartbeat(deadline=PRE_MOVE_DEADLINE_S):
        raise RobotError("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi trước khi căn điểm bắt đầu.")
    robot._ok(robot._call("GetSafetyCode", deadline=PRE_MOVE_DEADLINE_S), "GetSafetyCode")
    joints_now = robot.read_joints()
    if joints_now is None or np.asarray(joints_now).shape != (6,) or not np.isfinite(joints_now).all():
        raise RobotError("INVALID_JOINT_FEEDBACK", "Không đọc được góc khớp trước khi căn điểm bắt đầu.")
    joints = np.asarray(robot._ok(robot._call("GetInverseKinRef", 0, robot._pose(target), joints_now, deadline=PRE_MOVE_DEADLINE_S),
                                  "GetInverseKinRef")[1], float)
    if joints.shape != (6,) or not np.isfinite(joints).all():
        raise RobotError("INVALID_IK", "Nghiệm khớp không hợp lệ.")
    delta = np.abs(joints - np.asarray(joints_now))
    if np.max(delta) > ALIGN_MAX_JOINT_DELTA_DEG:
        raise RobotError("JOINT_BRANCH_CHANGE", f"Nghiệm khớp đổi {float(np.max(delta)):.0f} độ ở khớp {int(np.argmax(delta)) + 1}: có thể là lật nhánh "
                         "khớp; không di chuyển. Đưa bút gần điểm bắt đầu hơn bằng tay.",
                         {"joints_now_deg": [round(float(v), 1) for v in joints_now], "joints_target_deg": [round(float(v), 1) for v in joints],
                          "max_delta_deg": float(np.max(delta))})
    limits = robot._joint_limits
    if limits is None or len(limits) != 12 or any(q < limits[2 * j] + 5 or q > limits[2 * j + 1] - 5 for j, q in enumerate(joints)):
        raise RobotError("JOINT_LIMIT", "Nghiệm gần giới hạn khớp; không di chuyển.")
    speed = float(cfg.speed_cap_mm_s)
    previous_packet = robot._rpc.robot_state_pkg
    robot._send_linear(payload(robot._pose(target), joints, cfg.tool_id, speed, cfg.linear_accel_mm_s2))
    started = time.perf_counter()
    timeout = 10 + 3 * distance / speed + 2 * angle
    stale_s = float(getattr(cfg, "linear_stale_state_s", 0.2))
    packet, packet_at, fresh_seen, stable_at, anchor = previous_packet, started, False, None, None
    try:
        while True:
            if ctl.paused.is_set():
                ctl.request_stop("Tạm dừng khi căn điểm bắt đầu; kiểm tra vị trí trước khi làm tiếp.")
            ctl.checkpoint()
            now = time.perf_counter()
            if now - started > timeout:
                raise RobotError("ALIGN_TIMEOUT", "Chưa tới điểm bắt đầu trong thời gian cho phép.", {"timeout_s": timeout})
            current = robot._rpc.robot_state_pkg
            if current is not packet:
                packet, packet_at, fresh_seen = current, now, True
            elif now - packet_at > stale_s:
                raise CommunicationLost("STALE_ROBOT_STATE", f"Không nhận phản hồi robot mới trong {stale_s * 1000:.0f} ms.")
            pose = np.asarray(robot._ok(robot._call("GetActualTCPPose"), "GetActualTCPPose")[1], float)
            if not robot.heartbeat():
                raise RobotError("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi khi căn điểm bắt đầu.")
            robot._ok(robot._call("GetSafetyCode"), "GetSafetyCode")
            done = robot._ok(robot._call("GetRobotMotionDone"), "GetRobotMotionDone")[1]
            now = time.perf_counter()
            if fresh_seen and done == 1 and np.linalg.norm(pose[:3] - target) <= ALIGN_ARRIVE_MM and angle_error(pose) <= ALIGN_ARRIVE_DEG:
                if anchor is None or np.linalg.norm(pose[:3] - anchor) > SETTLE_JITTER_MM:
                    anchor, stable_at = pose[:3].copy(), now
                elif now - stable_at >= .2:
                    return {"moved": True, "distance_mm": distance, "angle_deg": angle, "final_pose": [round(float(v), 3) for v in pose]}
            else:
                anchor, stable_at = None, None
            time.sleep(.02)
    except (RobotError, StopRequested):
        robot.stop()
        raise
