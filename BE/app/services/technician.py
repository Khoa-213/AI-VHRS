"""Technical Staff on the workshop floor (Phase 4a): UC-31..39, FR-43..49, BR-17, BR-19, BR-20.

The technician sees only the jobs assigned to them (BR-19: another technician's job answers 404). The server records and
guards the job's life: package download with hash check, preparation, calibration, simulation result, start, progress
and safety events, the end of writing (stock is deducted then, FR-41) and incidents.

Nothing here talks to a robot yet (connecting it is deferred until the project owner asks): the client reports what
happened (simulation result, progress, safety stops) and the server records and guards it.
Every change of the job mirrors onto the order's production status in the same transaction (BR-17, FR-25); the database
trigger `fn_order_state_guard` has the last word.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import job_rules as jr
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.catalog import InkColor, PaperType, PenType
from app.models.ops import (Calibration, Incident, IncidentType, JobEvent, JobEventType, JobStatus, ProductionJob, Robot,
                            RobotStatus)
from app.models.order import Order, OrderStatus, ProductionStatus
from app.repositories.accounts import AccountRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import CalibrationRepository, EventRepository, IncidentRepository, JobRepository, RobotRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit, notifications
from app.services.stroke_ai import trajectory as tj

PACKAGE_URL_TTL = 1800                      # seconds a signed trajectory link stays valid
RUNNABLE_ROBOT = (RobotStatus.AVAILABLE, RobotStatus.BUSY)
_RULE_STATUS = {"JOB_STATE_CONFLICT": 409}  # every other JobRuleError is a 422


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rule_error(exc: jr.JobRuleError) -> AppError:
    return AppError(_RULE_STATUS.get(exc.code, 422), exc.code, exc.message, exc.details)


class TechnicianJobService:
    def __init__(self, session: Session, tech: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.tech, self.storage, self.ip = session, tech, storage, ip
        self.jobs = JobRepository(session)
        self.orders = OrderRepository(session)
        self.robots = RobotRepository(session)
        self.catalog = CatalogRepository(session)
        self.sketches = SketchRepository(session)
        self.calibrations = CalibrationRepository(session)
        self.events = EventRepository(session)
        self.incidents = IncidentRepository(session)
        self.accounts = AccountRepository(session)

    # ------------------------------------------------------------------ access and guards
    def _job(self, job_id: int, *, lock: bool = False) -> ProductionJob:
        job = self.jobs.get(job_id, lock=lock)
        if job is None or job.technician_id != self.tech.id:          # BR-19: not yours = not found
            raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
        return job

    def _order(self, job: ProductionJob, *, lock: bool = True) -> Order:
        order = self.orders.get(job.order_id, lock=lock)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return order

    def _storage(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def _require_open(self, job: ProductionJob, order: Order) -> None:
        if job.status not in jr.OPEN_STATUSES:
            raise AppError(409, "JOB_NOT_ACTIVE", f"Job đã {job.status.value}, không còn thao tác được.",
                           {"job_status": job.status.value})
        if order.order_status != OrderStatus.CONFIRMED:               # e.g. the customer cancelled meanwhile (BR-17)
            raise AppError(409, "ORDER_NOT_ACTIVE", "Đơn không còn ở trạng thái sản xuất.",
                           {"order_status": order.order_status.value})

    def _require_status(self, job: ProductionJob, *allowed: JobStatus, what: str) -> None:
        if job.status not in allowed:
            raise AppError(409, "JOB_STATE_CONFLICT", f"{what} khi job đang {job.status.value}.",
                           {"job_status": job.status.value, "allowed": [s.value for s in allowed]})

    def _robot_runnable(self, job: ProductionJob) -> Robot:
        robot = self.robots.get(job.robot_id, lock=True)
        if robot is None or robot.status not in RUNNABLE_ROBOT:
            raise AppError(409, "ROBOT_UNAVAILABLE",
                           f"Robot {robot.code if robot else job.robot_id} đang {robot.status.value if robot else 'không rõ'}.")
        return robot

    def _event(self, job: ProductionJob, kind: JobEventType, *, stroke_index: int | None = None,
               force_summary: dict[str, Any] | None = None, payload: dict[str, Any] | None = None,
               incident_id: int | None = None) -> JobEvent:
        return self.events.add(JobEvent(job_id=job.id, event_type=kind, actor_id=self.tech.id, incident_id=incident_id,
                                        stroke_index=stroke_index, force_summary=force_summary, payload=payload))

    def _move(self, job: ProductionJob, order: Order, dst: JobStatus, reason: str) -> None:
        """Job and order production status change together (BR-17, FR-25)."""
        if not jr.can_move(job.status, dst):
            raise AppError(409, "JOB_STATE_CONFLICT", f"Không chuyển job từ {job.status.value} sang {dst.value}.",
                           {"job_status": job.status.value})
        expected = ProductionStatus(job.status.value)
        if order.production_status != expected:
            raise AppError(409, "STATE_CONFLICT", "Trạng thái sản xuất của đơn không khớp job.",
                           {"job": job.status.value, "order_production": order.production_status.value})
        job.status = dst
        self.session.flush()
        set_actor(self.session, self.tech.id, reason)
        order.production_status = ProductionStatus(dst.value)
        self.session.flush()

    def _hash_mismatch(self, job: ProductionJob, expected: str | None, actual: str | None) -> AppError:
        """MSG14. The event and the audit row must survive the failed request, so they are committed first (S03)."""
        self._event(job, JobEventType.HASH_MISMATCH, payload={"expected": expected, "actual": actual})
        audit.record(self.session, actor_id=self.tech.id, action="JOB_HASH_MISMATCH", entity_type="production_job",
                     entity_id=job.id, new={"expected": expected, "actual": actual}, ip=self.ip)
        self.session.commit()
        return AppError(409, "JOB_HASH_MISMATCH", "Gói job không khớp phác thảo đã duyệt. Không thể chạy.")

    # ------------------------------------------------------------------ reads
    def search(self, *, statuses: list[JobStatus] | None, start: datetime | None, end: datetime | None,
               page: int, page_size: int):
        return self.jobs.search(statuses=statuses, robot_id=None, technician_id=self.tech.id, start=start, end=end,
                                offset=(page - 1) * page_size, limit=page_size)

    def get(self, job_id: int) -> ProductionJob:
        return self._job(job_id)

    def detail(self, job_id: int) -> dict[str, Any]:
        job = self._job(job_id)
        order = self.orders.get(job.order_id)
        sketch = self.sketches.get_by_id(job.sketch_id)
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        ink = self.catalog.ink(order.ink_color_id) if order.ink_color_id else None
        cal = self.calibrations.valid(job.id)
        return {"order_type": order.order_type.value, "quantity": order.quantity, "eta": order.eta,
                "paper_name": paper.name if paper else None, "pen_name": pen.name if pen else None,
                "ink_name": ink.name if ink else None, "approach_note": sketch.approach_note if sketch else None,
                "calibration": cal, "incidents": self.incidents.for_job(job.id),
                "can_start": bool(job.status == JobStatus.PREPARING and job.downloaded_at and cal
                                  and job.simulation_passed is True)}

    def event_page(self, job_id: int, page: int, page_size: int) -> tuple[list[JobEvent], int]:
        job = self._job(job_id)
        return self.events.for_job(job.id, offset=(page - 1) * page_size, limit=page_size)

    # ------------------------------------------------------------------ UC-32: download the package
    def package(self, job_id: int) -> dict[str, Any]:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        sketch = self.sketches.get_by_id(job.sketch_id)
        uri = job.package_uri or (sketch.trajectory_uri if sketch else None)
        if sketch is None or uri is None:
            raise AppError(409, "SKETCH_REQUIRED", "Job không có phác thảo để đóng gói.")
        store = self._storage()
        raw = store.read(uri)
        if raw is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được gói quỹ đạo từ kho lưu trữ.")
        actual = tj.content_hash(raw)
        if job.package_hash is None or actual != job.package_hash or sketch.content_hash != job.package_hash:
            raise self._hash_mismatch(job, job.package_hash, actual)
        try:
            pages = tj.parse(json.loads(raw))
        except (ValueError, AppError) as exc:
            raise AppError(409, "JOB_PACKAGE_INVALID", "Quỹ đạo trong gói job không hợp lệ.") from exc

        if job.downloaded_at is None:
            job.downloaded_at = _now()
        self._event(job, JobEventType.DOWNLOADED, payload={"hash": actual, "pages": len(pages)})
        self.session.flush()
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        ink = self.catalog.ink(order.ink_color_id) if order.ink_color_id else None
        preview = None
        if sketch.preview_url:
            try:
                preview = store.create_download_url(sketch.preview_url, PACKAGE_URL_TTL)
            except AppError:
                preview = None                                    # a preview is a convenience, the job does not need it
        return {"job_id": job.id, "order_code": order.code, "order_type": order.order_type.value,
                "quantity": order.quantity, "is_rewrite": job.is_rewrite,
                "estimated_duration_min": job.estimated_duration_min, "package_hash": actual,
                "trajectory_url": store.create_download_url(uri, PACKAGE_URL_TTL),
                "trajectory_url_expires_in": PACKAGE_URL_TTL, "trajectory_format": tj.FORMAT, "pages": len(pages),
                "paper": ({"name": paper.name, "gsm": paper.gsm, "surface": paper.surface, "size": paper.size.value}
                          if paper else None),
                "pen": ({"name": pen.name, "category": pen.category, "stroke_width_mm": float(pen.stroke_width_mm),
                         "f_target_n": float(pen.f_target_n), "f_min_n": float(pen.f_min_n),
                         "f_max_n": float(pen.f_max_n), "f_hard_n": float(pen.f_hard_n),
                         "v_max_mm_s": float(pen.v_max_mm_s)} if pen else None),
                "ink_name": ink.name if ink else None, "ink_hex": ink.hex_code if ink else None,
                "approach_note": sketch.approach_note, "preview_url": preview}

    # ------------------------------------------------------------------ UC-33: prepare and calibrate
    def prepare(self, job_id: int) -> ProductionJob:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, JobStatus.SCHEDULED, what="Chỉ bắt đầu chuẩn bị")
        if job.downloaded_at is None:
            raise AppError(409, "JOB_NOT_DOWNLOADED", "Hãy tải gói job và kiểm tra hash trước khi chuẩn bị (UC-32).")
        self._robot_runnable(job)
        self._move(job, order, JobStatus.PREPARING, "Technical Staff bắt đầu chuẩn bị")
        audit.record(self.session, actor_id=self.tech.id, action="JOB_PREPARE", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id}, ip=self.ip)
        return job

    def calibrate(self, job_id: int, *, checklist: dict[str, bool], force_zero_offset: float,
                  probe_points: list[dict[str, float]], frame_transform: dict[str, Any] | None,
                  height_map: Any, force_curve: Any) -> Calibration:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, JobStatus.PREPARING, what="Chỉ hiệu chuẩn")
        try:
            jr.check_checklist(checklist)
            jr.check_probe_points(probe_points)
        except jr.JobRuleError as exc:
            raise _rule_error(exc) from exc
        self.calibrations.invalidate_all(job.id)
        row = self.calibrations.add(Calibration(
            job_id=job.id, robot_id=job.robot_id, technician_id=self.tech.id, paper_type_id=order.paper_type_id,
            pen_type_id=order.pen_type_id, checklist=checklist, force_zero_offset=force_zero_offset,
            probe_points=probe_points, frame_transform=frame_transform, height_map=height_map,
            force_curve=force_curve, is_valid=True))
        # A new paper plane changes the robot-frame path, so an older simulation no longer proves anything.
        job.simulation_passed, job.simulation_report = None, None
        self._event(job, JobEventType.CALIBRATED, payload={"calibration_id": row.id, "probe_points": len(probe_points)})
        audit.record(self.session, actor_id=self.tech.id, action="JOB_CALIBRATE", entity_type="production_job",
                     entity_id=job.id, new={"calibration_id": row.id}, ip=self.ip)
        self.session.flush()
        return row

    # ------------------------------------------------------------------ UC-34: simulation result
    def record_simulation(self, job_id: int, *, passed: bool, errors: list[str], report: dict[str, Any] | None
                          ) -> ProductionJob:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, JobStatus.PREPARING, what="Chỉ ghi kết quả mô phỏng")
        cal = self.calibrations.valid(job.id)
        if cal is None:
            raise AppError(409, "CALIBRATION_REQUIRED", "Cần hiệu chuẩn trước khi mô phỏng (BR-19).")
        try:
            jr.check_simulation(passed, errors)
        except jr.JobRuleError as exc:
            raise _rule_error(exc) from exc
        job.simulation_passed = passed
        job.simulation_report = {"errors": errors, "report": report, "calibration_id": cal.id,
                                 "reported_at": _now().isoformat()}
        self._event(job, JobEventType.SIMULATED, payload={"passed": passed, "errors": len(errors)})
        self.session.flush()
        return job

    # ------------------------------------------------------------------ UC-35: start writing
    def start(self, job_id: int) -> ProductionJob:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, JobStatus.PREPARING, what="Chỉ chạy viết")
        sketch = self.sketches.get_by_id(job.sketch_id)
        if job.package_hash is None or sketch is None or sketch.content_hash != job.package_hash:
            raise self._hash_mismatch(job, job.package_hash, sketch.content_hash if sketch else None)   # MSG14
        if job.downloaded_at is None:
            raise AppError(409, "JOB_NOT_DOWNLOADED", "Hãy tải gói job và kiểm tra hash trước khi chạy (UC-32).")
        if self.calibrations.valid(job.id) is None:
            raise AppError(409, "CALIBRATION_REQUIRED", "Cần hiệu chuẩn mặt giấy và lực trước khi chạy (BR-19).")
        if job.simulation_passed is not True:
            raise AppError(409, "SIMULATION_REQUIRED" if job.simulation_passed is None else "SIMULATION_FAILED",
                           "Chưa có kết quả mô phỏng đạt; không cho chạy khi còn lỗi khả thi (FR-45).")
        self._robot_runnable(job)
        job.started_at, job.progress_pct = _now(), 0
        self._move(job, order, JobStatus.WRITING, "Bắt đầu viết")
        self._event(job, JobEventType.START)
        audit.record(self.session, actor_id=self.tech.id, action="JOB_START", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id}, ip=self.ip)
        return job

    # ------------------------------------------------------------------ UC-36: monitor, pause, safety stops
    def record_event(self, job_id: int, kind: JobEventType, *, stroke_index: int | None, progress_pct: float | None,
                     force_summary: dict[str, Any] | None, payload: dict[str, Any] | None) -> JobEvent:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        if job.status != JobStatus.WRITTEN:        # after WRITTEN only a closing force summary may still arrive
            self._require_open(job, order)
        try:
            dst = jr.event_effect(kind, job.status)
            if kind == JobEventType.FORCE_SUMMARY:
                jr.check_force_summary(force_summary or {})
        except jr.JobRuleError as exc:
            raise _rule_error(exc) from exc
        if kind == JobEventType.PROGRESS:
            if progress_pct is None:
                raise AppError(422, "PROGRESS_REQUIRED", "PROGRESS cần progress_pct (0..100).")
            job.progress_pct = max(float(job.progress_pct or 0), progress_pct)   # never goes backwards
        if dst is not None:
            self._move(job, order, dst, f"Máy trạm báo {kind.value}")
        event = self._event(job, kind, stroke_index=stroke_index,
                            force_summary=force_summary if kind == JobEventType.FORCE_SUMMARY else None, payload=payload)
        if kind in (JobEventType.ESTOP, JobEventType.OVER_FORCE):
            audit.record(self.session, actor_id=self.tech.id, action=f"JOB_{kind.value}", entity_type="production_job",
                         entity_id=job.id, new=payload, ip=self.ip)
            notifications.notify(account_id=job.scheduled_by, order_id=order.id, msg_code="JOB_SAFETY_STOP",
                                 code=order.code, event=kind.value)
        return event

    # ------------------------------------------------------------------ UC-39: writing finished, stock deducted
    def _pages(self, job: ProductionJob) -> tuple[int, bool]:
        """Sheets per copy from the stored trajectory. Falls back to 1 (flagged) when storage cannot answer."""
        try:
            raw = self._storage().read(job.package_uri or self.sketches.get_by_id(job.sketch_id).trajectory_uri)
            if raw is not None:
                return len(tj.parse(json.loads(raw))), False
        except (AppError, ValueError, AttributeError):
            pass
        return 1, True

    def finish(self, job_id: int) -> ProductionJob:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, JobStatus.WRITING, what="Chỉ kết thúc viết")
        pages, assumed = self._pages(job)
        use = jr.stock_use(order.quantity, pages)
        stock: dict[str, Any] = {"pages": pages, "pages_assumed": assumed}
        for key, model, pk, used in (("paper", PaperType, order.paper_type_id, use.paper),
                                     ("pen", PenType, order.pen_type_id, use.pen),
                                     ("ink", InkColor, order.ink_color_id, use.ink)):
            row = self.catalog.lock(model, pk) if pk else None
            if row is None:
                continue                                          # "để xưởng đề xuất" order without that item
            row.stock_qty, short = jr.deduct(row.stock_qty, used)
            stock[key] = {"id": pk, "used": used, "left": row.stock_qty, "shortfall": short}
        job.finished_at, job.progress_pct = _now(), 100
        self._move(job, order, JobStatus.WRITTEN, "Robot viết xong")
        self._event(job, JobEventType.WRITTEN, payload={"stock": stock})
        audit.record(self.session, actor_id=self.tech.id, action="JOB_WRITTEN", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id, "stock": stock}, ip=self.ip)
        return job

    # ------------------------------------------------------------------ UC-37: incident
    def report_incident(self, job_id: int, *, kind: IncidentType, description: str, robot_status_after: str | None) -> Incident:
        job = self._job(job_id, lock=True)
        order = self._order(job)
        self._require_open(job, order)
        self._require_status(job, *jr.INCIDENT_FROM, what="Chỉ báo sự cố")
        incident = self.incidents.add(Incident(
            job_id=job.id, robot_id=job.robot_id, reported_by=self.tech.id, type=kind, description=description,
            photo_urls=[], robot_status_after=RobotStatus(robot_status_after) if robot_status_after else None))
        if robot_status_after:
            robot = self.robots.get(job.robot_id, lock=True)
            robot.status = RobotStatus(robot_status_after)
        job.finished_at = _now()
        self._move(job, order, JobStatus.FAILED, f"Sự cố: {description}"[:200])   # order -> FAILED, back to the Manager's queue
        self._event(job, JobEventType.INCIDENT, incident_id=incident.id, payload={"type": kind.value})
        audit.record(self.session, actor_id=self.tech.id, action="INCIDENT_REPORT", entity_type="incident",
                     entity_id=incident.id, new={"job_id": job.id, "type": kind.value,
                                                 "robot_status_after": robot_status_after}, reason=description, ip=self.ip)
        notifications.notify(account_id=job.scheduled_by, order_id=order.id, msg_code="INCIDENT_REPORTED",
                             code=order.code, robot_id=job.robot_id)
        return incident
