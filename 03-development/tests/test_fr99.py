"""TDD-RED: failing tests for FR-99 — 階梯式降級策略 (9-level Circuit Breaker
with tsvector fallback).

Spec source: 02-architecture/TEST_SPEC.md (FR-99)
SRS source : SRS.md FR-99

Acceptance criteria (from SRS FR-99):
    各觸發條件正確觸發降級；恢復條件（連續成功次數）後自動回升；
    降級期間不影響已上線功能的基礎可用性

The seven TEST_SPEC cases (function names MUST match exactly):
    1. test_fr99_level1_triggers_on_llm_p95_800ms
         Inputs: level="level_1"; trigger="llm_p95_800ms_for_2m"
         Type  : happy_path (Q1)
    2. test_fr99_level3_triggers_on_5_consecutive_failures
         Inputs: level="level_3"; failures="5"
         Type  : happy_path (Q1)
    3. test_fr99_embedding_down_uses_tsvector_fallback
         Inputs: level="level_embedding_down"; expected_search="tsvector"
         Type  : fault_injection (Q5/NP-07)
    4. test_fr99_classifier_down_bypasses_l4
         Inputs: level="level_classifier_down"; expected_l4="bypassed"
         Type  : fault_injection (Q5/NP-07)
    5. test_fr99_recovery_auto_rises_on_success_count
         Inputs: consecutive_successes="3"; expected_level="level_0"
         Type  : happy_path (Q1)
    6. test_fr99_level_embedding_down_tsvector_search_returns_results
         Inputs: query="test"; embedding_api="down"
         Type  : integration (Q7/FR-82)
    7. test_fr99_concurrent_threshold_cross_single_probe
         Inputs: concurrent_threads="10"; failure_count="5";
                 expected_circuit_state="open"
         Type  : nfr_pattern (Q6/1b/NP-13)

Sub-assertion (per TEST_SPEC):
    fr99-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import threading

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-99 (SRS.md) requires a 9-level circuit breaker with trigger conditions
# and auto-recovery:
#
#   6 main levels:
#     level_0 = full functionality (base state)
#     level_1 = light delay, enable cache   (LLM p95 > 800ms for 2m)
#     level_2 = close Tier3, Tier1+Tier2    (LLM p95 > 1.5s for 2m)
#     level_3 = circuit break LLM, Tier1    (consecutive failures >= 5)
#     level_4 = DB degrade → Redis cache    (DB p95 > 2s for 1m)
#     level_5 = full outage, static page
#
#   3 lateral levels:
#     level_embedding_down  = Tier2 tsvector fallback (Embedding API
#                             failures >= 3 or p95 > 5s for 2m)
#     level_classifier_down = Bypass L4               (Classifier failures >= 3)
#     level_judge_down      = rule-based Judge        (dual Judge failures >= 3)
#
# Recovery: auto-rise on consecutive success count after each degradation.
#
# GREEN contract pinned by this spec:
#   - ``app.infra.circuit_breaker.CircuitBreaker`` class with level constants:
#     LEVEL_0, LEVEL_1, LEVEL_2, LEVEL_3, LEVEL_4, LEVEL_5,
#     LEVEL_EMBEDDING_DOWN, LEVEL_CLASSIFIER_DOWN, LEVEL_JUDGE_DOWN.
#   - ``current_level`` (property, str) — the active degradation level.
#   - ``record_llm_latency(p95_ms: float) -> str`` — tracks LLM p95 latency;
#     transitions to LEVEL_1 when p95 >= 800ms sustained over the observation
#     window. Returns the resulting circuit breaker level.
#   - ``record_llm_failure() -> str`` — records an LLM failure; transitions
#     to LEVEL_3 after 5 consecutive failures. Returns resulting level.
#   - ``record_llm_success() -> str`` — records an LLM success for recovery
#     tracking. After the required consecutive success count, auto-rises the
#     level back toward LEVEL_0. Returns resulting level.
#   - ``record_embedding_failure() -> str`` — records an embedding API failure;
#     sets embedding_down after 3 consecutive failures.
#   - ``record_classifier_failure() -> str`` — records a classifier failure;
#     sets classifier_down after 3 consecutive failures.
#   - ``get_search_strategy() -> str`` — returns "embedding" (normal) or
#     "tsvector" (when embedding is down).
#   - ``is_classifier_active() -> bool`` — returns False when classifier_down.
#   - ``tsvector_search(query: str) -> list[dict]`` — fallback full-text
#     search via PostgreSQL GIN tsvector index on knowledge_chunks.content
#     (per FR-82). Returns list of dicts with 'content' and 'score' keys.
#
# The imports below are unguarded: pytest will fail with Collection Error
# (Exit Code 2) because ``app.infra.circuit_breaker`` does not exist yet. That
# is the valid RED signal — GREEN creates the module with the class above.
# ---------------------------------------------------------------------------
from app.infra.circuit_breaker import CircuitBreaker


# ============================================================================
# 1. level_1 triggers when LLM p95 latency >= 800ms (happy_path).
#
# Spec input:  level="level_1"; trigger="llm_p95_800ms_for_2m".
# Spec sub-assertion: fr99-ok: result is not None.
# SRS FR-99:   "LLM p95>800ms for 2m" → level_1: light delay + cache.
# Test type:   happy_path (Q1 derivation).
# ============================================================================
def test_fr99_level1_triggers_on_llm_p95_800ms():
    level = "level_1"
    trigger = "llm_p95_800ms_for_2m"

    # Defence-in-depth: pin the spec sentinel strings.
    assert level == "level_1", (
        "FR-99: level sentinel must be 'level_1' (TEST_SPEC FR-99 case 1 "
        f"spec input); got {level!r}."
    )
    assert trigger == "llm_p95_800ms_for_2m", (
        "FR-99: trigger sentinel must be 'llm_p95_800ms_for_2m' (TEST_SPEC "
        f"FR-99 case 1 spec input); got {trigger!r}."
    )

    # GREEN TODO: CircuitBreaker.__init__ MUST start at LEVEL_0.
    cb = CircuitBreaker()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: CircuitBreaker must start at LEVEL_0 (full functionality); "
        f"got {cb.current_level!r}."
    )

    # GREEN TODO: record_llm_latency(p95_ms: float) -> str MUST track LLM
    # p95 latency and transition to LEVEL_1 when p95 >= 800ms is sustained
    # over the observation window (2 minutes per SRS FR-99). The return
    # value is the resulting circuit breaker level after the recording.
    result = cb.record_llm_latency(850.0)

    # fr99-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr99-ok predicate: record_llm_latency() must not return None; the "
        "latency recording must always produce a level string."
    )

    assert result == CircuitBreaker.LEVEL_1, (
        "FR-99: LLM p95=850ms must trigger level_1 (>=800ms threshold per "
        f"SRS FR-99); got {result!r}."
    )
    assert cb.current_level == CircuitBreaker.LEVEL_1, (
        "FR-99: current_level must reflect degradation after "
        f"record_llm_latency; expected LEVEL_1, got {cb.current_level!r}."
    )

    # Sentinel: level spec value MUST remain "level_1".
    assert level == "level_1", (
        "FR-99: level sentinel must remain 'level_1' per TEST_SPEC FR-99 "
        f"case 1; got {level!r}."
    )
    # Sentinel: trigger spec value MUST remain "llm_p95_800ms_for_2m".
    assert trigger == "llm_p95_800ms_for_2m", (
        "FR-99: trigger sentinel must remain 'llm_p95_800ms_for_2m' per "
        f"TEST_SPEC FR-99 case 1; got {trigger!r}."
    )


# ============================================================================
# 2. level_3 triggers after 5 consecutive LLM failures (happy_path).
#
# Spec input:  level="level_3"; failures="5".
# SRS FR-99:   "連續失敗≥5次" → level_3: circuit break LLM, only Tier1.
# Test type:   happy_path (Q1 derivation).
# ============================================================================
def test_fr99_level3_triggers_on_5_consecutive_failures():
    level = "level_3"
    failures = "5"

    # Defence-in-depth: pin the spec sentinel strings.
    assert level == "level_3", (
        "FR-99: level sentinel must be 'level_3' (TEST_SPEC FR-99 case 2 "
        f"spec input); got {level!r}."
    )
    assert failures == "5", (
        "FR-99: failures sentinel must be '5' (TEST_SPEC FR-99 case 2 "
        f"spec input); got {failures!r}."
    )

    # GREEN TODO: CircuitBreaker starts at LEVEL_0.
    cb = CircuitBreaker()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: CircuitBreaker must start at LEVEL_0; got "
        f"{cb.current_level!r}."
    )

    # GREEN TODO: record_llm_failure() -> str MUST track consecutive LLM
    # failures. Each call increments the failure counter; a success call
    # resets the counter. When the consecutive failure count reaches 5,
    # the circuit breaker transitions to LEVEL_3 (circuit open). The
    # return value is the resulting level after the recording.
    result = None
    for _ in range(5):
        result = cb.record_llm_failure()

    assert result is not None, (
        "FR-99: record_llm_failure() must not return None after 5 failures."
    )
    assert result == CircuitBreaker.LEVEL_3, (
        "FR-99: 5 consecutive LLM failures must trigger level_3 (circuit "
        f"break LLM per SRS FR-99); got {result!r}."
    )
    assert cb.current_level == CircuitBreaker.LEVEL_3, (
        "FR-99: current_level must be LEVEL_3 after 5 consecutive failures; "
        f"got {cb.current_level!r}."
    )

    # Sentinel: level spec value MUST remain "level_3".
    assert level == "level_3", (
        "FR-99: level sentinel must remain 'level_3' per TEST_SPEC FR-99 "
        f"case 2; got {level!r}."
    )
    # Sentinel: failures spec value MUST remain "5".
    assert failures == "5", (
        "FR-99: failures sentinel must remain '5' per TEST_SPEC FR-99 "
        f"case 2; got {failures!r}."
    )


# ============================================================================
# 3. Embedding down triggers tsvector fallback (fault_injection).
#
# Spec input:  level="level_embedding_down"; expected_search="tsvector".
# SRS FR-99:   "Embedding API 失敗≥3次或p95>5s for 2m" → embedding_down.
# Test type:   fault_injection (Q5/NP-07 derivation).
# ============================================================================
def test_fr99_embedding_down_uses_tsvector_fallback():
    level = "level_embedding_down"
    expected_search = "tsvector"

    # Defence-in-depth: pin the spec sentinel strings.
    assert level == "level_embedding_down", (
        "FR-99: level sentinel must be 'level_embedding_down' (TEST_SPEC "
        f"FR-99 case 3 spec input); got {level!r}."
    )
    assert expected_search == "tsvector", (
        "FR-99: expected_search sentinel must be 'tsvector' (TEST_SPEC "
        f"FR-99 case 3 spec input); got {expected_search!r}."
    )

    cb = CircuitBreaker()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: CircuitBreaker must start at LEVEL_0; got "
        f"{cb.current_level!r}."
    )

    # GREEN TODO: get_search_strategy() -> str MUST return "embedding" when
    # the embedding service is healthy (no failures recorded), and "tsvector"
    # when the embedding service is down (level_embedding_down triggered).
    assert cb.get_search_strategy() == "embedding", (
        "FR-99: default search strategy must be 'embedding' when circuit is "
        f"healthy; got {cb.get_search_strategy()!r}."
    )

    # GREEN TODO: record_embedding_failure() -> str MUST track embedding API
    # failures. After 3 consecutive failures, the embedding_down lateral
    # level is triggered. get_search_strategy() must then return "tsvector".
    for _ in range(3):
        cb.record_embedding_failure()

    assert cb.get_search_strategy() == "tsvector", (
        "FR-99: after 3 embedding failures, search strategy must fall back "
        f"to 'tsvector'; got {cb.get_search_strategy()!r}."
    )

    # Sentinel: level spec value MUST remain "level_embedding_down".
    assert level == "level_embedding_down", (
        "FR-99: level sentinel must remain 'level_embedding_down' per "
        f"TEST_SPEC FR-99 case 3; got {level!r}."
    )
    # Sentinel: expected_search spec value MUST remain "tsvector".
    assert expected_search == "tsvector", (
        "FR-99: expected_search sentinel must remain 'tsvector' per "
        f"TEST_SPEC FR-99 case 3; got {expected_search!r}."
    )


# ============================================================================
# 4. Classifier down bypasses L4 (fault_injection).
#
# Spec input:  level="level_classifier_down"; expected_l4="bypassed".
# SRS FR-99:   "Classifier 失敗≥3次" → level_classifier_down: bypass L4.
# Test type:   fault_injection (Q5/NP-07 derivation).
# ============================================================================
def test_fr99_classifier_down_bypasses_l4():
    level = "level_classifier_down"
    expected_l4 = "bypassed"

    # Defence-in-depth: pin the spec sentinel strings.
    assert level == "level_classifier_down", (
        "FR-99: level sentinel must be 'level_classifier_down' (TEST_SPEC "
        f"FR-99 case 4 spec input); got {level!r}."
    )
    assert expected_l4 == "bypassed", (
        "FR-99: expected_l4 sentinel must be 'bypassed' (TEST_SPEC FR-99 "
        f"case 4 spec input); got {expected_l4!r}."
    )

    cb = CircuitBreaker()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: CircuitBreaker must start at LEVEL_0; got "
        f"{cb.current_level!r}."
    )

    # GREEN TODO: is_classifier_active() -> bool MUST return True when the
    # classifier is healthy, and False when the classifier is down
    # (level_classifier_down triggered, meaning L4 is bypassed).
    assert cb.is_classifier_active() is True, (
        "FR-99: classifier must be active by default when circuit is "
        f"healthy; got {cb.is_classifier_active()!r}."
    )

    # GREEN TODO: record_classifier_failure() -> str MUST track classifier
    # failures. After 3 consecutive failures, the classifier_down lateral
    # level is triggered. is_classifier_active() must then return False
    # (meaning L4 classification is bypassed in favor of fallback routing).
    for _ in range(3):
        cb.record_classifier_failure()

    assert cb.is_classifier_active() is False, (
        "FR-99: after 3 classifier failures, L4 must be bypassed "
        f"(classifier not active); got {cb.is_classifier_active()!r}."
    )

    # Sentinel: level spec value MUST remain "level_classifier_down".
    assert level == "level_classifier_down", (
        "FR-99: level sentinel must remain 'level_classifier_down' per "
        f"TEST_SPEC FR-99 case 4; got {level!r}."
    )
    # Sentinel: expected_l4 spec value MUST remain "bypassed".
    assert expected_l4 == "bypassed", (
        "FR-99: expected_l4 sentinel must remain 'bypassed' per TEST_SPEC "
        f"FR-99 case 4; got {expected_l4!r}."
    )


# ============================================================================
# 5. Auto-recovery rises on consecutive success count (happy_path).
#
# Spec input:  consecutive_successes="3"; expected_level="level_0".
# SRS FR-99:   "恢復條件（連續成功次數）後自動回升".
# Test type:   happy_path (Q1 derivation).
# ============================================================================
def test_fr99_recovery_auto_rises_on_success_count():
    consecutive_successes = "3"
    expected_level = "level_0"

    # Defence-in-depth: pin the spec sentinel strings.
    assert consecutive_successes == "3", (
        "FR-99: consecutive_successes sentinel must be '3' (TEST_SPEC "
        f"FR-99 case 5 spec input); got {consecutive_successes!r}."
    )
    assert expected_level == "level_0", (
        "FR-99: expected_level sentinel must be 'level_0' (TEST_SPEC "
        f"FR-99 case 5 spec input); got {expected_level!r}."
    )

    cb = CircuitBreaker()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: CircuitBreaker must start at LEVEL_0; got "
        f"{cb.current_level!r}."
    )

    # First, degrade to level_3 via 5 consecutive LLM failures so we have a
    # degraded state from which to recover.
    for _ in range(5):
        cb.record_llm_failure()
    assert cb.current_level == CircuitBreaker.LEVEL_3, (
        "FR-99: after 5 consecutive LLM failures, level must be LEVEL_3 "
        f"before testing recovery; got {cb.current_level!r}."
    )

    # GREEN TODO: record_llm_success() -> str MUST track consecutive LLM
    # successes for auto-recovery. After the required number of consecutive
    # successes (3 per spec input), the circuit breaker MUST auto-rise the
    # degradation level back toward LEVEL_0. A single failure during the
    # recovery phase MUST reset the success counter. The return value is
    # the resulting level after the success recording.
    result = None
    for _ in range(3):
        result = cb.record_llm_success()

    assert result is not None, (
        "FR-99: record_llm_success() must not return None after recovery "
        "success count."
    )
    assert result == CircuitBreaker.LEVEL_0, (
        "FR-99: 3 consecutive LLM successes must auto-recover to LEVEL_0; "
        f"got {result!r}."
    )
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: current_level must be LEVEL_0 after recovery; got "
        f"{cb.current_level!r}."
    )

    # Sentinel: consecutive_successes spec value MUST remain "3".
    assert consecutive_successes == "3", (
        "FR-99: consecutive_successes sentinel must remain '3' per "
        f"TEST_SPEC FR-99 case 5; got {consecutive_successes!r}."
    )
    # Sentinel: expected_level spec value MUST remain "level_0".
    assert expected_level == "level_0", (
        "FR-99: expected_level sentinel must remain 'level_0' per "
        f"TEST_SPEC FR-99 case 5; got {expected_level!r}."
    )


# ============================================================================
# 6. When embedding is down, tsvector search returns actual results
#    (integration).
#
# Spec input:  query="test"; embedding_api="down".
# SRS FR-99 + FR-82: GIN tsvector index on knowledge_chunks.content.
# Test type:   integration (Q7/FR-82 derivation).
# ============================================================================
def test_fr99_level_embedding_down_tsvector_search_returns_results():
    query = "test"
    embedding_api = "down"

    # Defence-in-depth: pin the spec sentinel strings.
    assert query == "test", (
        "FR-99: query sentinel must be 'test' (TEST_SPEC FR-99 case 6 "
        f"spec input); got {query!r}."
    )
    assert embedding_api == "down", (
        "FR-99: embedding_api sentinel must be 'down' (TEST_SPEC FR-99 "
        f"case 6 spec input); got {embedding_api!r}."
    )

    cb = CircuitBreaker()

    # Trigger embedding_down state via 3 consecutive embedding failures.
    for _ in range(3):
        cb.record_embedding_failure()

    assert cb.get_search_strategy() == "tsvector", (
        "FR-99: search strategy must be 'tsvector' when embedding is down "
        f"before testing tsvector search; got {cb.get_search_strategy()!r}."
    )

    # GREEN TODO: tsvector_search(query: str) -> list[dict] MUST perform a
    # PostgreSQL full-text search using the GIN tsvector index on
    # knowledge_chunks.content (per FR-82) as a fallback when the embedding
    # service is unavailable. Returns a list of dicts, each containing at
    # minimum 'content' (str) and 'score' (float) keys. An empty list is
    # returned when no results match the query. The search MUST use
    # plainto_tsquery('simple', query) or equivalent for text normalization.
    results = cb.tsvector_search(query)

    assert results is not None, (
        "FR-99: tsvector_search() must not return None; the fallback search "
        "must always produce a result (empty list if no matches)."
    )
    assert isinstance(results, list), (
        "FR-99: tsvector_search() must return a list of search result "
        f"dicts; got type={type(results).__name__}."
    )

    # If results were returned, each must have the required keys.
    for entry in results:
        assert isinstance(entry, dict), (
            "FR-99: each tsvector_search result must be a dict; got "
            f"type={type(entry).__name__}."
        )
        assert "content" in entry, (
            "FR-99: each tsvector_search result must contain 'content' key "
            f"(FR-82 GIN index on knowledge_chunks.content); got "
            f"keys={sorted(entry.keys())!r}."
        )
        assert "score" in entry, (
            "FR-99: each tsvector_search result must contain 'score' key "
            f"for relevance ranking; got keys={sorted(entry.keys())!r}."
        )

    # Sentinel: query spec value MUST remain "test".
    assert query == "test", (
        "FR-99: query sentinel must remain 'test' per TEST_SPEC FR-99 "
        f"case 6; got {query!r}."
    )
    # Sentinel: embedding_api spec value MUST remain "down".
    assert embedding_api == "down", (
        "FR-99: embedding_api sentinel must remain 'down' per TEST_SPEC "
        f"FR-99 case 6; got {embedding_api!r}."
    )


# ============================================================================
# 7. Concurrent threshold crossing uses a single atomic probe (nfr_pattern).
#
# Spec input:  concurrent_threads="10"; failure_count="5";
#              expected_circuit_state="open".
# SRS FR-99:   NP-13 — shared mutable state (failure counters, level) under
#              concurrent async access must be correctly synchronized.
# Test type:   nfr_pattern (Q6/1b/NP-13 derivation).
# ============================================================================
def test_fr99_concurrent_threshold_cross_single_probe():
    concurrent_threads = "10"
    failure_count = "5"
    expected_circuit_state = "open"

    # Defence-in-depth: pin the spec sentinel strings.
    assert concurrent_threads == "10", (
        "FR-99: concurrent_threads sentinel must be '10' (TEST_SPEC FR-99 "
        f"case 7 spec input); got {concurrent_threads!r}."
    )
    assert failure_count == "5", (
        "FR-99: failure_count sentinel must be '5' (TEST_SPEC FR-99 case 7 "
        f"spec input); got {failure_count!r}."
    )
    assert expected_circuit_state == "open", (
        "FR-99: expected_circuit_state sentinel must be 'open' (TEST_SPEC "
        f"FR-99 case 7 spec input); got {expected_circuit_state!r}."
    )

    cb = CircuitBreaker()

    # Pre-condition: record 4 failures to put the circuit one step below the
    # level_3 threshold (5 consecutive failures). The circuit is still at
    # LEVEL_0 because the threshold hasn't been crossed yet.
    for _ in range(4):
        cb.record_llm_failure()
    assert cb.current_level == CircuitBreaker.LEVEL_0, (
        "FR-99: after 4 failures (< 5 threshold), level must remain "
        f"LEVEL_0; got {cb.current_level!r}."
    )

    # GREEN TODO: When multiple threads concurrently call record_llm_failure()
    # with the failure count already near the threshold, the circuit breaker
    # MUST use proper synchronization (NP-13: lock / compare-and-swap /
    # atomic counter) so that:
    #   - The threshold is crossed exactly once (no double-trigger).
    #   - The circuit state transitions atomically to LEVEL_3 ("open").
    #   - No lost updates or torn reads occur on the shared failure counter.
    #   - No thread raises an unhandled exception due to race conditions.
    errors: list[Exception] = []

    def cross_threshold():
        try:
            cb.record_llm_failure()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=cross_threshold)
        for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, (
        f"FR-99: concurrent record_llm_failure() must not raise exceptions; "
        f"got {len(errors)} errors: {errors}."
    )
    assert cb.current_level == CircuitBreaker.LEVEL_3, (
        "FR-99: after concurrent threshold crossing, level must be LEVEL_3 "
        f"(circuit open per expected_circuit_state='open'); got "
        f"{cb.current_level!r}."
    )

    # Sentinel: concurrent_threads spec value MUST remain "10".
    assert concurrent_threads == "10", (
        "FR-99: concurrent_threads sentinel must remain '10' per TEST_SPEC "
        f"FR-99 case 7; got {concurrent_threads!r}."
    )
    # Sentinel: failure_count spec value MUST remain "5".
    assert failure_count == "5", (
        "FR-99: failure_count sentinel must remain '5' per TEST_SPEC FR-99 "
        f"case 7; got {failure_count!r}."
    )
    # Sentinel: expected_circuit_state spec value MUST remain "open".
    assert expected_circuit_state == "open", (
        "FR-99: expected_circuit_state sentinel must remain 'open' per "
        f"TEST_SPEC FR-99 case 7; got {expected_circuit_state!r}."
    )
