"""Cancelling a paid order and how much comes back (BR-14, BR-16, FR-19). Pure rules, no database.

BR-14: before the order is scheduled -> 100 % of the deposit; scheduled but not written yet (SCHEDULED, PREPARING) -> the
deposit minus the setup fee S_type of the approved quotation, never below 0; once writing has started -> no cancellation,
unless BR-16: the ETA was postponed by more than `eta_cancel_threshold_days` in total -> 100 % of everything paid.
The workshop cancelling on its own initiative (it cannot make the order) always refunds 100 % of what was paid; it is still
bound by the same "not after writing started" line, which the database trigger enforces for everyone.

"Writing started" covers the order's current production state AND any earlier job that began writing (a rewrite puts the
order back to PENDING_SCHEDULE / SCHEDULED, but the sheet was already written once: that is not a free cancellation).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

# Order states the customer cancels without any refund because nothing was paid (handled by OrderService.cancel).
UNPAID_CANCELLABLE = frozenset({"SUBMITTED", "NEED_INFO", "QUOTED", "AWAITING_DEPOSIT"})
BEFORE_SCHEDULE = frozenset({"NOT_STARTED", "PENDING_SCHEDULE"})
SCHEDULED_NOT_WRITTEN = frozenset({"SCHEDULED", "PREPARING"})
WRITING_STARTED = frozenset({"WRITING", "PAUSED", "WRITTEN", "PHOTO_UPLOADED", "REWRITE_REQUIRED", "FAILED"})


class Initiator(str, Enum):
    CUSTOMER = "CUSTOMER"
    WORKSHOP = "WORKSHOP"


class Rule(str, Enum):
    NO_PAYMENT = "NO_PAYMENT"                         # cancelled before any money was paid
    BR14_BEFORE_SCHEDULE = "BR14_BEFORE_SCHEDULE"     # 100 % of the deposit
    BR14_AFTER_SCHEDULE = "BR14_AFTER_SCHEDULE"       # deposit minus the setup fee
    BR16_ETA_POSTPONED = "BR16_ETA_POSTPONED"         # 100 % of everything paid
    WORKSHOP_CANCEL = "WORKSHOP_CANCEL"               # the workshop cancels: 100 % of everything paid


@dataclass(frozen=True)
class CancelFacts:
    order_status: str
    production_status: str
    paid: Decimal                    # money received for the order and not refunded yet (deposit while CONFIRMED)
    setup_fee: Decimal               # S_type from the approved quotation's price snapshot
    eta_postponed_days: int
    threshold_days: int              # system_settings.eta_cancel_threshold_days (BR-16)
    wrote_before: bool = False       # an earlier job of this order already started writing


@dataclass(frozen=True)
class CancelDecision:
    allowed: bool
    rule: Rule | None
    refund_amount: Decimal
    deduction: Decimal               # what is kept (the setup fee under BR14_AFTER_SCHEDULE)
    error_code: str | None = None    # why not, when not allowed
    message: str = ""


def _no(code: str, message: str) -> CancelDecision:
    return CancelDecision(False, None, Decimal(0), Decimal(0), code, message)


def decide(facts: CancelFacts, initiator: Initiator) -> CancelDecision:
    status, prod = facts.order_status, facts.production_status
    if status in UNPAID_CANCELLABLE:
        if initiator == Initiator.WORKSHOP:
            return _no("ORDER_CANCEL_UNSUPPORTED", "Đơn chưa đặt cọc: xưởng dùng chức năng từ chối đơn, không huỷ.")
        return CancelDecision(True, Rule.NO_PAYMENT, Decimal(0), Decimal(0), message="Đơn chưa thanh toán, huỷ không mất phí.")
    if status != "CONFIRMED":
        return _no("ORDER_CANCEL_UNSUPPORTED", "Đơn ở trạng thái này không huỷ được.")
    paid = max(facts.paid, Decimal(0))
    started = prod in WRITING_STARTED or facts.wrote_before
    if prod == "WRITING":
        return _no("JOB_RUNNING", "Robot đang viết đơn này. Chờ job tạm dừng hoặc kết thúc rồi mới huỷ được.")
    if started:
        if facts.eta_postponed_days > facts.threshold_days:
            return CancelDecision(True, Rule.BR16_ETA_POSTPONED, paid, Decimal(0),
                                  message=f"Thời gian giao đã dời {facts.eta_postponed_days} ngày (quá "
                                          f"{facts.threshold_days} ngày): huỷ và hoàn 100% số đã thanh toán (BR-16).")
        return _no("CANCEL_AFTER_WRITING_STARTED", "Đơn đã bắt đầu viết nên không huỷ được (BR-14).")
    if initiator == Initiator.WORKSHOP:
        return CancelDecision(True, Rule.WORKSHOP_CANCEL, paid, Decimal(0),
                              message="Xưởng huỷ đơn: hoàn 100% số đã thanh toán.")
    if prod in BEFORE_SCHEDULE:
        return CancelDecision(True, Rule.BR14_BEFORE_SCHEDULE, paid, Decimal(0),
                              message="Đơn chưa xếp lịch sản xuất: hoàn 100% tiền cọc (BR-14).")
    if prod in SCHEDULED_NOT_WRITTEN:
        kept = min(max(facts.setup_fee, Decimal(0)), paid)
        return CancelDecision(True, Rule.BR14_AFTER_SCHEDULE, paid - kept, kept,
                              message="Đơn đã xếp lịch nhưng chưa viết: hoàn tiền cọc trừ phí setup (BR-14).")
    return _no("ORDER_CANCEL_UNSUPPORTED", "Đơn ở trạng thái này không huỷ được.")


def mask_account(number: str | None) -> str | None:
    """Show the customer only the last 4 digits of the account they gave for the refund."""
    if not number:
        return number
    return "•" * max(len(number) - 4, 0) + number[-4:]
