"""Production scheduling for the Manager (FR-37, FR-40, BR-18): queue, suggestion, schedule, change, calendar.

Only the schedule is written here. Nothing in this module contacts a robot.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import (JobOut, ProductionQueueRow, RescheduleIn, ScheduleIn, SuggestionOut, TechnicianOut,
                                 UnscheduleIn)
from app.api.schemas import ErrorOut, Page
from app.models.account import Account, RoleCode
from app.models.ops import JobStatus, ProductionJob
from app.services.scheduling import SchedulingService

router = APIRouter(prefix="/manager", tags=["Scheduling"])
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]


def _svc(session: SessionDep, manager: ManagerDep, request: Request) -> SchedulingService:
    return SchedulingService(session, manager, client_ip(request))


Svc = Annotated[SchedulingService, Depends(_svc)]


def _jobs_out(svc: SchedulingService, jobs: list[ProductionJob]) -> list[JobOut]:
    names = svc.labels(jobs)
    out = []
    for j in jobs:
        row = JobOut.model_validate(j)
        row.order_code, row.robot_code = names["order"].get(j.order_id, ""), names["robot"].get(j.robot_id, "")
        row.technician_name = names["tech"].get(j.technician_id, "")
        out.append(row)
    return out


@router.get("/schedule/queue", response_model=Page[ProductionQueueRow],
            summary="Đơn đã cọc đang chờ xếp lịch (PENDING_SCHEDULE) + đơn cần xếp lại (FAILED, REWRITE_REQUIRED)")
def queue(svc: Svc, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> Page[ProductionQueueRow]:
    rows, total = svc.queue(page, page_size)
    items = [ProductionQueueRow(order_id=o.id, code=o.code, customer_name=name, order_type=o.order_type.value,
                                quantity=o.quantity, eta=o.eta, production_status=o.production_status.value,
                                confirmed_at=o.confirmed_at, duration_min=svc.duration_min(o)) for o, name in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/orders/{order_id}/schedule-suggestion", response_model=SuggestionOut,
            summary="Gợi ý robot + Technical Staff + khung giờ sớm nhất (thời lượng = thời gian viết × SL + 15' + 5')",
            responses={409: {"model": ErrorOut, "description": "NOT_SCHEDULABLE / SKETCH_REQUIRED"}})
def suggestion(order_id: int, svc: Svc) -> SuggestionOut:
    return SuggestionOut(**svc.suggest(order_id))


@router.post("/orders/{order_id}/schedule", response_model=JobOut, status_code=status.HTTP_201_CREATED,
             summary="FR-37 Xếp lịch sản xuất (PENDING_SCHEDULE / FAILED / REWRITE_REQUIRED → SCHEDULED)",
             responses={409: {"model": ErrorOut, "description": "SLOT_CONFLICT / ROBOT_UNAVAILABLE / NOT_SCHEDULABLE"},
                        422: {"model": ErrorOut, "description": "OUTSIDE_WORKING_HOURS / ROBOT_NOT_SUITABLE / ..."}})
def schedule(order_id: int, body: ScheduleIn, svc: Svc) -> JobOut:
    job = svc.schedule(order_id, robot_id=body.robot_id, technician_id=body.technician_id,
                       slot_start=body.slot_start, note=body.note)
    return _jobs_out(svc, [job])[0]


@router.post("/jobs/{job_id}/reschedule", response_model=JobOut,
             summary="Đổi robot / Technical Staff / giờ của job chưa chuẩn bị (job cũ → CANCELLED, tạo job mới)")
def reschedule(job_id: int, body: RescheduleIn, svc: Svc) -> JobOut:
    job = svc.reschedule(job_id, robot_id=body.robot_id, technician_id=body.technician_id,
                         slot_start=body.slot_start, reason=body.reason)
    return _jobs_out(svc, [job])[0]


@router.post("/jobs/{job_id}/unschedule", response_model=JobOut,
             summary="Gỡ job khỏi lịch (SCHEDULED → CANCELLED, đơn quay về PENDING_SCHEDULE)")
def unschedule(job_id: int, body: UnscheduleIn, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.unschedule(job_id, body.reason)])[0]


@router.get("/jobs", response_model=Page[JobOut], summary="Lịch sản xuất: lọc theo trạng thái, robot, kỹ thuật viên, khoảng ngày")
def jobs(svc: Svc, status_: Annotated[list[JobStatus] | None, Query(alias="status")] = None,
         robot_id: int | None = None, technician_id: int | None = None,
         start: Annotated[datetime | None, Query(alias="from")] = None, end: Annotated[datetime | None, Query(alias="to")] = None,
         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[JobOut]:
    rows, total = svc.search(statuses=status_, robot_id=robot_id, technician_id=technician_id, start=start, end=end,
                             offset=(page - 1) * page_size, limit=page_size)
    return Page(items=_jobs_out(svc, rows), total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Chi tiết job")
def job_detail(job_id: int, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.get(job_id)])[0]


@router.get("/technicians", response_model=list[TechnicianOut], summary="Technical Staff đang hoạt động + số job đang giữ")
def technicians(svc: Svc) -> list[TechnicianOut]:
    return [TechnicianOut(**t) for t in svc.technicians()]
