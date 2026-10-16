"""Pure business rules for quotations (FR-15, FR-29, FR-31, BR-08, BR-09). No DB, no I/O."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.pricing import MONEY_STEP, PriceBreakdown, PricingParams

TWO_PLACES = Decimal("0.01")


def fmt_vnd(value: Decimal | int) -> str:
    """12345 -> '12.345' (Vietnamese thousands separator, Report 3 section 3.3 examples)."""
    return f"{int(value):,}".replace(",", ".")


def adjustment_pct(computed: Decimal, adjusted: Decimal) -> Decimal:
    """Same figure as quotations.adjustment_pct (generated column): (adjusted - computed) / computed, 2 dp."""
    if computed == 0:
        raise ValueError("computed total must be positive")
    return ((adjusted - computed) * 100 / computed).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class AdjustmentDecision:
    pct: Decimal
    needs_manager: bool


def classify_adjustment(computed: Decimal, adjusted: Decimal, threshold_pct: Decimal) -> AdjustmentDecision:
    """BR-09: within +/- threshold the Staff may adjust alone (reason required); beyond it a Manager must approve.
    The boundary is inclusive: exactly +/-15% is still allowed."""
    pct = adjustment_pct(computed, adjusted)
    return AdjustmentDecision(pct=pct, needs_manager=abs(pct) > threshold_pct)


def validate_adjusted_total(adjusted: Decimal) -> None:
    if adjusted <= 0 or adjusted % MONEY_STEP != 0:
        raise ValueError("adjusted total must be a positive multiple of 100")


def build_line_items(option: int, *, paper_id: int | None, pen_id: int | None, ink_id: int | None,
                     paper_name: str, pen_name: str, ink_name: str, paper_price: Decimal, pen_price: Decimal,
                     ink_price: Decimal, params: PricingParams, breakdown: PriceBreakdown,
                     complexity: str) -> list[dict[str, Any]]:
    """Table rows of the quotation (Report 3, section 3.3 example). Row amounts add up to breakdown.total."""
    k = params.k_by_complexity[complexity]
    d = breakdown.discount_pct
    ids = {"option": option, "paper_type_id": paper_id, "pen_type_id": pen_id, "ink_color_id": ink_id}

    def row(item: str, calc: str, amount: Decimal) -> dict[str, Any]:
        return {**ids, "item": item, "calc": calc, "amount": int(amount)}

    return [
        row("Giấy", paper_name, paper_price),
        row("Bút (phụ phí)", pen_name, pen_price),
        row("Mực", ink_name, ink_price),
        row("Công viết / bản",
            f"max({fmt_vnd(params.w_min)}; {breakdown.chars} × {fmt_vnd(params.u_per_char)}) × {k.normalize():f}",
            breakdown.writing_fee),
        row("Giá 1 bản", "giấy + bút + mực + công viết", breakdown.unit_price),
        row(f"{breakdown.quantity} bản",
            f"{breakdown.quantity} × {fmt_vnd(breakdown.unit_price)} × (1 − {d.normalize():f}%)",
            breakdown.total - breakdown.setup_fee),
        row("Phí setup", "phác thảo, chuẩn bị máy", breakdown.setup_fee),
        row("Tổng (chưa gồm phí giao hàng)", "", breakdown.total),
    ]


def min_deposit(total: Decimal, pct: Decimal) -> Decimal:
    """BR-10: D >= p_min * G, rounded UP to 100 d so the rule always holds."""
    from decimal import ROUND_CEILING
    return (total * pct / 100 / MONEY_STEP).quantize(Decimal(1), rounding=ROUND_CEILING) * MONEY_STEP
