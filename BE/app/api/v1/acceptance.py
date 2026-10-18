"""UC-18, UC-20 (FR-28, BR-13): the customer looks at the photos of the written product, accepts it or asks for a rewrite.

CUSTOMER only, own orders only (another customer's order answers 404). The auto-acceptance deadline is evaluated here,
when the customer reads or acts on the order (see services/acceptance.py).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.order_schemas import OrderOut
from app.api.photo_schemas import CustomerPhotoOut, ProductPhotosOut, RewriteIn
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.services.acceptance import AcceptanceService

router = APIRouter(tags=["Acceptance"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
ACCEPT_ERRORS = {409: {"model": ErrorOut, "description": "ORDER_NOT_AWAITING_ACCEPTANCE / ACCEPTANCE_CLOSED / REWRITE_LIMIT_REACHED / STATE_CONFLICT"}}


def _svc(session: SessionDep, customer: CustomerDep, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> AcceptanceService:
    return AcceptanceService(session, customer, storage, client_ip(request))


Svc = Annotated[AcceptanceService, Depends(_svc)]


@router.get("/orders/{order_id}/product-photos", response_model=ProductPhotosOut,
            summary="UC-18 Xem ảnh sản phẩm thật (chỉ ảnh QC đạt), phác thảo đối chiếu, hạn tự nghiệm thu",
            responses={409: {"model": ErrorOut, "description": "PHOTOS_NOT_AVAILABLE"}})
def product_photos(order_id: int, svc: Svc) -> ProductPhotosOut:
    data = svc.view(order_id)
    order = data.pop("order")
    return ProductPhotosOut(order_status=order.order_status.value, free_rewrite_used=order.free_rewrite_used,
                            photos=[CustomerPhotoOut(**p) for p in data.pop("photos")], **data)


@router.post("/orders/{order_id}/accept", response_model=OrderOut,
             summary="UC-18 / FR-28 Nghiệm thu sản phẩm (AWAITING_ACCEPTANCE → AWAITING_FINAL_PAYMENT)", responses=ACCEPT_ERRORS)
def accept(order_id: int, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.accept(order_id))


@router.post("/orders/{order_id}/rewrite", response_model=OrderOut,
             summary="UC-18 / BR-13 Yêu cầu viết lại miễn phí (1 lần): đơn về CONFIRMED, vào hàng đợi xếp lịch. Lần 2 trả REWRITE_LIMIT_REACHED",
             responses={**ACCEPT_ERRORS, 422: {"model": ErrorOut, "description": "INVALID_REWRITE_REASON / REWRITE_NOTE_REQUIRED"}})
def request_rewrite(order_id: int, body: RewriteIn, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.request_rewrite(order_id, body.reason_code, body.note))
