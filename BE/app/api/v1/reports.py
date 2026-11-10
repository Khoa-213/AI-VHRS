"""Manager dashboard and reports (Phase 5b: UC-45, UC-46, FR-50). Manager only."""
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import SessionDep, require_roles
from app.api.schemas import ErrorOut
from app.models.account import Account, RoleCode
from app.services.reports import ReportService

router = APIRouter(prefix="/manager", tags=["Reports"])
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
Group = Literal["day", "week", "month"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"


@router.get("/dashboard", response_model=dict[str, Any], summary="UC-45 Dashboard sản xuất")
def dashboard(_: ManagerDep, session: SessionDep) -> dict[str, Any]:
    return ReportService(session).dashboard()


@router.get("/reports", response_model=dict[str, Any], responses={422: {"model": ErrorOut}},
            summary="UC-46 · FR-50 Báo cáo: doanh thu, sản lượng, tỷ lệ từ chối / viết lại, robot, trễ ETA")
def report(_: ManagerDep, session: SessionDep, from_: Annotated[date | None, Query(alias="from")] = None,
           to: date | None = None, group: Group = "day") -> dict[str, Any]:
    return ReportService(session).report(from_, to, group)


@router.get("/reports/export", responses={200: {"content": {XLSX: {}, PDF: {}}}, 422: {"model": ErrorOut}},
            summary="FR-50 Xuất báo cáo ra Excel (mặc định) hoặc PDF (`format=pdf`)")
def export(_: ManagerDep, session: SessionDep, from_: Annotated[date | None, Query(alias="from")] = None,
           to: date | None = None, group: Group = "day", format: Literal["xlsx", "pdf"] = "xlsx") -> Response:
    svc = ReportService(session)
    data, name = svc.export_pdf(from_, to, group) if format == "pdf" else svc.export_xlsx(from_, to, group)
    return Response(content=data, media_type=PDF if format == "pdf" else XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
