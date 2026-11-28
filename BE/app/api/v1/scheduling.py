"""Production scheduling for the Manager (FR-37, FR-40, BR-18): queue, suggestion, schedule, change, calendar.

Only the schedule is written here. Nothing in this module contacts a robot.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import (FinishOverrideIn, IncidentOut, JobEventOut, JobOut, ManagerJobDetail, ProductionQueueRow,
                                 RescheduleIn, ResolveIncidentIn, StockSettleIn, StockSettleOut,
                                 RobotAssignIn, RobotOut, ScheduleConfigOut, ScheduleIn, SuggestionOut, TechnicianOut,
                                 UnscheduleIn)
from app.api.schemas import ErrorOut, Page
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.ops import JobStatus, ProductionJob
from app.services.scheduling import SchedulingService, robot_owners

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


@router.get("/schedule/config", response_model=ScheduleConfigOut,
            summary="Giờ làm việc và tham số xếp lịch, để vẽ lịch và tính mốc hạn giống backend",
            responses={503: {"model": ErrorOut, "description": "WORKING_HOURS_INVALID"}})
def schedule_config(svc: Svc) -> ScheduleConfigOut:
    return ScheduleConfigOut(**svc.config())


@router.get("/orders/{order_id}/schedule-suggestion", response_model=SuggestionOut,
            summary="Gợi ý Technical Staff + robot của họ + khung giờ sớm nhất (mỗi kỹ thuật viên một gợi ý; thời lượng = thời gian viết × SL + 15' + 5')",
            responses={409: {"model": ErrorOut, "description": "NOT_SCHEDULABLE / SKETCH_REQUIRED"}})
def suggestion(order_id: int, svc: Svc) -> SuggestionOut:
    return SuggestionOut(**svc.suggest(order_id))


@router.post("/orders/{order_id}/schedule", response_model=JobOut, status_code=status.HTTP_201_CREATED,
             summary="FR-37 Xếp lịch sản xuất cho một Technical Staff (robot tuỳ chọn, phải là robot của người đó)",
             responses={409: {"model": ErrorOut, "description": "SLOT_CONFLICT / ROBOT_UNAVAILABLE / NOT_SCHEDULABLE"},
                        422: {"model": ErrorOut, "description": "OUTSIDE_WORKING_HOURS / ROBOT_NOT_SUITABLE / ROBOT_NOT_ASSIGNED / "
                                                                 "TECHNICIAN_HAS_NO_ROBOT / ..."}})
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


@router.get("/jobs/{job_id}", response_model=ManagerJobDetail,
            summary="Chi tiết job, kèm số bản robot đã viết xong và lần chạy còn mở (để quyết định ghi nhận viết xong thay)")
def job_detail(job_id: int, svc: Svc, session: SessionDep) -> ManagerJobDetail:
    from app.models.order import Order
    from app.services.technician import open_run_info, written_runs
    job = svc.get(job_id)
    order = session.get(Order, job.order_id)
    from app.services.stock import ENDED_UNFINISHED, paper_held, stock_settled
    held = sum(paper_held(session, job.id).values())
    return ManagerJobDetail(**_jobs_out(svc, [job])[0].model_dump(), quantity=order.quantity if order else 1,
                            copies_written=len(written_runs(session, job.id)), open_run=open_run_info(session, job.id),
                            paper_held=held,
                            can_settle_stock=job.status in ENDED_UNFINISHED and held > 0 and not stock_settled(session, job.id))


@router.post("/jobs/{job_id}/stock/settle", response_model=StockSettleOut,
             summary="Quản lý quyết toán giấy của job đã hỏng hoặc đã huỷ: ghi số tờ hỏng, phần còn lại trả về kho (một lần)",
             responses={404: {"model": ErrorOut, "description": "JOB_NOT_FOUND"},
                        409: {"model": ErrorOut, "description": "STOCK_SETTLE_NOT_ALLOWED / STOCK_ALREADY_SETTLED / NOTHING_TO_SETTLE"},
                        422: {"model": ErrorOut, "description": "WASTE_OUT_OF_RANGE"}})
def settle_job_stock(job_id: int, body: StockSettleIn, session: SessionDep, manager: ManagerDep, request: Request) -> StockSettleOut:
    from sqlalchemy import select

    from app.core.errors import AppError
    from app.services.stock import settle_job
    job = session.scalar(select(ProductionJob).where(ProductionJob.id == job_id).with_for_update())
    if job is None:
        raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
    return StockSettleOut(**settle_job(session, job, actor_id=manager.id, waste=body.waste, ip=client_ip(request)))


@router.post("/jobs/{job_id}/finish-override", response_model=JobOut,
             summary="D06 Quản lý ghi nhận job đã viết xong khi máy trạm không báo được lần chạy (bắt buộc lý do, có nhật ký)",
             description=("Bình thường kỹ thuật viên chỉ ghi nhận viết xong được khi job có một lần chạy robot kết thúc DONE "
                          "(`409 RUN_EVIDENCE_REQUIRED`), đủ một lần cho mỗi bản của đơn (`409 COPIES_MISSING`). Endpoint này bỏ qua "
                          "hai điều kiện đó. Job vẫn phải đang WRITING. Một lần chạy còn mở mà không ai thực hiện (máy trạm mất "
                          "kết nối hoặc đang rảnh) được đóng luôn với kết quả UNKNOWN; nếu máy trạm còn báo robot đang chạy thì "
                          "vẫn `409 RUN_OPEN`. Ghi `JOB_FINISH_OVERRIDE` vào nhật ký dưới tên Quản lý."),
             responses={409: {"model": ErrorOut, "description": "JOB_STATE_CONFLICT / RUN_OPEN"},
                        422: {"model": ErrorOut, "description": "REASON_REQUIRED"}})
def finish_override(job_id: int, body: FinishOverrideIn, svc: Svc, session: SessionDep, manager: ManagerDep,
                    request: Request, store: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> JobOut:
    from app.services.technician import finish_by_manager
    finish_by_manager(session, manager, job_id, body.reason, client_ip(request), storage=store)
    return _jobs_out(svc, [svc.get(job_id)])[0]


def robot_out(session, robot) -> RobotOut:
    out = RobotOut.model_validate(robot)
    out.technician_id, out.technician_name = robot_owners(session).get(robot.id, (None, None))
    return out


@router.put("/robots/{robot_id}/technician", response_model=RobotOut,
            summary="Giao cố định robot cho một Technical Staff (mỗi robot thuộc tối đa một người; giao lại = chuyển người)",
            responses={404: {"model": ErrorOut, "description": "ROBOT_NOT_FOUND"},
                       409: {"model": ErrorOut, "description": "ROBOT_HAS_ACTIVE_JOBS (người đang giữ còn job trên robot)"},
                       422: {"model": ErrorOut, "description": "INVALID_TECHNICIAN"}})
def assign_robot(robot_id: int, body: RobotAssignIn, svc: Svc) -> RobotOut:
    return robot_out(svc.session, svc.assign_robot(robot_id, body.technician_id))


@router.delete("/robots/{robot_id}/technician", response_model=RobotOut, summary="Thu hồi robot khỏi Technical Staff đang giữ",
               responses={409: {"model": ErrorOut, "description": "ROBOT_HAS_ACTIVE_JOBS"}})
def unassign_robot(robot_id: int, svc: Svc) -> RobotOut:
    return robot_out(svc.session, svc.unassign_robot(robot_id))


@router.get("/technicians", response_model=list[TechnicianOut],
            summary="Technical Staff đang hoạt động + số job đang giữ + robot được giao")
def technicians(svc: Svc) -> list[TechnicianOut]:
    return [TechnicianOut(**t) for t in svc.technicians()]


@router.get("/jobs/{job_id}/events", response_model=Page[JobEventOut],
            summary="Nhật ký sự kiện của job (tải gói, hiệu chuẩn, mô phỏng, tiến độ, dừng khẩn cấp, sự cố)")
def job_events(job_id: int, svc: Svc, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500)) -> Page[JobEventOut]:
    rows, total = svc.events(job_id, page, page_size)
    return Page(items=[JobEventOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/incidents", response_model=Page[IncidentOut], summary="FR-48 Sự cố robot/vật tư (mới nhất trước); lọc chưa xử lý, theo robot")
def incidents(svc: Svc, resolved: bool | None = None, robot_id: int | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[IncidentOut]:
    rows, total = svc.incident_page(resolved=resolved, robot_id=robot_id, page=page, page_size=page_size)
    return Page(items=[IncidentOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentOut, summary="Đóng sự cố đã xử lý (trạng thái robot đổi qua API robot)")
def resolve_incident(incident_id: int, body: ResolveIncidentIn, svc: Svc) -> IncidentOut:
    return IncidentOut.model_validate(svc.resolve_incident(incident_id, body.note))
