"""FAIRINO FR3 adapter (REAL mode). Status: READY_FOR_HARDWARE_VALIDATION, never run against a robot by the authors.

Built against the official Python SDK, pinned to the last 3.8.x tag in github.com/FAIR-INNOVATION/fairino-python-sdk
(commit 55bcce6, "Python_SDK_2.1.7.1_robot_v3.8.7.1"). The workshop's controller reports V3.8.25-QX / firmware
FR_CTRL_FV2.010.12, newer than any 3.8.x SDK tag, so SDK/controller compatibility is UNVERIFIED until the read-only
`connect()` below succeeds on the real controller and the operator checks the printed versions.

What this module guarantees (and what it does not):
  * connect() only reads. It never calls RobotEnable, Mode, any Move*/Servo* function or any I/O setter.
  * The SDK re-sends a command forever on a socket error (`while flag: try ... except socket.error: flag = True`).
    That is unacceptable for motion, so every motion call here runs in a worker thread watched by a deadline: when a
    call does not return in time the adapter stops the robot, marks the link lost and raises CommunicationLost. The
    command is NEVER re-issued by this code. (The SDK thread may still retry on its own, which is why the stop is sent first
    and why the operator must confirm the state before any resume.)
  * Speed is set by spacing the Cartesian targets of ServoCart (one target per control period), not by the controller's
    percentage speed: the controller's MoveL speed is a percentage and the mm/s value of 100% is not documented.
  * The pen orientation is the orientation the operator probed with (rx, ry, rz of the pose at P0), held constant. No Euler
    convention is assumed or converted.

UNVERIFIED on hardware (spike list, see docs/ROBOT_AGENT.md): ServoCart timing at the chosen period (the manual text
recommends 0.001-0.0016 s but the default is 0.008 s), whether ServoCart works from a standstill without MoveL, behaviour of
StopMotion during servo mode, TCP identification (`tool_id`) and the real pose rounding.
"""
from __future__ import annotations

import math
import http.client
import hashlib
import json
import queue
import sys
import threading
import time
import xmlrpc.client
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from vhrs_agent.port import (CommunicationLost, Control, Mode, RobotError, RobotInfo, RobotPort, StopRequested, TcpCallback)

CONNECT_ATTEMPTS = 5
CONNECT_RETRY_WAIT_S = 4.0
JOINT_MARGIN_DEG = 5.0              # SRS S8: stay at least 5 degrees from the joint limits
SDK_COMMIT = "55bcce6e7eab6a3ae45ddb0391e580ee06892248"
START_ANGLE_TOL_DEG = 0.1  # refuse a sudden change to the fixed writing angles
START_POSITION_TOL_MM = 0.5
ENDPOINT_TIMEOUT_S = 2.0
ENDPOINT_STABLE_S = 0.1
ENDPOINT_STABLE_MM = 0.05


class _StopTransport(xmlrpc.client.Transport):
    """Dedicated, bounded HTTP connection; never replay a failed request."""

    def __init__(self, timeout):
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host):
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        connection = http.client.HTTPConnection(host, timeout=self.timeout)
        self._connection = (host, connection)
        return connection

    def request(self, host, handler, request_body, verbose=False):
        # Transport.request normally retries some disconnections once.
        return self.single_request(host, handler, request_body, verbose)


class _SDKWorker:
    """One daemon worker per connection, with no retry and cancellable queued calls.

    Creating a Windows thread for every 8 ms command adds scheduler overhead.
    Reuse this worker while retaining the existing per-call deadline.
    """

    def __init__(self):
        self.requests = queue.Queue()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="fairino-sdk")
        self.thread.start()

    def _run(self):
        while True:
            request = self.requests.get()
            if request is None:
                return
            fn, args, done, cancelled, box, timing = request
            if self.closed.is_set() or cancelled.is_set():
                done.set()
                continue
            try:
                if timing is not None:
                    timing["started"] = time.perf_counter()
                box["r"] = fn(*args)
            except Exception as exc:
                box["e"] = exc
            finally:
                if timing is not None:
                    timing["finished"] = time.perf_counter()
                done.set()

    def call(self, fn, args, timeout, timing=None):
        done, cancelled, box = threading.Event(), threading.Event(), {}
        if self.closed.is_set():
            raise RuntimeError("SDK worker is closed")
        if timing is not None:
            timing["queued"] = time.perf_counter()
        self.requests.put((fn, args, done, cancelled, box, timing))
        if not done.wait(timeout):
            cancelled.set()
            raise TimeoutError("SDK call deadline exceeded")
        if timing is not None:
            timing["returned"] = time.perf_counter()
        if "e" in box:
            raise box["e"]
        if "r" not in box:
            raise RuntimeError("SDK worker closed before call")
        return box["r"]

    def close(self):
        self.closed.set()
        self.requests.put(None)


@dataclass(frozen=True)
class FairinoConfig:
    ip: str                                    # measured on the robot's web page; never defaulted by us
    tool_id: int                               # the TCP slot holding the calibrated pen-tip TCP
    orientation_deg: tuple[float, float, float]   # rx, ry, rz of the pose probed at P0 (pen perpendicular to the paper)
    servo_cmd_period_s: float                  # chosen after the timing spike; UNCONFIGURED -> refuse
    call_deadline_s: float = 0.5               # a single SDK call that takes longer is treated as a lost link
    expected_controller_prefix: str = "V3.8"   # refuse a controller family this adapter was not written for
    expected_model_contains: str = "FR3"
    tcp_offset_mm: float | None = None         # measured pen length; when set it is compared with the controller's TCP
    speed_cap_mm_s: float | None = None        # optional operator-selected upper bound for initial hardware trials
    motion_method: str = "servo"
    linear_accel_mm_s2: float = 20.0
    linear_max_segment_mm: float = 5.0
    linear_stale_state_s: float = 0.2          # no fresh robot state packet for this long during a MoveL segment = stop (a hiccup shorter than this is tolerated)
    linear_arrival_tol_mm: float = 0.05       # a MoveL segment counts as finished when the TCP is this close to its end and has settled


def _open_sdk_connection(ip: str) -> Any:
    """Open the vendor's RPC object WITHOUT inheriting its sticky failure flag.

    `RPC.is_conect` is a CLASS attribute. The constructor probes the controller once with a 1 s timeout and, on ONE slow answer, sets
    it to False for the whole process; nothing ever sets it back, and every decorated SDK call then returns -4 forever, whatever the
    robot is doing (a new process works at once, a long-lived agent never recovers). Reset it before and after the probe: our own calls
    carry their own deadline and decide by the real answer."""
    sdk = load_sdk()
    sdk.RPC.is_conect = True
    rpc = sdk.RPC(ip)
    sdk.RPC.is_conect = True
    return rpc


def release_rpc(rpc: Any) -> None:
    """Close an SDK connection so that NOTHING of it survives.

    The vendor's RPC object starts a state-reader thread that, whenever its connection to the controller's state port (20004) is
    lost or refused, runs `reconnect()`: up to 1000 attempts, two seconds apart, which look at no stop flag. `CloseRPC()` does not
    stop such a loop, so after a failed or finished session an orphan loop can connect later and hold the controller's ONLY state
    connection for the life of the process; every new connection is then refused (SDK code -4). Here the close flags are set on the
    instance, its reconnect hook is replaced by one that cannot connect, and its socket is closed.
    """
    try:
        rpc.CloseRPC()
    except Exception:                                              # noqa: BLE001 - keep going: the point is to leave nothing open
        pass
    for name, value in (("closeRPC_state", True), ("robot_realstate_exit", True)):
        try:
            setattr(rpc, name, value)
        except Exception:                                          # noqa: BLE001
            pass
    try:
        rpc.stop_event.set()
    except Exception:                                              # noqa: BLE001
        pass
    try:
        rpc.connect_to_robot = lambda: False                      # an orphan reconnect loop can no longer open a socket
    except Exception:                                              # noqa: BLE001
        pass
    sock = getattr(rpc, "sock_cli_state", None)
    if sock is not None:
        try:
            sock.close()
        except Exception:                                          # noqa: BLE001
            pass
        try:
            rpc.sock_cli_state = None
        except Exception:                                          # noqa: BLE001
            pass


def load_sdk() -> Any:
    """Import the vendored official SDK (see vendor/README.md) or an installed `fairino` package."""
    vendor = Path(__file__).resolve().parents[1] / "vendor"
    if vendor.exists() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        from fairino import Robot                                   # type: ignore
    except ImportError as exc:
        raise RobotError("SDK_MISSING", "Chưa cài SDK Fairino. Chạy scripts/fetch_fairino_sdk.py (xem vendor/README.md).") from exc
    return Robot


class FairinoRobot(RobotPort):
    mode = Mode.REAL

    def __init__(self, cfg: FairinoConfig, sdk_factory: Callable[[str], Any] | None = None,
                 stop_sender: Callable[[], Any] | None = None):
        self.cfg = cfg
        self._factory = sdk_factory
        self._rpc: Any = None
        self._lost = False
        self._joint_limits: list[float] | None = None
        self._worker: _SDKWorker | None = None
        self._stop_sender = stop_sender or self._send_stop_rpc
        self._stop_lock = threading.Lock()
        self.last_stop_error: str | None = None
        self._linear_proxy = None

    def execution_signature(self) -> str:
        return hashlib.sha256(json.dumps({"adapter": "fairino-v2", "sdk": SDK_COMMIT,
                                          "config": asdict(self.cfg)}, sort_keys=True).encode()).hexdigest()

    def _send_linear(self, values) -> None:
        """One nonblocking MoveL request with the SDK's exact wire layout, no retry."""
        if self._lost:
            raise CommunicationLost("LINK_DOWN", "Không gửi MoveL trên kết nối đã lỗi.")
        if self._linear_proxy is None:
            self._linear_proxy = xmlrpc.client.ServerProxy(
                f"http://{self.cfg.ip}:20003/RPC2", transport=_StopTransport(self.cfg.call_deadline_s))
        try:
            result = self._worker.call(self._linear_proxy.MoveL, (values,), self.cfg.call_deadline_s)
        except Exception as exc:
            self._lost = True
            self._worker.close()
            self._best_effort_stop()
            raise CommunicationLost("LINEAR_RPC_FAILED", f"MoveL: {exc}; không gửi lại lệnh.") from exc
        self._ok(result, "MoveL")

    # ---- guarded SDK calls
    def _call(self, name: str, *args: Any, deadline: float | None = None, timing: dict | None = None) -> Any:
        """Run one SDK call under a deadline. On timeout: stop, mark lost, raise. Never repeats the call."""
        if self._lost:
            raise CommunicationLost("LINK_DOWN", "Kết nối đã bị ngắt; không gửi thêm lệnh SDK.")
        if self._worker is None:
            self._worker = _SDKWorker()
        try:
            return self._worker.call(getattr(self._rpc, name), args, deadline or self.cfg.call_deadline_s, timing)
        except TimeoutError:
            self._lost = True
            self._worker.close()
            self._best_effort_stop()
            raise CommunicationLost("SDK_TIMEOUT", f"{name} không trả lời trong {deadline or self.cfg.call_deadline_s} s")
        except Exception as exc:
            self._lost = True
            self._worker.close()
            self._best_effort_stop()
            raise CommunicationLost("SDK_EXCEPTION", f"{name}: {exc}") from exc

    def _send_stop_rpc(self) -> None:
        # Same StopMotion XML-RPC as the pinned SDK, on a separate connection.
        # Sharing its ServerProxy with ServoMoveEnd or an in-flight ServoCart
        # causes CannotSendRequest/ResponseNotReady and can lose the stop.
        with xmlrpc.client.ServerProxy(f"http://{self.cfg.ip}:20003/RPC2",
                                      transport=_StopTransport(self.cfg.call_deadline_s)) as proxy:
            self._ok(proxy.StopMotion(), "StopMotion")

    def _best_effort_stop(self) -> None:
        if not self._stop_lock.acquire(blocking=False):
            return  # an independent stop is already in flight
        def send():
            try:
                self._stop_sender()
                self.last_stop_error = None
            except Exception as exc:
                self.last_stop_error = f"{type(exc).__name__}: {exc}"
                print(f"StopMotion failed: {self.last_stop_error}. Use physical E-Stop if still moving.", file=sys.stderr)
            finally:
                self._stop_lock.release()
        try:
            threading.Thread(target=send, daemon=True, name="fairino-stop").start()
        except Exception as exc:
            self.last_stop_error = f"{type(exc).__name__}: {exc}"
            self._stop_lock.release()

    @staticmethod
    def _ok(res: Any, what: str) -> Any:
        code = res if isinstance(res, int) else res[0]
        if code != 0:
            raise RobotError("SDK_ERROR", f"{what} trả mã lỗi {code}", {"code": code})
        return res

    # ---- RobotPort
    def connect(self) -> RobotInfo:
        if self.cfg.motion_method not in ("servo", "movel"):
            raise RobotError("INVALID_CONFIG", "motion_method phải là servo hoặc movel.")
        if self.cfg.motion_method == "movel" and (
                self.cfg.speed_cap_mm_s is None
                or not 0 < self.cfg.linear_accel_mm_s2 <= 100
                or not 0 < self.cfg.linear_max_segment_mm <= 5):
            raise RobotError("INVALID_CONFIG", "MoveL cần giới hạn tốc độ, gia tốc và độ dài đoạn hợp lệ.")
        if self.cfg.servo_cmd_period_s is None or self.cfg.servo_cmd_period_s <= 0:
            raise RobotError("UNCONFIGURED", "servo_cmd_period_s chưa được cấu hình (cần đo ở bước spike).")
        cap = self.cfg.speed_cap_mm_s
        if cap is not None and (not math.isfinite(cap) or cap <= 0):
            raise RobotError("INVALID_CONFIG", "speed_cap_mm_s phải là số dương hữu hạn.")
        factory = self._factory or _open_sdk_connection
        ver = None
        for attempt in range(CONNECT_ATTEMPTS):                       # connecting only READS: trying again cannot move the robot
            self._rpc = factory(self.cfg.ip)
            self._lost = False
            if self._worker is not None:
                self._worker.close()
            self._worker = _SDKWorker()
            ver = self._call("GetSoftwareVersion")
            code = ver if isinstance(ver, int) else ver[0]
            if code == 0:
                break
            release_rpc(self._rpc)                                    # leave no half-open connection or reconnect loop behind
            self._rpc = None
            if attempt + 1 < CONNECT_ATTEMPTS:
                time.sleep(CONNECT_RETRY_WAIT_S)
        if self._rpc is None:
            self._worker.close()
            self._worker = None
            raise RobotError("ROBOT_CONNECTION_BUSY", f"Không đọc được robot (mã {code}) sau {CONNECT_ATTEMPTS} lần thử. Thường do chương trình khác "
                             "(agent cũ, công cụ kiểm tra, hay một kết nối treo) đang giữ cổng trạng thái 20004 của controller: tắt chúng "
                             "(khởi động lại agent) rồi thử lại. Robot không nhận lệnh nào.", {"sdk_code": code})
        self._ok(ver, "GetSoftwareVersion")
        model, web, controller = ver[1], ver[2], ver[3]
        sdk = self._ok(self._call("GetSDKVersion"), "GetSDKVersion")[1]
        if self.cfg.expected_model_contains not in str(model):
            raise RobotError("WRONG_ROBOT", f"Mẫu robot '{model}' không phải {self.cfg.expected_model_contains} (FAIRINO).")
        if not str(controller).startswith(self.cfg.expected_controller_prefix):
            raise RobotError("CONTROLLER_UNSUPPORTED", f"Controller {controller} ngoài dòng {self.cfg.expected_controller_prefix}x "
                             "mà adapter này viết cho; cần kiểm tra tương thích SDK trước.")
        if self.cfg.motion_method == "movel":
            import re
            version = tuple(map(int, re.findall(r"\d+", str(web))[:3]))
            if version < (3, 8, 5) or not hasattr(self._rpc, "GetInverseKinRef"):
                raise RobotError("CONTROLLER_UNSUPPORTED", "MoveL mm/s cần controller từ 3.8.5 và IK tham chiếu.")
            wobj = self._ok(self._call("GetActualWObjNum"), "GetActualWObjNum")[1]
            offset = self._ok(self._call("GetWObjOffset"), "GetWObjOffset")[1]
            if wobj != 0 or len(offset) != 6 or not np.isfinite(offset).all() or np.any(np.abs(offset) > 1e-6):
                raise RobotError("WOBJ_MISMATCH", "MoveL chỉ chạy với WObj 0, offset bằng 0 trong hệ BASE.")
            if getattr(self._rpc, "robot_state_pkg", None) is None or isinstance(self._rpc.robot_state_pkg, type):
                raise RobotError("INVALID_TCP_FEEDBACK", "Chưa nhận gói trạng thái robot.")
        tool = self._ok(self._call("GetActualTCPNum"), "GetActualTCPNum")[1]
        if int(tool) != self.cfg.tool_id:
            raise RobotError("TOOL_MISMATCH", f"Robot đang dùng tool {tool}, cấu hình yêu cầu tool {self.cfg.tool_id}.")
        self._check_tcp_offset()
        lim = self._ok(self._call("GetJointSoftLimitDeg"), "GetJointSoftLimitDeg")
        self._joint_limits = [float(v) for v in lim[1]]
        return RobotInfo(Mode.REAL, str(model), controller_version=str(controller), firmware_version=None,
                         sdk_version=" ".join(str(x) for x in sdk), ip=self.cfg.ip,
                         note=f"web {web}; SDK commit {SDK_COMMIT[:7]}; motion={self.cfg.motion_method}; hardware validation required")

    def _check_tcp_offset(self) -> None:
        if self.cfg.tcp_offset_mm is None:
            return
        tcp = np.array(self._ok(self._call("GetActualTCPPose"), "GetActualTCPPose")[1][:3], float)
        fl = np.array(self._ok(self._call("GetActualToolFlangePose"), "GetActualToolFlangePose")[1][:3], float)
        got = float(np.linalg.norm(tcp - fl))
        if abs(got - self.cfg.tcp_offset_mm) > 1.0:
            raise RobotError("TCP_OFFSET_MISMATCH", f"Khoảng cách flange-TCP {got:.2f} mm khác độ dài bút đã đo "
                             f"{self.cfg.tcp_offset_mm:.2f} mm: TCP chưa đúng, không điều khiển.")

    def disconnect(self) -> None:
        try:
            if self._rpc is not None:
                release_rpc(self._rpc)
        finally:
            if self._worker is not None:
                self._worker.close()
                self._worker = None
            self._rpc = None
            if self._linear_proxy is not None:
                self._linear_proxy.__exit__(None, None, None)
                self._linear_proxy = None

    def heartbeat(self, deadline: float | None = None) -> bool:
        if self._rpc is None or self._lost:
            return False
        try:
            err = self._ok(self._call("GetRobotErrorCode", deadline=deadline), "GetRobotErrorCode")[1]
            estop = self._ok(self._call("GetRobotEmergencyStopState", deadline=deadline), "GetRobotEmergencyStopState")[1]
        except (RobotError, CommunicationLost):
            return False
        return list(err) == [0, 0] and int(estop) == 0

    def read_tcp(self) -> np.ndarray:
        return np.array(self._ok(self._call("GetActualTCPPose"), "GetActualTCPPose")[1][:3], dtype=np.float64)

    def read_joints(self) -> list[float] | None:
        try:
            return [float(v) for v in self._ok(self._call("GetActualJointPosDegree"), "GetActualJointPosDegree")[1]]
        except (RobotError, CommunicationLost):
            return None

    def _pose(self, p: np.ndarray) -> list[float]:
        return [float(p[0]), float(p[1]), float(p[2]), *self.cfg.orientation_deg]

    def _read_aligned_pose(self) -> np.ndarray:
        pose = np.asarray(self._ok(self._call("GetActualTCPPose"), "GetActualTCPPose")[1], dtype=float)
        if pose.shape != (6,) or not np.all(np.isfinite(pose)):
            raise RobotError("INVALID_START_POSE", "Không đọc được tư thế TCP hợp lệ; không bắt đầu servo.")
        delta = (pose[3:] - np.asarray(self.cfg.orientation_deg) + 180.0) % 360.0 - 180.0
        if np.max(np.abs(delta)) > START_ANGLE_TOL_DEG:
            raise RobotError("START_ORIENTATION_MISMATCH",
                             f"Góc TCP hiện tại {pose[3:].round(3).tolist()} khác góc viết "
                             f"{list(self.cfg.orientation_deg)}. Căn hướng bút tại máy trước khi chạy; "
                             "không tự xoay bằng lệnh servo đầu tiên.",
                             {"actual_deg": pose[3:].tolist(), "expected_deg": list(self.cfg.orientation_deg)})
        return pose

    def check_start_ready(self) -> None:
        self._read_aligned_pose()

    def _wait_for_endpoint(self, target: np.ndarray, ctl: Control) -> None:
        """Read-only settling check: never resend a target to overcome a mismatch.

        ServoCart/ServoMoveEnd returning does not establish that feedback has
        reached the endpoint. Keep the next segment gated until the TCP is both
        within the existing start tolerances and stable for a bounded window.
        """
        started = time.perf_counter()
        stable_at = None
        anchor = None
        last_pose = None
        while True:
            ctl.checkpoint()
            now = time.perf_counter()
            if now - started >= ENDPOINT_TIMEOUT_S:
                raise RobotError("ENDPOINT_NOT_SETTLED", "TCP chưa tới đích và ổn định trong 2 giây; không chạy đoạn kế tiếp.",
                                 {"target_mm": target.tolist(), "actual_pose": last_pose,
                                  "timeout_s": ENDPOINT_TIMEOUT_S})
            pose = np.asarray(self._ok(self._call("GetActualTCPPose"), "GetActualTCPPose")[1], dtype=float)
            if pose.shape != (6,) or not np.all(np.isfinite(pose)):
                raise RobotError("INVALID_TCP_FEEDBACK", "Phản hồi TCP không hợp lệ khi chờ tới đích.")
            last_pose = pose.tolist()
            errors = self._ok(self._call("GetRobotErrorCode"), "GetRobotErrorCode")[1]
            estop = self._ok(self._call("GetRobotEmergencyStopState"), "GetRobotEmergencyStopState")[1]
            if list(errors) != [0, 0] or int(estop) != 0:
                raise RobotError("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi hoặc E-Stop khi chờ tới đích.",
                                 {"controller_errors": list(errors), "estop": int(estop)})
            angle_error = (pose[3:] - np.asarray(self.cfg.orientation_deg) + 180) % 360 - 180
            arrived = (np.linalg.norm(pose[:3] - target) <= START_POSITION_TOL_MM
                       and np.max(np.abs(angle_error)) <= START_ANGLE_TOL_DEG)
            now = time.perf_counter()
            if arrived:
                if anchor is None or np.linalg.norm(pose[:3] - anchor) > ENDPOINT_STABLE_MM:
                    anchor, stable_at = pose[:3].copy(), now
                elif now - stable_at >= ENDPOINT_STABLE_S:
                    return
            else:
                anchor, stable_at = None, None
            time.sleep(0.02)

    def check_reachable(self, points_mm: np.ndarray) -> list[str]:
        """Inverse kinematics on the controller for every sampled point, plus the 5-degree joint-limit margin. No motion."""
        problems: list[str] = []
        lim = self._joint_limits or []
        for i, p in enumerate(points_mm):
            res = self._call("GetInverseKin", 0, self._pose(p), -1)
            if res[0] != 0:
                problems.append(f"point {i}: no inverse-kinematics solution (code {res[0]})")
                continue
            joints = res[1]
            for j, q in enumerate(joints):
                lo, hi = (lim[2 * j], lim[2 * j + 1]) if len(lim) >= 12 else (None, None)
                if lo is not None and (q < lo + JOINT_MARGIN_DEG or q > hi - JOINT_MARGIN_DEG):
                    problems.append(f"point {i}: joint {j + 1} = {q:.1f} deg is within {JOINT_MARGIN_DEG:g} deg of its limit")
            if len(problems) > 50:
                break
        return problems

    def align_to(self, target_mm: np.ndarray, ctl: Control, box=None) -> dict:
        from vhrs_agent.linear_motion import align_to_start
        return align_to_start(self, target_mm, ctl, box)

    def execute(self, points_mm: np.ndarray, speeds_mm_s: np.ndarray, ctl: Control, on_tcp: TcpCallback) -> None:
        """Stream Cartesian targets, one per control period, spaced by the planned speed."""
        if self.cfg.motion_method == "movel":
            from vhrs_agent.linear_motion import LinearExecutor
            return LinearExecutor(self).execute(points_mm, speeds_mm_s, ctl, on_tcp)
        dt = self.cfg.servo_cmd_period_s
        pts = np.asarray(points_mm, dtype=np.float64)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        total = float(cum[-1])
        if total < 1e-9:
            return
        # ServoCart applies all six coordinates at once. Interpolating XYZ alone
        # must not silently snap the wrist from its current angles to the writing
        # angles in the very first control period. Alignment is an onsite step.
        pose = self._read_aligned_pose()
        start_error = float(np.linalg.norm(pose[:3] - pts[0]))
        if start_error > START_POSITION_TOL_MM:
            raise RobotError("START_POSITION_MISMATCH", "TCP lệch quá 0.5 mm so với đầu đoạn; không bắt đầu servo.",
                             {"actual_mm": pose[:3].tolist(), "expected_mm": pts[0].tolist(), "distance_mm": start_error})
        self._ok(self._call("ServoMoveStart"), "ServoMoveStart")
        stream_completed = False
        try:
            s, nxt = 0.0, time.perf_counter()
            commands = 0
            while s < total:
                ctl.checkpoint()
                if self._lost:
                    raise CommunicationLost("LINK_DOWN", "Mất kết nối trong lúc chạy.")
                sent_at = time.perf_counter()
                if sent_at - nxt > 2 * dt:
                    self._best_effort_stop()
                    raise CommunicationLost("STREAM_OVERRUN", f"Luồng lệnh trễ {(sent_at - nxt) * 1000:.0f} ms trước khi gửi; dừng để an toàn.",
                                            {"phase": "before_send", "lag_ms": (sent_at - nxt) * 1000, "commands": commands})
                i = int(np.searchsorted(cum, s, side="right") - 1)
                i = min(i, len(seg) - 1)
                v = float(speeds_mm_s[i] + (speeds_mm_s[i + 1] - speeds_mm_s[i]) * ((s - cum[i]) / max(seg[i], 1e-12)))
                v = max(v, 0.5)
                if self.cfg.speed_cap_mm_s is not None:
                    v = min(v, self.cfg.speed_cap_mm_s)
                s = min(total, s + v * dt)
                j = min(int(np.searchsorted(cum, s, side="right") - 1), len(seg) - 1)
                target = pts[j] + (pts[j + 1] - pts[j]) * ((s - cum[j]) / max(seg[j], 1e-12))
                rpc_at = time.perf_counter()
                timing = {}
                self._ok(self._call("ServoCart", 0, self._pose(target), [1.0] * 6, 0.0, 0.0, dt, 0.0, 0.0,
                                    deadline=max(5 * dt, 0.05), timing=timing), "ServoCart")
                received_at = time.perf_counter()
                commands += 1
                on_tcp(target, received_at)
                # Never send a burst to catch up with an old schedule: each
                # target keeps its v*dt spacing, and at least dt between sends.
                nxt = sent_at + dt
                callback_ended = time.perf_counter()
                lag = callback_ended - nxt
                if lag > 2 * dt:                                        # the stream cannot hold the planned speed
                    self._best_effort_stop()
                    raise CommunicationLost("STREAM_OVERRUN", f"Luồng lệnh trễ {lag * 1000:.0f} ms; dừng để an toàn.",
                                            {"phase": "after_send", "lag_ms": lag * 1000, "commands": commands,
                                             "sdk_ms": (received_at - rpc_at) * 1000,
                                             "worker_queue_ms": (timing["started"] - timing["queued"]) * 1000,
                                             "sdk_execution_ms": (timing["finished"] - timing["started"]) * 1000,
                                             "worker_return_ms": (timing["returned"] - timing["finished"]) * 1000,
                                             "callback_ms": (callback_ended - received_at) * 1000})
                wait = nxt - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
            stream_completed = True
        except StopRequested:
            self.stop()
            raise
        except CommunicationLost:
            raise
        except RobotError as exc:
            self.stop()
            # SDK return 14 is generic. Preserve the controller's separate main
            # and sub fault codes so diagnosis does not confuse the two tables.
            try:
                codes = self._ok(self._call("GetRobotErrorCode"), "GetRobotErrorCode")[1]
            except RobotError:
                codes = None
            raise RobotError(exc.code, f"{exc.message}; lỗi controller: {codes}",
                             {**(exc.details or {}), "controller_errors": codes}) from exc
        finally:
            if not self._lost:
                try:
                    end_result = self._call("ServoMoveEnd")
                    if stream_completed:
                        self._ok(end_result, "ServoMoveEnd")
                except RobotError:
                    self.stop()
                    if stream_completed:
                        raise
        # Only reached after a successful stream and ServoMoveEnd. No motion
        # commands are issued while waiting, and failed waits never retry.
        try:
            self._wait_for_endpoint(pts[-1], ctl)
        except (RobotError, StopRequested):
            self.stop()
            raise

    def stop(self) -> None:
        if self._rpc is not None:
            self._best_effort_stop()
