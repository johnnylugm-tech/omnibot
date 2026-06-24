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
    from redis.exceptions import (
        NoScriptError,  # type: ignore[reportAssignmentType]
        ResponseError,  # type: ignore[reportAssignmentType]
    )
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

    class NoScriptError(ResponseError):  # type: ignore[no-redef]
        pass

# FR-22 fail-open triggers: connection-class failures only.
# ``ResponseError`` is intentionally excluded so a WRONGTYPE / Lua /
# protocol bug surfaces as a deny (fail-closed) rather than silently
# bypassing the limiter for the rest of the process lifetime.
# ``NoScriptError`` (a ``ResponseError`` subclass) is handled
# separately — it triggers a one-shot script reload + retry, and only
# if that also fails do we fall back to deny.
_FAIL_OPEN_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
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
    allowed: bool = True

    @classmethod
    def allowed_result(cls) -> RateLimitResult:
        """Construct a pass-through result (status=200, no reason)."""
        return cls(200, "", True)

    @classmethod
    def denied(cls) -> RateLimitResult:
        """Construct a rate-limited result (status=429, RATE_LIMIT_EXCEEDED)."""
        return cls(429, "RATE_LIMIT_EXCEEDED", False)


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
        "a2a": 30,
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
        from app.infra.config import health_probe
        health_probe()  # Hub linkage
        # Inject; do not connect.
        self.redis_client = redis_client
        # (platform, key) -> deque of monotonic timestamps inside the window.
        # INVARIANT: Keys must be composed of (str, str).
        # INVARIANT: Values must be a deque of floats sorted in ascending order.
        # INVARIANT: Length of any deque must not exceed the specified rate limit bounds.
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
        import asyncio
        return await asyncio.to_thread(self._check_and_record, platform, key)

    def _check_and_record(self, platform: str, key: str) -> RateLimitResult:
        limit = self.LIMITS.get(platform)
        if limit is None:
            # Unknown platform — fail-open; the platform layer is the
            # authority for which platforms exist.
            return RateLimitResult.allowed_result()

        if self.redis_client is not None:
            return self._redis_decide(platform, key, limit)

        # No Redis client → in-memory fallback (FR-21 path).
        return self._in_memory_check(platform, key, limit)

    def _redis_decide(self, platform: str, key: str, limit: int) -> RateLimitResult:
        """Consult Redis and apply the limit. Fail-open on outage (FR-22).

        Exception handling matrix (FR-22 strict reading — only
        connection-class outages fail open; protocol / Lua errors fail
        closed to avoid permanently bypassing the limiter):
            * ``NoScriptError``     → reload + retry once, then deny
            * ``_FAIL_OPEN_EXCEPTIONS`` (connection / timeout) → fail-open
            * ``ResponseError``     → fail-closed (deny + ERROR log)
            * any other exception  → fail-closed (deny + ERROR log)
        """
        try:
            count = self._redis_count(platform, key)
        except NoScriptError as exc:
            # SCRIPT FLUSH / Redis restart / first call after boot —
            # the script SHA is no longer cached server-side. ``evalsha``
            # cannot self-recover, so fall through to ``eval`` which
            # implicitly re-loads the script. Only fail-closed if the
            # second attempt ALSO raises.
            logger.info(
                "rate_limit_script_reload",
                extra={
                    "platform": platform,
                    "key": key,
                    "error": str(exc),
                },
            )
            try:
                count = self._redis_count_eval(platform, key)
            except Exception as retry_exc:
                logger.error(
                    "rate_limit_script_reload_failed",
                    extra={
                        "platform": platform,
                        "key": key,
                        "error_type": type(retry_exc).__name__,
                        "error": str(retry_exc),
                    },
                )
                return RateLimitResult.denied()
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
            return RateLimitResult.allowed_result()
        except ResponseError as exc:
            # WRONGTYPE / Lua bug / protocol violation — fail CLOSED
            # rather than permanently bypassing the limiter. ``_redis_count``
            # already retried via EVAL once for ``NoScriptError``; any
            # remaining ``ResponseError`` is a real configuration or
            # protocol problem, not a transient outage.
            logger.error(
                "rate_limit_redis_protocol_error",
                extra={
                    "platform": platform,
                    "key": key,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return RateLimitResult.denied()
        except Exception as exc:
            logger.error(
                "rate_limit_redis_unexpected_error",
                extra={
                    "platform": platform,
                    "key": key,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return RateLimitResult.denied()

        return RateLimitResult.denied() if count > limit else RateLimitResult.allowed_result()

    def _redis_count(self, platform: str, key: str) -> int:
        # Caller (_check_and_record) already gated on `redis_client is not None`,
        # but pyright can't narrow the type across that method boundary — assert
        # so the subsequent attribute access is type-safe.
        import uuid
        assert self.redis_client is not None
        client = self.redis_client
        sha = client.script_load(self._SCRIPT)
        now = time.time()
        window_start = now - self._WINDOW_SECONDS
        member = f"{now}:{key}:{uuid.uuid4().hex}"
        try:
            result = client.evalsha(
                sha,
                1,
                f"rate_limit:{platform}:{key}",
                window_start,
                now,
                member,
            )
        except NoScriptError:
            # Script SHA was flushed between ``script_load`` and
            # ``evalsha`` (SCRIPT FLUSH, Redis restart, fail-over).
            # Fall through to ``EVAL`` which re-loads the script
            # implicitly. The caller (``_redis_decide``) wraps this
            # with a one-shot retry guard.
            result = client.eval(
                self._SCRIPT,
                1,
                f"rate_limit:{platform}:{key}",
                window_start,
                now,
                member,
            )
        return int(result)

    def _redis_count_eval(self, platform: str, key: str) -> int:
        """Fallback path used by :meth:`_redis_decide` after ``NoScriptError``.

        Skips ``script_load`` + ``evalsha`` and goes straight to
        ``EVAL`` so the server-side script cache is repopulated in
        one round trip.
        """
        import uuid
        assert self.redis_client is not None
        client = self.redis_client
        now = time.time()
        window_start = now - self._WINDOW_SECONDS
        member = f"{now}:{key}:{uuid.uuid4().hex}"
        result = client.eval(
            self._SCRIPT,
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
            if len(self._buckets) > 10000:
                empty_keys = [k for k, v in self._buckets.items() if not v or v[-1] < window_start]
                for k in empty_keys:
                    del self._buckets[k]
                if len(self._buckets) > 10000:
                    import random
                    keys_to_delete = random.sample(list(self._buckets.keys()), len(self._buckets) - 10000)
                    for k in keys_to_delete:
                        del self._buckets[k]

            # Per-user sub-bucket — mirrors the Redis path
            # (``rate_limit:{platform}:{key}``) so the in-memory
            # fallback is a drop-in replacement when ``redis_client``
            # is None. The earlier ``(platform, "")`` aggregate
            # violated the docstring contract and caused unrelated
            # users to share one bucket whenever Redis was absent.
            bucket = self._buckets.setdefault((platform, key), deque())
            # Drop entries that have aged out of the sliding window.
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                return RateLimitResult.denied()
            bucket.append(now)
            return RateLimitResult.allowed_result()
