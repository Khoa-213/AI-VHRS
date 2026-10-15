"""Data access for orders and their inputs. No business rules."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import HandwritingStyle, Order, OrderInput, OrderStatus


class OrderRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, order: Order) -> Order:
        self.s.add(order)
        self.s.flush()
        self.s.refresh(order)
        return order

    def get_owned(self, order_id: int, customer_id: int) -> Order | None:
        """Record-level authorization: an order that belongs to someone else is simply 'not found'."""
        return self.s.scalar(select(Order).where(Order.id == order_id, Order.customer_id == customer_id))

    def search_owned(self, customer_id: int, *, statuses: list[OrderStatus] | None, offset: int,
                     limit: int) -> tuple[list[Order], int]:
        stmt = select(Order).where(Order.customer_id == customer_id)
        if statuses:
            stmt = stmt.where(Order.order_status.in_(statuses))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.s.scalars(stmt.order_by(Order.last_saved_at.desc(), Order.id.desc()).offset(offset).limit(limit))
        return list(rows), total

    def delete(self, order: Order) -> None:
        self.s.delete(order)
        self.s.flush()

    # ---- inputs ----
    def inputs(self, order_id: int) -> list[OrderInput]:
        return list(self.s.scalars(select(OrderInput).where(OrderInput.order_id == order_id,
                                                            OrderInput.deleted_at.is_(None))
                                   .order_by(OrderInput.sort_order, OrderInput.id)))

    def input(self, order_id: int, input_id: int) -> OrderInput | None:
        return self.s.scalar(select(OrderInput).where(OrderInput.id == input_id, OrderInput.order_id == order_id,
                                                      OrderInput.deleted_at.is_(None)))

    def add_input(self, row: OrderInput) -> OrderInput:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def delete_input(self, row: OrderInput) -> None:
        self.s.delete(row)
        self.s.flush()

    def style(self, style_id: int) -> HandwritingStyle | None:
        return self.s.get(HandwritingStyle, style_id)
