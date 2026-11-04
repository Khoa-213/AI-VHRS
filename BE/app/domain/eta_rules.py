"""ETA: the latest date the customer should have the product (BR-15, BR-16, FR-26). Pure rules, no database.

BR-15: ETA = the day the deposit succeeds + the wait for the robot (the earliest free slot of a suitable robot) + a margin for
photos / QC / acceptance (`schedule_params.eta_buffer_days`) + the carrier's delivery time (`schedule_params.eta_delivery_days`
until the customer picks a carrier service, then that service's own estimate).

The system only ever moves the ETA LATER on its own (the schedule, an incident, a rewrite or the carrier needs more time); every
such move is a postponement with a reason, which the database adds up in `orders.eta_postponed_days` (BR-16). The first ETA of
an order is set when the deposit succeeds and is not a postponement: a customer paying a few days after the quotation moves it,
the workshop did not. Staff may also set it by hand, earlier or later, always with a reason.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo

DEFAULT_DELIVERY_DAYS = 3          # owner's decision 2026-11-04: until a carrier service is chosen
MAX_MANUAL_DAYS_AHEAD = 365


class EtaRuleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def finish_date(slot_end: datetime, buffer_days: int, tz: tzinfo) -> date:
    """Day the product should be accepted and ready to ship: end of the writing slot + the margin, in the workshop's time zone."""
    return (slot_end + timedelta(days=max(buffer_days, 0))).astimezone(tz).date()


def eta_from(finish: date, delivery_days: int) -> date:
    return finish + timedelta(days=max(delivery_days, 0))


def carrier_eta(shipping_eta: datetime, finish: date, tz: tzinfo) -> date:
    """The carrier's estimate is a delivery moment counted from today; never earlier than the day the product is ready."""
    return max(shipping_eta.astimezone(tz).date(), finish)


def automatic_change(current: date | None, proposed: date | None) -> date | None:
    """New ETA the system should set, or None to leave it. It never pulls an ETA earlier on its own."""
    if proposed is None:
        return None
    if current is None or proposed > current:
        return proposed
    return None


def check_manual(current: date | None, new: date, today: date) -> None:
    if new < today:
        raise EtaRuleError("ETA_IN_PAST", "Ngày giao dự kiến không được ở quá khứ.")
    if new > today + timedelta(days=MAX_MANUAL_DAYS_AHEAD):
        raise EtaRuleError("ETA_TOO_FAR", "Ngày giao dự kiến quá xa (tối đa 1 năm).")
    if current is not None and new == current:
        raise EtaRuleError("ETA_UNCHANGED", "Ngày giao dự kiến không đổi.")


def can_cancel_full_refund(postponed_days: int, threshold_days: int) -> bool:
    return postponed_days > threshold_days
