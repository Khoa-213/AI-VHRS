"""Data access for orders and their inputs. No business rules."""
from datetime import date

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.order import HandwritingStyle, Order, OrderInput, OrderStatus, ProductionStatus


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

    # ---- workshop side (Staff / Manager) ----
    def get(self, order_id: int, *, lock: bool = False) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def search_workshop(self, *, staff_id: int | None, statuses: list[OrderStatus] | None, order_type: str | None,
                        eta_before: date | None, unassigned_only: bool, q: str | None, offset: int,
                        limit: int) -> tuple[list[tuple[Order, str]], int]:
        """Orders visible to the workshop: never DRAFT (private to the customer).
        Staff (staff_id given): assigned to them, or still unassigned and SUBMITTED (the pool, FR-12)."""
        stmt = select(Order, Account.full_name).join(Account, Account.id == Order.customer_id) \
            .where(Order.order_status != OrderStatus.DRAFT)
        if staff_id is not None:
            stmt = stmt.where(or_(Order.assigned_staff_id == staff_id,
                                  (Order.assigned_staff_id.is_(None)) & (Order.order_status == OrderStatus.SUBMITTED)))
        if statuses:
            stmt = stmt.where(Order.order_status.in_(statuses))
        if order_type:
            stmt = stmt.where(Order.order_type == order_type)
        if eta_before:
            stmt = stmt.where(Order.eta <= eta_before)
        if unassigned_only:
            stmt = stmt.where(Order.assigned_staff_id.is_(None))
        if q:
            stmt = stmt.where(Order.code.ilike(f"%{q}%"))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.s.execute(stmt.order_by(Order.submitted_at.asc().nulls_last(), Order.id).offset(offset).limit(limit))
        return [(o, name) for o, name in rows], total

    def claim(self, order_id: int, staff_id: int) -> bool:
        """Atomic self-assignment: only one Staff wins when two click at once."""
        res = self.s.execute(update(Order).where(Order.id == order_id, Order.assigned_staff_id.is_(None),
                                                 Order.order_status == OrderStatus.SUBMITTED)
                             .values(assigned_staff_id=staff_id, assigned_by=staff_id))
        return res.rowcount == 1

    def open_counts_by_staff(self) -> dict[int, int]:
        rows = self.s.execute(select(Order.assigned_staff_id, func.count()).where(
            Order.assigned_staff_id.is_not(None),
            Order.order_status.not_in([OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED]))
            .group_by(Order.assigned_staff_id))
        return {sid: n for sid, n in rows}

    def production_queue(self, *, production_statuses: list[ProductionStatus], offset: int,
                         limit: int) -> tuple[list[tuple[Order, str]], int]:
        """Confirmed orders waiting for the Manager to put them on the schedule (FR-37)."""
        stmt = select(Order, Account.full_name).join(Account, Account.id == Order.customer_id).where(
            Order.order_status == OrderStatus.CONFIRMED, Order.production_status.in_(production_statuses))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.s.execute(stmt.order_by(Order.eta.asc().nulls_last(), Order.confirmed_at.asc().nulls_last(),
                                            Order.id).offset(offset).limit(limit))
        return [(o, name) for o, name in rows], total
