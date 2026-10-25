"""Robot operations: runs, alerts, heartbeat, robot status for the Technical Staff, health and process compliance for the Manager.

The Robot Agent reports FACTS (run opened / closed, alert code, heartbeat); this service turns them into what a person needs:
a level 1..4 with a plain-Vietnamese sentence and an action. The agent never chooses a level or a sentence: both come from
`alert_catalog`, so a faulty or careless agent cannot under-report. Level 4 means "press the physical E-Stop now"; the
software cannot press it and says so. Red alerts are e-mailed (SMTP when configured) to the technician and the Managers.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.mailer import get_mailer
from app.models.account import Account, AccountStatus, Role, RoleCode
from app.models.ops import (ACTIVE_JOB_STATUSES, AlertCatalog, Calibration, Incident, JobEvent, JobEventType, JobStatus,
                            ProductionJob, Robot, RobotAlert, RobotRun)
from app.services import audit

log = logging.getLogger("app.robot_ops")

OFFLINE_AFTER_S = 15.0                      # no heartbeat for this long = the agent is considered offline
SAFETY_STOP_EVENTS = (JobEventType.ESTOP, JobEventType.OVER_FORCE, JobEventType.STROKE_LOST, JobEventType.SENSOR_LOST)
EMAIL_REPEAT_AFTER = timedelta(minutes=5)   # a still-open red alert is e-mailed again at most this often
DRY_RUN_STATUSES = (JobStatus.PREPARING, JobStatus.PAUSED)   # a pen-up rehearsal writes nothing, so it may also run on a job paused after an abort
WRITE_RUN_STATUSES = (JobStatus.WRITING, JobStatus.PAUSED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


def dispatch_mail(mails: list[Mail]) -> None:
    """Send in a worker thread: a slow or failing SMTP server must never delay or break an alert."""
    if not mails:
        return

    def work() -> None:
        mailer = get_mailer()
        for m in mails:
            try:
                mailer.send(m.to, m.subject, m.body)
            except Exception as exc:                       # noqa: BLE001 - delivery problems are logged, not raised
                log.error("alert mail to %s failed: %s", m.to, exc)

    threading.Thread(target=work, daemon=True).start()


class RobotOpsService:
    def __init__(self, session: Session, actor: Account | None, ip: str | None = None):
        self.session, self.actor, self.ip = session, actor, ip
        self.pending_mail: list[Mail] = []
        self.is_manager = bool(actor and actor.role.code == RoleCode.MANAGER.value)

    # ------------------------------------------------------------------ access
    def _robot(self, robot_id: int, *, write: bool = False, lock: bool = False) -> Robot:
        stmt = select(Robot).where(Robot.id == robot_id)
        robot = self.session.scalar(stmt.with_for_update() if lock else stmt)
        if robot is None:
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        if self.is_manager or self.actor is None:
            return robot
        live = self.session.scalar(select(ProductionJob.id).where(
            ProductionJob.robot_id == robot_id, ProductionJob.technician_id == self.actor.id,
            ProductionJob.status.in_(ACTIVE_JOB_STATUSES)).limit(1))
        past = None if (live or write) else self.session.scalar(select(ProductionJob.id).where(
            ProductionJob.robot_id == robot_id, ProductionJob.technician_id == self.actor.id).limit(1))
        if live is None and past is None:                  # BR-19 spirit: a robot you hold no job on is not yours
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        return robot

    def _own_job(self, job_id: int, *, lock: bool = False) -> ProductionJob:
        stmt = select(ProductionJob).where(ProductionJob.id == job_id)
        job = self.session.scalar(stmt.with_for_update() if lock else stmt)
        if job is None or (self.actor and not self.is_manager and job.technician_id != self.actor.id):
            raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
        return job

    # ------------------------------------------------------------------ runs
    def open_run(self, job_id: int, *, run_id: str, mode: str, dry_run: bool, authorized: bool, plan_digest: str | None,
                 total_strokes: int, agent_version: str | None, robot_info: dict[str, Any] | None,
                 refused_reason: str | None) -> RobotRun:
        job = self._own_job(job_id, lock=True)
        robot = self._robot(job.robot_id, write=True, lock=True)
        if self.session.scalar(select(RobotRun.id).where(RobotRun.run_id == run_id)) is not None:
            raise AppError(409, "RUN_EXISTS", "run_id đã tồn tại.")
        now = _now()
        if refused_reason is None:
            if job.status not in (DRY_RUN_STATUSES if dry_run else WRITE_RUN_STATUSES):
                raise AppError(409, "JOB_STATE_CONFLICT", f"Không mở lần chạy {'thử' if dry_run else 'viết'} khi job đang {job.status.value}.",
                               {"job_status": job.status.value})
            if mode == "REAL" and not authorized:
                raise AppError(422, "AUTHORIZATION_REQUIRED", "Chạy robot thật cần người vận hành xác nhận cho job và kế hoạch này.")
        elif job.status not in ACTIVE_JOB_STATUSES:
            raise AppError(409, "JOB_NOT_ACTIVE", f"Job đã {job.status.value}.", {"job_status": job.status.value})
        run = RobotRun(run_id=run_id, job_id=job.id, robot_id=robot.id, mode=mode, dry_run=dry_run, started_at=now,
                       plan_digest=plan_digest, total_strokes=total_strokes, agent_version=agent_version,
                       robot_info=robot_info, created_by=self.actor.id if self.actor else job.technician_id)
        if authorized and mode == "REAL":
            run.authorized_by, run.authorized_at = (self.actor.id if self.actor else job.technician_id), now
        if refused_reason is not None:
            run.ended_at, run.result, run.summary = now, "REFUSED", {"reason": refused_reason}
        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
        except IntegrityError as exc:
            if "ux_robot_runs_one_open" in str(exc.orig):
                busy = self.session.scalar(select(RobotRun.run_id).where(RobotRun.robot_id == robot.id, RobotRun.ended_at.is_(None)))
                raise AppError(409, "ROBOT_BUSY", "Robot đang có một lần chạy khác chưa kết thúc.", {"open_run_id": busy}) from None
            raise
        self.session.refresh(run)
        robot.last_mode, robot.last_seen_at = mode, now
        audit.record(self.session, actor_id=run.created_by, action="ROBOT_RUN_OPEN", entity_type="robot_run", entity_id=run.id,
                     new={"job_id": job.id, "robot_id": robot.id, "mode": mode, "dry_run": dry_run,
                          "authorized": bool(run.authorized_by), "refused": refused_reason is not None}, ip=self.ip)
        return run

    def close_run(self, run_id: str, *, result: str, completed_strokes: int, total_strokes: int | None,
                  summary: dict[str, Any] | None) -> RobotRun:
        run = self.session.scalar(select(RobotRun).where(RobotRun.run_id == run_id).with_for_update())
        if run is None:
            raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy lần chạy.")
        self._own_job(run.job_id)
        if run.ended_at is not None:
            if run.result == result:                       # the agent retried a close that already went through
                return run
            raise AppError(409, "RUN_ALREADY_CLOSED", f"Lần chạy đã kết thúc với kết quả {run.result}.")
        if result == "DRY_RUN_DONE" and not run.dry_run:
            raise AppError(422, "RESULT_INVALID", "DRY_RUN_DONE chỉ dành cho lần chạy thử.")
        if result == "DONE" and run.dry_run:
            raise AppError(422, "RESULT_INVALID", "Lần chạy thử không thể kết thúc DONE.")
        total = total_strokes if total_strokes is not None else run.total_strokes
        if total and completed_strokes > total:
            raise AppError(422, "RESULT_INVALID", "Số nét đã viết lớn hơn tổng số nét.")
        run.ended_at, run.result, run.completed_strokes, run.total_strokes = _now(), result, completed_strokes, total
        run.summary = {**(run.summary or {}), **(summary or {})}
        audit.record(self.session, actor_id=run.created_by, action="ROBOT_RUN_CLOSE", entity_type="robot_run", entity_id=run.id,
                     new={"result": result, "completed": completed_strokes, "total": total}, ip=self.ip)
        return run

    # ------------------------------------------------------------------ alerts
    def raise_alert(self, *, robot_id: int, code: str, job_id: int | None = None, run_key: str | None = None,
                    details: dict[str, Any] | None = None, system: bool = False,
                    count_repeats: bool = True) -> tuple[RobotAlert, bool]:
        """Returns (alert, is_new). An alert already open for the same robot, code and job only counts one more occurrence."""
        robot = self._robot(robot_id, write=True) if not system else self.session.get(Robot, robot_id)
        if robot is None:
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        cat = self.session.get(AlertCatalog, code)
        if cat is None or not cat.is_active:
            raise AppError(422, "UNKNOWN_ALERT", "Mã cảnh báo không có trong danh mục hoặc đã tắt.", {"code": code})
        job = None
        if job_id is not None:
            job = self.session.get(ProductionJob, job_id) if system else self._own_job(job_id)
            if job is None or job.robot_id != robot.id:
                raise AppError(422, "JOB_ROBOT_MISMATCH", "Job không thuộc robot này.")
        run = None
        if run_key is not None:
            run = self.session.scalar(select(RobotRun).where(RobotRun.run_id == run_key, RobotRun.robot_id == robot.id))
            if run is None:
                raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy lần chạy.")
        now = _now()
        existing = self._open_alert(robot.id, code, job_id, lock=True)
        is_new = existing is None
        if existing is None:
            alert = RobotAlert(robot_id=robot.id, job_id=job_id, run_id=run.id if run else None, code=code, level=cat.level,
                               title_vi=cat.title_vi, action_vi=cat.action_vi, estop_advised=cat.estop_advised,
                               details=details, raised_at=now, last_raised_at=now)
            try:
                with self.session.begin_nested():
                    self.session.add(alert)
                    self.session.flush()
            except IntegrityError:                          # another request opened the same alert a moment ago
                existing, is_new = self._open_alert(robot.id, code, job_id, lock=True), False
                if existing is None:
                    raise
            else:
                self.session.refresh(alert)
        if existing is not None and not count_repeats:
            return existing, False                           # the server's own sweep must not inflate the counter on every read
        if existing is not None:
            existing.occurrences += 1
            existing.last_raised_at = now
            if details:
                existing.details = {**(existing.details or {}), **details}
            alert = existing
        actor_id = None if system or self.actor is None else self.actor.id
        if is_new and cat.level >= 3:
            audit.record(self.session, actor_id=actor_id, action="ROBOT_ALERT", entity_type="robot_alert", entity_id=alert.id,
                         new={"code": code, "level": cat.level, "robot_id": robot.id, "job_id": job_id}, ip=self.ip)
        if cat.send_email and (is_new or alert.emailed_at is None or now - alert.emailed_at > EMAIL_REPEAT_AFTER):
            self._queue_mail(alert, cat, robot, job)
            alert.emailed_at = now
        return alert, is_new

    def _open_alert(self, robot_id: int, code: str, job_id: int | None, *, lock: bool = False) -> RobotAlert | None:
        stmt = select(RobotAlert).where(RobotAlert.robot_id == robot_id, RobotAlert.code == code, RobotAlert.resolved_at.is_(None),
                                        RobotAlert.job_id.is_(None) if job_id is None else RobotAlert.job_id == job_id)
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def _recipients(self, cat: AlertCatalog, job: ProductionJob | None) -> list[Account]:
        out: dict[int, Account] = {}
        roles = set(cat.notify_roles or [])
        if RoleCode.TECHNICAL_STAFF.value in roles and job is not None:
            tech = self.session.get(Account, job.technician_id)
            if tech is not None and tech.status == AccountStatus.ACTIVE:
                out[tech.id] = tech
        elif RoleCode.TECHNICAL_STAFF.value in roles and self.actor is not None and not self.is_manager:
            out[self.actor.id] = self.actor
        for code in roles & {RoleCode.MANAGER.value, RoleCode.STAFF.value}:
            for acc in self.session.scalars(select(Account).join(Role, Role.id == Account.role_id).where(
                    Role.code == code, Account.status == AccountStatus.ACTIVE)):
                out[acc.id] = acc
        return list(out.values())

    def _queue_mail(self, alert: RobotAlert, cat: AlertCatalog, robot: Robot, job: ProductionJob | None) -> None:
        prefix = "[KHẨN - BẤM E-STOP]" if alert.estop_advised else f"[Cảnh báo mức {alert.level}]"
        subject = f"{prefix} Robot {robot.code}: {alert.title_vi}"
        lines = [alert.title_vi, "", f"Việc cần làm: {alert.action_vi}", "", f"Robot: {robot.code}",
                 f"Thời điểm: {alert.raised_at.astimezone(timezone(timedelta(hours=7))):%d/%m/%Y %H:%M:%S} (UTC+7)"]
        if job is not None:
            lines.append(f"Job: #{job.id}")
        if alert.estop_advised:
            lines += ["", "Phần mềm không thể bấm nút E-Stop thay bạn. Nếu robot còn chuyển động hoặc bạn không chắc, bấm nút E-Stop vật lý ngay."]
        body = "\n".join(lines)
        for acc in self._recipients(cat, job):
            self.pending_mail.append(Mail(acc.email, subject, body))

    def alerts(self, *, open_only: bool, robot_id: int | None, min_level: int, job_id: int | None, offset: int,
               limit: int) -> tuple[list[RobotAlert], int]:
        stmt = select(RobotAlert).where(RobotAlert.level >= min_level)
        if open_only:
            stmt = stmt.where(RobotAlert.resolved_at.is_(None))
        if robot_id is not None:
            stmt = stmt.where(RobotAlert.robot_id == robot_id)
        if job_id is not None:
            stmt = stmt.where(RobotAlert.job_id == job_id)
        if not self.is_manager and self.actor is not None:
            mine = select(ProductionJob.robot_id).where(ProductionJob.technician_id == self.actor.id)
            stmt = stmt.where(RobotAlert.robot_id.in_(mine))
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.session.scalars(stmt.order_by(RobotAlert.level.desc(), RobotAlert.raised_at.desc()).offset(offset).limit(limit)))
        return rows, total

    def _alert(self, alert_id: int) -> RobotAlert:
        alert = self.session.scalar(select(RobotAlert).where(RobotAlert.id == alert_id).with_for_update())
        if alert is None:
            raise AppError(404, "ALERT_NOT_FOUND", "Không tìm thấy cảnh báo.")
        self._robot(alert.robot_id)                          # 404 when it is another technician's robot
        return alert

    def acknowledge(self, alert_id: int) -> RobotAlert:
        alert = self._alert(alert_id)
        if alert.acknowledged_at is None:
            alert.acknowledged_by, alert.acknowledged_at = self.actor.id, _now()
        return alert

    def resolve(self, alert_id: int, note: str) -> RobotAlert:
        alert = self._alert(alert_id)
        if alert.resolved_at is not None:
            return alert
        if alert.level >= 4 and not self.is_manager:
            raise AppError(403, "RED_ALERT_NEEDS_MANAGER", "Cảnh báo đỏ chỉ Manager đóng được, sau khi kiểm tra robot an toàn.")
        if alert.level >= 3 and alert.acknowledged_at is None:
            alert.acknowledged_by, alert.acknowledged_at = self.actor.id, _now()
        alert.resolved_by, alert.resolved_at, alert.resolution_note = self.actor.id, _now(), note
        audit.record(self.session, actor_id=self.actor.id, action="ROBOT_ALERT_RESOLVE", entity_type="robot_alert",
                     entity_id=alert.id, new={"code": alert.code, "level": alert.level}, reason=note, ip=self.ip)
        return alert

    # ------------------------------------------------------------------ heartbeat and status
    def heartbeat(self, robot_id: int, *, mode: str, controller_version: str | None, firmware_version: str | None,
                  sdk_version: str | None, agent_version: str | None) -> Robot:
        robot = self._robot(robot_id, write=True, lock=True)
        robot.connection_state, robot.last_seen_at, robot.last_mode = "ONLINE", _now(), mode
        for field, value in (("controller_version", controller_version), ("firmware_version", firmware_version),
                             ("sdk_version", sdk_version), ("agent_version", agent_version)):
            if value is not None:
                setattr(robot, field, value)
        return robot

    def sweep_stale(self) -> int:
        """A robot with an open run whose agent has gone quiet is a risk nobody else will report: raise it here."""
        cutoff = _now() - timedelta(seconds=OFFLINE_AFTER_S)
        n = 0
        stale = self.session.execute(select(Robot, RobotRun).join(RobotRun, RobotRun.robot_id == Robot.id).where(
            RobotRun.ended_at.is_(None), or_(Robot.last_seen_at.is_(None), Robot.last_seen_at < cutoff))).all()
        for robot, run in stale:
            for code in ("AGENT_OFFLINE", "RUN_OUTCOME_UNKNOWN"):
                _, new = self.raise_alert(robot_id=robot.id, code=code, job_id=run.job_id, run_key=run.run_id, system=True, count_repeats=False,
                                          details={"last_seen_at": robot.last_seen_at.isoformat() if robot.last_seen_at else None})
                n += int(new)
            robot.connection_state = "OFFLINE"
        return n

    def status(self, robot: Robot) -> dict[str, Any]:
        now = _now()
        seen = robot.last_seen_at
        age = (now - seen).total_seconds() if seen else None
        conn = "UNKNOWN" if seen is None else ("ONLINE" if age is not None and age <= OFFLINE_AFTER_S else "OFFLINE")
        run = self.session.scalar(select(RobotRun).where(RobotRun.robot_id == robot.id, RobotRun.ended_at.is_(None)))
        alerts = list(self.session.scalars(select(RobotAlert).where(RobotAlert.robot_id == robot.id, RobotAlert.resolved_at.is_(None))
                                           .order_by(RobotAlert.level.desc(), RobotAlert.raised_at.desc())))
        job = self.session.get(ProductionJob, run.job_id) if run else self.session.scalar(
            select(ProductionJob).where(ProductionJob.robot_id == robot.id, ProductionJob.status.in_(ACTIVE_JOB_STATUSES))
            .order_by(ProductionJob.slot_start).limit(1))
        level = max([a.level for a in alerts], default=1)
        if level >= 4:
            state, head = "DANGER", "BẤM NÚT E-STOP NGAY"
        elif level == 3 or (job and job.status == JobStatus.PAUSED):
            state, head = "PAUSED_SAFE", "Đã dừng an toàn: kiểm tra rồi mới tiếp tục"
        elif run is not None and conn != "ONLINE":
            state, head = "OFFLINE", "Mất liên lạc với máy trạm khi đang chạy: đứng cạnh nút E-Stop"
        elif job is not None and job.status == JobStatus.WRITING:
            state, head = "WRITING", "Đang viết"
        elif job is not None and job.status == JobStatus.PREPARING:
            state, head = "PREPARING", "Đang chuẩn bị"
        elif conn != "ONLINE":
            state, head = "OFFLINE", "Máy trạm chưa kết nối"
        else:
            state, head = "IDLE", "Sẵn sàng"
        cal = self.session.scalar(select(Calibration.created_at).where(Calibration.job_id == job.id, Calibration.is_valid.is_(True))
                                  .order_by(Calibration.id.desc()).limit(1)) if job else None
        return {"robot_id": robot.id, "robot_code": robot.code, "state": state, "headline_vi": head, "level": level,
                "mode": robot.last_mode, "connection_state": conn, "last_seen_at": seen,
                "seconds_since_seen": round(age, 1) if age is not None else None,
                "controller_version": robot.controller_version, "firmware_version": robot.firmware_version,
                "sdk_version": robot.sdk_version, "agent_version": robot.agent_version, "job_id": job.id if job else None,
                "job_status": job.status.value if job else None, "open_run": run, "open_alerts": alerts,
                "calibration_age_minutes": round((now - cal).total_seconds() / 60, 1) if cal else None}

    def my_robots_status(self) -> list[dict[str, Any]]:
        self.sweep_stale()
        ids = select(ProductionJob.robot_id).where(ProductionJob.technician_id == self.actor.id,
                                                   ProductionJob.status.in_(ACTIVE_JOB_STATUSES))
        robots = list(self.session.scalars(select(Robot).where(Robot.id.in_(ids)).order_by(Robot.code)))
        return [self.status(r) for r in robots]

    # ------------------------------------------------------------------ manager views
    def all_robots_status(self) -> list[dict[str, Any]]:
        self.sweep_stale()
        return [self.status(r) for r in self.session.scalars(select(Robot).order_by(Robot.code))]

    def runs(self, *, robot_id: int | None, job_id: int | None, offset: int, limit: int) -> tuple[list[RobotRun], int]:
        stmt = select(RobotRun)
        if robot_id is not None:
            stmt = stmt.where(RobotRun.robot_id == robot_id)
        if job_id is not None:
            stmt = stmt.where(RobotRun.job_id == job_id)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        return list(self.session.scalars(stmt.order_by(RobotRun.started_at.desc()).offset(offset).limit(limit))), total

    def health(self, robot_id: int, days: int) -> dict[str, Any]:
        robot = self._robot(robot_id)
        self.sweep_stale()
        since = _now() - timedelta(days=days)
        runs = list(self.session.scalars(select(RobotRun).where(RobotRun.robot_id == robot_id, RobotRun.started_at >= since)))
        by_result: dict[str, int] = {}
        by_mode: dict[str, int] = {}
        secs, bands = 0.0, []
        for r in runs:
            by_result[r.result or "OPEN"] = by_result.get(r.result or "OPEN", 0) + 1
            by_mode[r.mode] = by_mode.get(r.mode, 0) + 1
            if r.ended_at:
                secs += (r.ended_at - r.started_at).total_seconds()
            band = (r.summary or {}).get("in_band_pct")
            if isinstance(band, (int, float)):
                bands.append(float(band))
        alerts = list(self.session.scalars(select(RobotAlert).where(RobotAlert.robot_id == robot_id, RobotAlert.raised_at >= since)))
        by_level: dict[str, int] = {}
        for a in alerts:
            by_level[str(a.level)] = by_level.get(str(a.level), 0) + 1
        stops = self.session.scalar(select(func.count()).select_from(JobEvent).join(ProductionJob, ProductionJob.id == JobEvent.job_id).where(
            ProductionJob.robot_id == robot_id, JobEvent.occurred_at >= since, JobEvent.event_type.in_(SAFETY_STOP_EVENTS))) or 0
        incidents = self.session.scalar(select(func.count()).select_from(Incident).where(
            Incident.robot_id == robot_id, Incident.resolved_at.is_(None))) or 0
        red_open = self.session.scalar(select(func.count()).select_from(RobotAlert).where(
            RobotAlert.robot_id == robot_id, RobotAlert.level >= 4, RobotAlert.resolved_at.is_(None))) or 0
        return {"robot": self.status(robot), "since": since, "runs_by_result": by_result, "runs_by_mode": by_mode,
                "run_seconds": round(secs, 1), "safety_stops": int(stops), "alerts_by_level": by_level,
                "in_band_pct_avg": round(sum(bands) / len(bands), 2) if bands else None, "open_incidents": int(incidents),
                "unresolved_red": int(red_open)}

    # ------------------------------------------------------------------ catalogue
    def catalog(self) -> list[AlertCatalog]:
        return list(self.session.scalars(select(AlertCatalog).order_by(AlertCatalog.level.desc(), AlertCatalog.code)))

    def patch_catalog(self, code: str, changes: dict[str, Any]) -> AlertCatalog:
        row = self.session.scalar(select(AlertCatalog).where(AlertCatalog.code == code).with_for_update())
        if row is None:
            raise AppError(404, "ALERT_CODE_NOT_FOUND", "Không có mã cảnh báo này.")
        if row.level >= 4 and (changes.get("is_active") is False or changes.get("send_email") is False
                               or (changes.get("notify_roles") is not None and "TECHNICAL_STAFF" not in changes["notify_roles"])):
            raise AppError(422, "RED_ALERT_PROTECTED", "Cảnh báo đỏ không được tắt, tắt email hay bỏ Technical Staff khỏi người nhận.")
        old = {k: getattr(row, k) for k in changes}
        for k, v in changes.items():
            if v is not None:
                setattr(row, k, v)
        row.updated_by = self.actor.id
        audit.record(self.session, actor_id=self.actor.id, action="ALERT_CATALOG_UPDATE", entity_type="alert_catalog", entity_id=None,
                     old={"code": code, **{k: v for k, v in old.items() if k != "threshold"}},
                     new={"code": code, **{k: v for k, v in changes.items() if k != "threshold"}}, ip=self.ip)
        return row

    # ------------------------------------------------------------------ process compliance
    def compliance(self, job_id: int) -> dict[str, Any]:
        job = self._own_job(job_id)
        robot = self.session.get(Robot, job.robot_id)
        from app.models.order import Order
        order = self.session.get(Order, job.order_id)
        events = list(self.session.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.id)))
        cal = self.session.scalar(select(Calibration).where(Calibration.job_id == job.id, Calibration.is_valid.is_(True))
                                  .order_by(Calibration.id.desc()).limit(1))
        runs = list(self.session.scalars(select(RobotRun).where(RobotRun.job_id == job.id).order_by(RobotRun.id)))
        steps: list[dict[str, Any]] = []

        def add(key: str, label: str, status: str, at: datetime | None = None, detail: str | None = None) -> None:
            steps.append({"key": key, "label_vi": label, "status": status, "at": at, "detail": detail})

        mismatch = any(e.event_type == JobEventType.HASH_MISMATCH for e in events)
        add("package", "Gói job khớp mã hash của phác thảo đã duyệt", "FAIL" if mismatch else ("PASS" if job.downloaded_at else "PENDING"),
            job.downloaded_at, "Mã hash không khớp" if mismatch else None)
        add("calibration", "Hiệu chuẩn mặt giấy và lực", "PASS" if cal else "PENDING", cal.created_at if cal else None)
        sv = ((job.simulation_report or {}).get("server_validation") or {}).get("status")
        add("server_validation", "Máy chủ tự kiểm lại quỹ đạo", {"PASS": "PASS", "FAIL": "FAIL"}.get(sv or "", "NOT_APPLICABLE" if sv == "NOT_RUN" else "PENDING"),
            None, "Chưa bật kiểm tra phía máy chủ cho hiệu chuẩn này" if sv == "NOT_RUN" else None)
        add("simulation", "Mô phỏng đạt", "PASS" if job.simulation_passed is True else ("FAIL" if job.simulation_passed is False else "PENDING"))
        dry = [r for r in runs if r.dry_run and r.result == "DRY_RUN_DONE"]
        real_writes = [r for r in runs if r.mode == "REAL" and not r.dry_run and r.result != "REFUSED"]
        add("dry_run", "Chạy thử pen-up (bút không chạm giấy)", "PASS" if dry else ("FAIL" if real_writes else "PENDING"),
            dry[-1].ended_at if dry else None, "Có lần viết thật mà chưa có chạy thử" if (real_writes and not dry) else None)
        auth = next((r for r in real_writes if r.authorized_by), None)
        who = self.session.get(Account, auth.authorized_by).full_name if auth else None
        add("authorized", "Người vận hành xác nhận chạy robot thật", "PASS" if auth else ("FAIL" if real_writes else "PENDING"),
            auth.authorized_at if auth else None, who)
        written = job.status in (JobStatus.WRITTEN, JobStatus.PHOTO_UPLOADED, JobStatus.DONE)
        add("written", "Viết xong", "PASS" if written else ("FAIL" if job.status == JobStatus.FAILED else "PENDING"), job.finished_at)
        done_real = any(r.mode == "REAL" and not r.dry_run and r.result == "DONE" for r in runs)
        add("real_run", "Có lần chạy robot thật hoàn tất cho job này",
            "PASS" if done_real else ("FAIL" if written else "PENDING"), None,
            "Job được ghi nhận đã viết xong nhưng không có lần chạy robot thật nào hoàn tất (MOCK/SIM không tính)" if (written and not done_real) else None)
        add("photos", "Ảnh sản phẩm và QC", "PASS" if job.status in (JobStatus.PHOTO_UPLOADED, JobStatus.DONE) else "PENDING")

        exceptions: list[str] = []
        stops = sum(1 for e in events if e.event_type in SAFETY_STOP_EVENTS)
        if stops:
            exceptions.append(f"Có {stops} lần dừng an toàn trong job này.")
        if len(real_writes) > 1:
            exceptions.append(f"Job được chạy thật {len(real_writes)} lần (viết dở rồi tiếp tục).")
        if any(r.result == "UNKNOWN" for r in runs):
            exceptions.append("Có lần chạy kết thúc không rõ (mất kết nối giữa chừng).")
        red = self.session.scalar(select(func.count()).select_from(RobotAlert).where(RobotAlert.job_id == job.id, RobotAlert.level >= 4)) or 0
        if red:
            exceptions.append(f"Có {red} cảnh báo đỏ liên quan job này.")
        thr = self.session.get(AlertCatalog, "CALIBRATION_OLD")
        limit = ((thr.threshold or {}).get("max_minutes") if thr else None)
        if cal and real_writes and isinstance(limit, (int, float)):
            age = (real_writes[0].started_at - cal.created_at).total_seconds() / 60
            if age > limit:
                exceptions.append(f"Hiệu chuẩn đã {age:.0f} phút khi bắt đầu viết (giới hạn {limit:g} phút).")
        followed = all(s["status"] in ("PASS", "NOT_APPLICABLE", "PENDING") for s in steps) and not any(
            s["status"] == "PENDING" for s in steps if s["key"] in ("package", "calibration", "simulation") and job.status in WRITE_RUN_STATUSES)
        return {"job_id": job.id, "order_code": order.code if order else "", "robot_code": robot.code if robot else "",
                "job_status": job.status.value, "steps": steps, "exceptions": exceptions, "followed_process": followed}
