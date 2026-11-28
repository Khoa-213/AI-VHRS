"""Run something once the request's transaction is really committed (never when it is rolled back).

SQLAlchemy fires the session's "after_commit" event for a released SAVEPOINT too (AR-08, audit 2026-11-27); a hook that does
not know this acts on data nobody else can see yet, while the request still holds its locks. This is the one helper that gets
it right, for work that must leave the transaction: sending an e-mail, deleting a file, pushing a live event.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger("app.after_commit")
_QUEUE = "after_commit_queue"
_HOOKED = "after_commit_hooked"


def run_after_commit(session: Session, fn: Callable[[], Any]) -> None:
    """Queue `fn` for after the commit of the transaction `session` is in. A failure of `fn` is logged, never raised."""
    if not session.info.get(_HOOKED):
        event.listen(session, "after_commit", _after_commit)
        event.listen(session, "after_soft_rollback", _after_soft_rollback)
        session.info[_HOOKED] = True
    session.info.setdefault(_QUEUE, []).append(fn)


def _after_soft_rollback(session: Session, previous_transaction: Any) -> None:
    if previous_transaction.parent is None:              # the whole transaction, not a SAVEPOINT
        session.info.pop(_QUEUE, None)


def _after_commit(session: Session) -> None:
    if session.in_nested_transaction():                  # a SAVEPOINT was released: nothing is committed yet
        return
    for fn in session.info.pop(_QUEUE, None) or ():
        try:
            fn()
        except Exception:                                # noqa: BLE001 - the database is already right
            log.exception("after-commit work failed")
