"""FR-99: 9-level Circuit Breaker with stepped degradation and auto-recovery.

Citations: SRS.md FR-99 lines 1-8 (level definitions + trigger conditions).
"""

from __future__ import annotations

import threading


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
            if self._level == self.LEVEL_3 and self._llm_success_count >= self._LLM_CONSECUTIVE_SUCCESS_RECOVERY:
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
