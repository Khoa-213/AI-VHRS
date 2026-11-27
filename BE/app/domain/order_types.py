"""Which order types customers may place right now (LI-10, MSG03).

`system_settings.order_types_enabled` holds the list the Admin chose. AI-10 (audit 2026-11-27): a MISSING row used to mean
"everything is open", so a database that was never seeded, or one whose row a test run had removed, let real customers order
OT-2 (not on sale). Missing now means the project default below: closed unless somebody opened it.
"""
from __future__ import annotations

from typing import Any, Iterable

DEFAULT_ENABLED: tuple[str, ...] = ("OT1_COPY_RESTORE", "OT3_TEMPLATE")

# Tests exercise every order type. They used to get there by deleting the database row, which also opened OT-2 to the real
# customers of that database for as long as the suite ran. The test process now says what IT accepts, in memory only.
_process_override: tuple[str, ...] | None = None


def enabled(setting_value: Any) -> tuple[str, ...]:
    """The order types that may be placed, given the stored setting (None = no row)."""
    if _process_override is not None:
        return _process_override
    if isinstance(setting_value, (list, tuple)):
        return tuple(str(v) for v in setting_value)
    return DEFAULT_ENABLED


def override_for_this_process(types: Iterable[str] | None) -> None:
    """Tests only: the list this process uses instead of the database row; None goes back to the row."""
    global _process_override
    _process_override = tuple(types) if types is not None else None
