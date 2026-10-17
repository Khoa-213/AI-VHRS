"""Record-level authorization for the workshop side (BR-02, FR-12).

MANAGER sees every order that has left DRAFT. STAFF sees the orders assigned to them, plus the pool
of SUBMITTED orders nobody owns yet (read-only until they claim one). Anything else answers 404 so
the order's existence is not revealed. DRAFT orders belong to the customer alone.
"""
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.models.order import Order, OrderStatus
from app.repositories.orders import OrderRepository


def not_found() -> AppError:
    return AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")


class WorkshopAccess:
    def __init__(self, session: Session, actor: Account):
        self.session, self.actor = session, actor
        self.orders = OrderRepository(session)

    @property
    def is_manager(self) -> bool:
        return self.actor.role.code == RoleCode.MANAGER.value

    def order(self, order_id: int, *, write: bool = False, allow_claim: bool = False, lock: bool = False) -> Order:
        order = self.orders.get(order_id, lock=lock)
        if order is None or order.order_status == OrderStatus.DRAFT:
            raise not_found()
        if self.is_manager or order.assigned_staff_id == self.actor.id:
            return order
        if order.assigned_staff_id is None and order.order_status == OrderStatus.SUBMITTED:
            if not write:
                return order
            if allow_claim:
                if not self.orders.claim(order.id, self.actor.id):
                    raise AppError(409, "ALREADY_ASSIGNED", "Đơn đã được nhân viên khác nhận.")
                self.session.refresh(order)
                return order
            raise AppError(409, "ORDER_NOT_CLAIMED", "Hãy nhận đơn trước khi thao tác.")
        raise not_found()
