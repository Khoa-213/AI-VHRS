"""Notification hook (FR-27, FR-57). Phase 2 only records WHAT should be sent; delivery (in-app rows in
`notifications` + e-mail) is implemented in the notification phase. Callers already pass the message
code from Report 3 section 5.3 so nothing changes for them later."""
import logging
from typing import Any

log = logging.getLogger("app.notify")


def notify(*, account_id: int, order_id: int | None, msg_code: str, **params: Any) -> None:
    log.info("notify account=%s order=%s code=%s params=%s", account_id, order_id, msg_code, params)
