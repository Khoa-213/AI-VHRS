"""The Robot Agent as a network service: every action (see the robot in 3D, load a job, check, rehearse, run, pause, stop) is an HTTP call.

Meant to run on the workstation (or, for SIM only, on any machine) and be used from other computers on the LAN with just a browser or any
HTTP client. People log in with their NORMAL system account: the agent checks the bearer token against the backend (`GET /api/v1/me`)
and uses the role the backend reports. Nothing is trusted from the client.

  view       Technical Staff, Manager      state, 3D data, WebSocket
  control    Technical Staff, Manager      pause, resume, stop (software stop only; never a substitute for the physical E-Stop)
  operate    Technical Staff               load / check / dry-run / run a job, confirm a paper change, identify the robot

Running the REAL robot through the API needs three independent things, so a remote caller can never start it alone:
  1. the agent was started with "real" in `modes` (only on the workstation wired to the robot);
  2. a person at the workstation ran `python -m vhrs_agent.cli real-enable --job N --minutes M` (an expiring file for THAT job);
  3. the caller sends the plan-bound authorization token (see runner.authorization_token) AND the job passes the dry-run requirement.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.requests import HTTPConnection

from app.services.motion.frame import build_frame
from app.services.motion.plan import MotionConfig
from app.services.motion.validate import Workspace, validate

from vhrs_agent import __version__
from vhrs_agent.bridge import BackendBridge, BridgeError
from vhrs_agent.gripper import ForceLimits, GripperPort, SimGripper
from vhrs_agent.ops import OpsReporter
from vhrs_agent.port import Control, Mode, RobotError, RobotPort, StopRequested
from vhrs_agent.runner import JobRunner, RunRefused, Watchdogs, authorization_token, plan_digest
from vhrs_agent.sim import MockRobot, SimRobot
from vhrs_agent.viewer import ViewerHub, create_app

ROLE_VIEW = {"TECHNICAL_STAFF", "MANAGER"}
ROLE_CONTROL = {"TECHNICAL_STAFF", "MANAGER"}
ROLE_OPERATE = {"TECHNICAL_STAFF"}
LEVEL_ROLES = {"view": ROLE_VIEW, "control": ROLE_CONTROL, "operate": ROLE_OPERATE}
REAL_ENABLE_MAX_MINUTES = 120


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


# ---------------------------------------------------------------------------------------------- configuration
@dataclass
class ServerConfig:
    backend_url: str
    host: str = "127.0.0.1"
    port: int = 8765
    modes: tuple[str, ...] = ("mock", "sim")             # add "real" only on the workstation wired to the robot
    run_dir: Path = Path("runs")
    sim: dict[str, Any] = field(default_factory=lambda: {"tool_offset_mm": 250.0, "table_z_mm": 19.0,
                                                         "start_mm": [-350.0, 0.0, 80.0], "speed_factor": 1.0, "yaw_deg": 0.0})
    fairino: dict[str, Any] | None = None                # {ip, tool_id, orientation_deg[3], servo_cmd_period_s, tcp_offset_mm?}
    watchdogs: dict[str, float] | None = None
    gripper_port: str | None = None
    cors_origins: list[str] = field(default_factory=list)
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    auth_cache_seconds: float = 30.0
    agent_key: str | None = None                          # per-robot key issued by a Manager; VHRS_AGENT_KEY in the environment wins
    link_loss_grace_s: float = 6.0                        # POLICY default (not a physical value): quiet this long during a write = link lost
    sync_idle_s: float = 1.0
    sync_active_s: float = 0.25
    start_point_mm: list[float] | None = None            # the fixed point the pen returns to (x, y, z in the robot base frame, mm); None = computed from the sheet
    unsensed_gripper: bool = False                        # the owner accepts REAL writing with a plain spring gripper (no force sensor); never a default
    robot_id: int | None = None                           # which robot this workstation drives (session login; needed when the technician has several)
    lan_server: bool = True                               # false: only the outbound link, no local web console / LAN API

    @classmethod
    def from_file(cls, path: str | Path) -> "ServerConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))      # Notepad may add a BOM
        raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        raw["run_dir"] = Path(raw.get("run_dir", "runs"))
        raw["modes"] = tuple(raw.get("modes", ("mock", "sim")))
        return cls(**raw)


@dataclass
class JobCtx:
    job_id: int
    owner_id: int
    robot_id: int
    pages: list
    package_hash: str
    probes: list
    cfg: MotionConfig
    ws: Workspace
    limits: ForceLimits
    pen_name: str | None
    summary: dict[str, Any]
    loaded_at: float = field(default_factory=time.time)


@dataclass
class Session:
    access: str
    refresh: str | None = None
    obtained: float = field(default_factory=time.monotonic)


class Body(BaseModel):
    model_config = {"extra": "forbid"}


class LoginIn(Body):
    email: str
    password: str = Field(min_length=1, max_length=72)


class ModeIn(Body):
    mode: str = Field(default="sim", pattern="^(mock|sim|real)$")


class RunIn(Body):
    mode: str = Field(default="sim", pattern="^(mock|sim|real)$")
    authorization: str | None = Field(default=None, max_length=200)
    resume_from: int | None = Field(default=None, ge=0)
    confirm_unknown: bool = False
    speed: float | None = Field(default=None, gt=0, le=1000, description="SIM only: simulation speed factor (1 = real time)")


class DryRunIn(Body):
    mode: str = Field(default="sim", pattern="^(mock|sim|real)$")
    authorization: str | None = Field(default=None, max_length=200)
    speed: float | None = Field(default=None, gt=0, le=1000)


# ---------------------------------------------------------------------------------------------- the service
class AgentService:
    def __init__(self, cfg: ServerConfig, *, transport: httpx.BaseTransport | None = None,
                 downloader: Callable[[str], bytes] | None = None,
                 robot_factory: Callable[[str], RobotPort] | None = None,
                 gripper_factory: Callable[[str, JobCtx, Any], GripperPort | None] | None = None):
        self.cfg, self.transport, self.downloader = cfg, transport, downloader
        self.robot_factory, self.gripper_factory = robot_factory, gripper_factory
        self.hub = ViewerHub(guard=self.guard)
        self.jobs: dict[int, JobCtx] = {}
        self.sessions: dict[str, Session] = {}
        self._who: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._busy = False
        self.align_ctl: Control | None = None
        self.current: dict[str, Any] | None = None
        self.last: dict[str, Any] | None = None
        self._kin = None
        self.paper_event = threading.Event()
        self.hub.paper_confirmed = self.paper_event                              # POST /api/paper-changed releases the runner's wait
        cfg.run_dir.mkdir(parents=True, exist_ok=True)

    # ---- backend
    def bridge(self, token: "str | Callable[[], str]") -> BackendBridge:
        return BackendBridge(self.cfg.backend_url, token, transport=self.transport, downloader=self.downloader)

    def identify(self, token: str) -> dict[str, Any]:
        key = hashlib.sha256(token.encode()).hexdigest()
        hit = self._who.get(key)
        if hit and time.monotonic() - hit[0] < self.cfg.auth_cache_seconds:
            return hit[1]
        try:
            me = self.bridge(token).root_req("GET", "/me")
        except BridgeError as exc:
            raise ApiError(401, "UNAUTHENTICATED", "Token không hợp lệ hoặc đã hết hạn: đăng nhập lại.") from exc
        except httpx.HTTPError as exc:
            raise ApiError(503, "BACKEND_UNREACHABLE", f"Không gọi được máy chủ: {exc}") from exc
        who = {"id": me["id"], "role": me["role"], "name": me.get("full_name", "")}
        self._who[key] = (time.monotonic(), who)
        return who

    @staticmethod
    def token_of(conn: HTTPConnection) -> str:
        auth = conn.headers.get("authorization", "")
        tok = auth[7:].strip() if auth.lower().startswith("bearer ") else conn.query_params.get("token", "")
        if not tok:
            raise ApiError(401, "UNAUTHENTICATED", "Cần đăng nhập (Authorization: Bearer <token>).")
        return tok

    def guard(self, level: str, conn: HTTPConnection) -> None:
        who = self.identify(self.token_of(conn))
        if who["role"] not in LEVEL_ROLES.get(level, ROLE_OPERATE):
            raise ApiError(403, "FORBIDDEN", f"Vai trò {who['role']} không được phép ({level}).")
        conn.state.user = who

    def user(self, request: Request) -> dict[str, Any]:
        self.guard("operate", request)
        return request.state.user

    def provider(self, access: "str | Callable[[], str]") -> Callable[[], str]:
        """The token to use for this user's backend calls; refreshed (if we hold a refresh token) so a long run does not lose it.
        A callable (the link's current session key) is used as it is: it already renews itself."""
        if callable(access):
            return access
        sess = self.sessions.setdefault(hashlib.sha256(access.encode()).hexdigest(), Session(access))

        def current() -> str:
            if sess.refresh and time.monotonic() - sess.obtained > 20 * 60:
                try:
                    out = self.bridge(sess.access).root_req("POST", "/auth/refresh", auth=False, json={"refresh_token": sess.refresh})
                    sess.access, sess.refresh, sess.obtained = out["access_token"], out["refresh_token"], time.monotonic()
                except Exception:                                             # noqa: BLE001 - keep using the old token
                    pass
            return sess.access

        return current

    # ---- login proxy: the browser never needs the backend's CORS
    def login(self, email: str, password: str) -> dict[str, Any]:
        try:
            out = self.bridge("").root_req("POST", "/auth/login", auth=False, json={"email": email, "password": password})
        except BridgeError as exc:
            raise ApiError(exc.status, exc.code, "Đăng nhập thất bại.") from exc
        except httpx.HTTPError as exc:
            raise ApiError(503, "BACKEND_UNREACHABLE", f"Không gọi được máy chủ: {exc}") from exc
        role = out["account"]["role"]
        if role not in ROLE_VIEW:
            raise ApiError(403, "FORBIDDEN", "Chỉ Technical Staff và Manager dùng được bảng điều khiển robot.")
        self.sessions[hashlib.sha256(out["access_token"].encode()).hexdigest()] = Session(out["access_token"], out["refresh_token"])
        return {"access_token": out["access_token"], "role": role, "name": out["account"]["full_name"]}

    # ---- robots
    def kin(self):
        if self._kin is None:
            from vhrs_agent.kinematics import FR3Kinematics
            self._kin = FR3Kinematics(tool_offset_mm=float(self.cfg.sim["tool_offset_mm"]), table_z_mm=self.cfg.sim.get("table_z_mm"))
        return self._kin

    def make_robot(self, mode: str, speed: float | None) -> RobotPort:
        if mode not in self.cfg.modes:
            raise ApiError(403, "MODE_DISABLED", f"Chế độ {mode.upper()} không được bật trên agent này.", {"enabled": list(self.cfg.modes)})
        if self.robot_factory is not None:
            return self.robot_factory(mode)
        sim = self.cfg.sim
        start = tuple(sim["start_mm"])
        sf = speed if speed is not None else sim.get("speed_factor", 1.0)
        if mode == "mock":
            return MockRobot(start)
        if mode == "sim":
            try:
                from vhrs_agent.sim_pybullet import PyBulletSimRobot
                return PyBulletSimRobot(self.kin(), start, speed_factor=sf, yaw_deg=float(sim.get("yaw_deg", 0.0)))
            except Exception:                                                 # noqa: BLE001 - no PyBullet or no model: timing model only
                return SimRobot(start, speed_factor=sf)
        from vhrs_agent.fairino_robot import FairinoConfig, FairinoRobot
        if not self.cfg.fairino:
            raise ApiError(409, "REAL_NOT_CONFIGURED", "Chưa cấu hình kết nối FAIRINO (ip, tool_id, orientation_deg, servo_cmd_period_s).")
        c = dict(self.cfg.fairino)
        c["orientation_deg"] = tuple(c["orientation_deg"])
        return FairinoRobot(FairinoConfig(**c))

    def make_gripper(self, mode: str, ctx: JobCtx, frame: Any) -> GripperPort | None:
        if self.gripper_factory is not None:
            return self.gripper_factory(mode, ctx, frame)
        if mode == "real":
            if not self.cfg.gripper_port:
                if self.cfg.unsensed_gripper:
                    return None                                               # explicit owner choice: no force sensing (see JobRunner.unsensed)
                raise ApiError(409, "GRIPPER_NOT_CONFIGURED", "Chưa cấu hình cổng serial của gripper (gripper_port). "
                               "Gripper thường không cảm biến: đặt \"unsensed_gripper\": true để tự chịu giám sát bằng E-Stop.")
            from vhrs_agent.gripper import SerialGripper
            return SerialGripper(self.cfg.gripper_port)

        def depth(p: np.ndarray) -> float:
            rel = np.asarray(p) - frame.origin
            return -(float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis)))

        return SimGripper(depth, float(ctx.cfg.spring_k_n_per_mm or 0.4), ctx.limits.f_hard, float(ctx.cfg.max_spring_travel_mm or 6.0))

    def do_identify(self, mode: str) -> dict[str, Any]:
        if self._busy:
            raise ApiError(409, "AGENT_BUSY", "Agent đang chạy một job.", self.current)
        robot = self.make_robot(mode, None)
        try:
            info = robot.connect()                                            # read-only identification, no motion, no enable
            return {"info": info.as_dict(), "healthy": robot.heartbeat(), "tcp_mm": [round(float(v), 2) for v in robot.read_tcp()],
                    "joints_deg": robot.read_joints()}
        except Exception as exc:                                              # noqa: BLE001
            raise ApiError(502, "ROBOT_UNREACHABLE", f"{type(exc).__name__}: {exc}") from exc
        finally:
            robot.disconnect()

    def do_preflight(self, ctx: "JobCtx", mode: str, token: str) -> dict[str, Any]:
        if self._busy:
            raise ApiError(409, "AGENT_BUSY", "Agent đang chạy một job.", self.current)
        runner, robot = self._runner(ctx, mode, None, token)
        try:
            plans, _, digest = runner.preflight(job_id=ctx.job_id, pages=ctx.pages, package_hash=ctx.package_hash, probes=ctx.probes,
                                                cfg=ctx.cfg, ws=ctx.ws, dry_run=True, authorization=None if mode != "real" else "-")
            return {"ok": True, "mode": mode, "plan_digest": digest, "moves": sum(len(p.moves) for p in plans)}
        except RunRefused as exc:
            if mode == "real" and exc.code in ("AUTHORIZATION_REQUIRED",):
                return {"ok": True, "mode": mode, "note": "Các kiểm tra khác đạt; cần mã xác nhận khi chạy thật."}
            return {"ok": False, "code": exc.code, "message": exc.message, "details": exc.details}
        finally:
            robot.disconnect()

    ALIGN_MARGIN_MM = 20.0          # the fixed start: this far in from the sheet's top-left corner,
    ALIGN_EXTRA_CLEARANCE_MM = 0.5  # this much above the pen-up height: the writing moves need pen-up height minus 0.5 mm, and the safe box is often tight above it

    def start_point(self, ctx: "JobCtx") -> np.ndarray:
        """The fixed start of this job: the configured `start_point_mm` (read from the robot's own display), else above the sheet near its
        top-left corner at the pen-up height plus a margin."""
        if self.cfg.start_point_mm is not None:
            if len(self.cfg.start_point_mm) != 3:
                raise ApiError(409, "INVALID_CONFIG", "start_point_mm phải có 3 số: x, y, z (mm).")
            return np.asarray(self.cfg.start_point_mm, dtype=np.float64)
        frame = build_frame(ctx.probes)
        page = ctx.pages[0]
        u, w = min(self.ALIGN_MARGIN_MM, page.width_mm / 4), min(self.ALIGN_MARGIN_MM, page.height_mm / 4)
        lift = float(ctx.cfg.pen_up_clearance_mm or 0.0) + self.ALIGN_EXTRA_CLEARANCE_MM
        return frame.origin + u * frame.x_axis + w * frame.y_axis + (float(frame.height(u, w)) + lift) * frame.normal

    def do_align(self, ctx: "JobCtx", mode: str, authorization: str | None) -> dict[str, Any]:
        """Move the arm to the job's fixed start pose (position AND the fixed writing orientation). REAL motion: same site switch and plan-bound
        token as a rehearsal. Refuses when the pen is lower than the pen-up height or the target leaves the safe box."""
        if mode == "real":
            if "real" not in self.cfg.modes:
                raise ApiError(403, "MODE_DISABLED", "Chế độ REAL không được bật trên agent này.")
            self.real_gate(ctx.job_id)
            if authorization != authorization_token(ctx.job_id, ctx.summary["plan_digest"]):
                raise ApiError(409, "AUTHORIZATION_REQUIRED", "Chưa có xác nhận của người vận hành cho job và kế hoạch này.")
        with self._lock:
            if self._busy:
                raise ApiError(409, "AGENT_BUSY", "Agent đang chạy một job khác.", self.current)
            self._busy = True
        robot = None
        try:
            ws = ctx.ws
            target = self.start_point(ctx)
            if ws.box_min_mm is None or ws.box_max_mm is None or np.any(target < np.asarray(ws.box_min_mm)) or np.any(target > np.asarray(ws.box_max_mm)):
                raise ApiError(409, "START_OUTSIDE_WORKSPACE", "Điểm bắt đầu nằm ngoài hộp an toàn (hoặc chưa cấu hình hộp).",
                               {"target_mm": [round(float(v), 2) for v in target]})
            robot = self.make_robot(mode, None)
            robot.connect()
            if mode == "real" and not robot.heartbeat():
                raise ApiError(409, "ROBOT_NOT_READY", "Robot không phản hồi hoặc đang báo lỗi / dừng khẩn.")
            self.current = {"job_id": ctx.job_id, "mode": mode, "align_start": True, "started_at": time.time()}
            return {**self.move_to_start(ctx, robot), "mode": mode, "target_mm": [round(float(v), 2) for v in target]}
        finally:
            self.align_ctl = None
            self.current = None
            if robot is not None:
                try:
                    robot.disconnect()
                except Exception:                                        # noqa: BLE001
                    pass
            self._busy = False

    def move_to_start(self, ctx: "JobCtx", robot: RobotPort) -> dict[str, Any]:
        """With the robot already connected: lift the pen straight up when it is lower than the pen-up height, then go to the fixed start
        pose with the writing orientation. STOP/PAUSE stop it through `align_ctl`. Raises ApiError."""
        ws = ctx.ws
        target = self.start_point(ctx)
        frame = build_frame(ctx.probes)
        cur = np.asarray(robot.read_tcp(), dtype=np.float64)
        rel = cur - frame.origin
        clearance = float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis))
        pen_up = float(ctx.cfg.pen_up_clearance_mm or 0.0)
        self.align_ctl = Control()
        try:
            lifted = None
            if clearance < pen_up - 0.5:
                # The pen is lower than the pen-up height (even resting on the paper): first straight UP, so that the sideways move
                # to the start can never drag it across the sheet.
                way = cur + frame.normal * (pen_up + self.ALIGN_EXTRA_CLEARANCE_MM - clearance)
                if np.any(way < np.asarray(ws.box_min_mm)) or np.any(way > np.asarray(ws.box_max_mm)):
                    raise ApiError(409, "START_OUTSIDE_WORKSPACE", "Điểm nhấc bút lên nằm ngoài hộp an toàn: nhấc bút lên bằng tay.",
                                   {"lift_point_mm": [round(float(v), 2) for v in way]})
                lifted = robot.align_to(way, self.align_ctl)
            res = robot.align_to(target, self.align_ctl)
            if lifted is not None:
                res = {**res, "lifted_first": True, "lift_mm": round(float(pen_up + self.ALIGN_EXTRA_CLEARANCE_MM - clearance), 1)}
            return res
        except StopRequested as exc:
            raise ApiError(409, "ALIGN_STOPPED", f"Đã dừng khi căn điểm bắt đầu: {exc}") from exc
        except RobotError as exc:
            raise ApiError(409, exc.code, exc.message, exc.details) from exc
        finally:
            self.align_ctl = None

    def return_to_start(self, ctx: "JobCtx", robot: RobotPort, runner: JobRunner) -> dict[str, Any]:
        """After a finished run the pen goes back to the fixed start by itself. A failure here never changes the result of the run; it is
        reported next to it (`return_to_start`) and the operator brings the pen back with `align-start`."""
        try:
            runner._emit(message="Xong. Đang đưa bút về điểm bắt đầu…")
            res = self.move_to_start(ctx, robot)
            runner._emit(message="Xong. Bút đã về điểm bắt đầu.")
            return {"ok": True, **res}
        except ApiError as exc:
            runner._emit(message=f"Xong, nhưng chưa về được điểm bắt đầu ({exc.code}). Dùng align-start.")
            return {"ok": False, "code": exc.code, "message": exc.message}
        except Exception as exc:                                              # noqa: BLE001
            return {"ok": False, "code": "RETURN_FAILED", "message": f"{type(exc).__name__}: {exc}"}

    def need_runner(self) -> JobRunner:
        if self.hub.runner is None or not self._busy:
            raise ApiError(409, "NO_RUN_ACTIVE", "Chưa có job đang chạy.")
        return self.hub.runner

    # ---- REAL gate
    def real_gate(self, job_id: int) -> dict[str, Any]:
        f = self.cfg.run_dir / "REAL_ENABLED.json"
        hint = f"Người vận hành tại máy trạm chạy: python -m vhrs_agent.cli real-enable --job {job_id} --minutes 30"
        if not f.exists():
            raise ApiError(403, "REAL_NOT_ENABLED_ON_SITE", "Chạy robot thật cần người ở máy trạm bật cho đúng job này. " + hint)
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ApiError(403, "REAL_NOT_ENABLED_ON_SITE", "File bật chạy thật hỏng. " + hint) from exc
        if data.get("job_id") != job_id or float(data.get("expires_at", 0)) < time.time():
            raise ApiError(403, "REAL_NOT_ENABLED_ON_SITE", "Việc bật chạy thật không áp dụng cho job này hoặc đã hết hạn. " + hint)
        return data

    # ---- jobs
    def load_job(self, job_id: int, token: str, who: dict[str, Any]) -> JobCtx:
        br = self.bridge(self.provider(token))
        try:
            job = br.fetch_job(job_id)
            detail = br.job_detail(job_id)
        except BridgeError as exc:
            raise ApiError(exc.status, exc.code, str(exc)) from exc
        cal = detail.get("calibration")
        if not cal:
            raise ApiError(409, "CALIBRATION_REQUIRED", "Job chưa có hiệu chuẩn hiện hành.")
        pen = job["package"]["pen"]
        if pen is None:
            raise ApiError(409, "PEN_REQUIRED", "Job chưa có bút (hồ sơ lực).")
        block = cal.get("frame_transform") or {}
        cfg = MotionConfig.from_dict({**(block.get("motion") or {}), "f_target_n": pen["f_target_n"], "v_max_mm_s": pen["v_max_mm_s"]})
        ws = Workspace.from_dict(block.get("workspace"))
        limits = ForceLimits(pen["f_min_n"], pen["f_target_n"], pen["f_max_n"], pen["f_hard_n"])
        report, plans = validate(job["pages"], cal["probe_points"], cfg, ws, require_box=False)
        digest = plan_digest(job["hash"], cal["probe_points"], cfg, ws)
        summary = {"job_id": job_id, "order_code": job["package"]["order_code"], "robot_id": detail["robot_id"],
                   "job_status": detail["status"], "pages": len(job["pages"]), "strokes": sum(len(p.strokes) for p in job["pages"]),
                   "package_hash": job["hash"], "plan_digest": digest, "pen": pen["name"],
                   "estimated_seconds": report.stats.get("estimated_seconds"), "validation": report.as_dict(),
                   "authorization_token": authorization_token(job_id, digest)}
        ctx = JobCtx(job_id, who["id"], detail["robot_id"], job["pages"], job["hash"], cal["probe_points"], cfg, ws, limits,
                     pen["name"], summary)
        self.jobs[job_id] = ctx
        return ctx

    def ctx(self, job_id: int, who: dict[str, Any]) -> JobCtx:
        ctx = self.jobs.get(job_id)
        if ctx is None or ctx.owner_id != who["id"]:
            raise ApiError(409, "JOB_NOT_LOADED", "Hãy tải job trước (POST /api/jobs/{id}/load).")
        return ctx

    def progress(self, job_id: int) -> dict[str, Any] | None:
        f = self.cfg.run_dir / f"job{job_id}" / "progress.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def watchdogs(self) -> Watchdogs | None:
        return Watchdogs(**self.cfg.watchdogs) if self.cfg.watchdogs else None

    # ---- running
    def _runner(self, ctx: JobCtx, mode: str, speed: float | None, token: str, waive_dry_run: bool = False) -> tuple[JobRunner, RobotPort]:
        robot = self.make_robot(mode, speed)
        frame = build_frame(ctx.probes)
        gripper = self.make_gripper(mode, ctx, frame)
        br = self.bridge(self.provider(token))
        ops = OpsReporter(br, robot_id=ctx.robot_id)
        runner = JobRunner(robot, gripper, run_dir=self.cfg.run_dir, limits=ctx.limits, bridge=br, ops=ops,
                           watchdogs=self.watchdogs(), wait_for_paper=self._wait_for_paper,
                           unsensed=bool(mode == "real" and gripper is None and self.cfg.unsensed_gripper), waive_dry_run=waive_dry_run)
        tool = float(self.cfg.sim["tool_offset_mm"]) if mode != "real" else float((self.cfg.fairino or {}).get("tcp_offset_mm") or 0) or None
        self.hub.attach(runner, ctx.pages, frame, ctx.limits, ctx.cfg.press_mm, ctx.cfg.pen_up_clearance_mm or 0.0, ctx.job_id, tool_mm=tool)
        return runner, robot

    def _wait_for_paper(self, page: int) -> bool:
        self.paper_event.clear()
        runner = self.hub.runner
        if runner is not None:
            runner._emit(state="AWAITING_PAPER", message=f"Đặt giấy mới cho trang {page + 1} rồi xác nhận")
            runner._raise("PAPER_CHANGE", {"page": page + 1})
        ok = self.paper_event.wait(timeout=900)
        if runner is not None and ok:
            runner._emit(state="WRITING", message="")
        return ok

    def start(self, ctx: JobCtx, token: str, by: str, *, mode: str, dry_run: bool, authorization: str | None, resume_from: int | None,
              confirm_unknown: bool, speed: float | None) -> dict[str, Any]:
        if mode == "real":
            if "real" not in self.cfg.modes:
                raise ApiError(403, "MODE_DISABLED", "Chế độ REAL không được bật trên agent này.")
            waive = bool(self.real_gate(ctx.job_id).get("waive_dry_run")) and not dry_run
        else:
            waive = False
        with self._lock:
            if self._busy:
                raise ApiError(409, "AGENT_BUSY", "Agent đang chạy một job khác.", self.current)
            self._busy = True
        try:
            runner, robot = self._runner(ctx, mode, speed, token, waive_dry_run=waive)
        except Exception:
            self._busy = False
            raise
        self.current = {"job_id": ctx.job_id, "mode": mode, "dry_run": dry_run, "started_at": time.time(), "by": by}
        self.last = None
        done = threading.Event()

        def work() -> None:
            try:
                res = runner.run(job_id=ctx.job_id, pages=ctx.pages, package_hash=ctx.package_hash, probes=ctx.probes, cfg=ctx.cfg, ws=ctx.ws,
                                 dry_run=dry_run, authorization=authorization, resume_from=resume_from, confirm_unknown=confirm_unknown)
                self.last = {"result": {k: v for k, v in res.__dict__.items()}, "job_id": ctx.job_id, "mode": mode, "dry_run": dry_run}
                if res.state in ("DONE", "DRY_RUN_DONE"):                       # finished cleanly: the pen goes back to the fixed start
                    self.last["return_to_start"] = self.return_to_start(ctx, robot, runner)
            except RunRefused as exc:
                self.last = {"refused": {"code": exc.code, "message": exc.message, "details": exc.details}, "job_id": ctx.job_id}
            except Exception as exc:                                          # noqa: BLE001 - never leave the agent stuck busy
                self.last = {"error": f"{type(exc).__name__}: {exc}", "job_id": ctx.job_id}
            finally:
                try:
                    robot.disconnect()
                except Exception:                                             # noqa: BLE001
                    pass
                self.current = None
                self._busy = False
                done.set()

        threading.Thread(target=work, daemon=True, name=f"run-{ctx.job_id}").start()
        end = time.monotonic() + 12.0                                          # report a refusal at once, otherwise say "started"
        while time.monotonic() < end:
            if done.wait(0.05):
                break
            if runner.snap.state not in ("PREFLIGHT", "IDLE", "REFUSED"):
                return {"started": True, "state": runner.snap.state, "mode": mode, "dry_run": dry_run}
        if self.last and "refused" in self.last:
            ref = self.last["refused"]
            raise ApiError(409, ref["code"], ref["message"], ref["details"])
        return {"started": not done.is_set(), "state": runner.snap.state, "last": self.last}


# ---------------------------------------------------------------------------------------------- the web app
def create_server_app(service: AgentService) -> FastAPI:
    app = create_app(service.hub)
    if service.cfg.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=service.cfg.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, status_code=exc.status)

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "details": None}},
                            status_code=exc.status_code)

    @app.get("/api/agent")
    def agent(request: Request) -> dict[str, Any]:
        sim_model = False
        try:
            from vhrs_agent.kinematics import DEFAULT_URDF
            sim_model = DEFAULT_URDF.exists()
        except Exception:                                                     # noqa: BLE001
            pass
        return {"version": __version__, "auth_required": True, "backend_url": service.cfg.backend_url, "modes": list(service.cfg.modes),
                "busy": service._busy, "current": service.current, "last": service.last, "joint_model_available": sim_model,
                "real_requires": "real-enable at the workstation + plan authorization token + a finished dry run"}

    @app.post("/api/login")
    def login(body: LoginIn) -> dict[str, Any]:
        return service.login(body.email, body.password)

    @app.get("/api/my-jobs")
    def my_jobs(request: Request) -> Any:
        service.guard("view", request)
        token = service.token_of(request)
        try:
            return service.bridge(service.provider(token))._req("GET", "/jobs", params={"page_size": 50})
        except BridgeError as exc:
            raise ApiError(exc.status, exc.code, str(exc)) from exc

    @app.post("/api/robot/identify")
    def identify(body: ModeIn, request: Request) -> dict[str, Any]:
        service.user(request)
        return service.do_identify(body.mode)

    @app.post("/api/jobs/{job_id}/load")
    def load(job_id: int, request: Request) -> dict[str, Any]:
        who = service.user(request)
        return service.load_job(job_id, service.token_of(request), who).summary

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: int, request: Request) -> dict[str, Any]:
        who = service.user(request)
        ctx = service.ctx(job_id, who)
        return {**ctx.summary, "progress": service.progress(job_id), "busy": service._busy, "current": service.current, "last": service.last}

    @app.post("/api/jobs/{job_id}/preflight")
    def preflight(job_id: int, body: ModeIn, request: Request) -> dict[str, Any]:
        who = service.user(request)
        ctx = service.ctx(job_id, who)
        return service.do_preflight(ctx, body.mode, service.token_of(request))

    @app.post("/api/jobs/{job_id}/dry-run", status_code=202)
    def dry_run(job_id: int, body: DryRunIn, request: Request) -> dict[str, Any]:
        who = service.user(request)
        return service.start(service.ctx(job_id, who), service.token_of(request), who["name"], mode=body.mode, dry_run=True, authorization=body.authorization,
                             resume_from=None, confirm_unknown=False, speed=body.speed)

    @app.post("/api/jobs/{job_id}/run", status_code=202)
    def run(job_id: int, body: RunIn, request: Request) -> dict[str, Any]:
        who = service.user(request)
        return service.start(service.ctx(job_id, who), service.token_of(request), who["name"], mode=body.mode, dry_run=False, authorization=body.authorization,
                             resume_from=body.resume_from, confirm_unknown=body.confirm_unknown, speed=body.speed)

    @app.get("/api/jobs/{job_id}/log")
    def log(job_id: int, request: Request, tail: int = 200) -> dict[str, Any]:
        service.guard("view", request)
        # Names contain a random suffix: lexical order is not chronological for
        # multiple runs started within the same second (including refusals).
        files = sorted((service.cfg.run_dir / f"job{job_id}").glob("run-*.jsonl"), key=lambda p: p.stat().st_mtime_ns)
        lines = files[-1].read_text(encoding="utf-8").splitlines()[-max(1, min(tail, 2000)):] if files else []
        return {"file": files[-1].name if files else None, "lines": [json.loads(x) for x in lines]}

    return app


def serve(cfg: ServerConfig) -> None:                                         # pragma: no cover - starts a real server
    import os

    import uvicorn
    service = AgentService(cfg)
    key = os.environ.get("VHRS_AGENT_KEY") or cfg.agent_key
    email, password = os.environ.get("VHRS_TECH_EMAIL"), os.environ.get("VHRS_TECH_PASSWORD")
    link = None
    provider = None
    if email and password and not key:                                # the desktop app: log in, get a short-lived key, renew it
        from vhrs_agent.link import LinkClient
        from vhrs_agent.session_key import SessionKeyError, SessionKeyProvider
        provider = SessionKeyProvider(cfg.backend_url, email, password, robot_id=cfg.robot_id)
        try:
            provider.start()
        except SessionKeyError as exc:
            raise SystemExit(f"Cannot take control of the robot: {exc}")
        link = LinkClient(service, provider=provider)
        threading.Thread(target=link.run_forever, daemon=True, name="backend-link").start()
        print(f"Backend link ON (session of {email} on robot {provider.robot_id}); the key renews itself")
    elif key:
        from vhrs_agent.link import LinkClient
        link = LinkClient(service, key=key)
        threading.Thread(target=link.run_forever, daemon=True, name="backend-link").start()
        print(f"Backend link ON: calling out to {cfg.backend_url} (commands from the app arrive here)")
    else:
        print("Backend link OFF: no agent key (VHRS_AGENT_KEY) and no technician login (VHRS_TECH_EMAIL/VHRS_TECH_PASSWORD); only the LAN API")
    if not cfg.lan_server:
        if link is None:
            raise SystemExit("lan_server is false but there is no agent key: nothing to serve.")
        try:
            threading.Event().wait()
        finally:
            if provider is not None:
                provider.release()
        return
    try:
        uvicorn.run(create_server_app(service), host=cfg.host, port=cfg.port, log_level="warning",
                    ssl_certfile=cfg.tls_certfile, ssl_keyfile=cfg.tls_keyfile)
    finally:
        if provider is not None:
            provider.release()
