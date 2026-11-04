"""Phase 4d-1: who may cancel a paid order and how much comes back (BR-14, BR-16). No database."""
from decimal import Decimal

import pytest

from app.domain.refund_rules import CancelFacts, Initiator, Rule, decide, mask_account

C, W = Initiator.CUSTOMER, Initiator.WORKSHOP


def facts(prod="PENDING_SCHEDULE", status="CONFIRMED", paid=300_000, setup=50_000, postponed=0, threshold=7,
          wrote_before=False) -> CancelFacts:
    return CancelFacts(order_status=status, production_status=prod, paid=Decimal(paid), setup_fee=Decimal(setup),
                       eta_postponed_days=postponed, threshold_days=threshold, wrote_before=wrote_before)


@pytest.mark.parametrize("status", ["SUBMITTED", "NEED_INFO", "QUOTED", "AWAITING_DEPOSIT"])
def test_unpaid_orders_cancel_for_free_but_only_by_the_customer(status):
    d = decide(facts(status=status, prod="NOT_STARTED", paid=0), C)
    assert (d.allowed, d.rule, d.refund_amount) == (True, Rule.NO_PAYMENT, 0)
    assert decide(facts(status=status, prod="NOT_STARTED", paid=0), W).error_code == "ORDER_CANCEL_UNSUPPORTED"


def test_before_scheduling_the_whole_deposit_comes_back():
    d = decide(facts(prod="PENDING_SCHEDULE"), C)
    assert (d.allowed, d.rule, d.refund_amount, d.deduction) == (True, Rule.BR14_BEFORE_SCHEDULE, 300_000, 0)


@pytest.mark.parametrize("prod", ["SCHEDULED", "PREPARING"])
def test_scheduled_but_not_written_keeps_the_setup_fee(prod):
    d = decide(facts(prod=prod), C)
    assert (d.allowed, d.rule, d.refund_amount, d.deduction) == (True, Rule.BR14_AFTER_SCHEDULE, 250_000, 50_000)


def test_the_setup_fee_never_takes_more_than_was_paid():
    d = decide(facts(prod="SCHEDULED", paid=40_000, setup=50_000), C)
    assert (d.refund_amount, d.deduction) == (0, 40_000)


@pytest.mark.parametrize("prod", ["PAUSED", "WRITTEN", "PHOTO_UPLOADED", "REWRITE_REQUIRED", "FAILED"])
def test_after_writing_started_no_cancel_unless_eta_slipped_past_the_threshold(prod):
    assert decide(facts(prod=prod, postponed=7), C).error_code == "CANCEL_AFTER_WRITING_STARTED"
    d = decide(facts(prod=prod, postponed=8), C)
    assert (d.allowed, d.rule, d.refund_amount) == (True, Rule.BR16_ETA_POSTPONED, 300_000)


def test_the_threshold_comes_from_the_setting():
    assert decide(facts(prod="PAUSED", postponed=4, threshold=3), C).rule == Rule.BR16_ETA_POSTPONED
    assert not decide(facts(prod="PAUSED", postponed=4, threshold=10), C).allowed


def test_a_rewrite_back_in_the_queue_still_counts_as_written():
    for prod in ("PENDING_SCHEDULE", "SCHEDULED"):
        assert decide(facts(prod=prod, wrote_before=True), C).error_code == "CANCEL_AFTER_WRITING_STARTED"
        assert decide(facts(prod=prod, wrote_before=True, postponed=9), C).rule == Rule.BR16_ETA_POSTPONED


def test_never_while_the_robot_is_writing_even_with_br16():
    assert decide(facts(prod="WRITING", postponed=30), C).error_code == "JOB_RUNNING"
    assert decide(facts(prod="WRITING", postponed=30), W).error_code == "JOB_RUNNING"


@pytest.mark.parametrize("prod", ["PENDING_SCHEDULE", "SCHEDULED", "PREPARING"])
def test_the_workshop_cancelling_refunds_everything(prod):
    d = decide(facts(prod=prod), W)
    assert (d.allowed, d.rule, d.refund_amount, d.deduction) == (True, Rule.WORKSHOP_CANCEL, 300_000, 0)


def test_the_workshop_is_bound_by_the_writing_line_too():
    assert decide(facts(prod="WRITTEN"), W).error_code == "CANCEL_AFTER_WRITING_STARTED"
    assert decide(facts(prod="WRITTEN", postponed=8), W).rule == Rule.BR16_ETA_POSTPONED


@pytest.mark.parametrize("status", ["AWAITING_ACCEPTANCE", "AWAITING_FINAL_PAYMENT", "READY_TO_DELIVER", "DELIVERING",
                                    "COMPLETED", "CANCELLED", "REJECTED", "DRAFT", "ACCEPTED", "AWAITING_PRIVACY"])
def test_other_states_do_not_cancel(status):
    assert decide(facts(status=status, prod="FINISHED"), C).error_code == "ORDER_CANCEL_UNSUPPORTED"


def test_account_masking():
    assert mask_account("0123456789") == "••••••6789"
    assert mask_account("123") == "123"
    assert mask_account(None) is None
