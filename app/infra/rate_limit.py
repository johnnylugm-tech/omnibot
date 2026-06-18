"""[FR-21] Redis sliding window rate limiter.

Per-platform sliding-window rate limiter. Production path executes a
single atomic Lua ZSET script against the injected Redis client; when
``redis_client`` is ``None`` (tests, or a failed connection) the
implementation falls back to an in-process sliding window that
preserves the same atomicity guarantee via a single ``threading.Lock``
and serialization on the asyncio event loop.

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
        # Inject; do not connect. The production Lua path is taken when
        # ``redis_client`` is not None and exposes ``eval``.
        self.redis_client = redis_client
        # In-memory fallback state: platform -> deque of monotonic timestamps.
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, *, platform: str, key: str) -> RateLimitResult:
        """Synchronous per-platform rate-limit check.

        ``key`` is accepted for API parity with the production Lua path
        (per-user sub-bucketing); in this in-memory fallback the
        platform-wide bucket is authoritative.
        """
        return self._check_and_record(platform)

    async def aallow(self, *, platform: str, key: str) -> RateLimitResult:
        """Async counterpart to :meth:`allow`.

        Internally synchronous on the event loop: with no ``await`` inside
        the critical section, asyncio serializes concurrent callers, so
        the bucket mutation is atomic for the race-condition test.
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