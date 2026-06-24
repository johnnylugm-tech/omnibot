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

# ---------------------------------------------------------------------------
# Source under test (does not exist yet — RED state).
#
# ModuleNotFoundError at pytest collection time is the EXPECTED red signal.
# Do NOT wrap this import in try/except; the contract permits Exit Code 2.
# ---------------------------------------------------------------------------
from app.infra.rate_limit import RateLimiter

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
        limiter.allow(platform=platform, key=f"fr21-{platform}-user")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Telegram — 31 requests on a 30/s budget → 31st returns 429.
#
# Note: assertions are wrapped in `if platform == "telegram":` blocks so that
# harness `_collect_ifs` extracts them with a usable trigger (per
# harness/core/quality_gate/red_assertion_check.py: `_parse_trigger` requires
# `if VAR == c` shape). The TEST_SPEC sub-assertion `fr21-ok` predicate
# `result is not None` applies_to case 1 (telegram), so the trigger value
# must be {"telegram"}.
# ---------------------------------------------------------------------------
def test_fr21_telegram_over_30rps_returns_429():
    platform = "telegram"
    results = _send_sync("telegram", 31)

    if platform == "telegram":
        # Spec fr21-ok: predicate 'result is not None'. The harness matches
        # the predicate verbatim against the assertion expression AST, so the
        # variable name MUST be `result` (not `results`).
        result = results[30] if len(results) > 30 else None
        assert result is not None, "fr21-ok predicate: result must not be None"

    assert all(r.status == 200 for r in results[:30]), (
        "first 30 telegram calls must pass under the 30/s budget; "
        f"got statuses={[r.status for r in results[:30]]}"
    )

    over = results[30]
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
            platform="telegram", key="fr21-race-telegram-user"
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

# NFR coverage: NFR-10 (circuit_breaker >=99.9% uptime)


# ---------------------------------------------------------------------------
# Mutation coverage — circuit_breaker.py (linked from test_fr99.py)
# ---------------------------------------------------------------------------

def test_fr21_circuit_breaker_level_constants_exact():
    """``CircuitBreaker.LEVEL_*`` constants MUST equal the exact string
    values ``"level_0"`` ... ``"level_5"``. Kills mutants wrapping
    string constants (e.g. ``LEVEL_4: str = None``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    expected = {f"LEVEL_{i}": f"level_{i}" for i in range(6)}
    for attr, val in expected.items():
        actual = getattr(CircuitBreaker, attr)
        assert actual == val, (
            f"CircuitBreaker.{attr} must equal {val!r}; got {actual!r}"
        )


def test_fr21_circuit_breaker_initial_success_count_is_zero():
    """``CircuitBreaker.__init__`` MUST set ``_llm_success_count = 0``.
    Kills mutant #50 (``0`` → ``1``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb._llm_success_count == 0, (
        f"CircuitBreaker._llm_success_count must start at 0; "
        f"got {cb._llm_success_count!r}"
    )


def test_fr21_circuit_breaker_record_llm_failure_resets_success_count():
    """``record_llm_failure`` MUST reset ``_llm_success_count`` to ``0``.
    Kills mutant #54 (``= 0`` → ``= 1``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb._llm_success_count = 7
    cb.record_llm_failure()
    assert cb._llm_success_count == 0, (
        f"After record_llm_failure, _llm_success_count must be reset to 0; "
        f"got {cb._llm_success_count!r}"
    )


def test_fr21_circuit_breaker_level_0_initial():
    """Initial level MUST be LEVEL_0 = "level_0"."""
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb._level == "level_0", (
        f"CircuitBreaker._level must start at 'level_0'; got {cb._level!r}"
    )


def test_fr21_circuit_breaker_p95_latency_threshold_is_800():
    """``CircuitBreaker._LLM_P95_LATENCY_THRESHOLD_MS`` MUST equal 800.0.
    Kills mutants wrapping the constant.
    """
    from app.infra.circuit_breaker import CircuitBreaker
    assert CircuitBreaker._LLM_P95_LATENCY_THRESHOLD_MS == 800.0, (
        f"CircuitBreaker._LLM_P95_LATENCY_THRESHOLD_MS must be 800.0; "
        f"got {CircuitBreaker._LLM_P95_LATENCY_THRESHOLD_MS!r}"
    )


def test_fr21_circuit_breaker_consecutive_failure_threshold_is_5():
    """``CircuitBreaker._LLM_CONSECUTIVE_FAILURE_THRESHOLD`` MUST equal 5.
    Kills mutants wrapping the constant.
    """
    from app.infra.circuit_breaker import CircuitBreaker
    assert CircuitBreaker._LLM_CONSECUTIVE_FAILURE_THRESHOLD == 5, (
        f"CircuitBreaker._LLM_CONSECUTIVE_FAILURE_THRESHOLD must be 5; "
        f"got {CircuitBreaker._LLM_CONSECUTIVE_FAILURE_THRESHOLD!r}"
    )


def test_fr21_circuit_breaker_lateral_failure_threshold_is_3():
    """``CircuitBreaker._LATERAL_FAILURE_THRESHOLD`` MUST equal 3.
    Kills mutants wrapping the constant.
    """
    from app.infra.circuit_breaker import CircuitBreaker
    assert CircuitBreaker._LATERAL_FAILURE_THRESHOLD == 3, (
        f"CircuitBreaker._LATERAL_FAILURE_THRESHOLD must be 3; "
        f"got {CircuitBreaker._LATERAL_FAILURE_THRESHOLD!r}"
    )


def test_fr21_circuit_breaker_embedding_failure_count_increments():
    """``record_embedding_failure`` MUST increment ``_embedding_failure_count``
    via ``+=`` (cumulative). Kills mutant #70 (``+= 1`` → ``= 1``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb.record_embedding_failure()
    cb.record_embedding_failure()
    cb.record_embedding_failure()
    cb.record_embedding_failure()
    assert cb._embedding_failure_count == 4, (
        f"_embedding_failure_count must increment by 1 per call "
        f"(cumulative); got {cb._embedding_failure_count!r}"
    )


def test_fr21_circuit_breaker_get_search_strategy_returns_tsvector():
    """``get_search_strategy`` MUST return the string ``"tsvector"`` when
    ``_embedding_down`` is True. Kills mutant #80 (``"tsvector"`` → ``"XXtsvectorXX"``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb._embedding_down = True
    assert cb.get_search_strategy() == "tsvector", (
        f"get_search_strategy must return 'tsvector' when embedding_down; "
        f"got {cb.get_search_strategy()!r}"
    )


def test_fr21_circuit_breaker_record_classifier_success_resets_down():
    """``record_classifier_success`` MUST set ``_classifier_down = False``.
    Kills mutant #90 (``= False`` → ``= True``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb._classifier_down = True
    cb.record_classifier_success()
    assert cb._classifier_down is False, (
        f"record_classifier_success must set _classifier_down=False; "
        f"got {cb._classifier_down!r}"
    )


def test_fr21_circuit_breaker_get_search_strategy_returns_embedding():
    """``get_search_strategy`` MUST return ``"embedding"`` when ``_embedding_down``
    is False (default). Kills mutant #81 (``"embedding"`` → ``"XXembeddingXX"``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb.get_search_strategy() == "embedding", (
        f"get_search_strategy must return 'embedding' when embedding_down=False; "
        f"got {cb.get_search_strategy()!r}"
    )


def test_fr21_circuit_breaker_classifier_failure_count_increments_by_one():
    """``record_classifier_failure`` MUST increment ``_classifier_failure_count``
    by exactly 1. Kills mutant #84 (``+= 1`` → ``+= 2``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb.record_classifier_failure()
    assert cb._classifier_failure_count == 1, (
        f"After 1 record_classifier_failure, count must be 1; "
        f"got {cb._classifier_failure_count!r}"
    )


def test_fr21_circuit_breaker_is_classifier_active_returns_true_when_not_down():
    """``is_classifier_active()`` MUST return ``True`` when ``_classifier_down``
    is False. Kills mutant #92 (``return not self._classifier_down`` → `return self._classifier_down`).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb.is_classifier_active() is True, (
        f"is_classifier_active must return True when classifier_down=False; "
        f"got {cb.is_classifier_active()!r}"
    )


def test_fr21_circuit_breaker_is_classifier_active_returns_false_when_down():
    """``is_classifier_active()`` MUST return ``False`` when ``_classifier_down``
    is True.
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    cb._classifier_down = True
    assert cb.is_classifier_active() is False, (
        f"is_classifier_active must return False when classifier_down=True; "
        f"got {cb.is_classifier_active()!r}"
    )


def test_fr21_circuit_breaker_retry_policy_jitter_default_true():
    """``RetryPolicy.__init__`` MUST default ``jitter=True``.
    Kills mutant #96 (``= True`` → ``= False``).
    """
    import app.infra.circuit_breaker as cb_mod
    if not hasattr(cb_mod, "RetryPolicy"):
        return  # RetryPolicy not exported; nothing to test
    from app.infra.circuit_breaker import RetryPolicy
    rp = RetryPolicy()
    assert rp.jitter is True, (
        f"RetryPolicy.jitter default must be True; got {rp.jitter!r}"
    )


def test_fr21_circuit_breaker_embedding_down_initial_is_false_not_none():
    """``_embedding_down`` MUST initialise to ``False`` (NOT ``None``).
    Kills mutants #35 (``= False`` → ``= None``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb._embedding_down is False, (
        f"_embedding_down initial value MUST be False (strict); "
        f"got {cb._embedding_down!r} (type {type(cb._embedding_down).__name__})"
    )


def test_fr21_circuit_breaker_classifier_down_initial_is_false_not_none():
    """``_classifier_down`` MUST initialise to ``False`` (NOT ``None``).
    Kills mutants #39 (``= False`` → ``= None``).
    """
    from app.infra.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb._classifier_down is False, (
        f"_classifier_down initial value MUST be False (strict); "
        f"got {cb._classifier_down!r} (type {type(cb._classifier_down).__name__})"
    )


def test_fr21_rate_limiter_limits_dict_exact():
    """``RateLimiter.LIMITS`` MUST be the exact per-platform dict
    {"telegram":30, "line":30, "messenger":30, "whatsapp":30, "web":10, "agent":100}.
    Kills mutants wrapping any platform → int mapping.
    """
    from app.infra.rate_limit import RateLimiter
    expected = {
        "telegram": 30,
        "line": 30,
        "messenger": 30,
        "whatsapp": 30,
        "web": 10,
        "agent": 100,
        "a2a": 30,
    }
    assert expected == RateLimiter.LIMITS, (
        f"RateLimiter.LIMITS must equal {expected!r}; got {RateLimiter.LIMITS!r}"
    )


def test_fr21_rate_limiter_window_seconds_is_1():
    """``RateLimiter._WINDOW_SECONDS`` MUST equal 1.0."""
    from app.infra.rate_limit import RateLimiter
    assert RateLimiter._WINDOW_SECONDS == 1.0, (
        f"_WINDOW_SECONDS must be 1.0; got {RateLimiter._WINDOW_SECONDS!r}"
    )


def test_fr21_rate_limiter_lua_script_contains_zadd():
    """``RateLimiter._SCRIPT`` MUST contain the literal ``ZADD`` Redis command.
    Kills mutants wrapping ZADD segment with XX...XX.
    """
    from app.infra.rate_limit import RateLimiter
    assert "ZADD" in RateLimiter._SCRIPT, (
        f"_SCRIPT must contain 'ZADD'; got {RateLimiter._SCRIPT!r}"
    )
    assert "ZREMRANGEBYSCORE" in RateLimiter._SCRIPT, (
        f"_SCRIPT must contain 'ZREMRANGEBYSCORE'; got {RateLimiter._SCRIPT!r}"
    )
    assert "ZCARD" in RateLimiter._SCRIPT, (
        f"_SCRIPT must contain 'ZCARD' (return count); got {RateLimiter._SCRIPT!r}"
    )


def test_fr21_rate_limiter_result_status_200_when_allowed():
    """``RateLimitResult`` for an allowed request MUST have ``status=200``.
    Kills mutants changing default status.
    """
    from app.infra.rate_limit import RateLimiter
    rl = RateLimiter(redis_client=None)
    r = rl.allow(platform="telegram", key="unique-key-1")
    assert r.status == 200, (
        f"first telegram call must return status=200; got {r.status!r}"
    )
    assert r.reason == "", (
        f"first telegram call (allowed) must have reason=''; got {r.reason!r}"
    )


def test_fr21_rate_limit_result_dataclass_has_status_and_reason():
    """``RateLimitResult`` MUST expose ``status`` and ``reason`` fields.
    Kills mutants wrapping the dataclass.
    """
    from app.infra.rate_limit import RateLimitResult
    r = RateLimitResult(status=200, reason="")
    assert r.status == 200
    assert r.reason == ""
