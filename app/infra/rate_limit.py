"""[FR-21] Sliding window rate limiter.

Per-platform sliding-window rate limiter. Atomicity is provided by a
single ``threading.Lock`` guarding the per-platform deque of
monotonic timestamps; under asyncio, callers serialize on the event
loop because the critical section performs no ``await``.

``redis_client`` is accepted for API parity with the production
Redis-backed path but is not exercised by the current implementation.

Citations:
- SRS.md FR-21 (description line 59, spec block lines 590-595)
- 02-architecture/TEST_SPEC.md FR-21
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate-limit check.

    Attributes:
        status: HTTP-style code carried by the platform contract.
            200 = allowed, 429 = rate-limited.
        reason: Machine-readable reason. ``"RATE_LIMIT_EXCEEDED"`` on 429,
            empty string otherwise.
    """

    status: int
    reason: str = ""


class RateLimiter:
    """Sliding-window rate limiter, bucketed per platform.

    Limit table (requests per 1-second window):
        telegram / line / messenger / whatsapp : 30
        web                                     : 10
        agent                                   : 100
    """

    LIMITS: dict[str, int] = {
        "telegram": 30,
        "line": 30,
        "messenger": 30,
        "whatsapp": 30,
        "web": 10,
        "agent": 100,
    }

    _WINDOW_SECONDS: float = 1.0

    def __init__(self, redis_client=None) -> None:
        # Inject; do not connect. Accepted for API parity with the
        # production Redis-backed path; not exercised here.
        self.redis_client = redis_client
        # platform -> deque of monotonic timestamps inside the window.
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, *, platform: str, key: str) -> RateLimitResult:
        """Synchronous per-platform rate-limit check.

        ``key`` is accepted for API parity with the production
        per-user sub-bucketing path; the in-memory implementation
        keys only by platform.
        """
        return self._check_and_record(platform)

    async def aallow(self, *, platform: str, key: str) -> RateLimitResult:
        """Async counterpart to :meth:`allow`.

        Internally synchronous on the event loop: with no ``await``
        inside the critical section, asyncio serializes concurrent
        callers, so the bucket mutation is atomic.
        """
        return self._check_and_record(platform)

    def _check_and_record(self, platform: str) -> RateLimitResult:
        limit = self.LIMITS.get(platform)
        if limit is None:
            # Unknown platform — fail-open; the platform layer is the
            # authority for which platforms exist.
            return RateLimitResult(200, "")

        now = time.monotonic()
        window_start = now - self._WINDOW_SECONDS

        with self._lock:
            bucket = self._buckets.setdefault(platform, deque())
            # Drop entries that have aged out of the sliding window.
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                return RateLimitResult(429, "RATE_LIMIT_EXCEEDED")
            bucket.append(now)
            return RateLimitResult(200, "")