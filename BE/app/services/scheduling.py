"""Production scheduling for the Manager: FR-37 (schedule a job), FR-40 (duration), BR-18 (one job per robot at a
time, robot fits the pen), re-scheduling after a failure or a rewrite request.

The service SUGGESTS robot / technician / slot and lets the Manager confirm or choose differently. It only writes
the schedule (production_jobs + production_status); it never talks to the robot.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import scheduling_rules as sr
from app.models.account import Account, AccountStatus, RoleCode
from app.models.ops import JobStatus, ProductionJob, Robot, RobotStatus
from app.models.order import Order, OrderStatus, ProductionStatus
from app.repositories.accounts import AccountRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, RobotRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit, notifications

SCHEDULABLE = (ProductionStatus.PENDING_SCHEDULE, ProductionStatus.FAILED, ProductionStatus.REWRITE_REQUIRED)
DEFAULT_LEAD_MIN = 60            # earliest start = now + lead (time to prepare paper/pen)
DEFAULT_ETA_BUFFER_DAYS = 2      # finish -> photo -> acceptance -> hand-over margin
MAX_SUGGESTIONS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SchedulingService:
    def __init__(self, session: Session, manager: Account, ip: str | None = None):
        self.session, self.manager, self.ip = session, manager, ip
        self.orders = OrderRepository(session)
        self.robots = RobotRepository(session)
        self.jobs = JobRepository(session)
        self.catalog = CatalogRepository(session)
        self.sketches = SketchRepository(session)
        self.accounts = AccountRepository(session)

    # ------------------------------------------------------------------ configuration
    def _params(self) -> tuple[sr.WorkCalendar, dict[str, int]]:
        try:
            cal = sr.WorkCalendar.from_setting(self.catalog.setting("working_hours"))
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(503, "WORKING_HOURS_INVALID", "Cấu hình giờ làm việc (working_hours) không hợp lệ.") from exc
        raw = self.catalog.setting("schedule_params") or {}
        p = {"prep_min": sr.DEFAULT_PREP_MIN, "photo_min": sr.DEFAULT_PHOTO_MIN, "lead_min": DEFAULT_LEAD_MIN,
             "eta_buffer_days": DEFAULT_ETA_BUFFER_DAYS}
        p.update({k: int(v) for k, v in raw.items() if k in p})
        return cal, p

    # ------------------------------------------------------------------ queue
    def queue(self, page: int, page_size: int):
        return self.orders.production_queue(production_statuses=list(SCHEDULABLE), offset=(page - 1) * page_size,
                                            limit=page_size)

    def duration_min(self, order: Order) -> int | None:
        sketch = self.sketches.final(order.id)
        if sketch is None or sketch.estimated_writing_sec is None:
            return None
        _, p = self._params()
        return sr.job_minutes(sketch.estimated_writing_sec, order.quantity, p["prep_min"], p["photo_min"])

    # ------------------------------------------------------------------ checks
    def _schedulable_order(self, order_id: int, *, lock: bool = False) -> Order:
        order = self.orders.get(order_id, lock=lock)
        if order is None or order.order_status == OrderStatus.DRAFT:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        if order.order_status != OrderStatus.CONFIRMED or order.production_status not in SCHEDULABLE:
            raise AppError(409, "NOT_SCHEDULABLE", "Đơn không ở trạng thái chờ xếp lịch sản xuất.",
                           {"order_status": order.order_status.value, "production_status": order.production_status.value})
        return order

    def _sketch(self, order: Order):
        sketch = self.sketches.final(order.id)
        if sketch is None or sketch.estimated_writing_sec is None:
            raise AppError(409, "SKETCH_REQUIRED", "Đơn chưa có phác thảo chốt với thời gian viết ước tính.")
        return sketch

    def _pen_category(self, order: Order) -> str | None:
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        return pen.category if pen else None

    def _robot_fits(self, robot: Robot, order: Order) -> bool:
        cats = robot.supported_pen_categories
        return not cats or (self._pen_category(order) in cats)       # no list = any pen (BR-18 assumption)

    def _technician(self, technician_id: int) -> Account:
        acc = self.accounts.get(technician_id)
        if acc is None or acc.role.code != RoleCode.TECHNICAL_STAFF.value or acc.status != AccountStatus.ACTIVE:
            raise AppError(422, "INVALID_TECHNICIAN", "Chỉ giao được cho Technical Staff đang hoạt động.")
        return acc

    def _busy(self, *, exclude_job_id: int | None = None):
        robot_busy: dict[int, list[sr.Interval]] = {}
        tech_busy: dict[int, list[sr.Interval]] = {}
        for j in self.jobs.busy(since=_now(), exclude_job_id=exclude_job_id):
            robot_busy.setdefault(j.robot_id, []).append((j.slot_start, j.slot_end))
            tech_busy.setdefault(j.technician_id, []).append((j.slot_start, j.slot_end))
        return robot_busy, tech_busy

    # ------------------------------------------------------------------ suggestion
    def suggest(self, order_id: int) -> dict[str, Any]:
        order = self._schedulable_order(order_id)
        sketch = self._sketch(order)
        cal, p = self._params()
        minutes = sr.job_minutes(sketch.estimated_writing_sec, order.quantity, p["prep_min"], p["photo_min"])
        earliest = _now() + timedelta(minutes=p["lead_min"])
        robot_busy, tech_busy = self._busy()
        role = self.accounts.role_by_code(RoleCode.TECHNICAL_STAFF.value)
        techs, _ = self.accounts.search(role_id=role.id, status=AccountStatus.ACTIVE, q=None, offset=0, limit=200)
        load = self.jobs.load_by_technician(_now())
        candidates = []
        for robot in self.robots.list(RobotStatus.AVAILABLE):
            if not self._robot_fits(robot, order):
                continue
            best = None
            for t in techs:
                try:
                    slot = sr.find_slot(cal, earliest, minutes, robot_busy.get(robot.id, []) + tech_busy.get(t.id, []))
                except sr.NoSlotError:
                    continue
                key = (slot[0], load.get(t.id, 0), t.id)
                if best is None or key < best[0]:
                    best = (key, t, slot)
            if best:
                candidates.append((best[2], robot, best[1]))
        candidates.sort(key=lambda c: (c[0][0], c[1].id))
        eta_buffer = timedelta(days=p["eta_buffer_days"])
        out = []
        for (start, end), robot, tech in candidates[:MAX_SUGGESTIONS]:
            finish_by = (end + eta_buffer).astimezone(cal.tz).date()
            out.append({"robot_id": robot.id, "robot_code": robot.code, "is_simulated": robot.is_simulated,
                        "technician_id": tech.id, "technician_name": tech.full_name, "slot_start": start,
                        "slot_end": end, "finish_by": finish_by,
                        "eta_risk": bool(order.eta and finish_by > order.eta)})
        return {"order_id": order.id, "duration_min": minutes, "writing_sec_per_copy": sketch.estimated_writing_sec,
                "quantity": order.quantity, "eta": order.eta, "stock_warnings": self._stock_warnings(order),
                "suggestions": out}

    def _stock_warnings(self, order: Order) -> list[str]:
        out = []
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        ink = self.catalog.ink(order.ink_color_id) if order.ink_color_id else None
        if paper and paper.stock_qty < order.quantity:
            out.append(f"Giấy '{paper.name}' còn {paper.stock_qty}, đơn cần ít nhất {order.quantity} tờ.")
        if pen and pen.stock_qty < 1:
            out.append(f"Bút '{pen.name}' đã hết hàng.")
        if ink and ink.stock_qty < 1:
            out.append(f"Mực '{ink.name}' đã hết hàng.")
        return out

    # ------------------------------------------------------------------ scheduling
    def schedule(self, order_id: int, *, robot_id: int, technician_id: int, slot_start: datetime,
                 note: str | None = None, _replacing: ProductionJob | None = None) -> ProductionJob:
        order = self._schedulable_order(order_id, lock=True)
        sketch = self._sketch(order)
        robot = self.robots.get(robot_id, lock=True)
        if robot is None:
            raise AppError(404, "ROBOT_NOT_FOUND", "Không tìm thấy robot.")
        if robot.status != RobotStatus.AVAILABLE:
            raise AppError(409, "ROBOT_UNAVAILABLE", f"Robot {robot.code} đang {robot.status.value}.")
        if not self._robot_fits(robot, order):
            raise AppError(422, "ROBOT_NOT_SUITABLE", f"Robot {robot.code} không phù hợp loại bút của đơn (BR-18).")
        tech = self._technician(technician_id)
        cal, p = self._params()
        if slot_start.tzinfo is None:
            raise AppError(422, "INVALID_SLOT", "slot_start phải có múi giờ.")
        if slot_start < _now() - timedelta(minutes=1):
            raise AppError(422, "SLOT_IN_PAST", "Không thể xếp lịch vào thời điểm đã qua.")
        if cal.next_open(slot_start) != slot_start.astimezone(cal.tz):
            raise AppError(422, "OUTSIDE_WORKING_HOURS", "Giờ bắt đầu nằm ngoài giờ làm việc của xưởng.")
        minutes = sr.job_minutes(sketch.estimated_writing_sec, order.quantity, p["prep_min"], p["photo_min"])
        slot_end = cal.add_working_minutes(slot_start, minutes)
        robot_busy, tech_busy = self._busy(exclude_job_id=_replacing.id if _replacing else None)
        slot = (slot_start, slot_end)
        if any(sr.overlaps(slot, b) for b in robot_busy.get(robot.id, [])):
            raise AppError(409, "SLOT_CONFLICT", f"Robot {robot.code} đã có job trong khung giờ này (BR-18).",
                           {"resource": "robot"})
        if any(sr.overlaps(slot, b) for b in tech_busy.get(tech.id, [])):
            raise AppError(409, "SLOT_CONFLICT", f"{tech.full_name} đã có job trong khung giờ này.",
                           {"resource": "technician"})

        prior = self.jobs.previous_outcomes(order.id)
        rewrite = order.production_status == ProductionStatus.REWRITE_REQUIRED or (
            _replacing.is_rewrite if _replacing else JobStatus.REWRITE_REQUIRED in prior)
        if order.production_status in (ProductionStatus.FAILED, ProductionStatus.REWRITE_REQUIRED):
            set_actor(self.session, self.manager.id, "Xếp lại lịch sản xuất")
            order.production_status = ProductionStatus.PENDING_SCHEDULE
            self.session.flush()
        job = self.jobs.add(ProductionJob(
            order_id=order.id, sketch_id=sketch.id, robot_id=robot.id, technician_id=tech.id,
            scheduled_by=self.manager.id, status=JobStatus.SCHEDULED, is_rewrite=rewrite, slot_start=slot_start,
            slot_end=slot_end, estimated_duration_min=minutes, package_hash=sketch.content_hash))
        set_actor(self.session, self.manager.id, note or "Xếp lịch sản xuất")
        order.production_status = ProductionStatus.SCHEDULED
        if order.eta is None:
            order.eta = (slot_end + timedelta(days=p["eta_buffer_days"])).astimezone(cal.tz).date()
        self.session.flush()
        audit.record(self.session, actor_id=self.manager.id, action="JOB_SCHEDULE", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id, "robot_id": robot.id, "technician_id": tech.id,
                                            "slot_start": slot_start.isoformat(), "slot_end": slot_end.isoformat(),
                                            "is_rewrite": rewrite}, reason=note, ip=self.ip)
        notifications.notify(account_id=tech.id, order_id=order.id, msg_code="JOB_ASSIGNED", code=order.code,
                             slot_start=slot_start.isoformat())
        return job

    # ------------------------------------------------------------------ change / cancel a planned job
    def _planned_job(self, job_id: int) -> tuple[ProductionJob, Order]:
        job = self.jobs.get(job_id, lock=True)
        if job is None:
            raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
        order = self.orders.get(job.order_id, lock=True)
        if job.status != JobStatus.SCHEDULED or order.production_status != ProductionStatus.SCHEDULED:
            raise AppError(409, "JOB_ALREADY_STARTED", "Chỉ đổi được job đang ở trạng thái SCHEDULED, chưa chuẩn bị.")
        return job, order

    def unschedule(self, job_id: int, reason: str) -> ProductionJob:
        job, order = self._planned_job(job_id)
        job.status = JobStatus.CANCELLED
        set_actor(self.session, self.manager.id, reason)
        order.production_status = ProductionStatus.PENDING_SCHEDULE
        self.session.flush()
        audit.record(self.session, actor_id=self.manager.id, action="JOB_UNSCHEDULE", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id}, reason=reason, ip=self.ip)
        return job

    def reschedule(self, job_id: int, *, robot_id: int | None, technician_id: int | None,
                   slot_start: datetime | None, reason: str) -> ProductionJob:
        old, order = self._planned_job(job_id)
        robot_id, technician_id = robot_id or old.robot_id, technician_id or old.technician_id
        slot_start = slot_start or old.slot_start
        old_slot = (old.robot_id, old.technician_id, old.slot_start)
        old.status = JobStatus.CANCELLED
        set_actor(self.session, self.manager.id, reason)
        order.production_status = ProductionStatus.PENDING_SCHEDULE
        self.session.flush()
        new = self.schedule(order.id, robot_id=robot_id, technician_id=technician_id, slot_start=slot_start,
                            note=reason, _replacing=old)
        audit.record(self.session, actor_id=self.manager.id, action="JOB_RESCHEDULE", entity_type="production_job",
                     entity_id=new.id, old={"job_id": old.id, "robot_id": old_slot[0],
                                            "technician_id": old_slot[1], "slot_start": old_slot[2].isoformat()},
                     new={"job_id": new.id}, reason=reason, ip=self.ip)
        return new

    # ------------------------------------------------------------------ reads
    def get(self, job_id: int) -> ProductionJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
        return job

    def search(self, **kw):
        return self.jobs.search(**kw)

    def technicians(self) -> list[dict[str, Any]]:
        role = self.accounts.role_by_code(RoleCode.TECHNICAL_STAFF.value)
        rows, _ = self.accounts.search(role_id=role.id, status=AccountStatus.ACTIVE, q=None, offset=0, limit=200)
        load = self.jobs.load_by_technician(_now())
        return [{"id": a.id, "full_name": a.full_name, "email": a.email, "active_jobs": load.get(a.id, 0)}
                for a in rows]

    def labels(self, jobs: list[ProductionJob]) -> dict[str, dict[int, str]]:
        """Display names for a page of jobs (order code, robot code, technician name)."""
        orders = {j.order_id: self.orders.get(j.order_id) for j in jobs}
        return {"order": {i: o.code for i, o in orders.items() if o},
                "robot": {r: (self.robots.get(r).code) for r in {j.robot_id for j in jobs}},
                "tech": {t: (self.accounts.get(t).full_name) for t in {j.technician_id for j in jobs}}}


