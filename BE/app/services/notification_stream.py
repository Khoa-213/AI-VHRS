"""In-process fan-out of new in-app notifications to open SSE connections (GET /me/notifications/stream).

One uvicorn worker serves the API (Dockerfile `--workers 1`), so a process-local broker reaches every connection. With more
workers or instances a shared channel (Postgres LISTEN/NOTIFY, Redis) would be needed; the list endpoint stays the source of
truth either way, the stream only says "something new arrived".

Publishers run in worker threads (sync endpoints, webhooks); subscribers are asyncio queues, so publishing goes through
`loop.call_soon_threadsafe`.

Besides notifications (SSE `event: notification`) the same stream carries other live events, e.g. a new chat message
(`event: message`, Phase 5d). Those are queued with `publish_after_commit`, so a rolled-back action pushes nothing.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger("app.notify")

QUEUE_SIZE = 100
EVENT_KEY = "_event"                                    # which SSE event a payload is sent as; absent = "notification"
_PENDING = "stream_pending"
_HOOKED = "stream_hooked"


class Broker:
    def __init__(self) -> None:
        self._subs: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, account_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        with self._lock:
            self._subs.setdefault(account_id, set()).add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, account_id: int, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subs.get(account_id, set())
            for item in [s for s in subs if s[1] is q]:
                subs.discard(item)
            if not subs:
                self._subs.pop(account_id, None)

    def listeners(self, account_id: int) -> int:
        with self._lock:
            return len(self._subs.get(account_id, ()))

    def publish(self, account_id: int, payload: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs.get(account_id, ()))
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(_put, q, payload)
            except RuntimeError:                        # the loop has closed: the connection is gone
                self.unsubscribe(account_id, q)


def _put(q: asyncio.Queue, payload: dict[str, Any]) -> None:
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:                           # a stuck client: drop, it re-reads the list on reconnect
        log.warning("notification stream queue full, dropping one event")


broker = Broker()


def split_event(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(SSE event name, data without the routing key). The queued dict is shared by every connection of the account, so
    it is never modified."""
    if EVENT_KEY not in item:
        return "notification", item
    return item[EVENT_KEY], {k: v for k, v in item.items() if k != EVENT_KEY}


def publish_after_commit(session: Session, account_ids: set[int], event_name: str, data: dict[str, Any]) -> None:
    """Push `data` as `event: <event_name>` to every open stream of these accounts once the caller's transaction commits."""
    if not account_ids:
        return
    if not session.info.get(_HOOKED):
        event.listen(session, "after_commit", _after_commit)
        event.listen(session, "after_soft_rollback", _after_soft_rollback)
        session.info[_HOOKED] = True
    session.info.setdefault(_PENDING, []).append((set(account_ids), {**data, EVENT_KEY: event_name}))


def _after_soft_rollback(session: Session, previous_transaction) -> None:
    if previous_transaction.parent is None:              # the whole transaction, not a SAVEPOINT
        session.info.pop(_PENDING, None)


def _after_commit(session: Session) -> None:
    for account_ids, item in session.info.pop(_PENDING, None) or ():
        for account_id in account_ids:
            try:
                broker.publish(account_id, item)
            except Exception:                            # noqa: BLE001 - a live push must never break the request
                log.exception("live event not pushed to account %s", account_id)
