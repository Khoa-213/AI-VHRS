"""Phase 4d-2: ETA rules (BR-15, BR-16). No database."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain import eta_rules as er

VN = timezone(timedelta(hours=7))


def test_finish_date_is_counted_in_the_workshop_time_zone():
    end = datetime(2026, 11, 5, 18, 30, tzinfo=timezone.utc)                  # 01:30 on the 6th in Vietnam
    assert er.finish_date(end, 2, VN) == date(2026, 11, 8)
    assert er.finish_date(end, 0, VN) == date(2026, 11, 6)


def test_eta_adds_the_delivery_days():
    assert er.eta_from(date(2026, 11, 8), 3) == date(2026, 11, 11)
    assert er.eta_from(date(2026, 11, 8), -1) == date(2026, 11, 8)


def test_the_carrier_estimate_never_beats_the_ready_day():
    ready = date(2026, 11, 8)
    assert er.carrier_eta(datetime(2026, 11, 10, 3, tzinfo=timezone.utc), ready, VN) == date(2026, 11, 10)
    assert er.carrier_eta(datetime(2026, 11, 6, 3, tzinfo=timezone.utc), ready, VN) == ready


def test_the_system_only_moves_the_eta_later():
    d = date(2026, 11, 10)
    assert er.automatic_change(None, d) == d                                  # first ETA
    assert er.automatic_change(d, d + timedelta(days=2)) == d + timedelta(days=2)
    assert er.automatic_change(d, d) is None
    assert er.automatic_change(d, d - timedelta(days=1)) is None              # never earlier on its own
    assert er.automatic_change(d, None) is None


@pytest.mark.parametrize("new,code", [(date(2026, 11, 3), "ETA_IN_PAST"), (date(2027, 12, 1), "ETA_TOO_FAR"),
                                      (date(2026, 11, 10), "ETA_UNCHANGED")])
def test_manual_eta_validation(new, code):
    with pytest.raises(er.EtaRuleError) as exc:
        er.check_manual(date(2026, 11, 10), new, date(2026, 11, 4))
    assert exc.value.code == code


def test_manual_eta_may_move_either_way():
    er.check_manual(date(2026, 11, 10), date(2026, 11, 7), date(2026, 11, 4))
    er.check_manual(date(2026, 11, 10), date(2026, 11, 20), date(2026, 11, 4))
    er.check_manual(None, date(2026, 11, 4), date(2026, 11, 4))


def test_full_refund_opens_strictly_beyond_the_threshold():
    assert not er.can_cancel_full_refund(7, 7)
    assert er.can_cancel_full_refund(8, 7)
