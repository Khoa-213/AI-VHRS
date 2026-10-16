"""Manager-only workshop operations: UC-47 (assign Staff) and UC-44 (approve price adjustments beyond +/-15%)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import Page
from app.api.staff_schemas import AssignIn, QuotationOut, ReasonIn, StaffBrief, WorkshopOrderRow
from app.api.v1.orders import optional_storage
from app.api.v1.workshop import quotation_out
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.services.quotations import QuotationService
from app.services.staff_orders import StaffOrderService

router = APIRouter(prefix="/manager", tags=["Manager"])
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]


@router.get("/staff", response_model=list[StaffBrief], summary="Danh sách Staff đang hoạt động + số đơn đang xử lý")
def staff_directory(session: SessionDep, manager: ManagerDep, storage: StorageDep) -> list[StaffBrief]:
    return [StaffBrief(**s) for s in StaffOrderService(session, manager, storage).staff_directory()]


@router.put("/orders/{order_id}/assignment", response_model=WorkshopOrderRow,
            summary="UC-47 Phân công / đổi Staff phụ trách đơn")
def assign(order_id: int, body: AssignIn, session: SessionDep, manager: ManagerDep, request: Request,
           storage: StorageDep) -> WorkshopOrderRow:
    order = StaffOrderService(session, manager, storage, client_ip(request)).assign(order_id, body.staff_id)
    return WorkshopOrderRow.model_validate(order)


@router.get("/quotations/pending-approval", response_model=Page[QuotationOut],
            summary="Báo giá có điều chỉnh vượt ngưỡng đang chờ duyệt")
def pending(session: SessionDep, manager: ManagerDep, storage: StorageDep, page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100)) -> Page[QuotationOut]:
    rows, total = QuotationService(session, manager, storage).pending_approvals(page, page_size)
    return Page(items=[quotation_out(q) for q in rows], total=total, page=page, page_size=page_size)


@router.post("/quotations/{quotation_id}/approve-adjustment", response_model=QuotationOut,
             summary="Duyệt điều chỉnh giá vượt ngưỡng (BR-09)")
def approve(quotation_id: int, session: SessionDep, manager: ManagerDep, request: Request,
            storage: StorageDep) -> QuotationOut:
    return quotation_out(QuotationService(session, manager, storage, client_ip(request)).approve_adjustment(quotation_id))


@router.post("/quotations/{quotation_id}/reject-adjustment", response_model=QuotationOut,
             summary="Từ chối điều chỉnh giá: báo giá quay về giá Pricing Engine")
def reject(quotation_id: int, body: ReasonIn, session: SessionDep, manager: ManagerDep, request: Request,
           storage: StorageDep) -> QuotationOut:
    return quotation_out(QuotationService(session, manager, storage, client_ip(request))
                         .reject_adjustment(quotation_id, body.reason))
