"""FR-18, FR-21, FR-23 (Phase 4c-1): how the customer receives the product and the final payment.

CUSTOMER only, own orders only (another customer's order answers 404). Payments are MOCK until a real gateway exists:
the result arrives through the signed webhook like the deposit's (see payments.py). The Staff's hand-over is in workshop.py.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.delivery_schemas import (DeliveryIn, DeliveryOptionOut, DeliveryQuoteOut, FinalPaymentIn, FinalPaymentOut)
from app.api.deps import SessionDep, client_ip, require_roles
from app.api.order_schemas import OrderOut
from app.api.schemas import ErrorOut
from app.api.v1.payments import payment_out
from app.models.account import Account, RoleCode
from app.services.delivery import DeliveryService

router = APIRouter(tags=["Delivery"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
STATE = {409: {"model": ErrorOut, "description": "FINAL_PAYMENT_NOT_EXPECTED / FINAL_ALREADY_PAID / DELIVERY_NOT_CHOSEN"}}


def _svc(session: SessionDep, customer: CustomerDep, request: Request) -> DeliveryService:
    return DeliveryService(session, customer, client_ip(request))


Svc = Annotated[DeliveryService, Depends(_svc)]


@router.get("/orders/{order_id}/delivery-quote", response_model=DeliveryQuoteOut,
            summary="FR-21 Phí nhận hàng của hai cách (giao hàng / nhận tại xưởng) và số tiền phải trả một lần (G − D) + phí ship",
            description="Phí lấy từ **bảng phí dự phòng** (`is_fallback_fee = true`); API hãng vận chuyển chưa được nối (Phase 4c-2).",
            responses={**STATE, 503: {"model": ErrorOut, "description": "SHIPPING_FEE_UNAVAILABLE"}})
def quote(order_id: int, svc: Svc) -> DeliveryQuoteOut:
    data = svc.quote(order_id)
    data["options"] = {k: DeliveryOptionOut(**v) for k, v in data["options"].items()}
    return DeliveryQuoteOut(**data)


@router.put("/orders/{order_id}/delivery", response_model=OrderOut,
            summary="FR-21/23 Chọn giao hàng (kèm địa chỉ) hoặc nhận tại xưởng (kèm khung giờ hẹn + SĐT). Đổi lựa chọn sẽ huỷ giao dịch thanh toán cuối đang mở",
            responses={**STATE, 422: {"model": ErrorOut, "description": "INVALID_ADDRESS / INVALID_SLOT / SLOT_IN_PAST / OUTSIDE_WORKING_HOURS / ..."}})
def choose(order_id: int, body: DeliveryIn, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.choose(
        order_id, body.method, address=body.address.model_dump() if body.address else None,
        slot_start=body.pickup_slot_start, slot_end=body.pickup_slot_end, contact_phone=body.contact_phone,
        receiver=body.receiver))


@router.post("/orders/{order_id}/payments/final", response_model=FinalPaymentOut, status_code=status.HTTP_201_CREATED,
             summary="FR-18 Thanh toán một lần (G − D) + phí ship: ghi 2 dòng FINAL + SHIPPING (nhận tại xưởng: chỉ FINAL). Giao dịch MOCK",
             description="Thanh toán thành công (webhook) → đơn `READY_TO_DELIVER`. Nếu không còn gì phải trả (cọc 100% + nhận tại xưởng) "
                         "thì `payment_required = false` và đơn sang `READY_TO_DELIVER` ngay.",
             responses=STATE)
def start_final(order_id: int, body: FinalPaymentIn, svc: Svc) -> FinalPaymentOut:
    rows, due, order = svc.start_final_payment(order_id, body.gateway)
    return FinalPaymentOut(payment_required=bool(rows), total_due=due.total, order_status=order.order_status.value,
                           payments=[payment_out(p) for p in rows])


@router.post("/orders/{order_id}/receipt", response_model=OrderOut,
             summary="UC-20 Xác nhận đã nhận hàng (chỉ ghi `received_confirmed_at`, không đổi trạng thái đơn)",
             responses={409: {"model": ErrorOut, "description": "ORDER_NOT_DELIVERED / RECEIPT_ALREADY_CONFIRMED"}})
def confirm_receipt(order_id: int, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.confirm_receipt(order_id))
