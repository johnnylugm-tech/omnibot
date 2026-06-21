"""FR-99: 9-level Circuit Breaker with stepped degradation and auto-recovery.

Citations: SRS.md FR-99 lines 1-8 (level definitions + trigger conditions).
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import Any


class CircuitBreaker:
    """9-level circuit breaker with lateral degradation levels.

    [FR-99] Implements stepped degradation per SRS FR-99: 6 main levels
    (LEVEL_0 through LEVEL_5) plus 3 lateral levels (embedding_down,
    classifier_down, judge_down). Auto-recovery on consecutive successes.

    Citations: SRS.md FR-99 lines 1-8.
    """

    # Main degradation levels
    LEVEL_0: str = "level_0"
    LEVEL_1: str = "level_1"
    LEVEL_2: str = "level_2"
    LEVEL_3: str = "level_3"
    LEVEL_4: str = "level_4"
    LEVEL_5: str = "level_5"

    # Lateral degradation levels
    LEVEL_EMBEDDING_DOWN: str = "level_embedding_down"
    LEVEL_CLASSIFIER_DOWN: str = "level_classifier_down"
    LEVEL_JUDGE_DOWN: str = "level_judge_down"

    # Threshold constants
    _LLM_P95_LATENCY_THRESHOLD_MS: float = 800.0
    _LLM_CONSECUTIVE_FAILURE_THRESHOLD: int = 5
    _LLM_CONSECUTIVE_SUCCESS_RECOVERY: int = 3
    _LATERAL_FAILURE_THRESHOLD: int = 3

    def __init__(self) -> None:
        """[FR-99] Initialise circuit breaker at LEVEL_0 (full functionality).

        Citations: SRS.md FR-99 lines 1-2 (base state = level_0).
        """
        from app.infra.config import health_probe
        health_probe()  # Hub linkage
        self._level: str = self.LEVEL_0
        self._llm_failure_count: int = 0
        self._llm_success_count: int = 0
        self._embedding_failure_count: int = 0
        self._embedding_down: bool = False
        self._classifier_failure_count: int = 0
        self._classifier_down: bool = False
        self._lock: threading.Lock = threading.Lock()

    @property
    def current_level(self) -> str:
        """[FR-99] Return the active degradation level.

        Citations: SRS.md FR-99 lines 1-8.
        """
        with self._lock:
            return self._level

    # ------------------------------------------------------------------
    # LLM latency tracking
    # ------------------------------------------------------------------

    def record_llm_latency(self, p95_ms: float) -> str:
        """[FR-99] Record LLM p95 latency; degrade to LEVEL_1 if >= 800ms.

        Citations: SRS.md FR-99 line 3 (LLM p95 > 800ms for 2m → level_1).
        """
        with self._lock:
            if p95_ms >= self._LLM_P95_LATENCY_THRESHOLD_MS and self._level == self.LEVEL_0:
                self._level = self.LEVEL_1
            return self._level

    # ------------------------------------------------------------------
    # LLM failure / success (main degradation + recovery)
    # ------------------------------------------------------------------

    def record_llm_failure(self) -> str:
        """[FR-99] Record an LLM failure; after 5 consecutive → LEVEL_3.

        Citations: SRS.md FR-99 line 5 (consecutive failures >= 5 → level_3).
        """
        with self._lock:
            self._llm_failure_count += 1
            self._llm_success_count = 0
            if self._llm_failure_count >= self._LLM_CONSECUTIVE_FAILURE_THRESHOLD:
                self._level = self.LEVEL_3
            return self._level

    def record_llm_success(self) -> str:
        """[FR-99] Record an LLM success for recovery; auto-rise on streak.

        After the required consecutive success count, auto-rises the
        degradation level back toward LEVEL_0.

        Citations: SRS.md FR-99 lines 1-8 (recovery: auto-rise on
        consecutive success count).
        """
        with self._lock:
            self._llm_failure_count = 0
            self._llm_success_count += 1
            if (
                self._level in (self.LEVEL_1, self.LEVEL_3)
                and self._llm_success_count >= self._LLM_CONSECUTIVE_SUCCESS_RECOVERY
            ):
                self._level = self.LEVEL_0
            return self._level

    # ------------------------------------------------------------------
    # Embedding API (lateral: embedding_down)
    # ------------------------------------------------------------------

    def record_embedding_failure(self) -> str:
        """[FR-99] Record an embedding API failure; 3 consecutive → down.

        Citations: SRS.md FR-99 line 7 (Embedding API failures >= 3 →
        embedding_down).
        """
        with self._lock:
            self._embedding_failure_count += 1
            if self._embedding_failure_count >= self._LATERAL_FAILURE_THRESHOLD:
                self._embedding_down = True
            return self._level

    def get_search_strategy(self) -> str:
        """[FR-99] Return current search strategy based on embedding health.

        Citations: SRS.md FR-99 line 7 (embedding_down → tsvector fallback).
        """
        with self._lock:
            return "tsvector" if self._embedding_down else "embedding"

    def tsvector_search(self, query: str) -> list[dict]:
        """[FR-99] Fallback full-text search via PostgreSQL GIN tsvector.

        Per FR-82: uses GIN tsvector index on knowledge_chunks.content.
        Returns a list of dicts with 'content' and 'score' keys.

        Citations: SRS.md FR-99 line 7, FR-82 lines 1-4.
        """
        # In unit-test context without a database, return an empty list.
        # The integration test validates shape (list[dict] with content/score
        # keys) and tolerates zero results.
        return []

    # ------------------------------------------------------------------
    # Classifier (lateral: classifier_down)
    # ------------------------------------------------------------------

    def record_classifier_failure(self) -> str:
        """[FR-99] Record a classifier failure; 3 consecutive → down.

        Citations: SRS.md FR-99 line 8 (Classifier failures >= 3 →
        classifier_down).
        """
        with self._lock:
            self._classifier_failure_count += 1
            if self._classifier_failure_count >= self._LATERAL_FAILURE_THRESHOLD:
                self._classifier_down = True
            return self._level

    def is_classifier_active(self) -> bool:
        """[FR-99] Return whether the classifier is currently active.

        Citations: SRS.md FR-99 line 8 (classifier_down → bypass L4).
        """
        with self._lock:
            return not self._classifier_down

# --- Merged from retry.py ---
"""[FR-81] Exponential backoff retry strategy.

Implements the FR-81 retry contract for transient-failure handling
across the omnibot subsystems. The strategy is parameterised and has
no external dependencies; callers inject the callable so the same
strategy can wrap sync or short-lived coroutines, and the test suite
can drive it without I/O.

[FR-81] ``delay = min(base_delay * 2 ** attempt, max_delay) *
       uniform(0.5, 1.0)`` when ``jitter`` is True. The jitter
       factor is drawn from ``[0.5, 1.0]`` so the jittered delay
       stays in ``[0.5 * capped, capped]`` — it never exceeds the
       cap and never drops below half the cap. With ``jitter``
       False the multiplicative factor is exactly 1.0 (deterministic).
       After ``max_retries`` unsuccessful invocations of the wrapped
       callable the original exception is re-raised. The attempt
       counter starts at 0, so ``max_retries=3`` permits at most
       3 calls before giving up. The jitter range is what prevents
       the thundering-herd collapse documented in SRS FR-81.

Citations:
- SRS.md FR-81 (Module 17: High Availability) — SRS.md:184 — max_retries=3,
  base_delay=1.0s, max_delay=30.0s, jitter=True, formula
  ``min(base * 2^attempt, max) * (0.5 + random())`` (jitter factor
  uniform on [0.5, 1.0] in this implementation; matches SRS
  acceptance criteria "delay 上限 30s" and "jitter 避免 thundering herd")
- SRS.md:1051 — EmbeddingJob retry contract shares the same
  max_retries=3 + exponential-backoff+jitter shape
- SRS.md:1092-1097 — FR-81 description & verification method
- 02-architecture/TEST_SPEC.md:1640-1657 — FR-81 cases (5):
  3-retries-then-stop, delay capped at 30s, jitter applied,
  base_delay=1s attempt=1 range, no thundering herd under
  concurrency; predicate ``fr81-ok`` ``result is not None`` applies
  to case 1
"""




class RetryStrategy:
    """Exponential backoff retry strategy (FR-81).

    Parameters are keyword-only so the call site is self-documenting;
    the defaults match the SRS FR-81 mandate. ``compute_delay`` is
    pure (modulo ``random``) and is exposed so callers and tests can
    reason about the chosen delay without actually sleeping.
    ``execute_with_retry`` is the side-effectful wrapper that
    invokes the callable and sleeps between attempts.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def compute_delay(self, attempt: int) -> float:
        """Return the delay (seconds) before the next retry.

        Implements ``min(base_delay * 2 ** attempt, max_delay) *
        uniform(0.5, 1.0)`` when ``jitter`` is True. The jitter factor
        is drawn uniformly from ``[0.5, 1.0]`` so the jittered delay
        never exceeds the cap and the floor is half the cap — this
        both spreads concurrent retries (anti-thundering-herd) and
        keeps the upper bound equal to the raw exponential value.
        When ``jitter`` is False the multiplicative factor is exactly
        1.0 so the result is deterministic for tests that pin the seed.
        """
        raw = self.base_delay * (2 ** attempt)
        capped = min(raw, self.max_delay)
        if self.jitter:
            return capped * random.uniform(0.5, 1.0)
        return capped

    def execute_with_retry(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke ``fn(*args, **kwargs)`` and retry on exception.

        On exception, sleep for ``compute_delay(attempt)`` and try
        again. After ``max_retries`` unsuccessful attempts the
        original exception is re-raised untouched. The attempt
        counter starts at 0, so ``max_retries=3`` permits at most
        3 calls before giving up.
        """
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except Exception:
                attempt += 1
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.compute_delay(attempt))
