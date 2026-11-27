"""Ways out for an order that is stuck after production (audit 2026-11-27, D08; state transitions: migration 0034).

Before this, an order whose product was written could only move forward: the customer pays the balance, the carrier
delivers, or the customer collects. When none of that happens the order stayed open for ever and the product sat in the
workshop. Three things are added, none of which moves money by itself:

* `switch_to_pickup`  the delivery failed or the parcel came back: the Staff in charge turn the order into a collection at
  the workshop (DELIVERING -> READY_TO_DELIVER). The shipping fee already paid is not given back here: the carrier did go.
* `close_by_manager`  a Manager ends an order that will not complete (unpaid balance, never collected, parcel lost) with a
  reason, and says how much of what was paid is to be given back. That opens an ordinary refund request (PENDING) which
  the Staff pay out by hand and confirm, like every other refund.
* `follow_up`         the background job: reminds the customer of an unpaid balance, and tells the Managers when an order
  has waited too long for the balance or for collection, so somebody decides instead of nobody noticing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.integrations import payment_gateway as gw
from app.models.account import Account, AccountStatus, AuditLog, RoleCode
from app.models.ops import Payment, PaymentStatus, PaymentType, ShipmentStatus
from app.models.order import DeliveryMethod, Order, OrderStatus
from app.repositories.ops import PaymentRepository, ShipmentRepository
from app.repositories.orders import OrderRepository
from app.services import audit, gateway_checkout as checkout, notifications
from app.services.workshop_access import WorkshopAccess

CLOSABLE = (OrderStatus.AWAITING_FINAL_PAYMENT, OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING)
NOT_MOVING = (ShipmentStatus.FAILED, ShipmentStatus.RETURNED, ShipmentStatus.CANCELLED)
# The refund a Manager's close opens is a CANCELLATION refund (the kinds the API and the web app know) with its own rule.
CLOSE_KIND, CLOSE_RULE = "CANCELLATION", "MANAGER_CLOSE"
DEFAULT_REMIND_DAYS = 3                 # system_settings.final_payment_remind_days
DEFAULT_OVERDUE_DAYS = 7                # system_settings.final_payment_overdue_days / pickup_overdue_days
BATCH = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_shipment(session: Session, order_id: int):
    rows = ShipmentRepository(session).for_order(order_id)
    return rows[-1] if rows else None


# ---------------------------------------------------------------------------------------------- a failed delivery
def switch_to_pickup(session: Session, staff: Account, order_id: int, reason: str, ip: str | None = None) -> Order:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AppError(422, "REASON_REQUIRED", "Vui lòng ghi rõ lý do chuyển sang nhận tại xưởng (ít nhất 5 ký tự).")
    order = WorkshopAccess(session, staff).order(order_id, write=True, lock=True)
    session.refresh(order)
    if order.order_status != OrderStatus.DELIVERING:
        raise AppError(409, "ORDER_NOT_DELIVERING", "Chỉ chuyển sang nhận tại xưởng khi đơn đang giao và giao không thành công.",
                       {"order_status": order.order_status.value})
    shipment = _latest_shipment(session, order.id)
    if shipment is None or shipment.status not in (ShipmentStatus.FAILED, ShipmentStatus.RETURNED):
        raise AppError(409, "SHIPMENT_NOT_FAILED", "Vận đơn mới nhất chưa báo giao thất bại hoặc hàng hoàn; chưa chuyển được.",
                       {"shipment_status": shipment.status.value if shipment else None})
    if not (order.delivery_address or {}).get("phone"):
        raise AppError(409, "PICKUP_CONTACT_MISSING", "Đơn chưa có số điện thoại người nhận để đối chiếu khi nhận tại xưởng.")
    order.delivery_method = DeliveryMethod.PICKUP                  # the address keeps the receiver and the phone checked at hand-over
    order.pickup_slot_start = order.pickup_slot_end = None         # agreed with the customer in the chat; none is booked
    set_actor(session, staff.id, f"Giao không thành công, chuyển sang nhận tại xưởng: {reason}"[:500])
    order.order_status = OrderStatus.READY_TO_DELIVER
    session.flush()
    session.refresh(order)
    audit.record(session, actor_id=staff.id, action="DELIVERY_TO_PICKUP", entity_type="order", entity_id=order.id,
                 new={"shipment_id": shipment.id, "shipment_status": shipment.status.value}, reason=reason, ip=ip)
    notifications.notify(session, account_id=order.customer_id, order_id=order.id, msg_code="DELIVERY_TO_PICKUP", code=order.code)
    return order


# ---------------------------------------------------------------------------------------------- a Manager closes it
def refundable(session: Session, order_id: int) -> Decimal:
    """What the customer paid for the order and has not been given back or promised back yet."""
    pays = PaymentRepository(session)
    paid = sum((p.amount for p in pays.paid_rows(order_id)), Decimal(0))
    back = sum((r.amount for r in pays.refunds(order_id=order_id)
                if r.status in (PaymentStatus.PENDING, PaymentStatus.SUCCESS)), Decimal(0))
    return max(paid - back, Decimal(0))


def close_by_manager(session: Session, manager: Account, order_id: int, reason: str, refund_amount: Decimal,
                     ip: str | None = None) -> tuple[Order, Payment | None]:
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise AppError(422, "REASON_REQUIRED", "Đóng đơn cần ghi rõ lý do (ít nhất 10 ký tự).")
    order = OrderRepository(session).get(order_id, lock=True)
    if order is None or order.order_status == OrderStatus.DRAFT:
        raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    session.refresh(order)
    if order.order_status not in CLOSABLE:
        raise AppError(409, "ORDER_CLOSE_UNSUPPORTED",
                       "Quản lý chỉ đóng được đơn đang chờ thanh toán cuối, chờ nhận hàng hoặc đang giao mà không hoàn tất được.",
                       {"order_status": order.order_status.value})
    if order.order_status == OrderStatus.DELIVERING:
        shipment = _latest_shipment(session, order.id)
        if shipment is not None and shipment.status not in NOT_MOVING:
            raise AppError(409, "SHIPMENT_IN_TRANSIT", "Hàng đang trên đường giao; chờ hãng báo kết quả rồi mới đóng đơn.",
                           {"shipment_status": shipment.status.value})
    can_refund = refundable(session, order.id)
    refund_amount = Decimal(refund_amount)
    if refund_amount < 0 or refund_amount > can_refund:
        raise AppError(422, "REFUND_AMOUNT_INVALID", "Số tiền hoàn phải từ 0 tới số khách đã trả mà chưa được hoàn.",
                       {"refundable": str(can_refund)})
    pays = PaymentRepository(session)
    for stale in pays.pending_final(order.id):                    # an open payment link must not be payable after the close
        stale.status = PaymentStatus.CANCELLED
        checkout.close(stale)
    was = order.order_status
    set_actor(session, manager.id, f"Quản lý đóng đơn: {reason}"[:500])
    order.order_status = OrderStatus.CANCELLED                    # production_status stays FINISHED: the product exists
    order.cancel_reason = reason
    session.flush()

    refund = None
    source = pays.success(order.id, PaymentType.DEPOSIT)
    if refund_amount > 0 and source is not None:
        from app.services.refunds import _add_refund
        refund = _add_refund(session, Payment(
            order_id=order.id, type=PaymentType.REFUND, amount=refund_amount, gateway=source.gateway,
            status=PaymentStatus.PENDING, refund_of_id=source.id, refund_reason=f"MANAGER_CLOSE: {reason}"[:1000],
            gateway_payload={"refund_kind": CLOSE_KIND, "rule": CLOSE_RULE, "initiator": "MANAGER", "requested_by": manager.id,
                             "closed_from": was.value,
                             "mode": (source.gateway_payload or {}).get("mode", gw.get_gateway().mode)}))
    session.refresh(order)
    audit.record(session, actor_id=manager.id, action="ORDER_CLOSE", entity_type="order", entity_id=order.id,
                 new={"from": was.value, "refundable": str(can_refund), "refund_amount": str(refund_amount),
                      "refund_id": refund.id if refund else None}, reason=reason, ip=ip)
    notifications.notify(session, account_id=order.customer_id, order_id=order.id, msg_code="ORDER_CANCELLED", code=order.code,
                         refund_amount=str(refund_amount))
    if order.assigned_staff_id and refund is not None:
        notifications.notify(session, account_id=order.assigned_staff_id, order_id=order.id, msg_code="REFUND_TO_PROCESS",
                             code=order.code, amount=str(refund.amount))
    return order, refund


# ---------------------------------------------------------------------------------------------- the background job
def _managers(session: Session) -> list[int]:
    return list(session.scalars(select(Account.id).where(Account.status == AccountStatus.ACTIVE,
                                                         Account.role.has(code=RoleCode.MANAGER.value))))


def _entered(session: Session, order_id: int, status: OrderStatus) -> datetime | None:
    """When the order last entered `status` (the trigger writes status_histories)."""
    return session.execute(text("select max(created_at) from status_histories where order_id = :o and state_type = 'ORDER' "
                                "and to_status = :s"), {"o": order_id, "s": status.value}).scalar()


def follow_up(session: Session, *, order_ids: list[int] | None = None, settings: dict[str, int] | None = None,
              **_: Any) -> dict[str, Any]:
    """One pass. Each order is told about once per stay in the state (the audit log is the marker, as for the acceptance
    reminder): a second stay (delivery failed, switched to collection) is followed up again."""
    cfg = {"remind": DEFAULT_REMIND_DAYS, "overdue": DEFAULT_OVERDUE_DAYS, "pickup": DEFAULT_OVERDUE_DAYS, **(settings or {})}
    now = _now()
    out = {"balance_reminded": 0, "balance_overdue": 0, "pickup_overdue": 0}
    plan = ((OrderStatus.AWAITING_FINAL_PAYMENT, cfg["remind"], "FINAL_PAYMENT_REMINDER", "balance_reminded", "customer"),
            (OrderStatus.AWAITING_FINAL_PAYMENT, cfg["overdue"], "FINAL_PAYMENT_OVERDUE", "balance_overdue", "managers"),
            (OrderStatus.READY_TO_DELIVER, cfg["pickup"], "PICKUP_OVERDUE", "pickup_overdue", "managers"))
    for status, days, action, counter, who in plan:
        q = select(Order.id).where(Order.order_status == status)
        if status == OrderStatus.READY_TO_DELIVER:
            q = q.where(Order.delivery_method == DeliveryMethod.PICKUP)
        if order_ids is not None:
            q = q.where(Order.id.in_(order_ids or [-1]))
        for oid in session.scalars(q.limit(BATCH)).all():
            order = session.get(Order, oid, with_for_update=True)
            session.refresh(order)
            since = _entered(session, oid, status)
            if order.order_status != status or since is None or since > now - timedelta(days=days):
                session.rollback()
                continue
            if session.scalar(select(AuditLog.id).where(AuditLog.action == action, AuditLog.entity_type == "order",
                                                        AuditLog.entity_id == oid, AuditLog.created_at >= since).limit(1)):
                session.rollback()
                continue
            waited = (now - since).days
            audit.record(session, actor_id=None, action=action, entity_type="order", entity_id=oid, new={"waited_days": waited})
            targets = [order.customer_id] if who == "customer" else _managers(session)
            for account_id in targets:
                notifications.notify(session, account_id=account_id, order_id=oid, msg_code=action, code=order.code, days=waited)
            session.commit()
            out[counter] += 1
    return out
