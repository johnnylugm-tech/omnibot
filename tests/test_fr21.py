"""TDD-RED: failing tests for FR-21 — Redis sliding window rate limiter.

Spec source: 02-architecture/TEST_SPEC.md (FR-21)
SRS source : SRS.md FR-21

Acceptance criteria (from SRS):
    Telegram / LINE / Messenger / WhatsApp : 30 req/s
    Web                                     : 10 req/s
    Agent                                   : 100 req/s
    Over limit                              : 429 RATE_LIMIT_EXCEEDED
    Lua atomic ZSET                         : no race condition under concurrency

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------------------
# Source under test (does not exist yet — RED state).
#
# ModuleNotFoundError at pytest collection time is the EXPECTED red signal.
# Do NOT wrap this import in try/except; the contract permits Exit Code 2.
# ---------------------------------------------------------------------------
from app.infra.rate_limit import RateLimiter  # noqa: F401  -- RED expected


# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   class RateLimiter:
#       def __init__(self, redis_client): ...          # inject, do not connect
#
#       def allow(self, *, platform: str, key: str) -> RateLimitResult:
#           # Sync API. Must execute one atomic Lua ZSET script. Status 200
#           # when allowed, 429 with reason "RATE_LIMIT_EXCEEDED" when over.
#
#       async def aallow(self, *, platform: str, key: str) -> RateLimitResult:
#           # Async counterpart used by the concurrency test below.
#
#   class RateLimitResult:
#       status: int   # 200 allowed, 429 rate-limited
#       reason: str   # "RATE_LIMIT_EXCEEDED" on 429, "" otherwise
#
# Per-platform limits (must be encoded in GREEN):
#     {"telegram": 30, "line": 30, "messenger": 30, "whatsapp": 30,
#      "web": 10, "agent": 100}
# ---------------------------------------------------------------------------


def _send_sync(platform: str, n: int) -> list:
    """Send `n` sequential calls on a fresh RateLimiter; return list of results."""
    limiter = RateLimiter(redis_client=None)
    return [
        limiter.allow(platform=platform, key=f"fr21-{platform}-{i}")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Telegram — 31 requests on a 30/s budget → 31st returns 429.
# ---------------------------------------------------------------------------
def test_fr21_telegram_over_30rps_returns_429():
    results = _send_sync("telegram", 31)

    assert all(r.status == 200 for r in results[:30]), (
        "first 30 telegram calls must pass under the 30/s budget; "
        f"got statuses={[r.status for r in results[:30]]}"
    )

    over = results[30]
    assert over is not None, "fr21-ok predicate: result must not be None"
    assert over.status == 429, f"31st telegram call must be 429, got {over.status}"
    assert over.reason == "RATE_LIMIT_EXCEEDED", (
        f"429 reason must be RATE_LIMIT_EXCEEDED, got {over.reason!r}"
    )


# ---------------------------------------------------------------------------
# 2. Web — 11 requests on a 10/s budget → 11th returns 429.
# ---------------------------------------------------------------------------
def test_fr21_web_over_10rps_returns_429():
    results = _send_sync("web", 11)

    assert all(r.status == 200 for r in results[:10]), (
        "first 10 web calls must pass under the 10/s budget; "
        f"got statuses={[r.status for r in results[:10]]}"
    )

    over = results[10]
    assert over is not None, "fr21-ok predicate: result must not be None"
    assert over.status == 429, f"11th web call must be 429, got {over.status}"
    assert over.reason == "RATE_LIMIT_EXCEEDED", (
        f"429 reason must be RATE_LIMIT_EXCEEDED, got {over.reason!r}"
    )


# ---------------------------------------------------------------------------
# 3. Agent — 101 requests on a 100/s budget → 101st returns 429.
# ---------------------------------------------------------------------------
def test_fr21_agent_over_100rps_returns_429():
    results = _send_sync("agent", 101)

    assert all(r.status == 200 for r in results[:100]), (
        "first 100 agent calls must pass under the 100/s budget"
    )

    over = results[100]
    assert over is not None, "fr21-ok predicate: result must not be None"
    assert over.status == 429, f"101st agent call must be 429, got {over.status}"
    assert over.reason == "RATE_LIMIT_EXCEEDED", (
        f"429 reason must be RATE_LIMIT_EXCEEDED, got {over.reason!r}"
    )


# ---------------------------------------------------------------------------
# 4. LINE — 31 requests on a 30/s budget → 31st returns 429.
# ---------------------------------------------------------------------------
def test_fr21_line_over_30rps_returns_429():
    results = _send_sync("line", 31)

    assert all(r.status == 200 for r in results[:30]), (
        "first 30 LINE calls must pass under the 30/s budget"
    )

    over = results[30]
    assert over is not None, "fr21-ok predicate: result must not be None"
    assert over.status == 429, f"31st LINE call must be 429, got {over.status}"
    assert over.reason == "RATE_LIMIT_EXCEEDED", (
        f"429 reason must be RATE_LIMIT_EXCEEDED, got {over.reason!r}"
    )


# ---------------------------------------------------------------------------
# 5. Lua atomicity — 50 concurrent telegram calls in the same window.
#
# Telegram limit is 30. A correct Lua-atomic implementation lets EXACTLY
# 30 through and 429s the remaining 20. A naive GET-then-ZADD from Python
# would over-admit under contention (race condition).
#
# pytest-asyncio is configured for asyncio_mode = "auto" in pyproject.toml,
# so the bare `async def` below is collected as an asyncio test.
# ---------------------------------------------------------------------------
async def test_fr21_lua_atomic_no_race_condition():
    limiter = RateLimiter(redis_client=None)

    async def one_call(i: int):
        # GREEN TODO: RateLimiter must expose an async entry point whose
        # body executes a single Lua script in one round-trip. Do NOT
        # split into read-then-write from Python.
        return await limiter.aallow(
            platform="telegram", key=f"fr21-race-telegram-{i}"
        )

    results = await asyncio.gather(*(one_call(i) for i in range(50)))

    allowed = [r for r in results if r.status == 200]
    denied = [r for r in results if r.status == 429]

    assert len(allowed) == 30, (
        f"atomic Lua must allow exactly 30 under 50 concurrent calls; "
        f"got {len(allowed)} (likely a race condition in ZSET handling)"
    )
    assert len(denied) == 20, f"expected 20 denied, got {len(denied)}"
    assert all(r.reason == "RATE_LIMIT_EXCEEDED" for r in denied), (
        "all denied results must carry the RATE_LIMIT_EXCEEDED reason"
    )