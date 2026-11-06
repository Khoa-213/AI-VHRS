"""In-process fan-out of new in-app notifications to open SSE connections (GET /me/notifications/stream).

One uvicorn worker serves the API (Dockerfile `--workers 1`), so a process-local broker reaches every connection. With more
workers or instances a shared channel (Postgres LISTEN/NOTIFY, Redis) would be needed; the list endpoint stays the source of
truth either way, the stream only says "something new arrived".

Publishers run in worker threads (sync endpoints, webhooks); subscribers are asyncio queues, so publishing goes through
`loop.call_soon_threadsafe`.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

log = logging.getLogger("app.notify")

QUEUE_SIZE = 100


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
