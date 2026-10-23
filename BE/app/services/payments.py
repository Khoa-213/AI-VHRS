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
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.core.config import get_settings
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
from app.services import audit, gateway_checkout as checkout, notifications, quotations

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
        if not lock:
            return order
        locked = self.orders.get(order.id, lock=True)
        self.session.refresh(locked)                 # loaded before the lock: re-read what other requests committed meanwhile
        return locked

    def list_for_order(self, order_id: int) -> list[Payment]:
        return self.payments.for_order(self._own_order(order_id).id)

    def start_deposit(self, order_id: int, gateway: PaymentGateway) -> Payment:
        order = self._own_order(order_id, lock=True)
        if order.order_status != OrderStatus.AWAITING_DEPOSIT or order.deposit_amount is None:
            raise AppError(409, "DEPOSIT_NOT_EXPECTED", "Đơn không ở bước chờ đặt cọc.")
        if self.payments.success(order.id, PaymentType.DEPOSIT) is not None:
            raise AppError(409, "DEPOSIT_ALREADY_PAID", "Đơn đã được đặt cọc.")
        for old in self.payments.pending(order.id, PaymentType.DEPOSIT):
            if old.gateway == gateway and old.amount == order.deposit_amount and checkout.usable(old):
                return old                                              # same intent: reuse the open transaction
            old.status = PaymentStatus.CANCELLED
            checkout.close(old)
        self.session.flush()
        txn_ref, mode = checkout.begin(gateway)
        row = self.payments.add(Payment(
            order_id=order.id, type=PaymentType.DEPOSIT, amount=order.deposit_amount, deposit_pct=order.deposit_pct,
            gateway=gateway, gateway_txn_id=txn_ref, status=PaymentStatus.PENDING, gateway_payload={"mode": mode}))
        checkout.attach([row], gateway, order, total=order.deposit_amount, ip=self.ip)
        audit.record(self.session, actor_id=self.customer.id if self.customer else None, action="PAYMENT_START",
                     entity_type="payment", entity_id=row.id,
                     new={"order_id": order.id, "amount": str(row.amount), "gateway": gateway.value, "mode": mode}, ip=self.ip)
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
        """The MOCK gateway's webhook. Its key is derived from JWT_SECRET, so once real payments are on (sandbox/live) this
        door is shut: nobody holding that key may be able to mark a real payment as paid."""
        if gateway == PaymentGateway.PAYOS:
            raise AppError(404, "NOT_FOUND", "Không có webhook mô phỏng cho PAYOS.")    # its webhook is POST /webhooks/payments/payos
        if get_settings().payment_mode != "mock":
            raise AppError(403, "MOCK_WEBHOOK_DISABLED", "Webhook mô phỏng đã tắt khi dùng cổng thanh toán thật.")
        if not self.gateway.verify(body, signature):
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký webhook không hợp lệ.")
        try:
            data = json.loads(body)
            txn_id, code, amount, result = str(data["txn_id"]), str(data["order_code"]), int(data["amount"]), data["result"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(422, "INVALID_WEBHOOK", "Nội dung webhook không hợp lệ.") from exc
        if result not in {"SUCCESS", "FAILED"}:
            raise AppError(422, "INVALID_WEBHOOK", "Kết quả giao dịch không hợp lệ.")
        return self._settle(gateway, txn_id=txn_id, code=code, amount=amount, ok=result == "SUCCESS", raw=data)

    def _lock_payment(self, gateway: PaymentGateway, txn_id: str) -> tuple[Payment | None, Order | None]:
        """Lock the ORDER first, then the payment. Every other money path (cancel, start a deposit, choose delivery, the final
        payment) takes the order lock and only then touches the payment rows; taking them the other way round here made a
        webhook and a customer action on the same order deadlock (Postgres aborted one of them with a 500: audit F-03).
        Both rows are re-read after their lock, because the unlocked read below may be older than what others committed."""
        probe = self.payments.by_txn(gateway, txn_id)                  # unlocked: only to learn which order it belongs to
        if probe is None:
            return None, None
        order = self.orders.get(probe.order_id, lock=True)
        if order is None:
            return None, None
        self.session.refresh(order)
        payment = self.payments.by_txn(gateway, txn_id, lock=True)
        if payment is None:
            return None, None
        self.session.refresh(payment)
        return payment, order

    # ---- the one place that turns a gateway's answer into SUCCESS / FAILED (mock webhook, VNPay/MoMo IPN, query) ----
    def _settle(self, gateway: PaymentGateway, *, txn_id: str, code: str | None, amount: int, ok: bool,
                raw: dict[str, Any]) -> dict[str, Any]:
        payment, order = self._lock_payment(gateway, txn_id)
        if payment is None or order is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Không tìm thấy giao dịch.")
        group = self._group(payment)
        if (code is not None and order.code != code) or int(sum((p.amount for p in group), Decimal(0))) != amount:
            audit.record(self.session, actor_id=None, action="PAYMENT_MISMATCH", entity_type="payment",
                         entity_id=payment.id, new={"order_code": code, "amount": amount})
            self.session.commit()                      # keep the security trail although the request itself fails
            raise AppError(422, "PAYMENT_MISMATCH", "Mã đơn hoặc số tiền không khớp giao dịch.")
        if payment.status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
            return {"result": "ALREADY_PROCESSED", "status": payment.status.value}      # idempotent (NFR-06)
        if payment.status == PaymentStatus.CANCELLED:
            if ok:                                      # the customer paid an intent we had already closed: real money, keep a record
                self._flag_orphan(order, payment, group, "cancelled payment paid")
            return {"result": "IGNORED", "status": payment.status.value}

        if not ok:
            for row in group:
                row.status, row.gateway_payload = PaymentStatus.FAILED, {**(row.gateway_payload or {}), "webhook": raw}
            self.session.flush()
            audit.record(self.session, actor_id=None, action="PAYMENT_FAILED", entity_type="payment",
                         entity_id=payment.id, new={"order_id": order.id})
            return {"result": "PROCESSED", "status": "FAILED"}

        paid_at = _now()
        for row in group:
            row.status, row.paid_at = PaymentStatus.SUCCESS, paid_at
            row.gateway_payload = {**(row.gateway_payload or {}), "webhook": raw}
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

    def _flag_orphan(self, order: Order, payment: Payment, group: list[Payment], why: str) -> None:
        """Money reached us for a payment that no longer counts. Keep the record and flag it for the refund flow (BR-14/16)."""
        if any((r.gateway_payload or {}).get("needs_refund") for r in group):
            return
        for row in group:
            row.gateway_payload = {**(row.gateway_payload or {}), "needs_refund": True}
        self.session.flush()
        audit.record(self.session, actor_id=None, action="PAYMENT_ORPHAN", entity_type="payment", entity_id=payment.id,
                     new={"order_id": order.id, "order_status": order.order_status.value, "reason": why})
        log.warning("Money received for order %s (%s): refund needed", order.code, why)

    # ---- real gateways: their own callbacks (IPN) ----
    def handle_vnpay_ipn(self, params: Mapping[str, str]) -> dict[str, str]:
        """VNPay calls this with GET and expects a JSON {RspCode, Message} with HTTP 200 whatever the outcome."""
        adapter: Any = gw.real_adapter(PaymentGateway.VNPAY, strict=False)
        try:
            if adapter is None:
                raise gw.InvalidSignature()
            result = adapter.parse_ipn(params)
        except gw.InvalidSignature:
            return {"RspCode": "97", "Message": "Invalid signature"}
        except gw.MalformedCallback:
            return {"RspCode": "99", "Message": "Invalid request"}
        try:
            out = self._settle(PaymentGateway.VNPAY, txn_id=result.txn_ref, code=None, amount=result.amount,
                               ok=result.success, raw=result.raw)
        except AppError as exc:
            if exc.code == "PAYMENT_NOT_FOUND":
                return {"RspCode": "01", "Message": "Order not found"}
            if exc.code == "PAYMENT_MISMATCH":
                return {"RspCode": "04", "Message": "Invalid amount"}
            raise
        if out["result"] == "ALREADY_PROCESSED":
            return {"RspCode": "02", "Message": "Order already confirmed"}
        return {"RspCode": "00", "Message": "Confirm Success"}

    def handle_momo_ipn(self, body: dict[str, Any]) -> dict[str, Any]:
        """MoMo POSTs JSON and expects HTTP 204 (within 15 s). Errors are signalled with a 4xx."""
        adapter: Any = gw.real_adapter(PaymentGateway.MOMO, strict=False)
        if adapter is None:
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký IPN không hợp lệ.")
        try:
            result = adapter.parse_ipn(body)
        except gw.InvalidSignature as exc:
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký IPN không hợp lệ.") from exc
        except gw.MalformedCallback as exc:
            raise AppError(422, "INVALID_WEBHOOK", "Nội dung IPN không hợp lệ.") from exc
        if not result.final:
            return {"result": "IGNORED", "status": "PENDING"}
        return self._settle(PaymentGateway.MOMO, txn_id=result.txn_ref, code=None, amount=result.amount,
                            ok=result.success, raw=result.raw)

    def handle_payos_webhook(self, body: dict[str, Any]) -> dict[str, Any]:
        """payOS POSTs JSON for every transfer it matched to one of our links and expects HTTP 200. The envelope is answered 200
        for everything that is validly signed (so payOS does not retry), including a transaction we do not know: that is how
        payOS's own test message succeeds when the webhook address is registered."""
        adapter: Any = gw.real_adapter(PaymentGateway.PAYOS, strict=False)
        if adapter is None:
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký webhook không hợp lệ.")
        try:
            result = adapter.parse_webhook(body)
        except gw.InvalidSignature as exc:
            raise AppError(401, "INVALID_SIGNATURE", "Chữ ký webhook không hợp lệ.") from exc
        except gw.MalformedCallback as exc:
            raise AppError(422, "INVALID_WEBHOOK", "Nội dung webhook không hợp lệ.") from exc
        payment, order = self._lock_payment(PaymentGateway.PAYOS, result.txn_ref)
        if payment is None or order is None:
            return {"result": "UNKNOWN_TRANSACTION", "status": "IGNORED"}
        expected = int(self._group_total(payment))
        if result.success and result.amount != expected and payment.status == PaymentStatus.PENDING:
            # The customer sent a different amount than the link asks for. The money is here, but it is not this payment:
            # keep the record for the refund flow and leave the payment pending (it expires or the customer pays correctly).
            self._flag_orphan(order, payment, self._group(payment), f"paid {result.amount}, expected {expected}")
            return {"result": "AMOUNT_MISMATCH", "status": "PENDING", "needs_refund": True}
        return self._settle(PaymentGateway.PAYOS, txn_id=result.txn_ref, code=None, amount=result.amount,
                            ok=result.success, raw=result.raw)

    # ---- real gateways: ask the gateway when the IPN is late or lost ----
    def refresh(self, payment_id: int) -> dict[str, Any]:
        assert self.customer is not None
        payment = self.payments.get(payment_id)
        order = self.orders.get_owned(payment.order_id, self.customer.id) if payment else None
        if payment is None or order is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Không tìm thấy giao dịch.")
        if payment.status != PaymentStatus.PENDING:
            return {"result": "ALREADY_PROCESSED", "status": payment.status.value, "order_status": order.order_status.value}
        payload = payment.gateway_payload or {}
        if payload.get("mode") == "MOCK":
            raise AppError(409, "NOT_A_REAL_PAYMENT", "Giao dịch mô phỏng không có cổng để hỏi; dùng mock-checkout.")
        adapter: Any = gw.real_adapter(payment.gateway)
        ref = checkout.group_ref(payment)
        result = adapter.query(txn_ref=ref, meta=payload.get("gateway_meta") or {}, client_ip=self.ip)
        if result is None or not result.final:
            return {"result": "IGNORED", "status": "PENDING", "order_status": order.order_status.value}
        return self._settle(payment.gateway, txn_id=ref, code=None, amount=result.amount, ok=result.success, raw=result.raw)

    @staticmethod
    def gateways() -> list[dict[str, Any]]:
        return gw.gateway_status()

    # ---- workshop read-only view ----
    def for_workshop(self, order_id: int) -> list[Payment]:
        return self.payments.for_order(order_id)
