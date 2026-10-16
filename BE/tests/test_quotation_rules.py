"""Pure quotation rules (BR-09, FR-29/31). No database."""
from decimal import Decimal

import pytest

from app.domain.quotation_rules import (adjustment_pct, build_line_items, classify_adjustment, fmt_vnd,
                                        validate_adjusted_total)
from app.services.pricing import MaterialPrices, PricingParams, compute_price

D = Decimal
PARAMS = PricingParams(u_per_char=D(300), w_min=D(50000), setup_fee=D(100000),
                       k_by_complexity={"SIMPLE": D("1.0"), "MEDIUM": D("1.3"), "COMPLEX": D("1.6")},
                       discount_tiers=((10, D(5)), (50, D(10)), (100, D(15))), p_min_pct=D(50))


def test_fmt_vnd():
    assert fmt_vnd(D(399600)) == "399.600" and fmt_vnd(0) == "0" and fmt_vnd(1000000) == "1.000.000"


@pytest.mark.parametrize("adjusted,pct,needs", [
    (1_150_000, "15.00", False),      # exactly +15% is still the Staff's call
    (1_150_100, "15.01", True),
    (850_000, "-15.00", False),
    (849_900, "-15.01", True),
    (1_000_000, "0.00", False),
])
def test_adjustment_boundary(adjusted, pct, needs):
    d = classify_adjustment(D(1_000_000), D(adjusted), D(15))
    assert d.pct == D(pct) and d.needs_manager is needs


def test_adjustment_pct_matches_db_rounding():
    assert adjustment_pct(D(399600), D(420000)) == D("5.11")


@pytest.mark.parametrize("bad", [0, -100, 1050, 99_999])
def test_adjusted_total_must_be_positive_multiple_of_100(bad):
    with pytest.raises(ValueError):
        validate_adjusted_total(D(bad))


def test_adjusted_total_ok():
    validate_adjusted_total(D(420_000))


def test_line_items_reproduce_the_srs_worked_example():
    """Report 3, FR-29: 320 chars, A4 art 15.000, fountain pen 10.000, ink 0, medium (1,3), 2 copies."""
    b = compute_price(PARAMS, chars=320, quantity=2, complexity="MEDIUM",
                      materials=MaterialPrices(paper=D(15000), pen=D(10000), ink=D(0)))
    assert (b.writing_fee, b.unit_price, b.total, b.min_deposit) == (D(124800), D(149800), D(399600), D(199800))
    rows = build_line_items(1, paper_id=1, pen_id=2, ink_id=3, paper_name="Giấy mỹ thuật A4", pen_name="Bút máy",
                            ink_name="Đen", paper_price=D(15000), pen_price=D(10000), ink_price=D(0),
                            params=PARAMS, breakdown=b, complexity="MEDIUM")
    by_item = {r["item"]: r for r in rows}
    assert by_item["Công viết / bản"]["calc"] == "max(50.000; 320 × 300) × 1.3"
    assert by_item["Công viết / bản"]["amount"] == 124800
    assert by_item["2 bản"]["amount"] + by_item["Phí setup"]["amount"] == by_item["Tổng (chưa gồm phí giao hàng)"]["amount"] == 399600
    assert all(r["option"] == 1 and r["paper_type_id"] == 1 for r in rows)


def test_discount_tier_is_shown():
    b = compute_price(PARAMS, chars=100, quantity=10, complexity="SIMPLE", materials=MaterialPrices())
    rows = build_line_items(1, paper_id=None, pen_id=None, ink_id=None, paper_name="-", pen_name="-", ink_name="-",
                            paper_price=D(0), pen_price=D(0), ink_price=D(0), params=PARAMS, breakdown=b,
                            complexity="SIMPLE")
    assert "(1 − 5%)" in next(r["calc"] for r in rows if r["item"] == "10 bản")
