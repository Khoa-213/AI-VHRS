"""Pure rules for the deposit (BR-10, FR-17). No DB, no I/O."""
from decimal import ROUND_CEILING, Decimal

from app.domain.quotation_rules import min_deposit
from app.services.pricing import MONEY_STEP

TWO_PLACES = Decimal("0.01")


class DepositError(ValueError):
    """The requested deposit percentage is outside the allowed range."""


def resolve_deposit(total: Decimal, min_pct: Decimal, requested_pct: Decimal | None) -> tuple[Decimal, Decimal]:
    """Return (deposit_pct, deposit_amount). The customer may pay anything from the minimum percentage up to
    100 %; with no choice the minimum applies. The amount is rounded UP to 100 d (so D >= p * G always holds)
    and never exceeds the total."""
    if total <= 0:
        raise DepositError("order total must be positive")
    pct = min_pct if requested_pct is None else requested_pct.quantize(TWO_PLACES)
    if pct < min_pct or pct > 100:
        raise DepositError(f"deposit must be between {min_pct}% and 100%")
    if pct == 100:
        return pct, total
    amount = (total * pct / 100 / MONEY_STEP).quantize(Decimal(1), rounding=ROUND_CEILING) * MONEY_STEP
    amount = min(amount, total)
    assert amount >= min_deposit(total, min_pct) or amount == total
    return pct, amount
