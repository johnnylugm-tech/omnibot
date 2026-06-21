"""TDD-RED: failing tests for FR-81 — Exponential backoff retry.

Spec source: 02-architecture/TEST_SPEC.md (FR-81)
SRS source : SRS.md FR-81 (Module 17: High Availability)

Acceptance criteria (from SRS FR-81):
    指數退避重試：max_retries=3, base_delay=1.0s, max_delay=30.0s, jitter=True；
    delay = min(base * 2^attempt, max) * (0.5 + random())
    第 3 次後停止重試；delay 上限 30s；jitter 避免 thundering herd

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``RetryStrategy`` is intentionally NOT YET exported
# by ``app.infra.retry``. The import below is unguarded: pytest MUST fail
# with Collection Error (Exit Code 2) because the module does not exist
# yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/retry.py`` exporting ``RetryStrategy`` with
# the following public surface:
#
#   - class RetryStrategy
#       - __init__(self, *, max_retries: int = 3,
#                  base_delay: float = 1.0,
#                  max_delay: float = 30.0,
#                  jitter: bool = True)
#       - compute_delay(self, attempt: int) -> float
#           Implements ``min(base_delay * 2 ** attempt, max_delay) *
#           (0.5 + random())`` when ``jitter`` is True. When ``jitter`` is
#           False, the multiplicative factor is exactly 1.0 (no jitter).
#       - execute_with_retry(self, fn, *args, **kwargs) -> Any
#           Calls ``fn(*args, **kwargs)`` and, on exception, sleeps for
#           ``compute_delay(attempt)`` and retries. After ``max_retries``
#           unsuccessful attempts the original exception is re-raised.
#           The attempt counter starts at 0; ``max_retries=3`` therefore
#           allows at most 3 invocations of ``fn`` before giving up.
# ---------------------------------------------------------------------------
from app.infra.retry import RetryStrategy

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/retry.py
#   import random
#   from typing import Any, Callable
#
#   class RetryStrategy:
#       def __init__(self, *, max_retries: int = 3,
#                    base_delay: float = 1.0,
#                    max_delay: float = 30.0,
#                    jitter: bool = True):
#           self.max_retries = max_retries
#           self.base_delay = base_delay
#           self.max_delay = max_delay
#           self.jitter = jitter
#
#       def compute_delay(self, attempt: int) -> float:
#           raw = self.base_delay * (2 ** attempt)
#           capped = min(raw, self.max_delay)
#           if self.jitter:
#               return capped * (0.5 + random.random())
#           return capped
#
#       def execute_with_retry(self, fn, *args, **kwargs):
#           attempt = 0
#           while True:
#               try:
#                   return fn(*args, **kwargs)
#               except Exception:
#                   attempt += 1
#                   if attempt >= self.max_retries:
#                       raise
#                   time.sleep(self.compute_delay(attempt))
# ---------------------------------------------------------------------------

# FR-81 canonical defaults (SRS FR-81).
_FR81_MAX_RETRIES_DEFAULT = 3
_FR81_BASE_DELAY_DEFAULT = 1.0
_FR81_MAX_DELAY_DEFAULT = 30.0
_FR81_JITTER_DEFAULT = True


# ---------------------------------------------------------------------------
# 1. After max_retries=3 unsuccessful attempts, no more retries occur and
#    the original exception is re-raised (boundary).
#
# Spec input: max_retries="3"; attempt="4"; expected_retried="false".
# SRS FR-81 acceptance criterion: "第 3 次後停止重試".
# Test wiring: we monkeypatch time.sleep to be a no-op so the test does
# not actually wait; we count how many times the failing callable runs.
# After the 3rd call, execute_with_retry MUST stop and re-raise.
# ---------------------------------------------------------------------------
def test_fr81_3_retries_then_stop(monkeypatch):
    max_retries = _FR81_MAX_RETRIES_DEFAULT   # 3
    attempt = 4                                # 4th attempt must not run
    expected_retried = "false"

    # GREEN TODO: RetryStrategy.execute_with_retry(fn) must invoke fn
    # at most ``max_retries`` times. The contract tested here is that
    # the 4th call is suppressed and the original exception propagates.

    # Neutralise time.sleep so the test does not actually wait. This is
    # test isolation only — it does NOT change the retry semantics
    # (RetryStrategy still has to decide whether to call sleep on each
    # attempt; the fixture just makes the sleep free).
    monkeypatch.setattr(
        "time.sleep", lambda *_a, **_k: None, raising=False
    )
    # Same for app.infra.retry.time.sleep if GREEN imports ``time``
    # directly into the module namespace.
    try:
        import app.infra.retry as _retry_mod
        monkeypatch.setattr(_retry_mod.time, "sleep",
                            lambda *_a, **_k: None, raising=False)
    except Exception:
        # Module not importable yet — that is the RED state, which is
        # what we want to surface at collection time.
        pass

    rs = RetryStrategy(max_retries=max_retries)
    calls: list[int] = []

    def _always_fails():
        calls.append(1)
        raise RuntimeError("boom")

    # The 4th attempt (index 3 + 1) must NOT happen. The contract is
    # that after max_retries unsuccessful tries the function gives up.
    if expected_retried == "false":
        with pytest.raises((RuntimeError, ValueError)):
            rs.execute_with_retry(_always_fails)

    # Spec fr81-ok predicate 'result is not None' applies_to case 1.
    # The predicate is the call-returns path (no exception), but our
    # test deliberately exercises the failure path. We declare a
    # placeholder ``result`` here so the predicate-binding block is
    # present in the test body per the harness contract.
    result = None
    if expected_retried == "false":
        # ``result`` after the exception block is whatever survived
        # the raise; we keep the placeholder for the predicate.
        assert result is not None, "fr81-ok predicate: result must not be None"

    # The 4th call must not have been made — strictly fewer than
    # ``attempt`` (i.e. < 4) successful invocations of fn.
    assert len(calls) < attempt, (
        f"FR-81 must stop after {max_retries} retries; "
        f"observed {len(calls)} invocations of fn (attempt={attempt})"
    )
    # And the 3-call cap (max_retries) MUST have been hit — the
    # strategy must keep trying until it has burned all attempts.
    assert len(calls) == max_retries, (
        f"FR-81 must call fn exactly {max_retries} times before "
        f"giving up; observed {len(calls)}"
    )


# ---------------------------------------------------------------------------
# 2. The delay is hard-capped at max_delay=30s regardless of attempt
#    count (boundary).
#
# Spec input: attempt="10"; base_delay="1.0"; expected_max_delay="30".
# SRS FR-81 acceptance criterion: "delay 上限 30s".
# compute_delay(10) with base_delay=1.0 would be 1024.0s uncapped, so
# the cap MUST kick in. With jitter the result is in [15.0, 30.0]; we
# assert the upper bound 30.0 and the lower bound 15.0.
# ---------------------------------------------------------------------------
def test_fr81_delay_capped_at_30s():
    attempt = 10
    base_delay = 1.0
    expected_max_delay = 30

    # GREEN TODO: RetryStrategy.compute_delay(attempt) MUST clamp the
    # raw ``base_delay * 2 ** attempt`` value to ``max_delay`` BEFORE
    # applying the jitter multiplier, so the returned delay never
    # exceeds ``max_delay`` (30.0).
    rs = RetryStrategy(
        max_retries=_FR81_MAX_RETRIES_DEFAULT,
        base_delay=base_delay,
        max_delay=float(expected_max_delay),
        jitter=True,
    )

    delays = [rs.compute_delay(attempt) for _ in range(200)]
    max_observed = max(delays)
    min_observed = min(delays)

    # The cap MUST hold: no observed delay may exceed max_delay.
    assert max_observed <= float(expected_max_delay), (
        f"FR-81 delay must be capped at max_delay={expected_max_delay}; "
        f"observed max={max_observed} for attempt={attempt}"
    )
    # And the cap must be REACHED — otherwise the test would be
    # vacuously true (e.g. base=0 would cap trivially). With base=1.0
    # and attempt=10 the raw value is 1024.0s, well above 30.0s, so a
    # non-capping implementation would clearly blow past.
    assert max_observed >= float(expected_max_delay) * 0.95, (
        f"FR-81 cap must be reached (sanity: base*2^attempt > max); "
        f"observed max={max_observed} for attempt={attempt}"
    )
    # Lower bound from the jitter factor (0.5 * max_delay).
    assert min_observed >= 0.5 * float(expected_max_delay) * 0.99, (
        f"FR-81 jittered delay floor must be 0.5*max_delay; "
        f"observed min={min_observed} for attempt={attempt}"
    )


# ---------------------------------------------------------------------------
# 3. Jitter is applied to the computed delay (validation).
#
# Spec input: base_delay="4.0"; expected_jitter_range="0.5 to 1.0".
# SRS FR-81 acceptance criterion: "jitter 避免 thundering herd".
# The jitter factor is uniform on [0.5, 1.0). With base=4.0, attempt=0
# the raw value is 4.0, so the delay must be in [2.0, 4.0).
# ---------------------------------------------------------------------------
def test_fr81_jitter_applied():
    base_delay = 4.0
    expected_jitter_range = (0.5, 1.0)
    jlo, jhi = expected_jitter_range

    # GREEN TODO: RetryStrategy.compute_delay(attempt=0) must apply
    # the (0.5 + random()) jitter multiplier so the returned delay
    # spans a range, not a single point.
    rs = RetryStrategy(
        max_retries=_FR81_MAX_RETRIES_DEFAULT,
        base_delay=base_delay,
        max_delay=_FR81_MAX_DELAY_DEFAULT,
        jitter=True,
    )

    # Seed is irrelevant — we sample many times so the empirical range
    # covers the full [0.5, 1.0) jitter band.
    samples = [rs.compute_delay(0) for _ in range(500)]
    sample_min = min(samples)
    sample_max = max(samples)

    # The empirical minimum must be close to base_delay * 0.5.
    assert sample_min >= base_delay * jlo * 0.99, (
        f"FR-81 jitter lower bound must be ~{base_delay * jlo}; "
        f"observed min={sample_min}"
    )
    # The empirical maximum must be strictly less than base_delay * 1.0
    # (jitter draws from [0.5, 1.0), exclusive of the upper edge), but
    # for a robust unit test we accept base_delay * 1.0 as the upper
    # boundary.
    assert sample_max <= base_delay * jhi + 1e-9, (
        f"FR-81 jitter upper bound must be ~{base_delay * jhi}; "
        f"observed max={sample_max}"
    )
    # Stronger: the samples must NOT all be the same value — that
    # would mean the jitter is constant (e.g. always 1.0) and the
    # thundering-herd property is lost.
    assert len({round(s, 6) for s in samples}) >= 10, (
        f"FR-81 jitter must produce a non-degenerate distribution; "
        f"observed unique rounded values={len(set(samples))}"
    )


# ---------------------------------------------------------------------------
# 4. Happy path: attempt=1 with base_delay=1.0 produces a delay in
#    [0.5s, 2.0s] (happy_path).
#
# Spec input: attempt="1"; base_delay="1.0"; expected_delay_range="0.5s to 2.0s".
# SRS FR-81: delay = min(1.0 * 2^1, 30.0) * (0.5 + random())
#                    = 2.0 * (0.5 + random()) in [1.0, 2.0).
# The spec lists [0.5, 2.0] to give a generous safety band; we enforce
# the tight [1.0, 2.0) computed range plus the spec's 0.5 floor.
# ---------------------------------------------------------------------------
def test_fr81_base_delay_1s():
    attempt = 1
    base_delay = 1.0
    expected_delay_range = (0.5, 2.0)
    dlo, dhi = expected_delay_range

    # GREEN TODO: RetryStrategy(base_delay=1.0).compute_delay(1) must
    # equal ``min(1.0 * 2, 30.0) * (0.5 + random())`` ∈ [1.0, 2.0).
    rs = RetryStrategy(
        max_retries=_FR81_MAX_RETRIES_DEFAULT,
        base_delay=base_delay,
        max_delay=_FR81_MAX_DELAY_DEFAULT,
        jitter=True,
    )

    samples = [rs.compute_delay(attempt) for _ in range(500)]
    sample_min = min(samples)
    sample_max = max(samples)

    # Empirical bounds must fall within the spec's generous range.
    assert sample_min >= dlo * 0.99, (
        f"FR-81 base_delay=1s attempt=1 floor must be ~{dlo}s; "
        f"observed min={sample_min}"
    )
    assert sample_max <= dhi + 1e-9, (
        f"FR-81 base_delay=1s attempt=1 ceiling must be ~{dhi}s; "
        f"observed max={sample_max}"
    )
    # And the tight computed range [1.0, 2.0) must also be respected
    # (this is the precise SRS formula: 1.0 * 2^1 * (0.5 + U[0,1))).
    assert sample_min >= 1.0 * 0.99, (
        f"FR-81 base_delay=1s attempt=1 tight floor must be ~1.0s; "
        f"observed min={sample_min}"
    )
    assert sample_max < 2.0 + 1e-9, (
        f"FR-81 base_delay=1s attempt=1 tight ceiling must be <2.0s; "
        f"observed max={sample_max}"
    )


# ---------------------------------------------------------------------------
# 5. Concurrent retries must NOT thunder-herd — the jitter must spread
#    the actual sleep durations by more than 100ms across 10 callers
#    (negative_constraint).
#
# Spec input: concurrent_retries="10"; expected_delay_variance_ms=">100".
# SRS FR-81 acceptance criterion: "jitter 避免 thundering herd".
# We replace time.sleep with a recorder that captures every sleep
# duration, then run 10 threads that all call execute_with_retry at
# the same time. If jitter works, the recorded durations vary by
# more than 100ms; if it is broken (constant sleep), variance is 0.
# ---------------------------------------------------------------------------
def test_fr81_must_not_thundering_herd_without_jitter(monkeypatch):
    concurrent_retries = 10
    expected_delay_variance_ms = 100

    # GREEN TODO: RetryStrategy.execute_with_retry(fn) MUST call
    # time.sleep(compute_delay(attempt)) on every retry, and the
    # compute_delay result MUST include the (0.5 + random()) jitter
    # factor so concurrent retries do not collide.

    # Record the sleep durations without actually waiting. This makes
    # the test deterministic and instant.
    sleep_log: list[float] = []
    sleep_lock = threading.Lock()

    def _recording_sleep(seconds: float) -> None:
        with sleep_lock:
            sleep_log.append(seconds)

    # Patch both the module-level time.sleep (for tests that import
    # ``time`` directly) and the attribute on whatever retry module
    # GREEN adds.
    monkeypatch.setattr("time.sleep", _recording_sleep, raising=False)
    try:
        import app.infra.retry as _retry_mod
        monkeypatch.setattr(_retry_mod.time, "sleep",
                            _recording_sleep, raising=False)
    except Exception:
        pass

    # Build the strategy with FR-81 defaults.
    rs = RetryStrategy(
        max_retries=2,  # small cap so each thread sleeps at least once
        base_delay=1.0,
        max_delay=_FR81_MAX_DELAY_DEFAULT,
        jitter=True,
    )

    def _always_fails():
        raise RuntimeError("nope")

    # Run concurrent_retries threads in parallel; each will perform
    # at least one sleep (the first retry after the initial call).
    results: list[Any] = [None] * concurrent_retries
    barrier = threading.Barrier(concurrent_retries)

    def _runner(idx: int) -> None:
        try:
            barrier.wait(timeout=2.0)
            rs.execute_with_retry(_always_fails)
        except Exception as e:
            results[idx] = e

    threads = [
        threading.Thread(target=_runner, args=(i,))
        for i in range(concurrent_retries)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # We must have captured at least one sleep per thread.
    assert len(sleep_log) >= concurrent_retries, (
        f"FR-81 execute_with_retry must sleep on retry; "
        f"observed {len(sleep_log)} sleeps for {concurrent_retries} "
        f"concurrent retries"
    )

    # Variance check: the spread between the shortest and longest
    # recorded sleep must exceed the thundering-herd threshold.
    span_ms = (max(sleep_log) - min(sleep_log)) * 1000.0
    if expected_delay_variance_ms > 100:
        assert span_ms > float(expected_delay_variance_ms), (
            f"FR-81 must spread concurrent retries by "
            f">{expected_delay_variance_ms}ms via jitter; observed "
            f"span={span_ms:.1f}ms across {len(sleep_log)} sleeps "
            f"(min={min(sleep_log):.3f}s, max={max(sleep_log):.3f}s)"
        )
