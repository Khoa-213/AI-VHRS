"""Customer side of the end of an order (Phase 4c-1): how to receive it, the final payment, confirming receipt; and the
Staff's hand-over at the workshop. FR-18, FR-21, FR-23, BR-11, BR-12.

After acceptance the order waits in AWAITING_FINAL_PAYMENT. The customer chooses DELIVERY or PICKUP, then makes ONE payment
(G - D) + F_ship through the (MOCK) gateway. Its webhook (services/payments.py) moves the order to READY_TO_DELIVER. A pickup order
is completed when the Staff confirm the hand-over (contact phone checked); delivery through a carrier is Phase 4c-2.

State changes are plain UPDATEs judged by the DB trigger `fn_order_state_guard`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.integrations import carrier as cx
from app.domain import carrier_rules as cr
from app.domain import delivery_rules as dr
from app.domain.scheduling_rules import NoSlotError, WorkCalendar
from app.models.account import Account
from app.models.ops import Payment, PaymentGateway, PaymentStatus, PaymentType
from app.models.order import DeliveryMethod, Order, OrderStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, PaymentRepository
from app.repositories.orders import OrderRepository
from app.services import audit, gateway_checkout as checkout, notifications
from app.services import parcel as parcel_svc
from app.services.workshop_access import WorkshopAccess

log = logging.getLogger("app")
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
        self.jobs = JobRepository(session)
        self.catalog = CatalogRepository(session)

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
        _, size, package = parcel_svc.paper_and_package(self.catalog, order)
        return size, package

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

    # ------------------------------------------------------------------ the parcel and the carriers' services
    def _parcel(self, order: Order) -> cr.Parcel:
        return parcel_svc.build_parcel(self.catalog, self.jobs, order)

    def _quotes(self, order: Order, address: dict[str, Any] | None) -> list[cr.ServiceQuote]:
        """What each carrier offers for this parcel and address. A carrier whose API is off (or fails) is offered with one option
        priced from the fallback table (FR-21); a carrier that cannot address this destination is left out."""
        base = self._fee(order)
        fee_table = self.catalog.setting("fallback_shipping_fees", None)
        flags = self.catalog.setting("integrations_enabled", {})
        parcel = self._parcel(order)
        out: list[cr.ServiceQuote] = []
        for carrier in cx.CARRIERS:
            if address and cx.api_enabled(carrier, flags):
                try:
                    found = cx.get_adapter(carrier, fee_table=fee_table).quote(parcel=parcel, to=address, order_code=order.code)
                    if found:
                        out.extend(found)
                        continue
                except AppError as exc:
                    if exc.code in ("ADDRESS_NAMES_REQUIRED", "INVALID_ADDRESS"):
                        continue
                    if exc.code not in ("CARRIER_UNAVAILABLE", "CARRIER_REJECTED", "CARRIER_NOT_CONFIGURED",
                                        "SHIPPING_FEE_UNAVAILABLE"):
                        raise
                    log.warning("carrier %s quote failed (%s): fallback fee used", carrier, exc.code)
            out.append(cr.fallback_quote(carrier, base))
        return out

    def _current_fee(self, order: Order) -> Decimal:
        """The fee of the service the customer chose, asked again now (an order from before carriers were offered: the table)."""
        if order.shipping_carrier is None:
            return self._fee(order)
        try:
            return Decimal(cr.pick_service(self._quotes(order, order.delivery_address), order.shipping_carrier,
                                           order.shipping_service_code).fee)
        except cr.CarrierRuleError as exc:
            raise AppError(409, exc.code, exc.message, exc.details) from exc

    # ------------------------------------------------------------------ FR-21: what it costs
    def quote(self, order_id: int, address: dict[str, Any] | None = None) -> dict[str, Any]:
        order = self._own(order_id)
        self._awaiting(order)
        size, package = self._package(order)
        try:
            use = dr.check_address(address) if address else (
                order.delivery_address if order.delivery_method == DeliveryMethod.DELIVERY else None)
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc
        quotes = self._quotes(order, use)
        balance = order.total_amount - order.deposit_amount
        services = [{"carrier": q.carrier, "service_code": q.service_code, "service_name": q.service_name, "fee": Decimal(q.fee),
                     "total_due": self._due(order, "DELIVERY", Decimal(q.fee)).total, "eta": q.eta,
                     "is_fallback_fee": q.is_fallback, "mode": q.mode} for q in quotes]
        cheapest = min(services, key=lambda s: s["fee"])
        chosen = next((s for s in services if (s["carrier"], s["service_code"]) ==
                       (order.shipping_carrier, order.shipping_service_code)), None)
        options = {"DELIVERY": {"fee": (chosen or cheapest)["fee"], "total_due": (chosen or cheapest)["total_due"]},
                   "PICKUP": {"fee": Decimal(0), "total_due": self._due(order, "PICKUP", Decimal(0)).total}}
        return {"paper_size": size, "package_type": package, "balance": balance,
                "is_fallback_fee": bool((chosen or cheapest)["is_fallback_fee"]), "options": options,
                "chosen": order.delivery_method, "services": services, "chosen_service": chosen}

    # ------------------------------------------------------------------ FR-21 / FR-23: how to receive it
    def choose(self, order_id: int, method: DeliveryMethod, *, address: dict[str, Any] | None,
               slot_start: datetime | None, slot_end: datetime | None, contact_phone: str | None,
               receiver: str | None, carrier: str | None = None, service_code: str | None = None) -> Order:
        order = self._lock(order_id)
        self._awaiting(order)
        try:
            if method == DeliveryMethod.DELIVERY:
                order.delivery_address = dr.check_address(address or {})
                order.pickup_slot_start = order.pickup_slot_end = None
                picked = cr.pick_service(self._quotes(order, order.delivery_address), carrier, service_code)
                order.shipping_carrier, order.shipping_service_code, order.shipping_eta = (
                    picked.carrier, picked.service_code, picked.eta)
            else:
                assert slot_start is not None and slot_end is not None
                dr.check_pickup_slot(slot_start, slot_end, _now(), self._calendar())
                if not dr.normalize_phone(contact_phone):
                    raise dr.DeliveryRuleError("INVALID_CONTACT", "Cần số điện thoại để đối chiếu khi nhận hàng.")
                order.delivery_address = {"receiver": (receiver or self.customer.full_name).strip(),
                                          "phone": dr.normalize_phone(contact_phone)}
                order.pickup_slot_start, order.pickup_slot_end = slot_start, slot_end
                order.shipping_carrier = order.shipping_service_code = order.shipping_eta = None
        except dr.DeliveryRuleError as exc:
            raise _rule_error(exc) from exc
        except cr.CarrierRuleError as exc:
            raise AppError(422, exc.code, exc.message, exc.details) from exc
        order.delivery_method = method
        for stale in self.payments.pending_final(order.id):          # their amount belonged to the previous choice
            stale.status = PaymentStatus.CANCELLED
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="DELIVERY_CHOOSE", entity_type="order",
                     entity_id=order.id, new={"method": method.value, "carrier": order.shipping_carrier,
                                              "service": order.shipping_service_code}, ip=self.ip)
        return order

    # ------------------------------------------------------------------ FR-18: the final payment
    def start_final_payment(self, order_id: int, gateway: PaymentGateway,
                            expected_total: Decimal | None = None) -> tuple[list[Payment], dr.AmountDue, Order]:
        order = self._lock(order_id)
        self._awaiting(order)
        if order.delivery_method is None:
            raise AppError(409, "DELIVERY_NOT_CHOSEN", "Hãy chọn giao hàng hoặc nhận tại xưởng trước khi thanh toán.")
        method = order.delivery_method.value
        due = self._due(order, method, self._current_fee(order) if method == "DELIVERY" else Decimal(0))
        if expected_total is not None and expected_total != due.total:
            raise AppError(409, "FEE_CHANGED", "Số tiền phải trả đã thay đổi so với lúc bạn xem. Vui lòng kiểm tra lại.",
                           {"expected_total": str(expected_total), "current_total": str(due.total)})

        wanted = sorted((ptype.value, amount) for ptype, amount in
                        ((PaymentType.FINAL, due.final), (PaymentType.SHIPPING, due.shipping)) if amount > 0)
        open_rows = self.payments.pending_final(order.id)
        if open_rows and sorted((p.type.value, p.amount) for p in open_rows) == wanted and all(
                p.gateway == gateway and checkout.usable(p) for p in open_rows):
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

        txn, mode = checkout.begin(gateway)
        rows: list[Payment] = []
        for ptype, amount in ((PaymentType.FINAL, due.final), (PaymentType.SHIPPING, due.shipping)):
            if amount <= 0:
                continue
            # One gateway transaction pays both rows; the unique index on (gateway, gateway_txn_id) needs distinct ids.
            txn_id = txn if not rows else f"{txn}:SHIP"
            rows.append(self.payments.add(Payment(
                order_id=order.id, type=ptype, amount=amount, gateway=gateway, gateway_txn_id=txn_id,
                status=PaymentStatus.PENDING, gateway_payload={"mode": mode, "group_txn": txn})))
        checkout.attach(rows, gateway, order, total=due.total, ip=self.ip)
        audit.record(self.session, actor_id=self.customer.id, action="PAYMENT_START", entity_type="payment",
                     entity_id=rows[0].id, new={"order_id": order.id, "final": str(due.final), "shipping": str(due.shipping),
                                                "gateway": gateway.value, "mode": mode}, ip=self.ip)
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
