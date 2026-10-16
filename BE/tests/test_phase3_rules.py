"""Pure Phase 3 rules: deposit amount (BR-10), pricing-config validation (FR-30), working calendar and slot
search (FR-37, FR-40, BR-18), mock gateway signature. No database."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain import pricing_config_rules as pcr
from app.domain import scheduling_rules as sr
from app.domain.payment_rules import DepositError, resolve_deposit
from app.integrations.payment_gateway import MockGateway, webhook_body

D = Decimal
ICT = timezone(timedelta(hours=7))


# ---- deposit ------------------------------------------------------------------------------------------
def test_deposit_default_is_the_minimum_and_matches_the_srs_example():
    assert resolve_deposit(D(399600), D(50), None) == (D(50), D(199800))


def test_deposit_rounds_up_to_100_and_never_below_the_minimum():
    pct, amount = resolve_deposit(D(399700), D(50), None)
    assert amount == D(199900) and amount >= D(399700) * D(50) / 100


@pytest.mark.parametrize("pct,expected", [("50", 199800), ("70", 279720 + 80), ("100", 399600)])
def test_deposit_custom_percentage(pct, expected):
    p, amount = resolve_deposit(D(399600), D(50), D(pct))
    assert p == D(pct).quantize(D("0.01")) and amount == D(expected) and amount % 100 == 0


@pytest.mark.parametrize("pct", ["49.99", "0", "-1", "100.01"])
def test_deposit_out_of_range(pct):
    with pytest.raises(DepositError):
        resolve_deposit(D(399600), D(50), D(pct))


def test_deposit_requires_positive_total():
    with pytest.raises(DepositError):
        resolve_deposit(D(0), D(50), None)


# ---- pricing configuration ----------------------------------------------------------------------------
GOOD = {"u_ot1": 300, "u_ot2": 300, "u_ot3": 300, "w_min": 50000, "s_ot1": 100000, "s_ot2": 100000, "s_ot3": 100000,
        "k_simple": "1.00", "k_medium": "1.30", "k_complex": "1.60", "p_min_pct": "50", "adjust_threshold_pct": "15",
        "canvas_mm_per_char": "40", "discount_tiers": [{"min_qty": 10, "pct": 5}, {"min_qty": 50, "pct": 10}]}


def test_pricing_config_valid():
    assert pcr.validate(GOOD) == []


@pytest.mark.parametrize("patch,field", [
    ({"u_ot1": 250}, "u_ot1"),                                    # not a multiple of 100
    ({"w_min": -100}, "w_min"),
    ({"k_medium": "0.90"}, "k_simple"),                           # K must not decrease
    ({"p_min_pct": "0"}, "p_min_pct"),
    ({"p_min_pct": "101"}, "p_min_pct"),
    ({"adjust_threshold_pct": "100.5"}, "adjust_threshold_pct"),
    ({"canvas_mm_per_char": "0"}, "canvas_mm_per_char"),
    ({"discount_tiers": [{"min_qty": 10, "pct": 10}, {"min_qty": 50, "pct": 5}]}, "discount_tiers"),
    ({"discount_tiers": [{"min_qty": 10, "pct": 5}, {"min_qty": 10, "pct": 6}]}, "discount_tiers"),
    ({"discount_tiers": [{"min_qty": 1, "pct": 5}]}, "discount_tiers"),
    ({"discount_tiers": [{"min_qty": 10, "pct": 100}]}, "discount_tiers"),
])
def test_pricing_config_rejects(patch, field):
    assert field in {p["field"] for p in pcr.validate({**GOOD, **patch})}


def test_pricing_threshold_zero_means_manager_approves_every_change():
    assert pcr.validate({**GOOD, "adjust_threshold_pct": "0"}) == []


# ---- working calendar ---------------------------------------------------------------------------------
CAL = sr.WorkCalendar.from_setting(None)          # Mon-Sat 08:00-17:00, UTC+7
FRI = datetime(2026, 10, 16)                      # a Friday


def at(day_offset: int, hh: int, mm: int = 0) -> datetime:
    return (FRI + timedelta(days=day_offset)).replace(hour=hh, minute=mm, tzinfo=ICT)


def test_next_open_inside_before_and_after_hours():
    assert CAL.next_open(at(0, 10)) == at(0, 10)
    assert CAL.next_open(at(0, 6)) == at(0, 8)
    assert CAL.next_open(at(0, 18)) == at(1, 8)                    # Friday evening -> Saturday morning
    assert CAL.next_open(at(1, 18)) == at(3, 8)                    # Saturday evening -> Monday (Sunday is closed)
    assert CAL.next_open(at(2, 9)) == at(3, 8)                     # Sunday -> Monday


def test_next_open_accepts_utc_input():
    assert CAL.next_open(at(0, 1).astimezone(timezone.utc)) == at(0, 8)   # 01:00 ICT


def test_add_working_minutes_wraps_over_the_night_and_the_closed_day():
    assert CAL.add_working_minutes(at(0, 16), 30) == at(0, 16, 30)
    assert CAL.add_working_minutes(at(0, 16), 120) == at(1, 9)             # 60' Fri + 60' Sat
    assert CAL.add_working_minutes(at(1, 16), 120) == at(3, 9)             # Sat -> Mon (Sunday closed)
    assert CAL.add_working_minutes(at(0, 8), 9 * 60) == at(0, 17)          # exactly one full day


def test_calendar_setting_validation():
    with pytest.raises(ValueError):
        sr.WorkCalendar.from_setting({"days": []})
    with pytest.raises(ValueError):
        sr.WorkCalendar.from_setting({"start": "17:00", "end": "08:00"})
    with pytest.raises(ValueError):
        sr.WorkCalendar.from_setting({"days": [8]})


# ---- duration, overlap, slot search -------------------------------------------------------------------
def test_job_minutes_follows_fr40():
    assert sr.job_minutes(600, 3) == 30 + 15 + 5                  # 10 min x 3 copies + prepare + photo
    assert sr.job_minutes(61, 1) == 2 + 20                        # writing time rounds up to whole minutes
    assert sr.job_minutes(0, 1) == 1 + 20                         # never zero writing time


def test_overlap_is_half_open():
    a = (at(0, 8), at(0, 9))
    assert not sr.overlaps(a, (at(0, 9), at(0, 10)))              # back-to-back jobs are fine
    assert sr.overlaps(a, (at(0, 8, 59), at(0, 10)))
    assert sr.overlaps((at(0, 7), at(0, 12)), a)


def test_find_slot_takes_the_first_gap():
    busy = [(at(0, 8), at(0, 12))]
    assert sr.find_slot(CAL, at(0, 8), 60, busy) == (at(0, 12), at(0, 13))
    assert sr.find_slot(CAL, at(0, 8), 60, []) == (at(0, 8), at(0, 9))


def test_find_slot_skips_a_gap_that_is_too_short():
    busy = [(at(0, 8), at(0, 10)), (at(0, 10, 30), at(0, 12))]
    assert sr.find_slot(CAL, at(0, 8), 60, busy)[0] == at(0, 12)           # the 30' gap does not fit 60'


def test_find_slot_rounds_start_up_to_five_minutes_and_uses_working_time():
    start, end = sr.find_slot(CAL, at(0, 16, 58), 120, [])
    assert start == at(0, 17) - timedelta(hours=9) + timedelta(days=1) and end == at(1, 10)   # 17:00 is closed


def test_find_slot_long_job_blocks_following_days():
    start, end = sr.find_slot(CAL, at(0, 8), 20 * 60, [])
    assert start == at(0, 8) and end == at(3, 10)                  # Fri 9h + Sat 9h + Mon 2h (Sunday is closed)
    other = sr.find_slot(CAL, at(0, 8), 60, [(start, end)])
    assert other[0] >= end


def test_find_slot_gives_up_beyond_the_horizon():
    forever = [(at(0, 0), at(0, 0) + timedelta(days=sr.HORIZON_DAYS + 5))]
    with pytest.raises(sr.NoSlotError):
        sr.find_slot(CAL, at(0, 8), 60, forever)


# ---- mock gateway signature ---------------------------------------------------------------------------
def test_mock_gateway_signature_roundtrip(monkeypatch):
    g = MockGateway()
    body = webhook_body(txn_id="MOCK-VNPAY-1", order_code="VHRS-1", amount=199800, result="SUCCESS", paid_at=None)
    sig = g.sign(body)
    assert g.verify(body, sig) and g.verify(body, sig.upper())
    assert not g.verify(body + b" ", sig)
    assert not g.verify(body, None) and not g.verify(body, "") and not g.verify(body, "0" * 64)


def test_webhook_body_is_canonical():
    a = webhook_body(txn_id="t", order_code="c", amount=1, result="SUCCESS", paid_at=None)
    assert a == b'{"amount":1,"order_code":"c","paid_at":null,"result":"SUCCESS","txn_id":"t"}'
