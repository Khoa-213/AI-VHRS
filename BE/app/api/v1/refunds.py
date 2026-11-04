"""Cancelling after the deposit and refunds (Phase 4d-1: FR-19, FR-20, UC-21, UC-28; BR-14, BR-16).

Customer: GET /orders/{id}/cancel-preview shows what a cancel would refund; POST /orders/{id}/cancel (orders.py) does it;
PUT /orders/{id}/refunds/{refund_id}/account says where to send the money. Refund rows appear in GET /orders/{id}/payments.
Workshop: Staff (and Manager, read only) see the refunds to pay and the money flagged `needs_refund`; the Staff assigned to the
order cancels it on the workshop's initiative (100 % refund), opens a refund for flagged money and confirms each transfer.
No money moves through the gateways here: Staff pays out by hand and confirms with the reference.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import (CancelPreviewOut, OrphanOut, OrphanRefundIn, PaymentOut, RefundAccount, RefundConfirmIn,
                                 RefundListOut, RefundOut, WorkshopCancelIn)
from app.api.order_schemas import OrderOut
from app.api.schemas import ErrorOut
from app.api.v1.payments import payment_out
from app.domain.refund_rules import Initiator
from app.models.account import Account, RoleCode
from app.models.ops import Payment, PaymentStatus
from app.models.order import Order
from app.services.refunds import CancelPreview, CancellationService, RefundService, set_refund_account

router = APIRouter(tags=["Refunds"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
WorkshopDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]
StaffDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value))]
_ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}}


def _preview_out(p: CancelPreview) -> CancelPreviewOut:
    d = p.decision
    return CancelPreviewOut(
        order_id=p.order.id, order_status=p.order.order_status.value, production_status=p.order.production_status.value,
        allowed=d.allowed, rule=d.rule.value if d.rule else None, error_code=d.error_code, message=d.message, paid=p.paid,
        refund_amount=d.refund_amount, deduction=d.deduction, setup_fee=p.setup_fee,
        eta_postponed_days=p.eta_postponed_days, threshold_days=p.threshold_days, account_required=p.account_required)


def _refund_out(p: Payment, order: Order) -> RefundOut:
    info = payment_out(p, masked=False).refund
    assert info is not None
    payload = p.gateway_payload or {}
    return RefundOut(id=p.id, order_id=order.id, order_code=order.code, amount=p.amount, gateway=p.gateway, status=p.status,
                     mode=payload.get("mode", "MOCK"), created_at=p.created_at, paid_at=p.paid_at, refund=info)


# ---------------------------------------------------------------- customer
@router.get("/orders/{order_id}/cancel-preview", response_model=CancelPreviewOut, responses=_ERR,
            summary="UC-21 · BR-14/16 Xem trước khi huỷ: có huỷ được không, hoàn bao nhiêu, có cần tài khoản nhận tiền")
def customer_preview(order_id: int, session: SessionDep, customer: CustomerDep) -> CancelPreviewOut:
    return _preview_out(CancellationService(session, customer, Initiator.CUSTOMER).preview(order_id))


@router.put("/orders/{order_id}/refunds/{refund_id}/account", response_model=PaymentOut, responses=_ERR,
            summary="FR-19 Khách nhập tài khoản ngân hàng nhận hoàn tiền (khi khoản hoàn còn PENDING)")
def customer_refund_account(order_id: int, refund_id: int, body: RefundAccount, session: SessionDep,
                            customer: CustomerDep, request: Request) -> PaymentOut:
    return payment_out(set_refund_account(session, customer, order_id, refund_id, body.model_dump(), client_ip(request)))


# ---------------------------------------------------------------- workshop
@router.get("/workshop/orders/{order_id}/cancel-preview", response_model=CancelPreviewOut, responses=_ERR,
            summary="FR-19 Xưởng xem trước khi huỷ đơn đã cọc (xưởng huỷ = hoàn 100%)")
def workshop_preview(order_id: int, session: SessionDep, actor: WorkshopDep) -> CancelPreviewOut:
    return _preview_out(CancellationService(session, actor, Initiator.WORKSHOP).preview(order_id))


@router.post("/workshop/orders/{order_id}/cancel", response_model=OrderOut, responses=_ERR,
             summary="FR-19 Staff được giao đơn huỷ đơn đã cọc vì xưởng không làm được: hoàn 100% (yêu cầu hoàn PENDING)")
def workshop_cancel(order_id: int, body: WorkshopCancelIn, session: SessionDep, staff: StaffDep,
                    request: Request) -> OrderOut:
    order, _ = CancellationService(session, staff, Initiator.WORKSHOP, client_ip(request)).cancel(order_id, body.reason)
    return OrderOut.model_validate(order)


@router.get("/workshop/refunds", response_model=RefundListOut,
            summary="UC-28 · FR-20 Danh sách cần hoàn tiền (Staff: đơn của mình; Manager: tất cả, chỉ đọc)")
def list_refunds(session: SessionDep, actor: WorkshopDep,
                 status: Annotated[Literal["PENDING", "SUCCESS"] | None, Query(alias="status")] = "PENDING") -> RefundListOut:
    svc = RefundService(session, actor)
    refunds = [_refund_out(p, o) for p, o in svc.list_refunds(PaymentStatus(status) if status else None)]
    orphans = [OrphanOut(payment_id=i.payment.id, order_id=i.order.id, order_code=i.order.code,
                         order_status=i.order.order_status.value, gateway=i.payment.gateway, types=i.types,
                         received_amount=i.amount, payment_status=i.payment.status) for i in svc.orphans()]
    return RefundListOut(refunds=refunds, orphans=orphans)


@router.post("/workshop/payments/{payment_id}/refund", response_model=RefundOut, status_code=201, responses=_ERR,
             summary="UC-28 Mở yêu cầu hoàn tiền cho khoản tiền về muộn / sai số tiền (needs_refund)")
def refund_orphan(payment_id: int, body: OrphanRefundIn, session: SessionDep, staff: StaffDep,
                  request: Request) -> RefundOut:
    svc = RefundService(session, staff, client_ip(request))
    refund = svc.refund_orphan(payment_id, amount=body.amount, reason=body.reason,
                               refund_account=body.refund_account.model_dump() if body.refund_account else None)
    return _refund_out(refund, svc.orders.get(refund.order_id))


@router.post("/workshop/refunds/{refund_id}/confirm", response_model=RefundOut, responses=_ERR,
             summary="UC-28 Staff xác nhận đã chuyển hoàn tiền (kèm mã tham chiếu): PENDING → SUCCESS")
def confirm_refund(refund_id: int, body: RefundConfirmIn, session: SessionDep, staff: StaffDep,
                   request: Request) -> RefundOut:
    svc = RefundService(session, staff, client_ip(request))
    refund = svc.confirm(refund_id, reference=body.reference, note=body.note,
                         refund_account=body.refund_account.model_dump() if body.refund_account else None)
    return _refund_out(refund, svc.orders.get(refund.order_id))

