"""Deposit payment (FR-17..20, NFR-06). The only gateway today is the MOCK adapter: nothing here moves real money.

Flow: customer approves the quote -> POST /orders/{id}/payments/deposit (PENDING + mock transaction) ->
the gateway reports the result to POST /webhooks/payments/{gateway} (signed, idempotent). With the mock gateway the
customer presses pay / fail on POST /payments/{id}/mock-checkout, which posts that same signed webhook.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import MockCheckoutIn, PaymentOut, StartDepositIn, WebhookResult
from app.api.schemas import ErrorOut
from app.core.ratelimit import rate_limit
from app.integrations.payment_gateway import SIGNATURE_HEADER, get_gateway
from app.models.account import Account, RoleCode
from app.models.ops import Payment, PaymentGateway, PaymentStatus
from app.services.payments import PaymentService

router = APIRouter(tags=["Payments"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


def payment_out(p: Payment) -> PaymentOut:
    payload = p.gateway_payload or {}
    out = PaymentOut.model_validate(p)
    out.mode = payload.get("mode", get_gateway().mode)
    out.needs_refund = bool(payload.get("needs_refund"))
    if p.status == PaymentStatus.PENDING:
        out.checkout_path = get_gateway().checkout_path(p.id)
    return out


@router.get("/orders/{order_id}/payments", response_model=list[PaymentOut],
            summary="Các giao dịch thanh toán của đơn (chỉ chủ đơn)")
def list_payments(order_id: int, session: SessionDep, customer: CustomerDep) -> list[PaymentOut]:
    return [payment_out(p) for p in PaymentService(session, customer).list_for_order(order_id)]


@router.post("/orders/{order_id}/payments/deposit", response_model=PaymentOut, status_code=status.HTTP_201_CREATED,
             summary="FR-17 Bắt đầu đặt cọc (AWAITING_DEPOSIT). Giao dịch MOCK, không chuyển tiền thật",
             responses={409: {"model": ErrorOut, "description": "DEPOSIT_NOT_EXPECTED / DEPOSIT_ALREADY_PAID"}})
def start_deposit(order_id: int, body: StartDepositIn, session: SessionDep, customer: CustomerDep,
                  request: Request) -> PaymentOut:
    return payment_out(PaymentService(session, customer, client_ip(request)).start_deposit(order_id, body.gateway))


@router.post("/payments/{payment_id}/mock-checkout", response_model=WebhookResult,
             summary="Cổng thanh toán MOCK: bấm thanh toán thành công / thất bại (phát webhook có chữ ký)")
def mock_checkout(payment_id: int, body: MockCheckoutIn, session: SessionDep, customer: CustomerDep,
                  request: Request) -> WebhookResult:
    return WebhookResult(**PaymentService(session, customer, client_ip(request)).mock_checkout(payment_id, body.result))


@router.post("/webhooks/payments/{gateway}", response_model=WebhookResult,
             dependencies=[Depends(rate_limit("payment_webhook", 120, 60))],
             summary="Webhook của cổng thanh toán (xác thực HMAC, idempotent theo txn_id)",
             description="Body JSON do cổng ký; header `X-Signature` = HMAC-SHA256(body). Gửi lại cùng giao dịch "
                         "trả `ALREADY_PROCESSED` và không đổi dữ liệu.",
             responses={401: {"model": ErrorOut, "description": "INVALID_SIGNATURE"},
                        422: {"model": ErrorOut, "description": "PAYMENT_MISMATCH / INVALID_WEBHOOK"}})
async def payment_webhook(gateway: PaymentGateway, request: Request, session: SessionDep,
                          x_signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None) -> WebhookResult:
    body = await request.body()
    return WebhookResult(**PaymentService(session, None, client_ip(request)).handle_webhook(gateway, body, x_signature))
