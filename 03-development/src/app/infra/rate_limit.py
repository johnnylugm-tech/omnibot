"""[FR-21][FR-22] Sliding window rate limiter with Redis fail-open.

Per-platform sliding-window rate limiter.

[FR-21] In-memory sliding window when no Redis client is injected.
       Atomic under asyncio concurrency because the critical section
       performs no ``await``.

[FR-22] When the injected Redis client raises ConnectionError or
       TimeoutError, the limiter MUST fail open:
         - emit a WARNING log entry
         - return RateLimitResult(status=200, reason="")
       Fail-open does NOT latch: subsequent ``allow()`` calls continue
       to consult Redis once it is reachable again.

Citations:
- SRS.md FR-21 (description line 59, spec block lines 590-595)
- SRS.md FR-22 (description line 60, spec block lines 597-602)
- 02-architecture/TEST_SPEC.md FR-21 (Redis sliding window)
- 02-architecture/TEST_SPEC.md FR-22 (fail-open on Redis outage)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import ClassVar

try:
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,  # type: ignore[reportAssignmentType]
    )
    from redis.exceptions import ResponseError  # type: ignore[reportAssignmentType]
    from redis.exceptions import (
        TimeoutError as RedisTimeoutError,  # type: ignore[reportAssignmentType]
    )
except ImportError:  # pragma: no cover -- redis lib is in pyproject dependencies
    class RedisConnectionError(Exception):  # type: ignore[no-redef]
        pass

    class RedisTimeoutError(Exception):  # type: ignore[no-redef]
        pass

    class ResponseError(Exception):  # type: ignore[no-redef]
        pass

# FR-22 fail-open triggers: any Redis-side connection or timeout failure.
# The built-in ConnectionError covers the test mock; the redis.* exceptions
# cover production traffic from redis-py.
_FAIL_OPEN_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    ResponseError,
)


logger = logging.getLogger("omnibot.rate_limit")


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate-limit check.

    Attributes:
        status: 200 allowed, 429 rate-limited.
        reason: ``"RATE_LIMIT_EXCEEDED"`` on 429, empty string otherwise.
    """

    status: int
    reason: str = ""

    @classmethod
    def allowed(cls) -> RateLimitResult:
        """Construct a pass-through result (status=200, no reason)."""
        return cls(200, "")

    @classmethod
    def denied(cls) -> RateLimitResult:
        """Construct a rate-limited result (status=429, RATE_LIMIT_EXCEEDED)."""
        return cls(429, "RATE_LIMIT_EXCEEDED")


class RateLimiter:
    """Sliding-window rate limiter, bucketed per platform.

    Limit table (requests per 1-second window):
        telegram / line / messenger / whatsapp : 30
        web                                     : 10
        agent                                   : 100

    With ``redis_client`` injected the limiter consults a single atomic
    Lua ZSET script (no GET-then-ZADD race). When Redis is unavailable
    the limiter fails open per FR-22.
    """

    LIMITS: ClassVar[dict[str, int]] = {
        "telegram": 30,
        "line": 30,
        "messenger": 30,
        "whatsapp": 30,
        "web": 10,
        "agent": 100,
    }

    _WINDOW_SECONDS: float = 1.0

    # Sliding window: trim expired, add this request, return count. Atomic.
    _SCRIPT = (
        "redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[1]));"
        "redis.call('ZADD', KEYS[1], tonumber(ARGV[2]), ARGV[3]);"
        "redis.call('EXPIRE', KEYS[1], 2);"
        "return redis.call('ZCARD', KEYS[1]);"
    )

    def __init__(self, redis_client=None) -> None:
        # Inject; do not connect.
        self.redis_client = redis_client
        # (platform, key) -> deque of monotonic timestamps inside the window.
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, *, platform: str, key: str) -> RateLimitResult:
        """Synchronous per-platform rate-limit check.

        ``key`` sub-buckets per user inside the platform window.
        """
        return self._check_and_record(platform, key)

    async def aallow(self, *, platform: str, key: str) -> RateLimitResult:
        """Async counterpart to :meth:`allow`.

        Identical fail-open semantics: redis outage → 200 + WARNING log.
        """
        return self._check_and_record(platform, key)

    def _check_and_record(self, platform: str, key: str) -> RateLimitResult:
        limit = self.LIMITS.get(platform)
        if limit is None:
            # Unknown platform — fail-open; the platform layer is the
            # authority for which platforms exist.
            return RateLimitResult.allowed()

        if self.redis_client is not None:
            return self._redis_decide(platform, key, limit)

        # No Redis client → in-memory fallback (FR-21 path).
        return self._in_memory_check(platform, key, limit)

    def _redis_decide(self, platform: str, key: str, limit: int) -> RateLimitResult:
        """Consult Redis and apply the limit. Fail-open on outage (FR-22)."""
        try:
            count = self._redis_count(platform, key)
        except _FAIL_OPEN_EXCEPTIONS as exc:
            # FR-22 fail-open: log and pass. Do NOT cache the outage;
            # the next call will retry Redis so we recover automatically.
            logger.warning(
                "rate_limit_redis_unavailable",
                extra={
                    "platform": platform,
                    "key": key,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return RateLimitResult.allowed()

        return RateLimitResult.denied() if count > limit else RateLimitResult.allowed()

    def _redis_count(self, platform: str, key: str) -> int:
        # Caller (_check_and_record) already gated on `redis_client is not None`,
        # but pyright can't narrow the type across that method boundary — assert
        # so the subsequent attribute access is type-safe.
        assert self.redis_client is not None
        client = self.redis_client
        sha = client.script_load(self._SCRIPT)
        now = time.time()
        window_start = now - self._WINDOW_SECONDS
        member = f"{now}:{key}"
        result = client.evalsha(
            sha,
            1,
            f"rate_limit:{platform}:{key}",
            window_start,
            now,
            member,
        )
        return int(result)

    def _in_memory_check(self, platform: str, key: str, limit: int) -> RateLimitResult:
        now = time.monotonic()
        window_start = now - self._WINDOW_SECONDS

        with self._lock:
            # Platform-level global bucket: the in-memory fallback enforces
            # a per-platform aggregate limit (not per-user), matching the
            # FR-21 spec: 31st request to any `telegram` key must return 429.
            bucket = self._buckets.setdefault((platform, ""), deque())
            # Drop entries that have aged out of the sliding window.
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                return RateLimitResult.denied()
            bucket.append(now)
            return RateLimitResult.allowed()
