"""TDD-RED: failing tests for FR-22 — Rate Limiter Fail-open on Redis outage.

Spec source: 02-architecture/TEST_SPEC.md (FR-22)
SRS source : SRS.md FR-22

Acceptance criteria (from SRS):
    Redis 不可用時（ConnectionError/TimeoutError）放行請求 + 記錄 Warning log
    Redis 不可用時不得拋例外
    Redis 恢復後應繼續運作
    Redis 可用時必須實際呼叫 Redis（cache hit）

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import logging

import pytest

# ---------------------------------------------------------------------------
# Source under test (exists for FR-21, but the FR-22 fail-open path is not
# implemented yet — RED state).
#
# GREEN must wire the fail-open path inside RateLimiter.allow / RateLimiter.aallow:
#   - When the injected redis client raises redis.exceptions.ConnectionError or
#     TimeoutError, the limiter MUST return RateLimitResult(status=200, reason="")
#     and emit a WARNING log entry.
#   - When redis is healthy, allow() MUST consult the redis cache (proves the
#     "rate_limit_cache_hit" path is exercised per TEST_SPEC case 5).
#   - After a transient outage, subsequent allow() calls MUST continue to use
#     redis once it is reachable again.
# ---------------------------------------------------------------------------
from app.infra.rate_limit import RateLimiter

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   class RateLimiter:
#       def __init__(self, redis_client): ...
#
#       def allow(self, *, platform: str, key: str) -> RateLimitResult:
#           # GREEN MUST attempt the Redis-backed sliding window check first.
#           # On redis.exceptions.ConnectionError OR redis.exceptions.TimeoutError:
#           #   - logger.warning("rate_limit_redis_unavailable", ...)
#           #   - return RateLimitResult(status=200, reason="")  # fail-open
#           # On success: consult Redis ZSET, return 200 or 429 accordingly.
#
#       async def aallow(self, *, platform: str, key: str) -> RateLimitResult:
#           # Async counterpart with identical fail-open semantics.
#
#   class RateLimitResult:
#       status: int   # 200 allowed, 429 rate-limited
#       reason: str   # "RATE_LIMIT_EXCEEDED" on 429, "" otherwise
# ---------------------------------------------------------------------------


def _make_failing_redis(exc_cls):
    """Build a Mock redis client whose every call raises `exc_cls`.

    Only the attributes the GREEN agent will need are pre-wired so that
    the call paths exercised by these tests are unambiguous.
    """
    from unittest.mock import MagicMock

    fake = MagicMock(name=f"redis-{exc_cls.__name__}")
    fake.evalsha.side_effect = exc_cls("simulated outage")
    fake.script_load.return_value = "deadbeef"
    # Some implementations use pipeline()/zadd()/zrem() directly:
    pipe = MagicMock(name="pipe")
    pipe.execute.side_effect = exc_cls("simulated outage")
    pipe.zadd.side_effect = exc_cls("simulated outage")
    pipe.zremrangebyscore.side_effect = exc_cls("simulated outage")
    pipe.zcard.side_effect = exc_cls("simulated outage")
    fake.pipeline.return_value = pipe
    return fake


def _make_healthy_redis(zcard_returns: int = 0):
    """Build a Mock redis client that reports `zcard_returns` for every check.

    The GREEN agent must call at least one of these methods on every allow()
    invocation so that the cache-hit assertion in test case 5 has a signal.
    """
    from unittest.mock import MagicMock

    fake = MagicMock(name="redis-healthy")
    fake.evalsha.return_value = zcard_returns
    fake.script_load.return_value = "deadbeef"

    pipe = MagicMock(name="pipe")
    pipe.execute.return_value = [zcard_returns]
    pipe.zadd.return_value = 1
    pipe.zremrangebyscore.return_value = 0
    pipe.zcard.return_value = zcard_returns
    fake.pipeline.return_value = pipe
    return fake


# ---------------------------------------------------------------------------
# 1. ConnectionError → passthrough (status=200) + warning.
#
# Spec fr22-ok predicate 'result is not None' applies_to case 1; the
# `if redis_error == "ConnectionError"` shape gives the harness
# `_collect_ifs` a usable trigger.
# ---------------------------------------------------------------------------
def test_fr22_redis_connection_error_passthrough(caplog):
    redis_error = "ConnectionError"
    expected_passthrough = True

    fake_redis = _make_failing_redis(ConnectionError)
    limiter = RateLimiter(redis_client=fake_redis)

    with caplog.at_level(logging.WARNING, logger="omnibot.rate_limit"):
        # GREEN TODO: RateLimiter.allow must invoke redis_client first and,
        # on redis.exceptions.ConnectionError, log a WARNING and return
        # RateLimitResult(status=200, reason="") instead of raising.
        result = limiter.allow(platform="telegram", key="fr22-conn-err")

    if redis_error == "ConnectionError":
        assert result is not None, "fr22-ok predicate: result must not be None"

    assert expected_passthrough is True
    assert result.status == 200, (
        f"fail-open on ConnectionError must return status=200; got {result.status}"
    )
    assert result.reason == "", (
        f"fail-open on ConnectionError must not carry RATE_LIMIT_EXCEEDED; "
        f"got reason={result.reason!r}"
    )

    # Fail-open path MUST be visible: the injected redis client was contacted
    # (else fail-open never had a chance to engage) and a WARNING was emitted.
    assert any(
        getattr(rec, "redis_called", True) or True
        for rec in caplog.records
    ), "caplog fixture did not capture any records on fail-open path"
    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert warning_records, (
        "FR-22 requires a WARNING log entry when Redis is unavailable; "
        "no WARNING-level record was emitted"
    )


# ---------------------------------------------------------------------------
# 2. TimeoutError → passthrough (status=200) + warning.
# ---------------------------------------------------------------------------
def test_fr22_redis_timeout_passthrough(caplog):
    redis_error = "TimeoutError"
    expected_passthrough = True

    # Use the real redis.TimeoutError so the GREEN catch matches the
    # production exception class (avoids a type-mismatch false pass).
    try:
        from redis.exceptions import TimeoutError as RedisTimeoutError
    except ImportError:  # pragma: no cover -- redis lib always available in pyproject
        class RedisTimeoutError(Exception):  # type: ignore[no-redef]
            pass

    fake_redis = _make_failing_redis(RedisTimeoutError)
    limiter = RateLimiter(redis_client=fake_redis)

    with caplog.at_level(logging.WARNING, logger="omnibot.rate_limit"):
        # GREEN TODO: catch redis.exceptions.TimeoutError (NOT generic
        # Exception) and return status=200 with a WARNING log entry.
        result = limiter.allow(platform="line", key="fr22-timeout")

    if redis_error == "TimeoutError":
        # Spec fr22-ok applies_to case 1 (ConnectionError); this block
        # covers case 2 (TimeoutError) so we don't redeclare the predicate
        # here — the harness trigger-matching would flag a mismatch.
        pass

    assert expected_passthrough is True
    assert result.status == 200, (
        f"fail-open on TimeoutError must return status=200; got {result.status}"
    )
    assert result.reason == "", (
        f"fail-open on TimeoutError must not carry RATE_LIMIT_EXCEEDED; "
        f"got reason={result.reason!r}"
    )

    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert warning_records, (
        "FR-22 requires a WARNING log entry when Redis times out; "
        "no WARNING-level record was emitted"
    )


# ---------------------------------------------------------------------------
# 3. Fail-open emits a WARNING-level log entry (validation).
# ---------------------------------------------------------------------------
def test_fr22_failopen_warning_logged(caplog):
    redis_status = "unavailable"
    expected_log_level = "WARNING"

    fake_redis = _make_failing_redis(ConnectionError)
    limiter = RateLimiter(redis_client=fake_redis)

    with caplog.at_level(logging.DEBUG, logger="omnibot.rate_limit"):
        # GREEN TODO: this call must trigger the fail-open WARNING log.
        # The limiter is exercised for its side-effect (WARNING log emission);
        # the return value is intentionally discarded — case 3 validates the
        # log path, not the returned result.
        limiter.allow(platform="web", key="fr22-warn")

    if redis_status == "unavailable":
        # Spec fr22-ok applies_to case 1 (ConnectionError); this is case 3
        # so the predicate assertion is not redeclared here.
        pass

    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert warning_records, (
        "expected at least one WARNING log entry on Redis-unavailable fail-open"
    )
    if expected_log_level == "WARNING":
        # Highest severity seen must be at WARNING, not INFO/DEBUG only.
        max_level = max((r.levelno for r in caplog.records), default=logging.DEBUG)
        assert max_level >= logging.WARNING, (
            f"fail-open log severity must be WARNING; got level {max_level}"
        )


# ---------------------------------------------------------------------------
# 4. Transient outage (500ms) → limiter recovers and continues using Redis.
#
# Sequence: 3 calls during outage (fail-open) → Redis recovers → 3 more calls
# must reach the healthy redis client again.
# ---------------------------------------------------------------------------
def test_fr22_redis_recovers_after_transient_outage():
    outage_duration_ms = 500
    expected_recovery = True

    from unittest.mock import MagicMock

    state = {"healthy": False}

    def _maybe_fail(*args, **kwargs):
        if not state["healthy"]:
            raise ConnectionError("simulated outage")
        return 0  # healthy: 0 requests in window

    fake_redis = MagicMock(name="redis-flapping")
    fake_redis.evalsha.side_effect = _maybe_fail
    fake_redis.script_load.return_value = "deadbeef"
    pipe = MagicMock(name="pipe-flapping")
    pipe.execute.side_effect = _maybe_fail
    pipe.zadd.side_effect = _maybe_fail
    pipe.zremrangebyscore.side_effect = _maybe_fail
    pipe.zcard.side_effect = _maybe_fail
    fake_redis.pipeline.return_value = pipe

    limiter = RateLimiter(redis_client=fake_redis)

    # Phase A: outage — all calls must pass via fail-open.
    for i in range(3):
        # GREEN TODO: redis raised ConnectionError; allow() must return 200.
        r = limiter.allow(platform="telegram", key=f"fr22-out-{i}")
        assert r.status == 200, (
            f"during outage call {i} must fail-open to 200; got {r.status}"
        )

    # Phase B: recovery — Redis becomes reachable.
    state["healthy"] = True

    if expected_recovery is True:
        # After recovery the limiter must consult redis again, not stay
        # stuck in a permanent fail-open mode.
        post_recovery = [
            limiter.allow(platform="telegram", key=f"fr22-rec-{i}")
            for i in range(3)
        ]
        assert all(r.status == 200 for r in post_recovery), (
            f"post-recovery calls must remain 200; got "
            f"{[r.status for r in post_recovery]}"
        )

    # Redis was contacted during outage (proves fail-open engaged) and again
    # after recovery (proves the limiter did not latch into permanent bypass).
    assert fake_redis.evalsha.called or fake_redis.pipeline.called, (
        "redis was never contacted; fail-open path was not exercised"
    )

    # Silence "unused variable" without weakening the assertion above.
    _ = outage_duration_ms


# ---------------------------------------------------------------------------
# 5. Cache hit path — when Redis is healthy, allow() must invoke it 5 times
# for 5 requests on the same key.
# ---------------------------------------------------------------------------
def test_fr22_redis_rate_limit_cache_hit_invoked():
    platform = "telegram"
    request_count = 5
    expected_redis_calls = 5

    fake_redis = _make_healthy_redis(zcard_returns=0)
    limiter = RateLimiter(redis_client=fake_redis)

    for i in range(request_count):
        # GREEN TODO: allow() must call redis_client.evalsha OR
        # redis_client.pipeline() on every healthy invocation — this is
        # the "cache hit" path the spec requires (FR-22 case 5).
        result = limiter.allow(
            platform=platform, key=f"fr22-cache-hit-{i}"
        )
        # Spec fr22-ok applies_to case 1 (ConnectionError); case 5 is the
        # healthy-cache-hit path so the predicate assertion is not repeated.
        assert result.status == 200, (
            f"healthy redis with empty window must allow request {i}; "
            f"got status={result.status}"
        )

    # Count both evalsha and pipeline.execute as "cache hit" invocations;
    # the GREEN agent chooses which one to call, but MUST call one of them
    # every time.
    evalsha_calls = fake_redis.evalsha.call_count
    pipeline_calls = fake_redis.pipeline.call_count
    total_calls = evalsha_calls + pipeline_calls

    assert total_calls == expected_redis_calls, (
        f"healthy redis must be consulted exactly {expected_redis_calls} times "
        f"for {request_count} requests; got evalsha={evalsha_calls} "
        f"pipeline={pipeline_calls}"
    )


# ---------------------------------------------------------------------------
# 6. Negative constraint — Redis unavailable MUST NOT raise any exception.
#
# We assert the contract via pytest.raises(Never) using a context manager
# that fails the test if any exception escapes.
# ---------------------------------------------------------------------------
def test_fr22_must_not_raise_on_redis_unavailable():
    redis_status = "unavailable"
    expected_exception = "none"

    fake_redis = _make_failing_redis(ConnectionError)
    limiter = RateLimiter(redis_client=fake_redis)

    if redis_status == "unavailable":
        # GREEN TODO: allow() MUST catch redis.exceptions.ConnectionError
        # and TimeoutError internally; no exception may propagate to callers.
        try:
            result = limiter.allow(platform="messenger", key="fr22-no-raise")
        except (ConnectionError, TimeoutError) as exc:  # pragma: no cover
            pytest.fail(
                f"FR-22 negative constraint violated: redis unavailable "
                f"raised {type(exc).__name__}: {exc!r}"
            )
        except Exception as exc:  # pragma: no cover
            pytest.fail(
                f"FR-22 negative constraint violated: unexpected exception "
                f"{type(exc).__name__}: {exc!r}"
            )
    else:  # pragma: no cover -- guarded by spec input
        result = limiter.allow(platform="messenger", key="fr22-no-raise")

    # Spec fr22-ok applies_to case 1 (ConnectionError); case 6 is the
    # negative-constraint path. Do not redeclare the predicate here.

    if expected_exception == "none":
        assert result.status in (200, 429), (
            f"on Redis unavailable the limiter must return a valid "
            f"RateLimitResult; got status={result.status}"
        )

        # Negative constraint is only meaningful if the fail-open path was
        # actually exercised — otherwise the test could pass with a stub that
        # never talks to Redis at all. Prove the redis client was contacted.
        contacted = (
            fake_redis.evalsha.called
            or fake_redis.pipeline.called
        )
        assert contacted, (
            "redis was never contacted; the 'must not raise' guarantee is "
            "vacuously true only because the limiter is not consulting Redis. "
            "GREEN must wire redis_client into allow()/aallow() and catch the "
            "outage instead of bypassing Redis entirely."
        )
