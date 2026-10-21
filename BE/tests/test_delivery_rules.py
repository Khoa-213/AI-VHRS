"""Phase 4c-1 pure rules: package and fee, what is left to pay, address / phone, pickup appointment. No database."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain import delivery_rules as dr
from app.domain.scheduling_rules import WorkCalendar

D = Decimal
VN = timezone(timedelta(hours=7))
CAL = WorkCalendar.from_setting({"days": [1, 2, 3, 4, 5, 6], "start": "08:00", "end": "17:00", "utc_offset_min": 420})
NOW = datetime(2026, 10, 19, 10, 0, tzinfo=VN)           # a Monday, 10:00 at the workshop


def _code(fn, *a, **kw) -> str:
    with pytest.raises(dr.DeliveryRuleError) as e:
        fn(*a, **kw)
    return e.value.code


# ---- package and fee ---------------------------------------------------------------------------------
def test_package_follows_the_paper_size():
    assert dr.package_type("A6") == dr.package_type("A5") == "FLAT_BOX_A5"
    assert dr.package_type("A4") == "FLAT_BOX_A4"
    assert _code(dr.package_type, "A3") == "PACKAGE_UNKNOWN"              # more than A4 is outside the project (LI-06)


def test_fee_comes_from_the_table_and_a_bad_entry_is_never_zero():
    table = {"FLAT_BOX_A5": 25000, "FLAT_BOX_A4": "30000", "TUBE": 45000.0}
    assert dr.shipping_fee(table, "FLAT_BOX_A5") == D(25000)
    assert dr.shipping_fee(table, "FLAT_BOX_A4") == D(30000)               # settings may store numbers as text
    assert dr.shipping_fee(table, "TUBE") == D(45000)
    for bad in (None, [], {}, {"FLAT_BOX_A5": None}, {"FLAT_BOX_A5": True}, {"FLAT_BOX_A5": "abc"},
                {"FLAT_BOX_A5": -100}, {"FLAT_BOX_A5": 25050}, {"FLAT_BOX_A5": [1]}):
        assert _code(dr.shipping_fee, bad, "FLAT_BOX_A5") == "SHIPPING_FEE_UNAVAILABLE", bad


# ---- (G - D) + F_ship --------------------------------------------------------------------------------
def test_amount_due_is_the_rest_plus_shipping():
    due = dr.amount_due(D(399600), D(199800), "DELIVERY", D(30000))        # the SRS worked example, 2nd instalment
    assert (due.final, due.shipping, due.total) == (D(199800), D(30000), D(229800))
    pickup = dr.amount_due(D(399600), D(199800), "PICKUP", D(30000))
    assert (pickup.final, pickup.shipping, pickup.total) == (D(199800), D(0), D(199800))   # BR-12: no shipping at the workshop


def test_nothing_left_to_pay_gives_zero_parts():
    full = dr.amount_due(D(399600), D(399600), "PICKUP", D(30000))
    assert full.total == 0 and full.final == 0
    shipping_only = dr.amount_due(D(399600), D(399600), "DELIVERY", D(30000))   # deposit 100 %, still pays the carrier
    assert (shipping_only.final, shipping_only.shipping) == (D(0), D(30000))


@pytest.mark.parametrize("total,deposit,method", [(None, D(1), "PICKUP"), (D(100), None, "PICKUP"), (D(0), D(0), "PICKUP"),
                                                  (D(1000), D(0), "PICKUP"), (D(1000), D(1100), "PICKUP"),
                                                  (D(1000), D(500), "COD")])
def test_amount_due_refuses_nonsense(total, deposit, method):
    with pytest.raises(dr.DeliveryRuleError):
        dr.amount_due(total, deposit, method, D(0))


# ---- address and contact ------------------------------------------------------------------------------
GOOD = {"receiver": " An ", "phone": "0901234567", "street": "1 Lê Lợi", "province_code": "79",
        "district_code": "760", "ward_code": "26734", "label": "Nhà", "extra": "ignored"}


def test_address_is_checked_trimmed_and_limited_to_known_fields():
    clean = dr.check_address(GOOD)
    assert clean["receiver"] == "An" and clean["label"] == "Nhà" and "extra" not in clean
    for field in dr.ADDRESS_FIELDS:
        with pytest.raises(dr.DeliveryRuleError) as e:
            dr.check_address({**GOOD, field: "  "})
        assert e.value.code == "INVALID_ADDRESS" and e.value.details == {"missing": [field]}
    assert _code(dr.check_address, {}) == "INVALID_ADDRESS"


def test_phone_numbers_compare_by_digits_not_by_spelling():
    assert dr.normalize_phone("+84 901 234 567") == dr.normalize_phone("0901.234.567") == "0901234567"
    assert dr.phones_match("0901234567", "+84901234567") and dr.phones_match(" 090-123-4567", "0901234567")
    assert not dr.phones_match("0901234567", "0901234568")
    assert not dr.phones_match("", "") and not dr.phones_match(None, "0901234567") and not dr.phones_match("0901234567", None)


# ---- pickup appointment -------------------------------------------------------------------------------
def _slot(day_offset: int, start_h: int, minutes: int, start_m: int = 0):
    start = (NOW + timedelta(days=day_offset)).replace(hour=start_h, minute=start_m)
    return start, start + timedelta(minutes=minutes)


def test_pickup_slot_inside_working_hours_is_accepted():
    for args in ((1, 9, 60), (0, 14, 30), (5, 8, 15), (1, 15, 120), (1, 8, 240)):
        dr.check_pickup_slot(*_slot(*args), NOW, CAL)
    dr.check_pickup_slot(*_slot(1, 16, 60), NOW, CAL)                       # ends exactly at closing time


@pytest.mark.parametrize("args,code", [
    ((1, 9, 10), "INVALID_SLOT"), ((1, 9, 241), "INVALID_SLOT"),            # too short / too long
    ((0, 9, 60), "SLOT_IN_PAST"), ((-1, 14, 60), "SLOT_IN_PAST"),
    ((31, 9, 60), "SLOT_TOO_FAR"),
    ((1, 7, 60), "OUTSIDE_WORKING_HOURS"), ((1, 16, 90), "OUTSIDE_WORKING_HOURS"),   # starts early / ends after 17:00
    ((1, 17, 30), "OUTSIDE_WORKING_HOURS"), ((1, 12, 15), None),
    ((6, 9, 60), "OUTSIDE_WORKING_HOURS"),                                  # Sunday: the workshop is closed
])
def test_pickup_slot_rules(args, code):
    start, end = _slot(*args)
    if code is None:
        dr.check_pickup_slot(start, end, NOW, CAL)
    else:
        assert _code(dr.check_pickup_slot, start, end, NOW, CAL) == code


def test_pickup_slot_needs_timezone_and_order():
    start, end = _slot(1, 9, 60)
    assert _code(dr.check_pickup_slot, start.replace(tzinfo=None), end, NOW, CAL) == "INVALID_SLOT"
    assert _code(dr.check_pickup_slot, start, end.replace(tzinfo=None), NOW, CAL) == "INVALID_SLOT"
    assert _code(dr.check_pickup_slot, end, start, NOW, CAL) == "INVALID_SLOT"
    assert _code(dr.check_pickup_slot, start, start, NOW, CAL) == "INVALID_SLOT"


def test_the_slot_is_judged_in_the_workshop_timezone_not_the_callers():
    day = (NOW + timedelta(days=1)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    utc = lambda h: day.replace(hour=h, minute=0)                            # noqa: E731
    dr.check_pickup_slot(utc(2), utc(3), NOW, CAL)                            # 02:00-03:00 UTC = 09:00-10:00 at the workshop
    dr.check_pickup_slot(utc(9), utc(10), NOW, CAL)                           # 16:00-17:00 local: ends exactly at closing
    assert _code(dr.check_pickup_slot, utc(10), utc(11), NOW, CAL) == "OUTSIDE_WORKING_HOURS"   # 17:00-18:00 local
    assert _code(dr.check_pickup_slot, utc(0), utc(1), NOW, CAL) == "OUTSIDE_WORKING_HOURS"     # 07:00-08:00 local
