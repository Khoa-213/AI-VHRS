"""Deposit payment (FR-17..20; BR-10, NFR-06) and the customer's approval of the quotation (FR-15, UC-15).

Money only moves through the gateway adapter. The gateway reports the result by a signed webhook; the handler is
idempotent on (gateway, gateway_txn_id) and is the only code that turns a payment into SUCCESS. The mock gateway's
"checkout" simply produces that same signed webhook, so the real code path is exercised.

Order and quotation status changes follow the same rule as elsewhere: plain UPDATEs, judged by the DB trigger.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import payment_rules as rules
from app.integrations import payment_gateway as gw
from app.models.account import Account
from app.models.ops import Payment, PaymentGateway, PaymentStatus, PaymentType
from app.models.order import Order, OrderStatus, ProductionStatus
from app.models.sketch import QuotationStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import PaymentRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import QuotationRepository
from app.services import audit, notifications, quotations

log = logging.getLogger("app")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------
# approving the quotation (QUOTED -> AWAITING_DEPOSIT)
# ---------------------------------------------------------------------------------------------
class QuotationApprovalService:
    def __init__(self, session: Session, customer: Account, ip: str | None = None):
        self.session, self.customer, self.ip = session, customer, ip
        self.orders = OrderRepository(session)
        self.quotes = QuotationRepository(session)
        self.catalog = CatalogRepository(session)

    def approve(self, order_id: int, *, option: int | None, deposit_pct: Decimal | None) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        order = self.orders.get(order.id, lock=True)
        if quotations.expire_and_persist(self.session, order):
            order = self.orders.get(order.id, lock=True)
        q = self.quotes.latest(order.id, (QuotationStatus.SENT,))
        if order.order_status != OrderStatus.QUOTED or q is None:
            raise AppError(409, "QUOTATION_NOT_OPEN", "Không có báo giá nào đang chờ bạn xác nhận.")
        if q.valid_until and q.valid_until < _now():
            raise AppError(409, "QUOTATION_EXPIRED", "Báo giá đã hết hạn.")
        options = q.price_snapshot.get("options", [])
        if len(options) > 1 and option is None:
            raise AppError(422, "OPTION_REQUIRED", "Báo giá có nhiều phương án vật tư; hãy chọn một phương án.")
        chosen = next((o for o in options if o["option"] == (option or 1)), None)
        if chosen is None:
            raise AppError(422, "INVALID_OPTION", "Phương án không tồn tại trong báo giá.")
        total = q.final_total if len(options) == 1 else Decimal(chosen["total"])
        try:
            pct, amount = rules.resolve_deposit(total, q.min_deposit_pct, deposit_pct)
        except rules.DepositError as exc:
            raise AppError(422, "INVALID_DEPOSIT",
                           f"Tiền cọc phải từ {q.min_deposit_pct.normalize():f}% đến 100% tổng giá trị đơn.",
                           {"min_deposit_pct": str(q.min_deposit_pct)}) from exc

        order.paper_type_id, order.pen_type_id, order.ink_color_id = (
            chosen["paper"]["id"], chosen["pen"]["id"], chosen["ink"]["id"])
        order.workshop_suggest_materials = False
        order.total_amount, order.deposit_pct, order.deposit_amount = total, pct, amount
        order.complexity = q.complexity
        if q.eta:
            order.eta = q.eta
        q.status, q.chosen_option, q.customer_responded_at = QuotationStatus.APPROVED, chosen["option"], _now()
        set_actor(self.session, self.customer.id, f"Khách duyệt báo giá v{q.version}")
        order.order_status = OrderStatus.AWAITING_DEPOSIT
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="QUOTATION_APPROVE", entity_type="quotation",
                     entity_id=q.id, new={"order_id": order.id, "option": chosen["option"], "total": str(total),
                                          "deposit_pct": str(pct), "deposit_amount": str(amount)}, ip=self.ip)
        return order


# ---------------------------------------------------------------------------------------------
# deposit payment
# ---------------------------------------------------------------------------------------------
class PaymentService:
    def __init__(self, session: Session, customer: Account | None = None, ip: str | None = None):
        self.session, self.customer, self.ip = session, customer, ip
        self.orders = OrderRepository(session)
        self.payments = PaymentRepository(session)
        self.gateway = gw.get_gateway()

    # ---- customer side ----
    def _own_order(self, order_id: int, *, lock: bool = False) -> Order:
        assert self.customer is not None
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return self.orders.get(order.id, lock=True) if lock else order

    def list_for_order(self, order_id: int) -> list[Payment]:
        return self.payments.for_order(self._own_order(order_id).id)

    def start_deposit(self, order_id: int, gateway: PaymentGateway) -> Payment:
        order = self._own_order(order_id, lock=True)
        if order.order_status != OrderStatus.AWAITING_DEPOSIT or order.deposit_amount is None:
            raise AppError(409, "DEPOSIT_NOT_EXPECTED", "Đơn không ở bước chờ đặt cọc.")
        if self.payments.success(order.id, PaymentType.DEPOSIT) is not None:
            raise AppError(409, "DEPOSIT_ALREADY_PAID", "Đơn đã được đặt cọc.")
        for old in self.payments.pending(order.id, PaymentType.DEPOSIT):
            if old.gateway == gateway and old.amount == order.deposit_amount:
                return old                                              # same intent: reuse the open transaction
            old.status = PaymentStatus.CANCELLED
        self.session.flush()
        row = self.payments.add(Payment(
            order_id=order.id, type=PaymentType.DEPOSIT, amount=order.deposit_amount, deposit_pct=order.deposit_pct,
            gateway=gateway, gateway_txn_id=self.gateway.new_txn_id(gateway.value), status=PaymentStatus.PENDING,
            gateway_payload={"mode": self.gateway.mode}))
        audit.record(self.session, actor_id=self.customer.id if self.customer else None, action="PAYMENT_START",
                     entity_type="payment", entity_id=row.id,
                     new={"order_id": order.id, "amount": str(row.amount), "gateway": gateway.value,
                          "mode": self.gateway.mode}, ip=self.ip)
        return row

    def mock_checkout(self, payment_id: int, result: str) -> dict[str, Any]:
        """The mock gateway's pay / fail button: posts the same signed webhook a real gateway would."""
        assert self.customer is not None
        if result not in {"SUCCESS", "FAILED"}:
            raise AppError(422, "INVALID_RESULT", "Kết quả phải là SUCCESS hoặc FAILED.")
        payment = self.payments.get(payment_id)
        order = self.orders.get_owned(payment.order_id, self.customer.id) if payment else None
        if payment is None or order is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Không tìm thấy giao dịch.")
        if (payment.gateway_payload or {}).get("mode") != self.gateway.mode:
            raise AppError(409, "NOT_A_MOCK_PAYMENT", "Giao dịch này không phải giao dịch mô phỏng.")
        body = gw.webhook_body(txn_id=payment.gateway_txn_id, order_code=order.code,
                               amount=int(self._group_total(payment)),
                               result=result, paid_at=_now() if result == "SUCCESS" else None)
        return self.handle_webhook(payment.gateway, body, self.gateway.sign(body))

    # ---- one gateway transaction can settle several rows (final payment = FINAL + SHIPPING) ----
    def _group(self, payment: Payment) -> list[Payment]:
        group_txn = (payment.gateway_payload or {}).get("group_txn")
        rows = self.payments.by_group(payment.order_id, group_txn) if group_txn else []
        return rows or [payment]

    def _group_total(self, payment: Payment) -> Decimal:
        return sum((p.amount for p in self._group(payment)), Decimal(0))

    # ---- gateway side (webhook) ----
    def handle_webhook(self, gateway: PaymentGateway, body: bytes, signature: str | None) -> dict[str, Any]:
        if not self.gateway.verify(body, signature):
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký webhook không hợp lệ.")
        try:
            data = json.loads(body)
            txn_id, code, amount, result = str(data["txn_id"]), str(data["order_code"]), int(data["amount"]), data["result"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(422, "INVALID_WEBHOOK", "Nội dung webhook không hợp lệ.") from exc
        if result not in {"SUCCESS", "FAILED"}:
            raise AppError(422, "INVALID_WEBHOOK", "Kết quả giao dịch không hợp lệ.")
        payment = self.payments.by_txn(gateway, txn_id, lock=True)
        if payment is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Không tìm thấy giao dịch.")
        order = self.orders.get(payment.order_id, lock=True)
        group = self._group(payment)
        if order.code != code or int(sum((p.amount for p in group), Decimal(0))) != amount:
            audit.record(self.session, actor_id=None, action="PAYMENT_MISMATCH", entity_type="payment",
                         entity_id=payment.id, new={"order_code": code, "amount": amount})
            self.session.commit()                      # keep the security trail although the request itself fails
            raise AppError(422, "PAYMENT_MISMATCH", "Mã đơn hoặc số tiền không khớp giao dịch.")
        if payment.status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
            return {"result": "ALREADY_PROCESSED", "status": payment.status.value}      # idempotent (NFR-06)
        if payment.status == PaymentStatus.CANCELLED:
            return {"result": "IGNORED", "status": payment.status.value}

        if result == "FAILED":
            for row in group:
                row.status, row.gateway_payload = PaymentStatus.FAILED, {**(row.gateway_payload or {}), "webhook": data}
            self.session.flush()
            audit.record(self.session, actor_id=None, action="PAYMENT_FAILED", entity_type="payment",
                         entity_id=payment.id, new={"order_id": order.id})
            return {"result": "PROCESSED", "status": "FAILED"}

        paid_at = _now()
        for row in group:
            row.status, row.paid_at = PaymentStatus.SUCCESS, paid_at
            row.gateway_payload = {**(row.gateway_payload or {}), "webhook": data}
        self.session.flush()
        if payment.type in (PaymentType.FINAL, PaymentType.SHIPPING) and order.order_status == OrderStatus.AWAITING_FINAL_PAYMENT:
            # Final payment (FR-18): production is already FINISHED, so only the order status moves (BR-17).
            set_actor(self.session, None, "Thanh toán cuối thành công")
            order.order_status = OrderStatus.READY_TO_DELIVER
            self.session.flush()
            audit.record(self.session, actor_id=None, action="PAYMENT_SUCCESS", entity_type="payment",
                         entity_id=payment.id, new={"order_id": order.id, "amount": str(sum((p.amount for p in group), Decimal(0))),
                                                    "types": [p.type.value for p in group]})
            notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="FINAL_PAID", code=order.code)
            if order.assigned_staff_id:
                notifications.notify(account_id=order.assigned_staff_id, order_id=order.id, msg_code="ORDER_READY_TO_DELIVER",
                                     code=order.code)
            return {"result": "PROCESSED", "status": "SUCCESS", "order_status": "READY_TO_DELIVER"}
        if payment.type == PaymentType.DEPOSIT and order.order_status == OrderStatus.AWAITING_DEPOSIT:
            set_actor(self.session, None, "Đặt cọc thành công")
            order.order_status, order.production_status = OrderStatus.CONFIRMED, ProductionStatus.PENDING_SCHEDULE
            self.session.flush()
            audit.record(self.session, actor_id=None, action="PAYMENT_SUCCESS", entity_type="payment",
                         entity_id=payment.id, new={"order_id": order.id, "amount": str(payment.amount)})
            notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="DEPOSIT_PAID",
                                 code=order.code, amount=str(payment.amount))
            return {"result": "PROCESSED", "status": "SUCCESS", "order_status": "CONFIRMED"}
        # Money arrived for an order that is no longer waiting for it (cancelled meanwhile): keep the record
        # and flag it, the refund is handled with the cancellation/refund flow (BR-14, BR-16).
        for row in group:
            row.gateway_payload = {**(row.gateway_payload or {}), "needs_refund": True}
        self.session.flush()
        audit.record(self.session, actor_id=None, action="PAYMENT_ORPHAN", entity_type="payment",
                     entity_id=payment.id, new={"order_id": order.id, "order_status": order.order_status.value})
        log.warning("Deposit received for order %s in status %s: refund needed", order.code, order.order_status.value)
        return {"result": "PROCESSED", "status": "SUCCESS", "order_status": order.order_status.value,
                "needs_refund": True}

    # ---- workshop read-only view ----
    def for_workshop(self, order_id: int) -> list[Payment]:
        return self.payments.for_order(order_id)
