"""Pure rules for the final payment and the way the customer gets the product (FR-18, FR-21, FR-23, BR-11, BR-12). No DB, no I/O.

After acceptance the customer pays ONE time what is left of the order plus the shipping fee: (G - D) + F_ship, recorded as two
Payment rows (FINAL and SHIPPING). Collecting at the workshop costs no shipping (BR-12) and has no SHIPPING row. A part that
is 0 gets no row at all (payments.amount must be > 0); when nothing is left to pay the order moves on without a payment.

The shipping fee here comes from the fallback table in `system_settings.fallback_shipping_fees` (the table FR-21 asks for when the
carrier API is down). The carrier adapter that quotes real fees arrives in Phase 4c-2 and plugs in at the same place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.domain.scheduling_rules import WorkCalendar


class DeliveryRuleError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


# ---------------------------------------------------------------------------------------------- assumptions (kept in one place)
# SRS FR-21: "hộp phẳng A5/A4, ống cứng cho poster". The paper is at most A4 (LI-06), so no poster tube is ever needed here.
PACKAGE_BY_PAPER = {"A6": "FLAT_BOX_A5", "A5": "FLAT_BOX_A5", "A4": "FLAT_BOX_A4"}
PICKUP_MIN_MINUTES, PICKUP_MAX_MINUTES = 15, 240      # length of the appointment window
PICKUP_HORIZON_DAYS = 30                              # how far ahead a pickup can be booked
MONEY_STEP = Decimal(100)
ADDRESS_FIELDS = ("receiver", "phone", "street", "province_code", "district_code", "ward_code")
_DIGITS = re.compile(r"\D+")


# ---------------------------------------------------------------------------------------------- package and fee
def package_type(paper_size: str) -> str:
    try:
        return PACKAGE_BY_PAPER[paper_size]
    except KeyError as exc:
        raise DeliveryRuleError("PACKAGE_UNKNOWN", f"Chưa có loại gói cho khổ giấy {paper_size}.") from exc


def shipping_fee(table: Any, package: str) -> Decimal:
    """Fee of one package from the fallback table. A missing or malformed entry is a configuration error, never 0."""
    value = table.get(package) if isinstance(table, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise DeliveryRuleError("SHIPPING_FEE_UNAVAILABLE", "Chưa cấu hình phí vận chuyển cho loại gói này.")
    try:
        fee = Decimal(str(value))
    except ArithmeticError as exc:
        raise DeliveryRuleError("SHIPPING_FEE_UNAVAILABLE", "Phí vận chuyển cấu hình không hợp lệ.") from exc
    if fee < 0 or fee % MONEY_STEP != 0:
        raise DeliveryRuleError("SHIPPING_FEE_UNAVAILABLE", "Phí vận chuyển phải là số không âm, bội của 100đ.")
    return fee


# ---------------------------------------------------------------------------------------------- amounts
@dataclass(frozen=True)
class AmountDue:
    final: Decimal       # (G - D): the FINAL payment row
    shipping: Decimal    # F_ship: the SHIPPING row (0 when collecting at the workshop)

    @property
    def total(self) -> Decimal:
        return self.final + self.shipping


def amount_due(total_amount: Decimal, deposit_amount: Decimal, method: str, fee: Decimal) -> AmountDue:
    """BR-11 / FR-18: what the customer still owes before the order may be handed over."""
    if total_amount is None or deposit_amount is None or total_amount <= 0 or not 0 < deposit_amount <= total_amount:
        raise DeliveryRuleError("ORDER_AMOUNTS_INVALID", "Đơn chưa có tổng tiền và tiền cọc hợp lệ.")
    if method not in ("DELIVERY", "PICKUP"):
        raise DeliveryRuleError("INVALID_DELIVERY_METHOD", "Hình thức nhận hàng không hợp lệ.")
    return AmountDue(final=total_amount - deposit_amount, shipping=fee if method == "DELIVERY" else Decimal(0))


# ---------------------------------------------------------------------------------------------- address and contact
def check_address(address: dict[str, Any]) -> dict[str, Any]:
    """The delivery address snapshot stored on the order: codes follow the carrier's location tables (FR-02)."""
    clean: dict[str, Any] = {k: str(address.get(k) or "").strip() for k in ADDRESS_FIELDS}
    missing = [k for k, v in clean.items() if not v]
    if missing:
        raise DeliveryRuleError("INVALID_ADDRESS", "Địa chỉ giao hàng thiếu thông tin.", {"missing": missing})
    if address.get("label"):
        clean["label"] = str(address["label"]).strip()[:50]
    return clean


def normalize_phone(phone: str | None) -> str:
    """Digits only, with the +84 / 84 prefix written as the leading 0 (0901234567 == +84 901 234 567)."""
    digits = _DIGITS.sub("", phone or "")
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_phone(a), normalize_phone(b)
    return bool(na) and na == nb


# ---------------------------------------------------------------------------------------------- pickup appointment (FR-23)
def check_pickup_slot(start: datetime, end: datetime, now: datetime, calendar: WorkCalendar) -> None:
    """The appointment lies inside one working day of the workshop, in the future, not too far ahead."""
    if start.tzinfo is None or end.tzinfo is None:
        raise DeliveryRuleError("INVALID_SLOT", "Khung giờ nhận hàng phải có múi giờ.")
    if end <= start:
        raise DeliveryRuleError("INVALID_SLOT", "Giờ kết thúc phải sau giờ bắt đầu.")
    minutes = (end - start).total_seconds() / 60
    if not PICKUP_MIN_MINUTES <= minutes <= PICKUP_MAX_MINUTES:
        raise DeliveryRuleError("INVALID_SLOT", f"Khung giờ nhận hàng dài {PICKUP_MIN_MINUTES}–{PICKUP_MAX_MINUTES} phút.")
    if start < now:
        raise DeliveryRuleError("SLOT_IN_PAST", "Không thể hẹn nhận hàng vào thời điểm đã qua.")
    if start > now + timedelta(days=PICKUP_HORIZON_DAYS):
        raise DeliveryRuleError("SLOT_TOO_FAR", f"Chỉ hẹn được trong vòng {PICKUP_HORIZON_DAYS} ngày.")
    if calendar.next_open(start) != start.astimezone(calendar.tz) or end > calendar.day_end(start):
        raise DeliveryRuleError("OUTSIDE_WORKING_HOURS", "Khung giờ nhận hàng phải nằm trong giờ làm việc của xưởng.")
