"""Pricing Engine unit tests (FR-29). Pure functions: no DB."""
from decimal import Decimal

import pytest

from app.services import pricing as p

D = Decimal
PARAMS = p.PricingParams(
    u_per_char=D(300), w_min=D(50000), setup_fee=D(100000),
    k_by_complexity={"SIMPLE": D("1.0"), "MEDIUM": D("1.3"), "COMPLEX": D("1.6")},
    discount_tiers=p.parse_tiers([{"min_qty": 10, "pct": 5}, {"min_qty": 50, "pct": 10}, {"min_qty": 100, "pct": 15}]),
    p_min_pct=D(50))
MATERIALS = p.MaterialPrices(paper=D(15000), pen=D(10000), ink=D(0))


def test_report3_worked_example():
    r = p.compute_price(PARAMS, chars=320, quantity=2, complexity="MEDIUM", materials=MATERIALS)
    assert r.writing_fee == D(124800)
    assert r.unit_price == D(149800)
    assert r.total == D(399600)
    assert r.min_deposit == D(199800)


def test_minimum_writing_fee_applies_to_short_text():
    r = p.compute_price(PARAMS, chars=10, quantity=1, complexity="SIMPLE")
    assert r.writing_fee == D(50000)          # max(W_min, 10 * 300) = W_min
    assert r.total == D(150000)               # setup + 1 * 50,000


@pytest.mark.parametrize("qty,pct", [(1, 0), (9, 0), (10, 5), (49, 5), (50, 10), (99, 10), (100, 15), (500, 15)])
def test_quantity_discount_tiers(qty, pct):
    assert p.discount_pct(qty, PARAMS.discount_tiers) == D(pct)


@pytest.mark.parametrize("complexity,k", [("SIMPLE", "1.0"), ("MEDIUM", "1.3"), ("COMPLEX", "1.6")])
def test_complexity_multiplier(complexity, k):
    r = p.compute_price(PARAMS, chars=1000, quantity=1, complexity=complexity)
    assert r.writing_fee == D(300000) * D(k)


def test_rounding_to_100_dong():
    cfg = p.PricingParams(u_per_char=D(333), w_min=D(0), setup_fee=D(0),
                          k_by_complexity={"SIMPLE": D(1)}, discount_tiers=(), p_min_pct=D(50))
    r = p.compute_price(cfg, chars=7, quantity=1, complexity="SIMPLE")   # 2331 -> 2300
    assert r.total == D(2300) and r.total % 100 == 0


def test_min_deposit_never_below_p_min_share():
    cfg = p.PricingParams(u_per_char=D(333), w_min=D(0), setup_fee=D(0),
                          k_by_complexity={"SIMPLE": D(1)}, discount_tiers=(), p_min_pct=D(50))
    r = p.compute_price(cfg, chars=7, quantity=1, complexity="SIMPLE")   # G=2300, half=1150 -> 1200
    assert r.min_deposit >= r.total * D("0.5")
    assert r.min_deposit % 100 == 0


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        p.compute_price(PARAMS, chars=-1, quantity=1, complexity="SIMPLE")
    with pytest.raises(ValueError):
        p.compute_price(PARAMS, chars=1, quantity=0, complexity="SIMPLE")


def test_text_char_count_ignores_whitespace_and_counts_vietnamese_marks_once():
    assert p.count_text_chars("Xin chào\n bạn ") == 10
    assert p.count_text_chars("") == 0


def test_canvas_chars_from_stroke_length():
    assert p.canvas_chars(0, D(40)) == 0
    assert p.canvas_chars(400, D(40)) == 10
    assert p.canvas_chars(401, D(40)) == 11
