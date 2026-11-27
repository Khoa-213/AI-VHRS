"""Manager-only workshop operations: UC-47 (assign Staff) and UC-44 (approve price adjustments beyond +/-15%)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import CloseOrderIn, CloseOrderOut
from app.api.schemas import ErrorOut, Page
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


@router.post("/orders/{order_id}/close", response_model=CloseOrderOut,
             summary="D08 Quản lý đóng một đơn kẹt sau sản xuất (không thanh toán cuối, không đến nhận, giao không được), kèm số tiền hoàn",
             description=("Đơn ở `AWAITING_FINAL_PAYMENT`, `READY_TO_DELIVER`, hoặc `DELIVERING` mà vận đơn mới nhất đã `FAILED` / "
                          "`RETURNED` / `CANCELLED` → `CANCELLED`. `refund_amount` từ 0 tới số khách đã trả mà chưa hoàn "
                          "(`422 REFUND_AMOUNT_INVALID` kèm `refundable`); lớn hơn 0 thì mở một yêu cầu hoàn tiền PENDING để Staff "
                          "chuyển khoản và xác nhận như mọi khoản hoàn khác. Link thanh toán đang mở bị đóng. Khách nhận thông báo."),
             responses={404: {"model": ErrorOut, "description": "ORDER_NOT_FOUND"},
                        409: {"model": ErrorOut, "description": "ORDER_CLOSE_UNSUPPORTED / SHIPMENT_IN_TRANSIT"},
                        422: {"model": ErrorOut, "description": "REASON_REQUIRED / REFUND_AMOUNT_INVALID"}})
def close_order(order_id: int, body: CloseOrderIn, session: SessionDep, manager: ManagerDep, request: Request) -> CloseOrderOut:
    from app.services import order_exits as ox
    before = ox.refundable(session, order_id)
    order, refund = ox.close_by_manager(session, manager, order_id, body.reason, body.refund_amount, client_ip(request))
    return CloseOrderOut(order_id=order.id, order_status=order.order_status.value, refundable_before=before,
                         refund_id=refund.id if refund else None, refund_amount=refund.amount if refund else 0)
