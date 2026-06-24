"""Mutation-killing tests for app.infra.rate_limit.

Field-level invariants to kill mutmut survivors (initial 31.9%; need 70%).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.infra.rate_limit import (  # noqa: E402
    RateLimiter,
    RateLimitResult,
)


def test_rate_limit_result_allowed_factory() -> None:
    """Mutant on ``RateLimitResult.allowed_result()`` flipping status or reason.
    """
    r = RateLimitResult.allowed_result()
    assert r.status == 200
    assert r.reason == ""


def test_rate_limit_result_denied_factory() -> None:
    """Mutant on ``RateLimitResult.denied()`` flipping status (200 instead
    of 429) or reason string.
    """
    r = RateLimitResult.denied()
    assert r.status == 429
    assert r.reason == "RATE_LIMIT_EXCEEDED"


def test_rate_limit_result_frozen() -> None:
    """Mutant removing ``frozen=True`` would allow field mutation.
    """
    r = RateLimitResult.allowed_result()
    try:
        r.status = 500  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "RateLimitResult must be frozen (mutant removes @dataclass(frozen=True))"


def test_rate_limit_limits_table() -> None:
    """Mutant on the per-platform limit table — values 30/10/100 etc.
    Asserting the dict exactly guards against changes.
    """
    assert RateLimiter.LIMITS == {
        "telegram": 30,
        "line": 30,
        "messenger": 30,
        "whatsapp": 30,
        "web": 10,
        "agent": 100,
        "a2a": 30,
    }


def test_rate_limit_unknown_platform_fails_open() -> None:
    """Mutant on the unknown-platform branch — failing closed (return denied)
    would break FR-22. The contract is fail-open.
    """
    rl = RateLimiter()
    result = rl.allow(platform="unknown_platform_xyz", key="user1")
    assert result.status == 200
    assert result.reason == ""


def test_rate_limit_first_request_allowed() -> None:
    """A first request for a (platform, key) tuple must be allowed
    (the bucket starts empty, count=1 < limit).
    """
    rl = RateLimiter()
    result = rl.allow(platform="telegram", key="user_first")
    assert result.status == 200


def test_rate_limit_in_memory_below_limit_allowed() -> None:
    """Send N-1 requests (where N=telegram limit=30) — all must pass.
    """
    rl = RateLimiter()
    for i in range(29):  # 30 - 1 = 29 should pass
        result = rl.allow(platform="telegram", key=f"user_{i}")
        assert result.status == 200, f"request {i} should be allowed"


def test_rate_limit_in_memory_exceeds_limit_denied() -> None:
    """Send 31 requests for the same key — the 31st must be denied
    (sliding-window overflow).

    Mutant that resets the bucket or doesn't trim expired entries would
    fail this.
    """
    rl = RateLimiter()
    for _i in range(30):
        rl.allow(platform="telegram", key="user_overflow")
    # 31st request must be denied.
    result = rl.allow(platform="telegram", key="user_overflow")
    assert result.status == 429
    assert result.reason == "RATE_LIMIT_EXCEEDED"


def test_rate_limit_per_key_isolation() -> None:
    """Mutant that uses a single global bucket would fail this: different
    keys must be independent.
    """
    rl = RateLimiter()
    for _ in range(30):
        rl.allow(platform="telegram", key="user_a")
    # user_a is now at limit; user_b must still be allowed.
    result = rl.allow(platform="telegram", key="user_b")
    assert result.status == 200
