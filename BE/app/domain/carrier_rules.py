"""Pure rules for carriers and waybills (FR-21, FR-22, UC-29, BR-12). No DB, no I/O.

The carriers (GHN, GHTK) each have their own status vocabulary; here they are mapped onto the system's `shipment_status`, and
the rules for which moves a waybill may make and what a move means for the order are kept in one place. A carrier's callbacks
arrive repeated and out of order, so every move is judged against the current status and an old or repeated one is ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.models.ops import ShipmentStatus as S


# ---------------------------------------------------------------------------------------------- shared value objects
@dataclass(frozen=True)
class Parcel:
    package_type: str
    weight_g: int
    length_cm: int
    width_cm: int
    height_cm: int
    value: int = 0                # declared value (insurance), VND


@dataclass(frozen=True)
class ServiceQuote:
    carrier: str
    service_code: str
    service_name: str
    fee: int                      # VND, multiple of 100
    eta: datetime | None
    is_fallback: bool = False     # True: from the fallback fee table, not from the carrier's API
    mode: str = "MOCK"


@dataclass(frozen=True)
class Waybill:
    code: str
    fee: int | None = None        # what the carrier charges the workshop, when it says so
    eta: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingEvent:
    waybill_code: str
    raw_status: str
    status: S | None              # None = informational only, nothing to apply
    occurred_at: datetime | None = None
    reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CarrierRuleError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


# ---------------------------------------------------------------------------------------------- waybill state machine
_MOVES: dict[S, frozenset[S]] = {
    S.CREATED: frozenset({S.PICKED_UP, S.DELIVERING, S.DELIVERED, S.FAILED, S.RETURNED, S.CANCELLED}),
    S.PICKED_UP: frozenset({S.DELIVERING, S.DELIVERED, S.FAILED, S.RETURNED}),
    S.DELIVERING: frozenset({S.DELIVERED, S.FAILED, S.RETURNED}),
    S.FAILED: frozenset({S.DELIVERING, S.DELIVERED, S.RETURNED}),         # a second delivery attempt may still succeed
    S.DELIVERED: frozenset(),
    S.RETURNED: frozenset(),
    S.CANCELLED: frozenset(),
}
TERMINAL = frozenset({S.DELIVERED, S.RETURNED, S.CANCELLED})


def can_move(old: S, new: S) -> bool:
    return new in _MOVES.get(old, frozenset())


def order_effect(new: S) -> str | None:
    """What a waybill status means for the order: DELIVERING once the carrier has the parcel, COMPLETED when it is delivered."""
    if new in (S.PICKED_UP, S.DELIVERING):
        return "DELIVERING"
    if new == S.DELIVERED:
        return "COMPLETED"
    return None


# ---------------------------------------------------------------------------------------------- carrier vocabularies
# GHN order status (webhook `Status` / order detail). Only `delivered` is final on GHN's side.
GHN_STATUS: dict[str, S] = {
    "ready_to_pick": S.CREATED, "picking": S.CREATED, "money_collect_picking": S.CREATED,
    "picked": S.PICKED_UP,
    "storing": S.DELIVERING, "transporting": S.DELIVERING, "sorting": S.DELIVERING, "delivering": S.DELIVERING,
    "money_collect_delivering": S.DELIVERING,
    "delivered": S.DELIVERED,
    "delivery_fail": S.FAILED, "waiting_to_return": S.FAILED, "return": S.FAILED, "return_transporting": S.FAILED,
    "return_sorting": S.FAILED, "returning": S.FAILED, "return_fail": S.FAILED, "exception": S.FAILED,
    "damage": S.FAILED, "lost": S.FAILED,
    "returned": S.RETURNED,
    "cancel": S.CANCELLED,
}
# GHTK `status_id`. The shipper-reported ids (123, 127, 128, 45, 49, 410) are informational and may be corrected: ignored.
GHTK_STATUS: dict[int, S] = {
    -1: S.CANCELLED, 1: S.CREATED, 2: S.CREATED, 12: S.CREATED, 8: S.CREATED,
    3: S.PICKED_UP,
    4: S.DELIVERING, 10: S.DELIVERING,
    5: S.DELIVERED, 6: S.DELIVERED, 11: S.DELIVERED,
    7: S.FAILED, 9: S.FAILED, 13: S.FAILED, 20: S.FAILED,
    21: S.RETURNED,
}


def map_ghn_status(raw: str | None) -> S | None:
    return GHN_STATUS.get(str(raw or "").strip().lower())


def map_ghtk_status(status_id: Any) -> S | None:
    try:
        return GHTK_STATUS.get(int(status_id))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------- the parcel (FR-21)
# ASSUMPTIONS (SRS: "kích thước gói suy ra từ khổ giấy và số bản"): a flat box per paper size, sheets weigh area x gsm.
_PAPER_MM = {"A6": (105, 148), "A5": (148, 210), "A4": (210, 297)}                 # same sizes as the trajectory pages
BOX = {"FLAT_BOX_A5": (23, 17, 3, 60), "FLAT_BOX_A4": (32, 23, 3, 90)}             # length, width, height (cm), tare (g)
DECLARED_VALUE_CAP = 5_000_000


def parcel_for(package_type: str, paper_size: str, gsm: int, sheets: int, order_total: Decimal | int) -> Parcel:
    if package_type not in BOX:
        raise CarrierRuleError("PACKAGE_UNKNOWN", f"Chưa có kích thước cho loại gói {package_type}.")
    if paper_size not in _PAPER_MM:
        raise CarrierRuleError("PACKAGE_UNKNOWN", f"Chưa có khổ giấy {paper_size}.")
    w, h = _PAPER_MM[paper_size]
    length, width, height, tare = BOX[package_type]
    grams = math.ceil(w * h / 1_000_000 * max(gsm, 1) * max(sheets, 1)) + tare
    return Parcel(package_type=package_type, weight_g=grams, length_cm=length, width_cm=width, height_cm=height,
                  value=min(int(order_total or 0), DECLARED_VALUE_CAP))


def round_up_100(value: float | Decimal) -> int:
    return int(math.ceil(float(value) / 100.0) * 100)


# ---------------------------------------------------------------------------------------------- MOCK service catalogue
# What the simulated carriers offer. Prices are derived from the fallback table so nothing is invented out of thin air, and
# every quote carries mode="MOCK". Replaced by the carriers' own answers when their real adapters are switched on.
MOCK_SERVICES: dict[str, list[tuple[str, str, float, int]]] = {
    "GHN": [("STANDARD", "Giao tiêu chuẩn", 1.0, 3), ("EXPRESS", "Giao nhanh", 1.4, 1)],
    "GHTK": [("ROAD", "Đường bộ", 0.9, 4), ("FAST", "Giao nhanh", 1.5, 2)],
}


def mock_services(carrier: str, base_fee: Decimal | int, now: datetime) -> list[ServiceQuote]:
    return [ServiceQuote(carrier=carrier, service_code=code, service_name=name, fee=round_up_100(Decimal(base_fee) * Decimal(str(k))),
                         eta=now + timedelta(days=days), mode="MOCK")
            for code, name, k, days in MOCK_SERVICES[carrier]]


def fallback_quote(carrier: str, base_fee: Decimal | int) -> ServiceQuote:
    """The single option shown for a carrier whose API is off: the fallback table fee, no delivery estimate."""
    return ServiceQuote(carrier=carrier, service_code="STANDARD", service_name="Giao tiêu chuẩn (phí dự phòng)",
                        fee=int(base_fee), eta=None, is_fallback=True, mode="FALLBACK")


def pick_service(quotes: list[ServiceQuote], carrier: str | None, service_code: str | None) -> ServiceQuote:
    """The customer's choice must be one of the quotes just offered. No choice = the cheapest, so a client that does not know
    about services still gets a working order (ties: the faster one, then the carrier's name)."""
    if carrier is None and service_code is None:
        if not quotes:
            raise CarrierRuleError("SERVICE_NOT_AVAILABLE", "Hiện chưa có dịch vụ vận chuyển nào.")
        return min(quotes, key=lambda q: (q.fee, q.eta.timestamp() if q.eta else float("inf"), q.carrier, q.service_code))
    if carrier is None or service_code is None:
        raise CarrierRuleError("SERVICE_NOT_AVAILABLE", "Cần chọn cả hãng và dịch vụ vận chuyển.")
    found = next((q for q in quotes if q.carrier == carrier and q.service_code == service_code), None)
    if found is None:
        raise CarrierRuleError("SERVICE_NOT_AVAILABLE", "Dịch vụ vận chuyển đã chọn không còn khả dụng.",
                               {"carrier": carrier, "service_code": service_code})
    return found
