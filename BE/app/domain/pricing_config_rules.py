"""Validation of a PricingConfig version before it is saved (FR-30). Pure: no DB, no I/O."""
from decimal import Decimal
from typing import Any, Iterable

from app.services.pricing import MONEY_STEP

MONEY_FIELDS = ("u_ot1", "u_ot2", "u_ot3", "w_min", "s_ot1", "s_ot2", "s_ot3")


def validate(values: dict[str, Any]) -> list[dict[str, str]]:
    """Return a list of {field, message}; empty when the configuration is consistent."""
    problems: list[dict[str, str]] = []

    def bad(field: str, message: str) -> None:
        problems.append({"field": field, "message": message})

    for f in MONEY_FIELDS:
        v = Decimal(str(values[f]))
        if v < 0 or v % MONEY_STEP != 0:
            bad(f, "phải là số không âm, làm tròn đến 100đ")
    ks, km, kc = (Decimal(str(values[k])) for k in ("k_simple", "k_medium", "k_complex"))
    if not (0 < ks <= km <= kc):
        bad("k_simple", "cần 0 < K_simple ≤ K_medium ≤ K_complex")
    p_min = Decimal(str(values["p_min_pct"]))
    if not (0 < p_min <= 100):
        bad("p_min_pct", "tỷ lệ cọc tối thiểu phải trong (0; 100]")
    thr = Decimal(str(values["adjust_threshold_pct"]))
    if not (0 <= thr <= 100):
        bad("adjust_threshold_pct", "ngưỡng điều chỉnh giá phải trong [0; 100]")
    if Decimal(str(values["canvas_mm_per_char"])) <= 0:
        bad("canvas_mm_per_char", "phải lớn hơn 0")
    problems += _tiers(values["discount_tiers"])
    return problems


def _tiers(tiers: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    rows = [(int(t["min_qty"]), Decimal(str(t["pct"]))) for t in tiers]
    out: list[dict[str, str]] = []
    if any(q < 2 for q, _ in rows):
        out.append({"field": "discount_tiers", "message": "min_qty phải ≥ 2"})
    if len({q for q, _ in rows}) != len(rows):
        out.append({"field": "discount_tiers", "message": "min_qty không được trùng nhau"})
    ordered = sorted(rows)
    if any(not (0 <= p < 100) for _, p in rows):
        out.append({"field": "discount_tiers", "message": "pct phải trong [0; 100)"})
    if any(b[1] < a[1] for a, b in zip(ordered, ordered[1:])):
        out.append({"field": "discount_tiers", "message": "chiết khấu phải không giảm khi số lượng tăng"})
    return out
