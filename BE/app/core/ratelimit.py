"""In-memory sliding-window rate limiter (per client IP and rule).

Good for a single API process. With several workers/instances each keeps its own counters, so
move the store to Redis (same interface) before scaling out.
"""
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.net import resolve_client_ip


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._clock = clock

    def hit(self, rule: str, key: str, limit: int, window_s: int) -> int:
        """Record a request. Returns 0 if allowed, else seconds until the client may retry."""
        now = self._clock()
        with self._lock:
            q = self._hits[(rule, key)]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(q[0] + window_s - now) + 1)
            q.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def rate_limit(rule: str, limit: int, window_s: int) -> Callable[[Request], None]:
    """FastAPI dependency: at most `limit` calls per `window_s` seconds per client IP."""
    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        key = resolve_client_ip(request) or "unknown"
        retry_after = limiter.hit(rule, key, limit, window_s)
        if retry_after:
            raise AppError(429, "RATE_LIMITED", "Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
                           details={"retry_after_seconds": retry_after})
    return dependency
