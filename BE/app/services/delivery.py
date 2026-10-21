"""Customer side of the end of an order (Phase 4c-1): how to receive it, the final payment, confirming receipt; and the
Staff's hand-over at the workshop. FR-18, FR-21, FR-23, BR-11, BR-12.

After acceptance the order waits in AWAITING_FINAL_PAYMENT. The customer chooses DELIVERY or PICKUP, then makes ONE payment
(G - D) + F_ship through the (MOCK) gateway. Its webhook (services/payments.py) moves the order to READY_TO_DELIVER. A pickup order
is completed when the Staff confirm the hand-over (contact phone checked); delivery through a carrier is Phase 4c-2.

State changes are plain UPDATEs judged by the DB trigger `fn_order_state_guard`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import delivery_rules as dr
from app.domain.scheduling_rules import NoSlotError, WorkCalendar
from app.integrations import payment_gateway as gw
from app.models.account import Account
from app.models.ops import Payment, PaymentGateway, PaymentStatus, PaymentType
from app.models.order import DeliveryMethod, Order, OrderStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import PaymentRepository
from app.repositories.orders import OrderRepository
from app.services import audit, notifications
from app.services.workshop_access import WorkshopAccess

_STATUS = {"SLOT_IN_PAST": 422, "SHIPPING_FEE_UNAVAILABLE": 503}      # every other DeliveryRuleError is a 422


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rule_error(exc: dr.DeliveryRuleError) -> AppError:
    return AppError(_STATUS.get(exc.code, 422), exc.code, exc.message, exc.details)


class DeliveryService:
    def __init__(self, session: Session, customer: Account, ip: str | None = None):
        self.session, self.customer, self.ip = session, customer, ip
        self.orders = OrderRepository(session)
        self.payments = PaymentRepository(session)
        self.catalog = CatalogRepository(session)
        self.gateway = gw.get_gateway()

    # ------------------------------------------------------------------ helpers
    def _own(self, order_id: int) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return order

    def _lock(self, order_id: int) -> Order:
        """Own the row, take the row lock, then re-read: the object may be in the session with pre-lock values."""
        order = self._own(order_id)
        locked = self.orders.get(order.id, lock=True)
        self.session.refresh(locked)
        return locked

    @staticmethod
    def _awaiting(order: Order) -> None:
        if order.order_status == OrderStatus.AWAITING_FINAL_PAYMENT:
            return
        paid = order.order_status in (OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING, OrderStatus.COMPLETED)
        raise AppError(409, "FINAL_ALREADY_PAID" if paid else "FINAL_PAYMENT_NOT_EXPECTED",
                       "Đơn đã thanh toán phần còn lại." if paid else "Đơn không ở bước thanh toán cuối.",
                       {"order_status": order.order_status.value})

    def _package(self, order: Order) -> tuple[str, str]:
        paper = self.catalog.paper(order.paper_type_id) if order.paper_type_id else None
        if paper is None:
            raise AppError(409, "DELIVERY_NOT_READY", "Đơn chưa có loại giấy để xác định gói hàng.")
        try:
            return paper.size.value, dr.package_type(paper.size.value)
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc

    def _fee(self, order: Order) -> Decimal:
        _, package = self._package(order)
        try:
            return dr.shipping_fee(self.catalog.setting("fallback_shipping_fees", None), package)
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc

    def _due(self, order: Order, method: str, fee: Decimal) -> dr.AmountDue:
        try:
            return dr.amount_due(order.total_amount, order.deposit_amount, method, fee)
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc

    def _calendar(self) -> WorkCalendar:
        try:
            return WorkCalendar.from_setting(self.catalog.setting("working_hours"))
        except (ValueError, NoSlotError) as exc:
            raise AppError(503, "WORKING_HOURS_INVALID", "Cấu hình giờ làm việc (working_hours) không hợp lệ.") from exc

    # ------------------------------------------------------------------ FR-21: what it costs
    def quote(self, order_id: int) -> dict[str, Any]:
        order = self._own(order_id)
        self._awaiting(order)
        size, package = self._package(order)
        fee = self._fee(order)
        options = {m: {"fee": f, "total_due": self._due(order, m, f).total}
                   for m, f in (("DELIVERY", fee), ("PICKUP", Decimal(0)))}
        return {"paper_size": size, "package_type": package, "balance": order.total_amount - order.deposit_amount,
                "is_fallback_fee": True, "options": options, "chosen": order.delivery_method}

    # ------------------------------------------------------------------ FR-21 / FR-23: how to receive it
    def choose(self, order_id: int, method: DeliveryMethod, *, address: dict[str, Any] | None,
               slot_start: datetime | None, slot_end: datetime | None, contact_phone: str | None,
               receiver: str | None) -> Order:
        order = self._lock(order_id)
        self._awaiting(order)
        try:
            if method == DeliveryMethod.DELIVERY:
                order.delivery_address = dr.check_address(address or {})
                order.pickup_slot_start = order.pickup_slot_end = None
            else:
                assert slot_start is not None and slot_end is not None
                dr.check_pickup_slot(slot_start, slot_end, _now(), self._calendar())
                if not dr.normalize_phone(contact_phone):
                    raise dr.DeliveryRuleError("INVALID_CONTACT", "Cần số điện thoại để đối chiếu khi nhận hàng.")
                order.delivery_address = {"receiver": (receiver or self.customer.full_name).strip(),
                                          "phone": dr.normalize_phone(contact_phone)}
                order.pickup_slot_start, order.pickup_slot_end = slot_start, slot_end
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc
        order.delivery_method = method
        for stale in self.payments.pending_final(order.id):          # their amount belonged to the previous choice
            stale.status = PaymentStatus.CANCELLED
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="DELIVERY_CHOOSE", entity_type="order",
                     entity_id=order.id, new={"method": method.value}, ip=self.ip)
        return order

    # ------------------------------------------------------------------ FR-18: the final payment
    def start_final_payment(self, order_id: int, gateway: PaymentGateway) -> tuple[list[Payment], dr.AmountDue, Order]:
        order = self._lock(order_id)
        self._awaiting(order)
        if order.delivery_method is None:
            raise AppError(409, "DELIVERY_NOT_CHOSEN", "Hãy chọn giao hàng hoặc nhận tại xưởng trước khi thanh toán.")
        method = order.delivery_method.value
        due = self._due(order, method, self._fee(order) if method == "DELIVERY" else Decimal(0))

        wanted = sorted((ptype.value, amount) for ptype, amount in
                        ((PaymentType.FINAL, due.final), (PaymentType.SHIPPING, due.shipping)) if amount > 0)
        open_rows = self.payments.pending_final(order.id)
        if open_rows and sorted((p.type.value, p.amount) for p in open_rows) == wanted and all(
                p.gateway == gateway for p in open_rows):
            return open_rows, due, order                              # same intent: reuse the open transaction
        for stale in open_rows:
            stale.status = PaymentStatus.CANCELLED
        self.session.flush()

        if due.total == 0:                                            # fully paid by the deposit, collecting at the workshop
            set_actor(self.session, self.customer.id, "Không còn khoản phải thanh toán")
            order.order_status = OrderStatus.READY_TO_DELIVER
            self.session.flush()
            audit.record(self.session, actor_id=self.customer.id, action="FINAL_PAYMENT_NOT_REQUIRED",
                         entity_type="order", entity_id=order.id, new={"method": method}, ip=self.ip)
            self._notify_ready(order)
            return [], due, order

        txn = self.gateway.new_txn_id(gateway.value)
        rows: list[Payment] = []
        for ptype, amount in ((PaymentType.FINAL, due.final), (PaymentType.SHIPPING, due.shipping)):
            if amount <= 0:
                continue
            # One gateway transaction pays both rows; the unique index on (gateway, gateway_txn_id) needs distinct ids.
            txn_id = txn if not rows else f"{txn}:SHIP"
            rows.append(self.payments.add(Payment(
                order_id=order.id, type=ptype, amount=amount, gateway=gateway, gateway_txn_id=txn_id,
                status=PaymentStatus.PENDING, gateway_payload={"mode": self.gateway.mode, "group_txn": txn})))
        audit.record(self.session, actor_id=self.customer.id, action="PAYMENT_START", entity_type="payment",
                     entity_id=rows[0].id, new={"order_id": order.id, "final": str(due.final), "shipping": str(due.shipping),
                                                "gateway": gateway.value, "mode": self.gateway.mode}, ip=self.ip)
        return rows, due, order

    def _notify_ready(self, order: Order) -> None:
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="FINAL_PAID", code=order.code)

    # ------------------------------------------------------------------ the customer has the product
    def confirm_receipt(self, order_id: int) -> Order:
        order = self._lock(order_id)
        if order.order_status not in (OrderStatus.DELIVERING, OrderStatus.COMPLETED):
            raise AppError(409, "ORDER_NOT_DELIVERED", "Đơn chưa được giao hoặc bàn giao.",
                           {"order_status": order.order_status.value})
        if order.received_confirmed_at is not None:
            raise AppError(409, "RECEIPT_ALREADY_CONFIRMED", "Bạn đã xác nhận nhận hàng.")
        order.received_confirmed_at = _now()        # only a record: COMPLETED comes from the hand-over / carrier (FR-22, FR-23)
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="ORDER_RECEIPT_CONFIRM", entity_type="order",
                     entity_id=order.id, ip=self.ip)
        return order


class PickupService:
    """Staff hand the product over at the workshop (FR-23): code + phone are checked, then the order is COMPLETED."""

    def __init__(self, session: Session, staff: Account, ip: str | None = None):
        self.session, self.staff, self.ip = session, staff, ip

    def confirm(self, order_id: int, phone: str) -> Order:
        order = WorkshopAccess(self.session, self.staff).order(order_id, write=True, lock=True)
        self.session.refresh(order)
        if order.order_status != OrderStatus.READY_TO_DELIVER or order.delivery_method != DeliveryMethod.PICKUP:
            raise AppError(409, "PICKUP_NOT_EXPECTED", "Đơn không ở bước chờ nhận tại xưởng.",
                           {"order_status": order.order_status.value,
                            "delivery_method": order.delivery_method.value if order.delivery_method else None})
        contact = (order.delivery_address or {}).get("phone")
        if not dr.phones_match(phone, contact):
            audit.record(self.session, actor_id=self.staff.id, action="PICKUP_VERIFY_FAILED", entity_type="order",
                         entity_id=order.id, ip=self.ip)
            self.session.commit()                       # keep the failed attempt on record although the request fails (S03)
            raise AppError(422, "PICKUP_PHONE_MISMATCH", "Số điện thoại không khớp với người nhận đã đăng ký.")
        set_actor(self.session, self.staff.id, "Khách đã nhận hàng tại xưởng")
        order.order_status = OrderStatus.COMPLETED
        self.session.flush()
        self.session.refresh(order)
        audit.record(self.session, actor_id=self.staff.id, action="ORDER_PICKUP_CONFIRM", entity_type="order",
                     entity_id=order.id, ip=self.ip)
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="ORDER_COMPLETED", code=order.code)
        return order
