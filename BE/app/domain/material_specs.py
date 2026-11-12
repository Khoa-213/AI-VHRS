"""Upgrade U6: extended material specifications, each value with WHERE IT COMES FROM (docs/UPGRADE_AI_ROBOT_PLAN.md VII).

`specs` on a paper / pen / ink is {key: {"value": ..., "source": SUPPLIER | MEASURED | ASSUMED, "note"?: str}}. Only
the keys below are accepted, with their type and range, so a typo cannot hide a value from the code that reads it. A
value without a source is refused: the point of U6 is that nobody mistakes a guess for a measurement.

These fields are descriptive. What the robot / preview actually uses for a paper + pen + ink combination lives in a
material profile (models.catalog.MaterialProfile), which is measured on a test sheet.
"""
from __future__ import annotations

import re
from typing import Any

SOURCES = ("SUPPLIER", "MEASURED", "ASSUMED")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# key -> (kind, rule, unit, Vietnamese label)
#   kind "num": rule = (min, max); "enum": rule = allowed values; "bool"; "hex"; "text": rule = max length
FIELDS: dict[str, dict[str, tuple[str, Any, str | None, str]]] = {
    "paper": {
        "thickness_mm": ("num", (0.01, 2.0), "mm", "Độ dày"),
        "absorbency": ("enum", ("LOW", "MEDIUM", "HIGH"), None, "Độ thấm mực"),
        "tone_hex": ("hex", None, None, "Màu giấy"),
        "texture": ("enum", ("SMOOTH", "VELLUM", "LAID", "ROUGH"), None, "Bề mặt"),
        "brand": ("text", 80, None, "Hãng"),
        "supplier_sku": ("text", 60, None, "Mã nhà cung cấp"),
    },
    "pen": {
        "tip_mm": ("num", (0.05, 15.0), "mm", "Cỡ ngòi"),
        "ink_base": ("enum", ("OIL", "GEL", "WATER", "PIGMENT", "ALCOHOL"), None, "Gốc mực"),
        "line_life_m": ("num", (1, 100000), "m", "Độ dài nét viết được"),
        "needs_priming": ("bool", None, None, "Cần mồi mực trước khi viết"),
        "brand": ("text", 80, None, "Hãng"),
        "supplier_sku": ("text", 60, None, "Mã nhà cung cấp"),
    },
    "ink": {
        "drying_s": ("num", (0, 3600), "s", "Thời gian khô"),
        "waterproof": ("bool", None, None, "Chống nước"),
        "opacity": ("enum", ("TRANSPARENT", "SEMI", "OPAQUE"), None, "Độ phủ"),
        "brand": ("text", 80, None, "Hãng"),
        "supplier_sku": ("text", 60, None, "Mã nhà cung cấp"),
    },
}


class SpecError(ValueError):
    def __init__(self, message: str, key: str | None = None):
        super().__init__(message)
        self.message, self.key = message, key


def _check_value(kind: str, rule: Any, v: Any) -> Any:
    if kind == "num":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("cần số")
        lo, hi = rule
        if not lo <= v <= hi:
            raise ValueError(f"cần trong khoảng {lo}..{hi}")
        return v
    if kind == "enum":
        if v not in rule:
            raise ValueError("cần một trong " + ", ".join(rule))
        return v
    if kind == "bool":
        if not isinstance(v, bool):
            raise ValueError("cần true / false")
        return v
    if kind == "hex":
        if not isinstance(v, str) or not _HEX.match(v):
            raise ValueError("cần mã màu #RRGGBB")
        return v.upper()
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > rule:
        raise ValueError(f"cần chuỗi 1..{rule} ký tự")
    return v.strip()


def validate(material: str, specs: Any) -> dict[str, dict[str, Any]]:
    """Return the cleaned specs or raise SpecError (Vietnamese message)."""
    fields = FIELDS[material]
    if not isinstance(specs, dict):
        raise SpecError("specs phải là object {khoá: {value, source}}.")
    out: dict[str, dict[str, Any]] = {}
    for key, item in specs.items():
        if key not in fields:
            raise SpecError(f"Không có trường '{key}'. Các trường hợp lệ: {', '.join(fields)}.", key)
        if not isinstance(item, dict) or "value" not in item:
            raise SpecError(f"'{key}': cần {{\"value\": ..., \"source\": ...}}.", key)
        source = item.get("source")
        if source not in SOURCES:
            raise SpecError(f"'{key}': source phải là {', '.join(SOURCES)} (bắt buộc ghi nguồn).", key)
        extra = set(item) - {"value", "source", "note"}
        if extra:
            raise SpecError(f"'{key}': không nhận {', '.join(sorted(extra))}.", key)
        kind, rule, unit, _ = fields[key]
        try:
            value = _check_value(kind, rule, item["value"])
        except ValueError as exc:
            raise SpecError(f"'{key}': {exc}.", key) from None
        clean: dict[str, Any] = {"value": value, "source": source}
        if unit:
            clean["unit"] = unit
        note = item.get("note")
        if note is not None:
            if not isinstance(note, str) or len(note) > 300:
                raise SpecError(f"'{key}': note tối đa 300 ký tự.", key)
            clean["note"] = note.strip()
        out[key] = clean
    return out


def catalog() -> dict[str, list[dict[str, Any]]]:
    """Field list for the Manager form."""
    out = {}
    for material, fields in FIELDS.items():
        out[material] = [{"key": k, "kind": kind, "rule": list(rule) if isinstance(rule, tuple) else rule,
                          "unit": unit, "label": label} for k, (kind, rule, unit, label) in fields.items()]
    return out
