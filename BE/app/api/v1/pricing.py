"""FR-10, FR-29 (UC-12): instant estimate. Never asks the customer for a character count."""
import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_roles
from app.api.order_schemas import EstimateIn, EstimateOut
from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.models.order import OrderInput, OrderInputKind
from app.repositories.orders import OrderRepository
from app.services.orders import PricingService

router = APIRouter(prefix="/pricing", tags=["Pricing"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


@router.post("/estimate", response_model=EstimateOut, summary="UC-12 Giá ước tính tức thời (chưa gồm phí ship)")
def estimate(body: EstimateIn, customer: CustomerDep, session: SessionDep) -> EstimateOut:
    inputs: list[OrderInput] = []
    if body.order_id is not None:
        repo = OrderRepository(session)
        order = repo.get_owned(body.order_id, customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        inputs = repo.inputs(order.id)
    if body.text:
        inputs = [r for r in inputs if r.kind != OrderInputKind.TEXT_CONTENT]
        inputs.append(OrderInput(kind=OrderInputKind.TEXT_CONTENT,
                                 text_content=unicodedata.normalize("NFC", body.text)))
    est = PricingService(session).estimate(
        order_type=body.order_type, quantity=body.quantity, paper_id=body.paper_type_id, pen_id=body.pen_type_id,
        ink_id=body.ink_color_id, inputs=inputs)
    return EstimateOut(chars_min=est.chars_min, chars_max=est.chars_max, price_min=est.price_min,
                       price_max=est.price_max, min_deposit_pct=est.min_deposit_pct, basis=est.basis,  # type: ignore[arg-type]
                       materials_priced=est.materials_priced)
