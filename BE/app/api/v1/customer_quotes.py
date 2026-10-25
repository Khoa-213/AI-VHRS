"""Customer side of the quotation: privacy consent (FR-52, BR-25) and viewing / questioning the quote (UC-15).

The sketch and the quote are hidden until the customer accepts the current privacy policy. Approving the
quote moves the order to AWAITING_DEPOSIT; the deposit itself is in payments.py.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.order_schemas import OrderOut
from app.api.schemas import ErrorOut
from app.api.ops_schemas import ApproveQuotationIn
from app.api.staff_schemas import (ChangeRequestIn, PrivacyDecisionIn, PrivacyPolicyOut, QuotationCustomerOut,
                                   SketchForCustomer)
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.repositories.catalog import CatalogRepository
from app.services.payments import QuotationApprovalService
from app.services.quotations import CustomerQuoteService, current_privacy_policy, option_summaries

router = APIRouter(tags=["Quotations"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


def _svc(session: SessionDep, customer: CustomerDep, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> CustomerQuoteService:
    return CustomerQuoteService(session, customer, storage, client_ip(request))


Svc = Annotated[CustomerQuoteService, Depends(_svc)]


@router.get("/privacy-policy", response_model=PrivacyPolicyOut, summary="Chính sách riêng tư hiện hành (không cần đăng nhập)")
def privacy_policy(session: SessionDep) -> PrivacyPolicyOut:
    return PrivacyPolicyOut(**{k: v for k, v in current_privacy_policy(CatalogRepository(session)).items()
                               if k in PrivacyPolicyOut.model_fields})


@router.post("/orders/{order_id}/privacy", response_model=OrderOut,
             summary="FR-52 Chấp nhận / từ chối chính sách riêng tư (AWAITING_PRIVACY → QUOTED hoặc CANCELLED)")
def decide_privacy(order_id: int, body: PrivacyDecisionIn, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.decide_privacy(order_id, body.accept))


@router.get("/orders/{order_id}/quotation", response_model=QuotationCustomerOut,
            summary="UC-15 Xem phác thảo và báo giá (chỉ sau khi đã đồng ý chính sách riêng tư)",
            responses={403: {"model": ErrorOut, "description": "PRIVACY_REQUIRED"},
                       404: {"model": ErrorOut, "description": "Đơn chưa có báo giá"}})
def view_quotation(order_id: int, svc: Svc) -> QuotationCustomerOut:
    data = svc.view(order_id)
    q, sketch = data["quotation"], data["sketch"]
    pdf, previews = svc.asset_urls(q, sketch)
    return QuotationCustomerOut(
        id=q.id, version=q.version, status=q.status, line_items=q.line_items, options=option_summaries(q),
        chosen_option=q.chosen_option, char_count=q.char_count, quantity=q.quantity, final_total=q.final_total,
        min_deposit_pct=q.min_deposit_pct, eta=q.eta, valid_until=q.valid_until, pdf_url=pdf,
        sketch=SketchForCustomer(version=sketch.version, preview_urls=svc.sketch_image_urls(sketch) or previews,
                                 image_urls=svc.sketch_image_urls(sketch), approach_note=sketch.approach_note,
                                 estimated_writing_sec=sketch.estimated_writing_sec,
                                 similarity_score=sketch.similarity_score) if sketch else None)


@router.post("/orders/{order_id}/quotation/request-changes", response_model=OrderOut,
             summary="UC-15 Yêu cầu chỉnh phác thảo/báo giá (QUOTED → ACCEPTED, Staff lập lại)")
def request_changes(order_id: int, body: ChangeRequestIn, svc: Svc) -> OrderOut:
    return OrderOut.model_validate(svc.request_changes(order_id, body.note))


@router.post("/orders/{order_id}/quotation/approve", response_model=OrderOut,
             summary="FR-15 Duyệt báo giá và chọn mức cọc (QUOTED → AWAITING_DEPOSIT)",
             responses={409: {"model": ErrorOut, "description": "QUOTATION_NOT_OPEN / QUOTATION_EXPIRED"},
                        422: {"model": ErrorOut, "description": "INVALID_DEPOSIT / OPTION_REQUIRED / INVALID_OPTION"}})
def approve_quotation(order_id: int, body: ApproveQuotationIn, session: SessionDep, customer: CustomerDep,
                      request: Request) -> OrderOut:
    return OrderOut.model_validate(QuotationApprovalService(session, customer, client_ip(request))
                                   .approve(order_id, option=body.option, deposit_pct=body.deposit_pct))
