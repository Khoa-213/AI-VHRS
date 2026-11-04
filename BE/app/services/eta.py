"""ETA of an order (Phase 4d-2: BR-15, BR-16, FR-26, UC-30). The rules are in domain/eta_rules.py.

Where the ETA comes from:
* quotation (Staff): `estimate` fills it when Staff leaves it empty; GET /workshop/orders/{id}/eta shows the suggestion;
* deposit success: the order's FIRST ETA = the later of the quotation's ETA and a fresh estimate from that day (not a postponement);
* scheduling / rescheduling (after an incident, for a rewrite): the planned finish + delivery moves it later when needed;
* the customer's carrier service: its delivery estimate moves it later when needed;
* Staff, by hand, earlier or later, with a reason.
Every later move of an existing ETA is recorded by the database trigger (`status_histories`, state_type ETA) with the reason set
through `set_actor`, and added to `orders.eta_postponed_days`, which opens the full-refund cancellation of BR-16 (4d-1).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import eta_rules as er
from app.domain import scheduling_rules as sr
from app.models.account import Account
from app.models.ops import RobotStatus
from app.models.order import Order, OrderStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.services import audit, notifications

log = logging.getLogger("app")

# Orders whose ETA still means something: paid and not delivered or closed yet.
ETA_OPEN = (OrderStatus.CONFIRMED, OrderStatus.AWAITING_ACCEPTANCE, OrderStatus.AWAITING_FINAL_PAYMENT,
            OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EtaService:
    def __init__(self, session: Session, actor: Account | None = None, ip: str | None = None):
        self.session, self.actor, self.ip = session, actor, ip
        self.orders = OrderRepository(session)
        self.catalog = CatalogRepository(session)

    # ---- configuration ----
    def _scheduling(self):
        from app.services.scheduling import SchedulingService      # scheduling imports this module
        return SchedulingService(self.session, self.actor)

    def params(self) -> tuple[sr.WorkCalendar, dict[str, int]]:
        return self._scheduling()._params()

    def threshold(self) -> int:
        return int(self.catalog.setting("eta_cancel_threshold_days", 7))

    # ---- estimate (BR-15) ----
    def estimate(self, order: Order, *, start: datetime | None = None) -> date | None:
        """ETA if the order were confirmed at `start` (default now): earliest free slot of a suitable robot + margin + delivery.
        None when it cannot be estimated (no final sketch, no available robot, no working hours)."""
        sched = self._scheduling()
        try:
            cal, p = sched._params()
            sketch = sched.sketches.final(order.id)
            if sketch is None or sketch.estimated_writing_sec is None:
                return None
            minutes = sr.job_minutes(sketch.estimated_writing_sec, order.quantity, p["prep_min"], p["photo_min"])
            earliest = max(start or _now(), _now())
            robot_busy, _ = sched._busy()
            ends = []
            for robot in sched.robots.list(RobotStatus.AVAILABLE):
                if not sched._robot_fits(robot, order):
                    continue
                try:
                    ends.append(sr.find_slot(cal, earliest, minutes, robot_busy.get(robot.id, []))[1])
                except sr.NoSlotError:
                    continue
            if not ends:
                return None
            finish = er.finish_date(min(ends), p["eta_buffer_days"], cal.tz)
            return er.eta_from(finish, p["eta_delivery_days"])
        except AppError:
            return None

    # ---- the system moves it (never earlier) ----
    def apply(self, order: Order, proposed: date | None, reason: str) -> bool:
        """Set `proposed` when the order has no ETA yet or when it is later than the current one. Returns True when changed."""
        new = er.automatic_change(order.eta, proposed)
        if new is None:
            return False
        old = order.eta
        if old is not None:
            set_actor(self.session, self.actor.id if self.actor else None, reason)       # the trigger requires the reason (BR-16)
        order.eta = new
        self.session.flush()
        if old is not None:
            self.session.refresh(order)
            audit.record(self.session, actor_id=self.actor.id if self.actor else None, action="ETA_POSTPONE",
                         entity_type="order", entity_id=order.id, old={"eta": old.isoformat()},
                         new={"eta": new.isoformat(), "postponed_days": order.eta_postponed_days}, reason=reason, ip=self.ip)
            notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="ETA_POSTPONED", code=order.code,
                                 eta=new.isoformat(), reason=reason)
        return True

    def set_initial(self, order: Order, quoted: date | None) -> None:
        """At deposit success: the order's first ETA. Never raises (it runs inside the payment webhook)."""
        try:
            fresh = self.estimate(order)
        except Exception:                                    # noqa: BLE001 - a payment must never fail because of an estimate
            log.exception("ETA estimate failed for order %s", order.code)
            fresh = None
        candidates = [d for d in (quoted, fresh) if d is not None]
        if candidates:
            self.apply(order, max(candidates), "Ước tính lại thời gian giao khi đặt cọc")

    # ---- Staff (UC-30) ----
    def set_manual(self, order_id: int, new_eta: date, reason: str) -> Order:
        from app.services.workshop_access import WorkshopAccess, not_found
        order = WorkshopAccess(self.session, self.actor).order(order_id, write=True)
        if order.assigned_staff_id != self.actor.id:
            raise not_found()
        order = self.orders.get(order.id, lock=True)
        self.session.refresh(order)
        if order.order_status not in ETA_OPEN:
            raise AppError(409, "ETA_NOT_EDITABLE", "Chỉ đổi ngày giao dự kiến của đơn đã cọc và chưa giao xong.",
                           {"order_status": order.order_status.value})
        cal, _ = self.params()
        try:
            er.check_manual(order.eta, new_eta, _now().astimezone(cal.tz).date())
        except er.EtaRuleError as exc:
            raise AppError(422, exc.code, exc.message) from exc
        old = order.eta
        set_actor(self.session, self.actor.id, reason)
        order.eta = new_eta
        self.session.flush()
        self.session.refresh(order)
        later = old is None or new_eta > old
        audit.record(self.session, actor_id=self.actor.id, action="ETA_POSTPONE" if later else "ETA_ADVANCE",
                     entity_type="order", entity_id=order.id, old={"eta": old.isoformat() if old else None},
                     new={"eta": new_eta.isoformat(), "postponed_days": order.eta_postponed_days}, reason=reason, ip=self.ip)
        notifications.notify(account_id=order.customer_id, order_id=order.id,
                             msg_code="ETA_POSTPONED" if later else "ETA_CHANGED", code=order.code, eta=new_eta.isoformat(),
                             reason=reason)
        return order

    # ---- reading ----
    def history(self, order_id: int) -> list[dict[str, Any]]:
        rows = self.session.execute(text(
            """select old_eta, new_eta, reason, actor_id, created_at from status_histories
               where order_id = :o and state_type = 'ETA' order by created_at, id"""), {"o": order_id})
        return [dict(r._mapping) for r in rows]

    def view(self, order: Order) -> dict[str, Any]:
        threshold = self.threshold()
        days = order.eta_postponed_days or 0
        return {"order_id": order.id, "eta": order.eta, "postponed_days": days, "threshold_days": threshold,
                "can_cancel_full_refund": er.can_cancel_full_refund(days, threshold), "history": self.history(order.id)}
