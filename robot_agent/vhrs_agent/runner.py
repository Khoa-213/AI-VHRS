"""Job runner: preflight, dry run, controlled writing, stop / pause, partial-job recovery.

Rules this module enforces (they come from the project brief, not from convenience):
  * one controller at a time: a lock file plus an in-process lock; a second run is refused, never queued;
  * REAL mode needs the operator's per-job authorization token and a finished pen-up dry run for the SAME plan;
  * a motion command is never re-sent after a stop, a fault or a lost link; the interrupted stroke is recorded and the
    operator decides explicitly where to resume (never silently from zero: that would write strokes on top of each other);
  * nothing from the AI reaches the robot: the plan is rebuilt here from the approved trajectory and validated again;
  * every command, state change and fault goes to the run log (jsonl) first, the backend second.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.services.motion.frame import PaperFrame, build_frame
from app.services.motion.plan import MotionConfig, PagePlan
from app.services.motion.validate import Workspace, validate
from app.services.stroke_ai.trajectory import Page

from vhrs_agent.gripper import FLAG_TOUCH, ForceLimits, GripperPort, SafetyMonitor
from vhrs_agent import __version__
from vhrs_agent.ops import OpsReporter
from vhrs_agent.port import CommunicationLost, Control, Mode, RobotError, RobotPort, StopRequested

REST_FORCE_TOL_N = 0.05          # docs 5: zero drift beyond 0.05 N means "recalibrate"
REACH_SAMPLE_MM = 5.0            # SRS S8: inverse kinematics every 5 mm
CONTACT_GRACE_POINTS = 6         # no contact-loss judgement for the first ~1 mm of a stroke
_PROCESS_LOCK = threading.Lock()


@dataclass(frozen=True)
class Watchdogs:
    """Checks that look at what the robot REALLY does instead of trusting the commands we sent. Every number must be measured on
    the robot; None = UNCONFIGURED and REAL mode refuses to run (the software could not then tell you to press the E-Stop)."""
    stop_settle_s: float | None = None          # time the robot is allowed to need to stand still after a stop command
    stop_window_s: float | None = None          # how long we watch it afterwards
    stop_tolerance_mm: float | None = None      # movement in that window that still counts as standing still
    tracking_tolerance_mm: float | None = None  # largest allowed distance between the commanded and the real pen position
    tracking_grace_s: float | None = None       # how long it may exceed that before we stop

    def configured(self) -> bool:
        return all(v is not None and v > 0 for v in (self.stop_settle_s, self.stop_window_s, self.stop_tolerance_mm,
                                                     self.tracking_tolerance_mm, self.tracking_grace_s))


class RunRefused(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


# ---------------------------------------------------------------------------------------------- persistence
class RunLog:
    """Append-only jsonl: the local activity log of the robot (every command, state and fault)."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._lock = 0, threading.Lock()

    def write(self, kind: str, **data: Any) -> None:
        with self._lock:
            self._seq += 1
            rec = {"seq": self._seq, "ts": time.time(), "kind": kind, **data}
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


class ProgressStore:
    """What is physically on the paper, written BEFORE the next stroke starts."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any] | None:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    def mark_dry_run_ok(self, job_id: int, digest: str, mode: str = "SIM", execution_signature: str | None = None) -> None:
        """A rehearsal finished. It must never touch what is recorded about the paper: only note that THIS plan was rehearsed, and in which
        mode. `dry_run_ok` holds the mode ("REAL" wins): a rehearsal in the simulator does not qualify a REAL run."""
        cur = self.load()
        if not cur:
            self.save({"digest": digest, "job_id": job_id, "state": "IDLE", "completed": 0, "interrupted": None,
                       "dry_run_ok": mode, "execution_signature": execution_signature})
        elif cur.get("digest") == digest:
            signature = cur.get("execution_signature") if cur.get("dry_run_ok") == "REAL" and mode != "REAL" else execution_signature
            self.save({**cur, "dry_run_ok": "REAL" if "REAL" in (cur.get("dry_run_ok"), mode) else mode,
                       "execution_signature": signature})

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


class _NullStore:
    """A dry run writes nothing about the paper: the pen never touches it."""

    def save(self, data: dict[str, Any]) -> None:
        return None


class ControllerLock:
    """Only one source may command the robot. Exclusive file create; a stale file must be removed by a person."""

    def __init__(self, path: Path):
        self.path, self.held = path, False

    def __enter__(self) -> "ControllerLock":
        if not _PROCESS_LOCK.acquire(blocking=False):
            raise RunRefused("CONTROLLER_BUSY", "Agent này đang điều khiển robot cho một job khác.")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"pid={os.getpid()}\n".encode())
            os.close(fd)
            self.held = True
        except FileExistsError:
            _PROCESS_LOCK.release()
            raise RunRefused("CONTROLLER_BUSY", f"Có tiến trình khác đang giữ quyền điều khiển ({self.path}). "
                             "Nếu chắc chắn không còn, người vận hành xoá file khoá.") from None
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            _PROCESS_LOCK.release()
            self.held = False


# ---------------------------------------------------------------------------------------------- plan digest
def plan_digest(package_hash: str, probes: list[Any], cfg: MotionConfig, ws: Workspace) -> str:
    blob = json.dumps({"hash": package_hash, "probes": probes, "cfg": cfg.__dict__, "ws": ws.__dict__},
                      sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def authorization_token(job_id: int, digest: str) -> str:
    """What the operator must type for a REAL run. It binds the approval to this job and this exact plan."""
    return f"AUTHORIZE-{job_id}-{digest[:8]}"


# ---------------------------------------------------------------------------------------------- the runner
@dataclass
class RunResult:
    state: str                       # DONE | STOPPED | FAULT | UNKNOWN | DRY_RUN_DONE
    reason: str = ""
    completed_strokes: int = 0
    total_strokes: int = 0
    interrupted_stroke: int | None = None
    fault: str | None = None
    force_summary: dict[str, float] | None = None
    duration_s: float = 0.0


@dataclass
class Snapshot:
    """What the viewer shows right now."""
    state: str = "IDLE"
    mode: str = ""
    job_id: int | None = None
    tcp: list[float] | None = None
    move_kind: str = ""
    stroke: int = 0
    total_strokes: int = 0
    progress_pct: float = 0.0
    force_n: float | None = None
    touching: bool = False
    fault: str | None = None
    message: str = ""
    joints_deg: list | None = None                  # joint angles for the 3D viewer (None when the robot has no joint model)
    level: int = 1                                  # highest open alert level (4 = press the E-Stop now)
    alerts: list = field(default_factory=list)      # [{code, level, title_vi, action_vi, estop_advised}]


class JobRunner:
    def __init__(self, robot: RobotPort, gripper: GripperPort | None, *, run_dir: Path, limits: ForceLimits,
                 bridge: Any = None, wait_for_paper: Callable[[int], bool] | None = None,
                 on_snapshot: Callable[[Snapshot], None] | None = None, clock: Callable[[], float] = time.monotonic,
                 ops: OpsReporter | None = None, watchdogs: Watchdogs | None = None, unsensed: bool = False,
                 waive_dry_run: bool = False):
        """`unsensed`: the owner chose to write with a plain spring gripper that has no force sensor. Without it a write needs gripper data."""
        self.clock = clock
        self.unsensed = unsensed
        self.waive_dry_run = waive_dry_run          # the person at the workstation waived the REAL pen-up rehearsal for this job (real-enable --waive-dry-run)
        self.ops = ops or OpsReporter(None, robot_id=None)
        self.watchdogs = watchdogs
        self.robot, self.gripper, self.run_dir, self.limits = robot, gripper, Path(run_dir), limits
        self.bridge, self.wait_for_paper, self.on_snapshot = bridge, wait_for_paper, on_snapshot
        self.ctl = Control()
        self.snap = Snapshot(mode=robot.mode.value)
        self.log: RunLog | None = None
        self._forces: list[float] = []
        self.info = None
        self.run_id = ""
        self._stop_lock = threading.Lock()

    # ---- helpers
    def _emit(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self.snap, k, v)
        if self.on_snapshot:
            self.on_snapshot(self.snap)

    def _event(self, kind: str, **payload: Any) -> None:
        if self.log:
            self.log.write("event", type=kind, **payload)
        if self.bridge is not None:
            try:
                self.bridge.event(self.snap.job_id, kind, **payload)
            except Exception as exc:                       # the run must not depend on the network
                if self.log:
                    self.log.write("bridge_error", type=kind, error=str(exc))

    # ---- stop / pause controls (called from the viewer or CLI threads)
    def pause(self) -> None:
        self.ctl.paused.set()
        self._emit(state="PAUSED")
        self._event("PAUSE", by="operator")

    def pause_after_stroke(self, reason: str = "") -> None:
        """Finish the stroke being written, then hold with the pen lifted (used when the link to the backend is lost)."""
        self.ctl.pause_after_stroke.set()
        if self.log:
            self.log.write("pause_after_stroke", reason=reason)

    def resume(self) -> None:
        self.ctl.pause_after_stroke.clear()
        self.ctl.paused.clear()
        self._emit(state="WRITING")
        self._event("RESUME", by="operator")

    def _raise(self, code: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Name an alert: the backend's catalogue gives level and wording, a built-in copy covers a dead network."""
        self.ops.log = self.log
        alert = self.ops.alert(code, job_id=self.snap.job_id, run_id=self.run_id or None, details=details)
        alerts = [a for a in self.snap.alerts if a["code"] != code] + [alert]
        alerts.sort(key=lambda a: -a["level"])
        self._emit(alerts=alerts, level=max(a["level"] for a in alerts))
        if alert["level"] >= 4:
            self._emit(state="DANGER", message=alert["title_vi"])
        return alert

    def _software_stop(self, reason: str) -> None:
        """Stop command + a check that the robot really stands still. This is NOT the hardware E-Stop."""
        with self._stop_lock:
            self.ctl.request_stop(reason)
            self.robot.stop()
            if self.log:
                self.log.write("software_stop", reason=reason)
        w = self.watchdogs
        if w is not None and w.configured():
            threading.Thread(target=self._verify_stopped, args=(reason,), daemon=True).start()

    def _verify_stopped(self, reason: str) -> None:
        w = self.watchdogs
        try:
            time.sleep(w.stop_settle_s)
            p0 = np.asarray(self.robot.read_tcp(), dtype=np.float64)
            time.sleep(w.stop_window_s)
            p1 = np.asarray(self.robot.read_tcp(), dtype=np.float64)
        except Exception as exc:                                   # noqa: BLE001 - not being able to look is itself a warning
            if self.log:
                self.log.write("stop_verify_error", error=str(exc))
            self._raise("LINK_LOST_MOVING", {"after_stop": reason, "error": str(exc)})
            return
        moved = float(np.linalg.norm(p1 - p0))
        if self.log:
            self.log.write("stop_verified", moved_mm=round(moved, 3), tolerance_mm=w.stop_tolerance_mm, reason=reason)
        if moved > w.stop_tolerance_mm:
            self._raise("STOP_NOT_EFFECTIVE", {"moved_mm": round(moved, 2), "after_stop": reason})
        elif self.gripper is not None:
            s = self.gripper.latest()
            if s is not None and s.force_n > self.limits.f_hard:
                self._raise("OVER_FORCE_STILL", {"force_n": round(s.force_n, 3)})

    def stop(self, reason: str = "operator stop") -> None:
        self._software_stop(reason)

    # ---- preflight
    def preflight(self, *, job_id: int, pages: list[Page], package_hash: str, probes: list[Any], cfg: MotionConfig,
                  ws: Workspace, dry_run: bool, authorization: str | None) -> tuple[list[PagePlan], PaperFrame, str]:

        def fail(code: str, msg: str, details: Any = None) -> None:
            if self.log:
                self.log.write("preflight_fail", code=code, message=msg)
            raise RunRefused(code, msg, details)

        info = self.robot.connect()
        self.info = info
        if self.log:
            self.log.write("robot_info", **info.as_dict())
        if info.mode != self.robot.mode:
            fail("MODE_MISMATCH", "Chế độ robot báo về khác chế độ yêu cầu.")
        if not self.robot.heartbeat():
            fail("ROBOT_NOT_READY", "Robot không phản hồi hoặc đang báo lỗi / dừng khẩn.")
        if self.robot.mode == Mode.REAL and not (self.watchdogs and self.watchdogs.configured()):
            fail("WATCHDOG_UNCONFIGURED", "Chưa cấu hình ngưỡng kiểm tra dừng thật và lệch đường (stop/tracking); "
                 "không chạy robot thật khi phần mềm chưa thể tự phát hiện robot không dừng.")
        if len(pages) > 1 and not dry_run and self.wait_for_paper is None:
            fail("PAPER_CHANGE_UNSUPPORTED", "Job nhiều trang cần người vận hành xác nhận thay giấy giữa các trang.")
        report, plans = validate(pages, probes, cfg, ws, require_box=self.robot.mode == Mode.REAL)
        if not report.passed:
            fail("VALIDATION_FAILED", "Kiểm chứng quỹ đạo không đạt; không chạy.", report.error_texts())
        frame = build_frame(probes)
        digest = plan_digest(package_hash, probes, cfg, ws)

        if self.robot.mode == Mode.REAL:
            cur = np.asarray(self.robot.read_tcp(), dtype=float)
            if cur.shape != (3,) or not np.all(np.isfinite(cur)):
                fail("INVALID_START_POSE", "Không đọc được vị trí TCP hợp lệ.")
            if np.any(cur < np.asarray(ws.box_min_mm)) or np.any(cur > np.asarray(ws.box_max_mm)):
                fail("START_OUTSIDE_WORKSPACE", "TCP hiện tại nằm ngoài vùng chạy đã cấu hình. Đưa robot về tư thế khởi đầu bằng jog tại máy.",
                     {"actual_mm": cur.tolist(), "box_min_mm": list(ws.box_min_mm), "box_max_mm": list(ws.box_max_mm)})
            rel = cur - frame.origin
            clearance = float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis))
            if clearance < cfg.pen_up_clearance_mm - 0.5:
                fail("START_POSE_UNSAFE", f"Đầu bút cao {clearance:.1f} mm so với giấy; cần nâng ít nhất {cfg.pen_up_clearance_mm:g} mm.")
            try:
                self.robot.check_start_ready()
            except RobotError as exc:
                fail(exc.code, exc.message, exc.details)

        pts = np.concatenate([p.all_points() for p in plans])
        keep, last = [0], pts[0]
        for i in range(1, len(pts)):
            if np.linalg.norm(pts[i] - last) >= REACH_SAMPLE_MM:
                keep.append(i)
                last = pts[i]
        problems = self.robot.check_reachable(pts[keep])
        if problems:
            fail("NOT_REACHABLE", "Bộ điều khiển báo có điểm ngoài tầm với hoặc không có nghiệm IK.", problems[:20])

        if self.gripper is not None:
            if hasattr(self.gripper, "observe"):          # the model needs the current pose; real hardware streams by itself
                self.gripper.observe(self.robot.read_tcp())
            s = self.gripper.latest()
            if s is None:
                fail("GRIPPER_NO_DATA", "Chưa nhận dữ liệu từ gripper.")
            elif s.flags & 8:
                fail("GRIPPER_UNCALIBRATED", "Gripper chưa hiệu chuẩn lực (bảng Hall -> N).")
            elif abs(s.force_n) > REST_FORCE_TOL_N:
                fail("GRIPPER_ZERO_DRIFT", f"Lực lúc nhấc bút {s.force_n:.3f} N lệch quá {REST_FORCE_TOL_N} N: cần TARE/hiệu chuẩn lại.")
        elif not dry_run and not self.unsensed:
            fail("GRIPPER_REQUIRED", "Viết cần dữ liệu lực từ gripper.")
        if self.gripper is None and self.unsensed and not dry_run:
            if self.log:
                self.log.write("no_force_sensing", note="writing without a force sensor: pen pressure follows the spring model only; "
                               "no over-force or lost-contact detection. The operator watches and holds the E-Stop.")
            self._emit(message="KHÔNG có cảm biến lực: áp lực bút chỉ theo mô hình lò xo. Người vận hành giữ E-Stop.")

        stored = ProgressStore(self.run_dir / f"job{job_id}" / "progress.json").load()
        if self.robot.mode == Mode.REAL:
            if authorization != authorization_token(job_id, digest):
                fail("AUTHORIZATION_REQUIRED", "Chưa có xác nhận của người vận hành cho job và kế hoạch này.",
                     {"expected_format": "AUTHORIZE-<job>-<8 ký tự đầu của digest>"})
            if not dry_run and not self.waive_dry_run and not (stored and stored.get("dry_run_ok") == "REAL" and stored.get("digest") == digest
                                                              and stored.get("execution_signature") == self.robot.execution_signature()):
                fail("DRY_RUN_REQUIRED", "Chưa chạy thử pen-up thành công bằng robot THẬT cho đúng kế hoạch này "
                     "(chạy thử trong mô phỏng không thay được).")
        if not dry_run and self.robot.mode == Mode.REAL and self.waive_dry_run and self.log:
            self.log.write("dry_run_waived", note="the operator at the workstation waived the REAL pen-up rehearsal for this job")
        return plans, frame, digest

    # ---- the run
    def run(self, *, job_id: int, pages: list[Page], package_hash: str, probes: list[Any], cfg: MotionConfig,
            ws: Workspace, dry_run: bool = False, authorization: str | None = None, resume_from: int | None = None,
            confirm_unknown: bool = False) -> RunResult:
        job_dir = self.run_dir / f"job{job_id}"
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-j{job_id}-{uuid.uuid4().hex[:6]}"
        self.run_id = run_id
        self.log = RunLog(job_dir / f"run-{run_id}.jsonl")
        self.ctl = Control()
        self._forces = []
        self.snap = Snapshot(mode=self.robot.mode.value, job_id=job_id, state="PREFLIGHT")
        store = ProgressStore(job_dir / "progress.json")
        with ControllerLock(self.run_dir / "agent.lock"):
            try:
                plans, frame, digest = self.preflight(job_id=job_id, pages=pages, package_hash=package_hash,
                                                      probes=probes, cfg=cfg, ws=ws, dry_run=dry_run,
                                                      authorization=authorization)
            except RunRefused as exc:
                self._emit(state="REFUSED", message=exc.message)
                self.ops.log = self.log
                self.ops.open_run(job_id, run_id=run_id, mode=self.robot.mode.value, dry_run=dry_run, authorized=False,
                                  digest=None, total=0, robot_info=self.info.as_dict() if self.info else None,
                                  agent_version=__version__, refused_reason=f"{exc.code}: {exc.message}"[:500])
                self._raise("PREFLIGHT_REFUSED", {"code": exc.code, "reason": exc.message})
                raise
            prog = store.load() or {}
            if prog.get("digest") not in (None, digest):
                # the approved package or the calibration changed: whatever is on the paper belongs to another plan
                if prog.get("completed", 0) > 0 and not dry_run:
                    raise RunRefused("PLAN_CHANGED", "Kế hoạch khác với lần chạy dở trước đó; cần giấy mới và xác nhận.")
                prog = {}
            if not dry_run:
                prog = self._check_resume(prog, resume_from, confirm_unknown)
            moves_by_stroke = self._group(plans)
            total = len(moves_by_stroke)
            start = prog.get("resume_at", 0) if not dry_run else 0
            self.ops.log = self.log
            if not self.ops.open_run(job_id, run_id=run_id, mode=self.robot.mode.value, dry_run=dry_run,
                                     authorized=self.robot.mode == Mode.REAL, digest=digest, total=total,
                                     robot_info=self.info.as_dict() if self.info else None, agent_version=__version__):
                if self.robot.mode == Mode.REAL:
                    raise RunRefused("BACKEND_UNREACHABLE", "Không ghi được lần chạy lên máy chủ (cần cho chạy robot thật): "
                                     + (self.ops.last_error or ""))
            self.ops.start_heartbeat(self.robot, self.robot.mode.value,
                                     {"controller_version": getattr(self.info, "controller_version", None),
                                      "firmware_version": getattr(self.info, "firmware_version", None),
                                      "sdk_version": getattr(self.info, "sdk_version", None), "agent_version": __version__})
            self._emit(total_strokes=total, state="DRY_RUN" if dry_run else "WRITING")
            self.log.write("run_start", job_id=job_id, mode=self.robot.mode.value, dry_run=dry_run, digest=digest,
                           start_stroke=start, total=total)
            if not dry_run:
                self._event("PROGRESS", stroke_index=start, progress_pct=100.0 * start / max(total, 1),
                            agent_run={"run_id": run_id, "digest": digest, "total_strokes": total, "start_stroke": start,
                                       "robot": self.info.as_dict() if self.info else None,
                                       "estimated_seconds": round(sum(p.duration_s for p in plans), 1)})
            monitor = SafetyMonitor(self.limits, self.clock)
            t0 = time.monotonic()
            try:
                result = self._execute(job_id, moves_by_stroke, frame, cfg, monitor, dry_run, start, total, digest, store, prog)
            except RunRefused as exc:                             # e.g. the pen starts too low: refused, nothing moved
                self.ops.close_run(run_id, result="REFUSED", completed=0, total=total,
                                   summary={"reason": f"{exc.code}: {exc.message}"[:500]})
                self._raise("PREFLIGHT_REFUSED", {"code": exc.code, "reason": exc.message})
                self._emit(state="REFUSED", message=exc.message)
                raise
            except BaseException:                                 # an unexpected crash is still a run that must be closed
                self.ops.close_run(run_id, result="UNKNOWN", completed=0, total=total, summary={"reason": "agent crashed"})
                raise
            finally:
                self.ops.stop_heartbeat()
            result.duration_s = round(time.monotonic() - t0, 2)
            self.log.write("run_end", **{k: v for k, v in result.__dict__.items()})
            self.ops.close_run(run_id, result=result.state, completed=result.completed_strokes, total=result.total_strokes,
                               summary={**(result.force_summary or {}), "duration_s": result.duration_s,
                                        "reason": result.reason, "fault": result.fault, "force_sensing": self.gripper is not None,
                                        "dry_run_waived": bool(self.waive_dry_run and not dry_run and self.robot.mode == Mode.REAL)})
            return result

    def _check_resume(self, prog: dict[str, Any], resume_from: int | None, confirm_unknown: bool) -> dict[str, Any]:
        done = int(prog.get("completed", 0))
        state = prog.get("state")
        if done == 0 and state not in ("STOPPED", "UNKNOWN", "RUNNING", "FAULT"):
            return {**prog, "resume_at": 0}
        if state == "DONE":
            raise RunRefused("JOB_ALREADY_WRITTEN", "Job này đã viết xong; chạy lại sẽ viết chồng nét.")
        if state in ("RUNNING", "UNKNOWN") and not confirm_unknown:
            raise RunRefused("OUTCOME_UNKNOWN", "Lần chạy trước kết thúc không rõ (mất kết nối hoặc agent tắt đột ngột). "
                             "Kiểm tra bản viết trên giấy rồi xác nhận bằng confirm_unknown.", {"completed": done})
        allowed = {done, done + 1}
        if resume_from is None or resume_from not in allowed:
            raise RunRefused("PARTIAL_JOB_EXISTS", f"Đã viết {done} nét. Chọn resume_from={done} (viết lại nét dở) hoặc "
                             f"{done + 1} (bỏ qua nét dở) sau khi xem tờ giấy; không tự chạy lại từ đầu.",
                             {"completed": done, "allowed": sorted(allowed)})
        return {**prog, "resume_at": int(resume_from)}

    @staticmethod
    def _group(plans: list[PagePlan]) -> list[list[tuple[int, Any]]]:
        """One entry per stroke: its moves, with the page index (strokes keep their global order)."""
        out: list[list[tuple[int, Any]]] = []
        for pi, plan in enumerate(plans):
            cur: list[tuple[int, Any]] = []
            for mv in plan.moves:
                if mv.kind == "travel":
                    cur.append((pi, mv))
                    continue
                cur.append((pi, mv))
                if mv.kind == "retract":
                    out.append(cur)
                    cur = []
        return out

    def _execute(self, job_id: int, strokes: list[list[tuple[int, Any]]], frame: PaperFrame, cfg: MotionConfig,
                 monitor: SafetyMonitor, dry_run: bool, start: int, total: int, digest: str, store: ProgressStore,
                 prog: dict[str, Any]) -> RunResult:
        real_store = store
        if dry_run:
            store = _NullStore()                                # type: ignore[assignment]
        lift_dry = frame.normal * (cfg.press_mm + cfg.pen_up_clearance_mm)
        state: dict[str, Any] = {"kind": "", "idx": 0, "n": 0, "last_emit": 0.0, "fault": None, "last_poll": 0.0,
                                "last_health": 0.0, "track_since": None}

        def on_tcp(p: np.ndarray, _t: float) -> None:
            if self.gripper is not None and hasattr(self.gripper, "observe"):
                self.gripper.observe(p)
            state["n"] += 1
            sample = self.gripper.latest() if self.gripper is not None else None
            writing = state["kind"] == "write" and not dry_run and state["n"] > CONTACT_GRACE_POINTS
            fault = None
            if self.gripper is not None:
                if dry_run and sample is not None and sample.flags & FLAG_TOUCH:
                    from vhrs_agent.gripper import Fault
                    fault = Fault("OVER_FORCE", "Bút chạm giấy trong lúc chạy thử pen-up", True)
                else:
                    fault = monitor.evaluate(sample, writing=writing)
            if sample is not None and state["kind"] == "write":
                self._forces.append(sample.force_n)
            now = time.monotonic()
            if now - state["last_emit"] > 0.1:
                state["last_emit"] = now
                self._emit(tcp=[round(float(v), 3) for v in p], joints_deg=self.robot.read_joints(), move_kind=state["kind"], stroke=state["idx"],
                           force_n=None if sample is None else round(sample.force_n, 3),
                           touching=bool(sample and sample.touching))
            w = self.watchdogs
            tc = self.clock()                                       # watchdog timing follows the injectable clock (tests)
            if fault is None and w is not None and w.configured() and not self.ctl.stop.is_set() and tc - state["last_poll"] >= 0.1:
                state["last_poll"] = tc
                from vhrs_agent.gripper import Fault
                err = float(np.linalg.norm(np.asarray(self.robot.read_tcp(), dtype=np.float64) - np.asarray(p, dtype=np.float64)))
                if err > w.tracking_tolerance_mm:
                    state["track_since"] = state["track_since"] if state["track_since"] is not None else tc
                    if tc - state["track_since"] > w.tracking_grace_s:
                        fault = Fault("TRACKING_ERROR", f"Đầu bút lệch {err:.1f} mm so với lệnh", True)
                else:
                    state["track_since"] = None
                if fault is None and tc - state["last_health"] >= 1.0:
                    state["last_health"] = tc
                    if not self.robot.heartbeat():
                        fault = Fault("CONTROLLER_SAFETY_FAULT", "Controller báo lỗi hoặc dừng khẩn", True)
            if fault is not None and state["fault"] is None:
                state["fault"] = fault if fault.stop else None
                self.log.write("fault", code=fault.code, reason=fault.reason, stop=fault.stop, stroke=state["idx"])
                self._raise(fault.code, {"reason": fault.reason, "stroke": state["idx"]})
                if fault.stop:
                    self._software_stop(f"{fault.code}: {fault.reason}")
                else:
                    self.ctl.paused.set()                           # the motion loop blocks in checkpoint() until resumed
                    self._emit(state="PAUSED", fault=fault.code, message=fault.reason)
                    self._event(fault.code, stroke_index=state["idx"], reason=fault.reason)
                    monitor.reset_contact()                         # a fresh window after the operator resumes

        completed = start
        first_move, cur_page = True, strokes[start][0][0] if start < total else 0
        try:
            for si in range(start, total):
                state["idx"] = si
                if self.ctl.pause_after_stroke.is_set() and not self.ctl.paused.is_set():
                    self.ctl.paused.set()                               # between strokes: the previous stroke ended with the pen up
                    self._emit(state="PAUSED", message="Mất kết nối hệ thống: đã viết xong nét, robot tạm dừng.")
                    self._event("PAUSE", by="link_lost")
                store.save({**prog, "digest": digest, "job_id": job_id, "state": "RUNNING", "completed": completed,
                            "interrupted": si, "dry_run_ok": prog.get("dry_run_ok", False)})
                for pi, mv in strokes[si]:
                    if mv.kind == "travel" and first_move:
                        continue                                            # replaced by the approach from the real pose
                    if pi != cur_page and mv.kind in ("travel", "plunge"):
                        if not dry_run and (self.wait_for_paper is None or not self.wait_for_paper(pi)):
                            self.ctl.request_stop("Chưa xác nhận đã thay giấy cho trang mới")
                            return self._stopped(job_id, si, completed, state, store, prog, digest, total)
                        cur_page = pi
                    pts = mv.points
                    if first_move:
                        first_move = False
                        pts_first = self._approach(frame, cfg, pts[0] if mv.kind == "plunge" else None, strokes[si], dry_run)
                        state["kind"], state["n"] = "travel", 0
                        self.log.write("command", move="approach", stroke=si, n_points=len(pts_first), mode=self.robot.mode.value)
                        try:
                            self.robot.execute(pts_first, np.full(len(pts_first), cfg.travel_speed_mm_s), self.ctl, on_tcp)
                        except StopRequested:
                            return self._stopped(job_id, si, completed, state, store, prog, digest, total)
                    if dry_run:
                        if mv.kind in ("plunge", "retract"):
                            continue                                        # no vertical moves while the pen stays up
                        if mv.kind == "write":
                            pts = pts + lift_dry
                    state["kind"], state["n"] = mv.kind, 0
                    monitor.reset_contact()
                    self.log.write("command", move=mv.kind, stroke=si, n_points=len(pts), mode=self.robot.mode.value)
                    try:
                        self.robot.execute(pts, mv.speeds, self.ctl, on_tcp)
                    except StopRequested:
                        return self._stopped(job_id, si, completed, state, store, prog, digest, total)
                    stats = getattr(self.robot, "motion_stats", None)
                    if stats:                                               # how stop-and-go the controller-planned moves were
                        self.log.write("motion_stats", move=mv.kind, stroke=si, **stats)
                        self.robot.motion_stats = None
                    if state["fault"] is not None and not state["fault"].stop:
                        state["fault"] = None                               # it was a pause: the operator resumed
                completed = si + 1
                store.save({**prog, "digest": digest, "job_id": job_id, "state": "RUNNING", "completed": completed,
                            "interrupted": None, "dry_run_ok": prog.get("dry_run_ok", False)})
                pct = 100.0 * completed / max(total, 1)
                self._emit(stroke=completed, progress_pct=round(pct, 1))
                if not dry_run:
                    self._event("PROGRESS", stroke_index=si, progress_pct=round(pct, 2))
        except CommunicationLost as exc:
            store.save({**prog, "digest": digest, "job_id": job_id, "state": "UNKNOWN", "completed": completed,
                        "interrupted": state["idx"], "dry_run_ok": prog.get("dry_run_ok", False)})
            self.log.write("comm_lost", code=exc.code, error=exc.message, details=exc.details, stroke=state["idx"])
            self._raise("LINK_LOST_MOVING", {"stroke": state["idx"], "error": exc.message})
            self._raise("RUN_OUTCOME_UNKNOWN", {"stroke": state["idx"]})
            self._emit(state="UNKNOWN", message="Mất kết nối: không rõ lệnh cuối đã chạy đến đâu. KHÔNG tự chạy lại.")
            self._event("ESTOP", reason="communication lost", stroke_index=state["idx"])
            return RunResult("UNKNOWN", exc.message, completed, total, state["idx"], exc.code)
        except RobotError as exc:
            # A rejected SDK motion must terminate the visible run as well as
            # the worker; otherwise status misleadingly stays DRY_RUN/WRITING.
            self.robot.stop()
            store.save({**prog, "digest": digest, "job_id": job_id, "state": "FAULT", "completed": completed,
                        "interrupted": state["idx"], "dry_run_ok": prog.get("dry_run_ok", False)})
            self.log.write("robot_error", code=exc.code, error=exc.message, details=exc.details, stroke=state["idx"])
            self._raise("CONTROLLER_SAFETY_FAULT", {"code": exc.code, "reason": exc.message, "details": exc.details})
            self._emit(state="FAULT", fault=exc.code, message=exc.message)
            return RunResult("FAULT", exc.message, completed, total, state["idx"], exc.code)

        if dry_run:
            real_store.mark_dry_run_ok(job_id, digest, self.robot.mode.value, self.robot.execution_signature())
            self._emit(state="DRY_RUN_DONE", progress_pct=100.0)
            return RunResult("DRY_RUN_DONE", "", total, total)
        store.save({**prog, "digest": digest, "job_id": job_id, "state": "DONE", "completed": total, "interrupted": None,
                    "dry_run_ok": prog.get("dry_run_ok", False)})
        summary = self._force_summary()
        self._emit(state="DONE", progress_pct=100.0)
        if summary:
            self._event("FORCE_SUMMARY", force_summary=summary, run_id=self.run_id, mode=self.robot.mode.value)
        return RunResult("DONE", "", total, total, force_summary=summary)

    def _approach(self, frame: PaperFrame, cfg: MotionConfig, plunge_start: np.ndarray | None,
                  stroke_moves: list[tuple[int, Any]], dry_run: bool) -> np.ndarray:
        """From the robot's real pose to the point above the first stroke, never below the clearance height.
        Refuses when the pen is not already clear of the paper: no automatic guess about where the arm is."""
        cur = np.asarray(self.robot.read_tcp(), dtype=np.float64)
        rel = cur - frame.origin
        u, w, h = float(rel @ frame.x_axis), float(rel @ frame.y_axis), float(rel @ frame.normal)
        lift = h - float(frame.height(u, w))
        if lift < cfg.pen_up_clearance_mm - 0.5:
            raise RunRefused("START_POSE_UNSAFE", f"Đầu bút đang cao {lift:.1f} mm so với giấy, thấp hơn độ cao nâng "
                             f"{cfg.pen_up_clearance_mm:g} mm. Nâng bút lên trước khi chạy (không tự di chuyển).")
        first = next(mv for _, mv in stroke_moves if mv.kind in ("plunge", "write"))
        above = np.asarray(first.points[0], dtype=np.float64)
        if first.kind == "write":
            above = above + frame.normal * (cfg.press_mm + cfg.pen_up_clearance_mm)
        return np.stack([cur, above])

    def _stopped(self, job_id: int, si: int, completed: int, state: dict[str, Any], store: ProgressStore,
                 prog: dict[str, Any], digest: str, total: int) -> RunResult:
        fault = state["fault"]
        store.save({**prog, "digest": digest, "job_id": job_id, "state": "STOPPED", "completed": completed,
                    "interrupted": si, "dry_run_ok": prog.get("dry_run_ok", False)})
        reason = self.ctl.reason or "stop"
        self.log.write("stopped", stroke=si, reason=reason)
        self._emit(state="STOPPED", fault=fault.code if fault else None, message=reason)
        if fault is None:
            self._raise("STROKE_INTERRUPTED", {"stroke": si, "reason": reason})
        kind = fault.code if fault else "ESTOP"
        self._event(kind, stroke_index=si, reason=reason, source="agent_software_stop")   # not the hardware E-stop
        return RunResult("FAULT" if fault else "STOPPED", reason, completed, total, si, fault.code if fault else None)

    def _force_summary(self) -> dict[str, float] | None:
        if not self._forces:
            return None
        f = np.array(self._forces)
        lim = self.limits
        in_band = float(np.mean((f >= lim.f_min) & (f <= lim.f_max)) * 100.0)
        rms = float(np.sqrt(np.mean((f - lim.f_target) ** 2)) / lim.f_target * 100.0)
        return {"f_mean": round(float(f.mean()), 4), "f_max": round(float(f.max()), 4), "rms_err_pct": round(rms, 2),
                "in_band_pct": round(in_band, 2), "samples": float(len(f))}
