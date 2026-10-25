"""Service G routes: evaluate a product photo against the approved sketch (Technical Staff), read results (Technical Staff, Manager)."""
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.services.quality_service import QualityService

technician_router = APIRouter(prefix="/technician", tags=["Quality evaluation (Service G)"])
manager_router = APIRouter(prefix="/manager", tags=["Quality evaluation (Service G)"])
TechDep = Annotated[Account, Depends(require_roles(RoleCode.TECHNICAL_STAFF.value))]
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]


class EvaluateIn(BaseModel):
    page: int = Field(default=1, ge=1, le=10, description="Trang của phác thảo mà ảnh này chụp (mặc định trang 1).")


class QualityOut(BaseModel):
    id: int
    photo_id: int
    job_id: int
    page: int
    method: str
    verdict: str = Field(description="PASS | NEEDS_REVIEW | FAIL: ngưỡng mặc định CHƯA kiểm chứng (xem metrics.thresholds.source).")
    metrics: dict[str, Any]
    overlay_url: str | None = Field(description="Ảnh chồng: xanh dương = nét đo được, xanh lá = nét có đủ, đỏ = nét kế hoạch bị thiếu.")
    created_at: datetime
    advisory: str


def _tech(session: SessionDep, tech: TechDep, storage: StorageDep, request: Request) -> QualityService:
    return QualityService(session, tech, storage, client_ip(request))


def _mgr(session: SessionDep, manager: ManagerDep, storage: StorageDep, request: Request) -> QualityService:
    return QualityService(session, manager, storage, client_ip(request))


Tech = Annotated[QualityService, Depends(_tech)]
Mgr = Annotated[QualityService, Depends(_mgr)]


@technician_router.post("/jobs/{job_id}/photos/{photo_id}/evaluate", response_model=QualityOut, status_code=status.HTTP_201_CREATED,
                        summary="Service G: so ảnh chụp bản viết với phác thảo đã duyệt (mm, độ phủ, Chamfer, Hausdorff, ảnh chồng)",
                        responses={422: {"description": "PAPER_NOT_FOUND / NO_INK / NO_MATCH / PHOTO_UNREADABLE: ảnh không đo được, không đoán"}})
def evaluate(job_id: int, photo_id: int, body: EvaluateIn, svc: Tech) -> QualityOut:
    return QualityOut(**svc.to_out(svc.evaluate(job_id, photo_id, body.page)))


@technician_router.get("/jobs/{job_id}/quality", response_model=list[QualityOut], summary="Các lần đánh giá chất lượng của job (mới → cũ)")
def tech_list(job_id: int, svc: Tech) -> list[QualityOut]:
    return [QualityOut(**svc.to_out(r)) for r in svc.list(job_id)]


@manager_router.get("/jobs/{job_id}/quality", response_model=list[QualityOut], summary="Quản lý: các lần đánh giá chất lượng của job")
def mgr_list(job_id: int, svc: Mgr) -> list[QualityOut]:
    return [QualityOut(**svc.to_out(r)) for r in svc.list(job_id)]
