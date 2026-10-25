"""Robot Agent link: the agent on the workstation connects OUT to this backend (it sits behind the LAN), so every robot function
is an API of this one deployed backend.

* Technical Staff (or a Manager, for PAUSE/RESUME/STOP only) create COMMANDS. A command is a durable row; the agent PULLS it with
  `sync` (about once a second, 4 times a second while a run is live), so nothing needs an inbound port at the workshop.
* A command is never replayed late: PENDING past `expires_at` becomes EXPIRED. A command is refused at once when the agent is not
  online, so a person is told "the robot is not reachable" instead of waiting for a stale order to run later.
* The agent pushes live frames (joint angles, tool position, force, alert level) in `sync`; they are kept in memory (single
  uvicorn worker) for the 3D view and the status screen. Only facts that matter later (runs, alerts) go to the database.
* The agent authenticates with a per-robot key (shown once, only its SHA-256 stored). With that key it may also call the
  existing `/technician/*` routes AS the technician who holds the live job on its robot (see `deps.current_principal`), so it
  needs no password and every old gate (BR-19, hash check, calibration, simulation, run rules) still applies.
Real-robot motion still needs the on-site `real-enable` file and a plan-bound authorisation token: those are checked by the agent.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.models.ops import ACTIVE_JOB_STATUSES, JobStatus, ProductionJob, Robot, RobotAgent, RobotCommand, RobotRun
from app.services import audit
from app.services.robot_ops import OFFLINE_AFTER_S, RobotOpsService

AGENT_KEY_PREFIX = "vhrs_ak_"
KINDS = ("LOAD", "PREFLIGHT", "DRY_RUN", "RUN", "PAUSE", "RESUME", "STOP", "PAPER_CHANGED", "IDENTIFY", "ALIGN_START")
JOB_KINDS = ("LOAD", "PREFLIGHT", "DRY_RUN", "RUN", "PAPER_CHANGED", "ALIGN_START")
CONTROL_KINDS = ("PAUSE", "RESUME", "STOP")
MANAGER_KINDS = ("PAUSE", "RESUME", "STOP")             # a Manager may watch and pause/stop, never start a run
TTL_S = {"CONTROL": 20, "DEFAULT": 60}
AUTH_CACHE_S = 60.0
FRAME_KEEP = 300                                        # ~75 s at 4 frames/s
HEARTBEAT_EVERY_S = 10.0
DB_POLL_EVERY_S = 5.0                                   # re-check the table at least this often (survives a restart)
MAX_FRAMES_PER_SYNC = 40
SESSION_TTL = timedelta(hours=4)                        # POLICY default: "a few hours"; the app renews at RENEW_FRACTION of it
RENEW_FRACTION = 0.75
SESSION_GRACE = timedelta(seconds=120)                  # the old key keeps working this long after a renewal: no gap, no "lost link"
FRESH_KEY_S = 60                                        # a key issued less than this ago whose agent has not connected yet still holds the robot


@dataclass(frozen=True)
class AgentIdentity:
    robot_id: int
    agent_id: int
    account_id: int | None                              # None for a Manager key
    expires_at: datetime | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class _RobotLive:
    def __init__(self) -> None:
        self.frames: deque[dict[str, Any]] = deque(maxlen=FRAME_KEEP)
        self.seq = 0
        self.status: dict[str, Any] = {}
        self.last_sync = 0.0                            # time.monotonic()
        self.last_heartbeat_db = 0.0
        self.last_db_poll = 0.0
        self.pending = True                             # force a table check on the first sync after a restart
        self.agent_id: int | None = None                # the key of the agent that synced last


class RobotHub:
    """In-memory live data. One uvicorn worker (see the Dockerfile), so this is the single source of live state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._robots: dict[int, _RobotLive] = {}
        self._auth: dict[str, tuple[AgentIdentity, float]] = {}  # key_hash -> (identity, cached_at)

    def live(self, robot_id: int) -> _RobotLive:
        with self._lock:
            return self._robots.setdefault(robot_id, _RobotLive())

    def reset(self) -> None:
        with self._lock:
            self._robots.clear()
            self._auth.clear()

    def cached_agent(self, key_hash: str) -> AgentIdentity | None:
        with self._lock:
            hit = self._auth.get(key_hash)
        if hit and time.monotonic() - hit[1] < AUTH_CACHE_S and (hit[0].expires_at is None or hit[0].expires_at > _now()):
            return hit[0]
        return None

    def cache_agent(self, key_hash: str, ident: AgentIdentity) -> None:
        with self._lock:
            self._auth[key_hash] = (ident, time.monotonic())

    def forget_robot_keys(self, robot_id: int) -> None:
        with self._lock:
            for k in [k for k, v in self._auth.items() if v[0].robot_id == robot_id]:
                del self._auth[k]

    def notify_command(self, robot_id: int) -> None:
        self.live(robot_id).pending = True

    def online(self, robot_id: int) -> bool:
        live = self.live(robot_id)
        return live.last_sync > 0 and time.monotonic() - live.last_sync < OFFLINE_AFTER_S


hub = RobotHub()


def agent_identity(session: Session, key: str) -> AgentIdentity:
    """Who a valid key belongs to (not revoked, not expired). Cached for a minute; revoking clears the cache at once."""
    if not key.startswith(AGENT_KEY_PREFIX):
        raise AppError(401, "INVALID_AGENT_KEY", "Khoá agent không hợp lệ.")
    h = hash_key(key)
    hit = hub.cached_agent(h)
    if hit:
        return hit
    row = session.scalar(select(RobotAgent).where(RobotAgent.key_hash == h, RobotAgent.revoked_at.is_(None),
                                                  or_(RobotAgent.expires_at.is_(None), RobotAgent.expires_at > _now())))
    if row is None:
        raise AppError(401, "INVALID_AGENT_KEY", "Khoá agent không hợp lệ, đã hết hạn hoặc đã bị thu hồi.")
    ident = AgentIdentity(row.robot_id, row.id, row.account_id, row.expires_at)
    hub.cache_agent(h, ident)
    return ident


def agent_for_key(session: Session, key: str) -> tuple[int, int]:
    ident = agent_identity(session, key)
    return ident.robot_id, ident.agent_id


def technician_for_agent(session: Session, robot_id: int, job_id: int | None, account_id: int | None = None) -> Account:
    """The technician the agent acts as: the key's own account (session key) or the one holding the job it works on (Manager key).
    Either way the job must be live on THIS robot."""
    stmt = select(ProductionJob).where(ProductionJob.robot_id == robot_id, ProductionJob.status.in_(ACTIVE_JOB_STATUSES))
    if job_id is not None:
        stmt = stmt.where(ProductionJob.id == job_id)
    if account_id is not None:
        stmt = stmt.where(ProductionJob.technician_id == account_id)
    job = session.scalar(stmt.order_by(ProductionJob.slot_start).limit(1))
    if job is None:
        raise AppError(401, "AGENT_HAS_NO_ACTIVE_JOB", "Robot này hiện không có job đang hoạt động; agent không có quyền gọi API kỹ thuật viên.")
    return session.get(Account, job.technician_id)


class RobotLinkService:
    def __init__(self, session: Session, actor: Account | None, ip: str | None = None):
        self.session, self.actor, self.ip = session, actor, ip
        self.ops = RobotOpsService(session, actor, ip)
        self.is_manager = bool(actor and actor.role.code == RoleCode.MANAGER.value)

    # ------------------------------------------------------------------ agent credential (Manager)
    def issue_key(self, robot_id: int) -> tuple[str, RobotAgent]:
        robot = self.session.get(Robot, robot_id)
        if robot is None:
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        now = _now()
        for old in self.session.scalars(select(RobotAgent).where(RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None),
                                                                 RobotAgent.kind == "MANAGER")):
            old.revoked_at = now
        self.session.flush()
        key = AGENT_KEY_PREFIX + secrets.token_urlsafe(32)
        row = RobotAgent(robot_id=robot_id, key_hash=hash_key(key), key_prefix=key[:12], created_by=self.actor.id, kind="MANAGER")
        self.session.add(row)
        self.session.flush()
        hub.forget_robot_keys(robot_id)
        audit.record(self.session, actor_id=self.actor.id, action="ROBOT_AGENT_KEY_ISSUE", entity_type="robot", entity_id=robot_id,
                     new={"key_prefix": row.key_prefix}, ip=self.ip)
        return key, row

    def revoke_key(self, robot_id: int) -> int:
        n = 0
        for old in self.session.scalars(select(RobotAgent).where(RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None))):
            old.revoked_at, n = _now(), n + 1
        hub.forget_robot_keys(robot_id)
        if n:
            audit.record(self.session, actor_id=self.actor.id, action="ROBOT_AGENT_KEY_REVOKE", entity_type="robot",
                         entity_id=robot_id, ip=self.ip)
        return n

    def agent_info(self, robot_id: int) -> dict[str, Any]:
        row = self.session.scalar(select(RobotAgent).where(RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None),
                                                           RobotAgent.kind == "MANAGER"))
        sessions = self.session.scalars(select(RobotAgent).where(RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None),
                                                                 RobotAgent.kind == "SESSION", RobotAgent.expires_at > _now()))
        active = [{"account_id": k.account_id, "instance_id": k.instance_id, "expires_at": k.expires_at, "last_seen_at": k.last_seen_at}
                  for k in sessions]
        holder = self._online_holder(robot_id)
        return {"robot_id": robot_id, "has_key": row is not None, "key_prefix": row.key_prefix if row else None,
                "issued_at": row.created_at if row else None, "online": hub.online(robot_id),
                "last_seen_at": row.last_seen_at if row else None, "session_keys": active,
                "controlled_by_account_id": holder.account_id if holder else None}

    # ------------------------------------------------------------------ session keys (Technical Staff, desktop app)
    def _online_holder(self, robot_id: int) -> RobotAgent | None:
        if not hub.online(robot_id):
            return None
        aid = hub.live(robot_id).agent_id
        return self.session.get(RobotAgent, aid) if aid else None

    def issue_session_key(self, robot_id: int, instance_id: str) -> tuple[str, RobotAgent, int]:
        """Key for THIS app instance of THIS technician. One controlling app per robot: another instance (or account) is refused while the
        robot is held (agent online, a run open, or a key issued moments ago); the same instance renews, and its old key keeps
        working for SESSION_GRACE so a renewal is never a gap."""
        if self.actor is None or self.is_manager:
            raise AppError(403, "FORBIDDEN", "Chỉ Technical Staff đang giữ job của robot mới lấy được khoá phiên.")
        self.ops._robot(robot_id, write=True, lock=True)             # 404 unless this technician holds a live job on the robot
        now = _now()
        live_keys = list(self.session.scalars(select(RobotAgent).where(
            RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None), RobotAgent.kind == "SESSION",
            RobotAgent.expires_at > now).with_for_update()))
        mine = [k for k in live_keys if k.account_id == self.actor.id and k.instance_id == instance_id]
        others = [k for k in live_keys if k not in mine]
        if not mine:
            holder = self._online_holder(robot_id)
            run_open = self.session.scalar(select(RobotRun.run_id).where(RobotRun.robot_id == robot_id, RobotRun.ended_at.is_(None)).limit(1))
            fresh = [k for k in others if k.last_seen_at is None and (now - k.created_at).total_seconds() < FRESH_KEY_S]
            if holder is not None or run_open or fresh:
                raise AppError(409, "ROBOT_IN_USE", "Robot đang do người khác (hoặc máy khác) điều khiển. Không thể cướp quyền giữa chừng.",
                               {"online": holder is not None, "run_open": bool(run_open)})
        for k in others:                                             # nobody holds them: the previous app is gone
            k.revoked_at = now
        for k in mine:                                               # renewal: overlap for a short grace, then the old key ends
            k.expires_at = min(k.expires_at, now + SESSION_GRACE)
        key = AGENT_KEY_PREFIX + secrets.token_urlsafe(32)
        row = RobotAgent(robot_id=robot_id, key_hash=hash_key(key), key_prefix=key[:12], created_by=self.actor.id, kind="SESSION",
                         account_id=self.actor.id, instance_id=instance_id, expires_at=now + SESSION_TTL)
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        hub.forget_robot_keys(robot_id) if others else None
        audit.record(self.session, actor_id=self.actor.id, action="ROBOT_AGENT_SESSION_KEY", entity_type="robot", entity_id=robot_id,
                     new={"key_prefix": row.key_prefix, "instance": instance_id, "renewal": bool(mine),
                          "took_over_from": [k.account_id for k in others] or None}, ip=self.ip)
        return key, row, int(SESSION_TTL.total_seconds() * RENEW_FRACTION)

    def release_session_key(self, robot_id: int, instance_id: str) -> int:
        """The app is closing: end its keys. Refused while a run is open (stop it first; a crashed app's keys simply expire)."""
        if self.actor is None or self.is_manager:
            raise AppError(403, "FORBIDDEN", "Chỉ Technical Staff mới trả khoá phiên.")
        self.ops._robot(robot_id, write=True)
        if self.session.scalar(select(RobotRun.run_id).where(RobotRun.robot_id == robot_id, RobotRun.ended_at.is_(None)).limit(1)):
            raise AppError(409, "RUN_OPEN", "Robot đang có lần chạy chưa kết thúc: hãy dừng hoặc chờ xong rồi mới đóng.")
        n = 0
        for k in self.session.scalars(select(RobotAgent).where(RobotAgent.robot_id == robot_id, RobotAgent.revoked_at.is_(None),
                                                               RobotAgent.kind == "SESSION", RobotAgent.account_id == self.actor.id,
                                                               RobotAgent.instance_id == instance_id)):
            k.revoked_at, n = _now(), n + 1
        hub.forget_robot_keys(robot_id)
        if n:
            audit.record(self.session, actor_id=self.actor.id, action="ROBOT_AGENT_SESSION_RELEASE", entity_type="robot",
                         entity_id=robot_id, new={"instance": instance_id}, ip=self.ip)
        return n

    # ------------------------------------------------------------------ commands (app side)
    def _agent_online(self, robot: Robot) -> bool:
        if hub.online(robot.id):
            return True
        return False

    def create_command(self, *, robot_id: int | None, job_id: int | None, kind: str, params: dict[str, Any],
                       idempotency_key: str | None) -> RobotCommand:
        if kind not in KINDS:
            raise AppError(422, "UNKNOWN_COMMAND", f"Lệnh không hợp lệ: {kind}.")
        if self.is_manager and kind not in MANAGER_KINDS:
            raise AppError(403, "FORBIDDEN", "Quản lý chỉ được tạm dừng, tiếp tục hoặc dừng robot.")
        if kind in JOB_KINDS and job_id is None:
            raise AppError(422, "JOB_REQUIRED", f"Lệnh {kind} cần job_id.")
        job = None
        if job_id is not None:
            job = self.ops._own_job(job_id)
            if robot_id is not None and robot_id != job.robot_id:
                raise AppError(422, "ROBOT_JOB_MISMATCH", "Job không thuộc robot này.")
            robot_id = job.robot_id
        if robot_id is None:
            raise AppError(422, "ROBOT_REQUIRED", "Cần robot_id hoặc job_id.")
        robot = self.ops._robot(robot_id, write=True, lock=True)
        if self.actor and idempotency_key:
            prior = self.session.scalar(select(RobotCommand).where(RobotCommand.created_by == self.actor.id,
                                                                    RobotCommand.idempotency_key == idempotency_key))
            if prior is not None:
                if prior.kind != kind or prior.job_id != job_id:
                    raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "idempotency_key đã dùng cho một lệnh khác.")
                return prior
        mode = str(params.get("mode", "")).upper()
        if kind in ("RUN", "DRY_RUN", "PREFLIGHT", "IDENTIFY", "ALIGN_START") and mode not in ("MOCK", "SIM", "REAL"):
            raise AppError(422, "MODE_REQUIRED", "params.mode phải là MOCK, SIM hoặc REAL.")
        if kind in ("RUN", "ALIGN_START") and mode == "REAL" and not str(params.get("authorization", "")).startswith("AUTHORIZE-"):
            raise AppError(422, "AUTHORIZATION_REQUIRED", "Chạy robot thật cần mã xác nhận AUTHORIZE-<job>-<mã kế hoạch> của người vận hành.")
        if job is not None and job.status not in ACTIVE_JOB_STATUSES and kind in JOB_KINDS:
            raise AppError(409, "JOB_NOT_ACTIVE", f"Job đã {job.status.value}.", {"job_status": job.status.value})
        if job is not None and kind == "DRY_RUN" and job.status not in (JobStatus.PREPARING, JobStatus.PAUSED):
            raise AppError(409, "JOB_STATE_CONFLICT", "Chạy thử chỉ khi job đang chuẩn bị (đã hiệu chuẩn, chưa bắt đầu viết) hoặc đang tạm dừng sau một lần dừng.",
                           {"job_status": job.status.value})
        if job is not None and kind == "RUN" and job.status not in (JobStatus.WRITING, JobStatus.PAUSED):
            raise AppError(409, "JOB_STATE_CONFLICT", "Hãy bấm Bắt đầu viết (POST /technician/jobs/{id}/start) trước khi gửi lệnh RUN.",
                           {"job_status": job.status.value})
        if not self._agent_online(robot):
            raise AppError(409, "AGENT_OFFLINE", "Máy trạm của robot chưa kết nối tới hệ thống. Không gửi lệnh; kiểm tra Robot Agent "
                           "(nếu đang có nguy hiểm: nhấn nút E-Stop vật lý).", {"robot_id": robot.id})
        holder = self._online_holder(robot.id)
        if (holder is not None and holder.account_id is not None and self.actor and not self.is_manager
                and holder.account_id != self.actor.id):
            raise AppError(409, "ROBOT_IN_USE", "Robot đang do kỹ thuật viên khác điều khiển.", {"robot_id": robot.id})
        ttl = TTL_S["CONTROL"] if kind in CONTROL_KINDS else TTL_S["DEFAULT"]
        cmd = RobotCommand(id=str(uuid.uuid4()), robot_id=robot.id, job_id=job_id, kind=kind, params=params, status="PENDING",
                           idempotency_key=idempotency_key, created_by=self.actor.id, expires_at=_now() + timedelta(seconds=ttl))
        try:
            with self.session.begin_nested():
                self.session.add(cmd)
                self.session.flush()
        except IntegrityError:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "idempotency_key đã được dùng.") from None
        audit.record(self.session, actor_id=self.actor.id, action="ROBOT_COMMAND", entity_type="robot", entity_id=robot.id,
                     new={"command_id": cmd.id, "kind": kind, "job_id": job_id, "mode": mode or None,
                          "real_authorization_given": bool(kind == "RUN" and mode == "REAL")}, ip=self.ip)
        self.session.refresh(cmd)
        hub.notify_command(robot.id)
        return cmd

    def command(self, command_id: str) -> RobotCommand:
        cmd = self.session.get(RobotCommand, command_id)
        if cmd is None:
            raise AppError(404, "COMMAND_NOT_FOUND", "Không tìm thấy lệnh.")
        if cmd.status == "PENDING" and cmd.expires_at <= _now():
            cmd.status, cmd.finished_at = "EXPIRED", _now()
        self.ops._robot(cmd.robot_id)                       # raises 404 for someone who holds no job on this robot
        if not self.is_manager and self.actor and cmd.created_by != self.actor.id:
            job = self.session.get(ProductionJob, cmd.job_id) if cmd.job_id else None
            if job is None or job.technician_id != self.actor.id:
                raise AppError(404, "COMMAND_NOT_FOUND", "Không tìm thấy lệnh.")
        return cmd

    def job_commands(self, job_id: int, limit: int = 50) -> list[RobotCommand]:
        job = self.ops._own_job(job_id)
        self._expire(job.robot_id)
        return list(self.session.scalars(select(RobotCommand).where(RobotCommand.job_id == job.id)
                                         .order_by(RobotCommand.created_at.desc()).limit(limit)))

    def _expire(self, robot_id: int) -> None:
        for c in self.session.scalars(select(RobotCommand).where(RobotCommand.robot_id == robot_id, RobotCommand.status == "PENDING",
                                                                 RobotCommand.expires_at <= _now()).with_for_update()):
            c.status, c.finished_at = "EXPIRED", _now()

    # ------------------------------------------------------------------ live view (app side)
    def live(self, robot_id: int, after: int = 0) -> dict[str, Any]:
        robot = self.ops._robot(robot_id)
        lv = hub.live(robot_id)
        online = hub.online(robot_id)
        frames = [f for f in list(lv.frames) if f["seq"] > after]
        return {"robot_id": robot.id, "robot_code": robot.code, "agent_online": online,
                "age_s": round(time.monotonic() - lv.last_sync, 2) if lv.last_sync else None,
                "mode": lv.status.get("mode"), "status": lv.status, "last_seq": lv.seq, "frames": frames}

    def scene(self, robot_id: int) -> dict[str, Any]:
        """What the 3D view draws besides the robot: sheet, frame and strokes of the last job the agent loaded."""
        self.ops._robot(robot_id)
        cmd = self.session.scalar(select(RobotCommand).where(RobotCommand.robot_id == robot_id, RobotCommand.kind == "LOAD",
                                                             RobotCommand.status == "DONE").order_by(RobotCommand.created_at.desc()).limit(1))
        if cmd is None or not (cmd.result or {}).get("scene"):
            raise AppError(404, "SCENE_NOT_AVAILABLE", "Chưa có job nào được nạp vào agent của robot này.")
        return {"command_id": cmd.id, "job_id": cmd.job_id, "scene": cmd.result["scene"]}

    # ------------------------------------------------------------------ agent side
    def sync(self, robot_id: int, agent_id: int, *, status: dict[str, Any], frames: list[dict[str, Any]],
             versions: dict[str, str | None]) -> list[RobotCommand]:
        lv = hub.live(robot_id)
        now_m = time.monotonic()
        lv.last_sync = now_m
        lv.agent_id = agent_id
        lv.status = {**status, "reported_at": _now().isoformat()}
        for f in frames[-MAX_FRAMES_PER_SYNC:]:
            lv.seq += 1
            lv.frames.append({**f, "seq": lv.seq})
        if now_m - lv.last_heartbeat_db >= HEARTBEAT_EVERY_S:
            lv.last_heartbeat_db = now_m
            self.ops.heartbeat(robot_id, mode=str(status.get("mode") or "MOCK")[:10], controller_version=versions.get("controller_version"),
                               firmware_version=versions.get("firmware_version"), sdk_version=versions.get("sdk_version"),
                               agent_version=versions.get("agent_version"))
            agent = self.session.get(RobotAgent, agent_id)
            if agent is not None:
                agent.last_seen_at = _now()
        if not lv.pending and now_m - lv.last_db_poll < DB_POLL_EVERY_S:
            return []
        lv.last_db_poll = now_m
        self._expire(robot_id)
        rows = list(self.session.scalars(select(RobotCommand).where(RobotCommand.robot_id == robot_id, RobotCommand.status == "PENDING")
                                         .order_by(RobotCommand.created_at).with_for_update()))
        # control commands (STOP first) go ahead of everything else
        rows.sort(key=lambda c: (0 if c.kind == "STOP" else 1 if c.kind in CONTROL_KINDS else 2, c.created_at))
        for c in rows:
            c.status, c.delivered_at = "DELIVERED", _now()
        lv.pending = False
        return rows

    def finish_command(self, robot_id: int, command_id: str, *, ok: bool, result: dict[str, Any] | None, error_code: str | None,
                       message: str | None) -> RobotCommand:
        cmd = self.session.scalar(select(RobotCommand).where(RobotCommand.id == command_id, RobotCommand.robot_id == robot_id).with_for_update())
        if cmd is None:
            raise AppError(404, "COMMAND_NOT_FOUND", "Không tìm thấy lệnh.")
        if cmd.status in ("DONE", "FAILED"):
            return cmd                                      # idempotent
        if cmd.status != "DELIVERED":
            raise AppError(409, "COMMAND_NOT_DELIVERED", f"Lệnh đang {cmd.status}, chưa được giao cho agent.")
        cmd.status, cmd.result, cmd.finished_at = ("DONE" if ok else "FAILED"), result, _now()
        cmd.error_code, cmd.error_message = (None, None) if ok else ((error_code or "AGENT_ERROR")[:40], message)
        return cmd
