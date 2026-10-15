"""Pricing Engine (FR-29, BR-08, BR-10). Pure functions: no DB, no I/O, no framework imports.

    N      = non-whitespace characters (canvas: total stroke length / canvas_mm_per_char)
    Write  = max(W_min, N * u_type) * K_cx          writing fee for one copy
    Unit   = P_paper + P_pen + P_ink + Write        price of one copy
    G      = S_type + Q * Unit * (1 - d(Q))         order total, shipping excluded
    D      >= p_min * G                             minimum deposit
All money is VND, rounded to 100 d (Report 3, 5.2).
"""
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Iterable

MONEY_STEP = Decimal(100)
ZERO = Decimal(0)


@dataclass(frozen=True)
class PricingParams:
    u_per_char: Decimal           # u_type for the order's type
    w_min: Decimal
    setup_fee: Decimal            # S_type
    k_by_complexity: dict[str, Decimal]
    discount_tiers: tuple[tuple[int, Decimal], ...]   # (min_qty, pct) ascending
    p_min_pct: Decimal
    canvas_mm_per_char: Decimal = Decimal(40)


@dataclass(frozen=True)
class MaterialPrices:
    paper: Decimal = ZERO
    pen: Decimal = ZERO
    ink: Decimal = ZERO


@dataclass(frozen=True)
class PriceBreakdown:
    chars: int
    writing_fee: Decimal       # per copy, after K_cx
    unit_price: Decimal        # per copy, before quantity discount
    quantity: int
    discount_pct: Decimal
    setup_fee: Decimal
    total: Decimal             # G
    min_deposit: Decimal       # p_min * G rounded UP to 100 d so that D >= p_min * G always holds


def round_money(value: Decimal) -> Decimal:
    return (value / MONEY_STEP).quantize(Decimal(1), rounding=ROUND_HALF_UP) * MONEY_STEP


def _ceil_money(value: Decimal) -> Decimal:
    return (value / MONEY_STEP).quantize(Decimal(1), rounding=ROUND_CEILING) * MONEY_STEP


def parse_tiers(raw: Iterable[dict]) -> tuple[tuple[int, Decimal], ...]:
    return tuple(sorted((int(t["min_qty"]), Decimal(str(t["pct"]))) for t in raw))


def discount_pct(quantity: int, tiers: tuple[tuple[int, Decimal], ...]) -> Decimal:
    pct = ZERO
    for min_qty, tier_pct in tiers:
        if quantity >= min_qty:
            pct = tier_pct
    return pct


def count_text_chars(text: str) -> int:
    """N for typed content: characters excluding whitespace (FR-29)."""
    return sum(1 for ch in text if not ch.isspace())


def canvas_chars(total_stroke_length_mm: float, mm_per_char: Decimal) -> int:
    if total_stroke_length_mm <= 0:
        return 0
    return int((Decimal(str(total_stroke_length_mm)) / mm_per_char).to_integral_value(rounding=ROUND_CEILING))


def compute_price(params: PricingParams, *, chars: int, quantity: int, complexity: str,
                  materials: MaterialPrices = MaterialPrices()) -> PriceBreakdown:
    if chars < 0 or quantity < 1:
        raise ValueError("chars must be >= 0 and quantity >= 1")
    k = params.k_by_complexity[complexity]
    writing = max(params.w_min, Decimal(chars) * params.u_per_char) * k
    unit = materials.paper + materials.pen + materials.ink + writing
    d = discount_pct(quantity, params.discount_tiers)
    total = round_money(params.setup_fee + Decimal(quantity) * unit * (Decimal(100) - d) / Decimal(100))
    return PriceBreakdown(
        chars=chars, writing_fee=round_money(writing), unit_price=round_money(unit), quantity=quantity,
        discount_pct=d, setup_fee=params.setup_fee, total=total,
        min_deposit=_ceil_money(total * params.p_min_pct / Decimal(100)))
