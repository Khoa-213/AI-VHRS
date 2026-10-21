"""Technical Staff: the workshop floor (UC-31..39, FR-43..49, BR-17, BR-19, BR-20).

Only TECHNICAL_STAFF, and only for jobs assigned to them (another technician's job answers 404). The workstation
(Flutter app + Robot Agent) drives the robot itself; these endpoints hold the job's package, preparation, calibration,
simulation result, progress, safety events, end of writing and incidents. Nothing here moves a robot yet: connecting the robot is deferred until the project owner asks for it.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import (CalibrationIn, CalibrationOut, IncidentIn, IncidentOut, JobEventIn, JobEventOut,
                                 JobOut, JobPackageOut, SimulationIn, TechJobDetail)
from app.api.photo_schemas import PhotoOut, PhotoQcIn, PhotoRegisterIn, PhotoUploadIn, PhotoUploadOut, QcFailIn
from app.api.schemas import ErrorOut, Page
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.ops import JobStatus, ProductionJob
from app.services.product_photos import ProductPhotoService
from app.services.scheduling import job_labels
from app.services.technician import TechnicianJobService

router = APIRouter(prefix="/technician", tags=["Technician"])
TechDep = Annotated[Account, Depends(require_roles(RoleCode.TECHNICAL_STAFF.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]

CONFLICT = {409: {"model": ErrorOut, "description": "JOB_STATE_CONFLICT / JOB_NOT_ACTIVE / ORDER_NOT_ACTIVE / STATE_CONFLICT"}}


def _svc(session: SessionDep, tech: TechDep, request: Request, storage: StorageDep) -> TechnicianJobService:
    return TechnicianJobService(session, tech, storage, client_ip(request))


Svc = Annotated[TechnicianJobService, Depends(_svc)]


def _photo_svc(session: SessionDep, tech: TechDep, request: Request, storage: StorageDep) -> ProductPhotoService:
    return ProductPhotoService(session, tech, storage, client_ip(request))


PhotoSvc = Annotated[ProductPhotoService, Depends(_photo_svc)]


def _jobs_out(svc: TechnicianJobService, jobs: list[ProductionJob]) -> list[JobOut]:
    names = job_labels(svc.session, jobs)
    out = []
    for j in jobs:
        row = JobOut.model_validate(j)
        row.order_code, row.robot_code = names["order"].get(j.order_id, ""), names["robot"].get(j.robot_id, "")
        row.technician_name = names["tech"].get(j.technician_id, "")
        out.append(row)
    return out


@router.get("/jobs", response_model=Page[JobOut], summary="UC-31 Job được giao cho tôi (lọc theo trạng thái, khoảng ngày)")
def jobs(svc: Svc, status_: Annotated[list[JobStatus] | None, Query(alias="status")] = None,
         start: Annotated[datetime | None, Query(alias="from")] = None,
         end: Annotated[datetime | None, Query(alias="to")] = None,
         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[JobOut]:
    rows, total = svc.search(statuses=status_, start=start, end=end, page=page, page_size=page_size)
    return Page(items=_jobs_out(svc, rows), total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=TechJobDetail,
            summary="Chi tiết job: đơn, vật tư, hiệu chuẩn hiện hành, sự cố, `can_start`")
def job_detail(job_id: int, svc: Svc) -> TechJobDetail:
    job = svc.get(job_id)
    extra = svc.detail(job_id)
    base = _jobs_out(svc, [job])[0].model_dump()
    extra["calibration"] = CalibrationOut.model_validate(extra["calibration"]) if extra["calibration"] else None
    extra["incidents"] = [IncidentOut.model_validate(i) for i in extra["incidents"]]
    return TechJobDetail(**base, **extra)


@router.get("/jobs/{job_id}/package", response_model=JobPackageOut,
            summary="UC-32 Tải gói job: liên kết quỹ đạo có chữ ký + SHA-256, hồ sơ bút (BR-20). Ghi sự kiện DOWNLOADED",
            responses={**CONFLICT, 503: {"model": ErrorOut, "description": "STORAGE_NOT_CONFIGURED"}})
def package(job_id: int, svc: Svc) -> JobPackageOut:
    return JobPackageOut(**svc.package(job_id))


@router.post("/jobs/{job_id}/prepare", response_model=JobOut,
             summary="UC-33 Bắt đầu chuẩn bị robot (SCHEDULED → PREPARING; cần đã tải gói job)", responses=CONFLICT)
def prepare(job_id: int, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.prepare(job_id)])[0]


@router.post("/jobs/{job_id}/calibration", response_model=CalibrationOut, status_code=status.HTTP_201_CREATED,
             summary="FR-44 Ghi hiệu chuẩn mặt giấy + lực (checklist, zero lực, điểm dò P0-P2). Bản mới thay bản cũ và xoá kết quả mô phỏng",
             responses=CONFLICT)
def calibration(job_id: int, body: CalibrationIn, svc: Svc) -> CalibrationOut:
    return CalibrationOut.model_validate(svc.calibrate(
        job_id, checklist=body.checklist, force_zero_offset=body.force_zero_offset, probe_points=body.probe_points,
        frame_transform=body.frame_transform, height_map=body.height_map, force_curve=body.force_curve))


@router.post("/jobs/{job_id}/simulation", response_model=JobOut,
             summary="FR-45 Ghi kết quả mô phỏng do máy trạm báo (cần đã hiệu chuẩn). Không chạy được khi chưa đạt",
             responses=CONFLICT)
def simulation(job_id: int, body: SimulationIn, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.record_simulation(job_id, passed=body.passed, errors=body.errors, report=body.report)])[0]


@router.post("/jobs/{job_id}/start", response_model=JobOut,
             summary="UC-35 Bắt đầu viết (PREPARING → WRITING; cần hiệu chuẩn + mô phỏng đạt + hash khớp, MSG14)",
             responses=CONFLICT)
def start(job_id: int, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.start(job_id)])[0]


@router.post("/jobs/{job_id}/events", response_model=JobEventOut, status_code=status.HTTP_201_CREATED,
             summary="UC-36 Máy trạm báo PROGRESS / PAUSE / RESUME / ESTOP / OVER_FORCE / STROKE_LOST / SENSOR_LOST / FORCE_SUMMARY",
             responses=CONFLICT)
def post_event(job_id: int, body: JobEventIn, svc: Svc) -> JobEventOut:
    return JobEventOut.model_validate(svc.record_event(
        job_id, body.event_type, stroke_index=body.stroke_index, progress_pct=body.progress_pct,
        force_summary=body.force_summary, payload=body.payload))


@router.get("/jobs/{job_id}/events", response_model=Page[JobEventOut], summary="Nhật ký sự kiện của job (cũ → mới)")
def events(job_id: int, svc: Svc, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500)) -> Page[JobEventOut]:
    rows, total = svc.event_page(job_id, page, page_size)
    return Page(items=[JobEventOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.post("/jobs/{job_id}/finish", response_model=JobOut,
             summary="UC-39 Viết xong (WRITING → WRITTEN). Trừ tồn kho giấy/bút/mực (FR-41)", responses=CONFLICT)
def finish(job_id: int, svc: Svc) -> JobOut:
    return _jobs_out(svc, [svc.finish(job_id)])[0]


@router.post("/jobs/{job_id}/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED,
             summary="UC-37 Báo sự cố: job → FAILED, đơn về hàng đợi xếp lại; tuỳ chọn đưa robot vào bảo trì/hỏng",
             responses=CONFLICT)
def incident(job_id: int, body: IncidentIn, svc: Svc) -> IncidentOut:
    return IncidentOut.model_validate(svc.report_incident(
        job_id, kind=body.type, description=body.description, robot_status_after=body.robot_status_after))


# ---- UC-38 / FR-49: product photos and QC (Phase 4b) ---------------------------------------------------------------
PHOTO_ERRORS = {**CONFLICT, 422: {"model": ErrorOut, "description": "INVALID_PHOTO / PHOTO_TOO_SMALL / TOO_MANY_PHOTOS / QC_NOTE_REQUIRED"}}


@router.post("/jobs/{job_id}/photos/upload-url", response_model=PhotoUploadOut, status_code=status.HTTP_201_CREATED,
             summary="UC-38 Xin liên kết tải ảnh sản phẩm lên kho (job phải WRITTEN). PUT file vào `upload_url`, rồi đăng ký ảnh",
             responses={**PHOTO_ERRORS, 503: {"model": ErrorOut, "description": "STORAGE_NOT_CONFIGURED"}})
def photo_upload_url(job_id: int, body: PhotoUploadIn, svc: PhotoSvc) -> PhotoUploadOut:
    key, target = svc.request_upload(job_id, body.mime_type, body.size_bytes)
    return PhotoUploadOut(photo_key=key, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@router.post("/jobs/{job_id}/photos", response_model=PhotoOut, status_code=status.HTTP_201_CREATED,
             summary="UC-38 Đăng ký ảnh đã tải lên: server đọc lại file, kiểm tra loại/dung lượng/độ phân giải, ghi loại ảnh (toàn cảnh/cận cảnh) và QC",
             responses={**PHOTO_ERRORS, 409: {"model": ErrorOut, "description": "UPLOAD_NOT_FOUND / JOB_STATE_CONFLICT / PHOTO_REMOVED"}})
def photo_register(job_id: int, body: PhotoRegisterIn, svc: PhotoSvc) -> PhotoOut:
    return PhotoOut(**svc.to_out(svc.register(job_id, body.photo_key, body.kind, body.qc_result, body.qc_note)))


@router.get("/jobs/{job_id}/photos", response_model=list[PhotoOut],
            summary="Ảnh sản phẩm của job kèm liên kết xem có chữ ký và kết quả QC")
def photo_list(job_id: int, svc: PhotoSvc) -> list[PhotoOut]:
    return [PhotoOut(**svc.to_out(p)) for p in svc.list_photos(job_id)]


@router.patch("/jobs/{job_id}/photos/{photo_id}", response_model=PhotoOut,
              summary="UC-38 Đánh dấu QC đạt / không đạt cho một ảnh (FAIL cần ghi chú)", responses=PHOTO_ERRORS)
def photo_qc(job_id: int, photo_id: int, body: PhotoQcIn, svc: PhotoSvc) -> PhotoOut:
    return PhotoOut(**svc.to_out(svc.set_qc(job_id, photo_id, body.qc_result, body.qc_note)))


@router.delete("/jobs/{job_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Xoá một ảnh (xoá mềm) trước khi nộp ảnh", responses=CONFLICT)
def photo_remove(job_id: int, photo_id: int, svc: PhotoSvc) -> Response:
    svc.remove(job_id, photo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jobs/{job_id}/photos/submit", response_model=JobOut,
             summary="UC-38/39 Nộp ảnh: cần ≥ 2 ảnh (toàn cảnh + cận cảnh), mọi ảnh QC đạt (BR-21). Job → PHOTO_UPLOADED, đơn → AWAITING_ACCEPTANCE",
             responses={**CONFLICT, 409: {"model": ErrorOut, "description": "PHOTO_REQUIREMENTS_NOT_MET / JOB_STATE_CONFLICT / STATE_CONFLICT"}})
def photo_submit(job_id: int, svc: PhotoSvc) -> JobOut:
    return _jobs_out(svc, [svc.submit(job_id)])[0]


@router.post("/jobs/{job_id}/qc-fail", response_model=JobOut,
             summary="UC-38 Sản phẩm không đạt QC: job → REWRITE_REQUIRED, đơn về hàng đợi xếp lịch (không tính lượt viết lại miễn phí của khách)",
             responses=PHOTO_ERRORS)
def qc_fail(job_id: int, body: QcFailIn, svc: PhotoSvc) -> JobOut:
    return _jobs_out(svc, [svc.qc_fail(job_id, body.note)])[0]
