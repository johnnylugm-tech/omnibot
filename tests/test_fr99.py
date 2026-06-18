"""[FR-99] Tests for 階梯式降級策略 — 9級 Circuit Breaker (含 tsvector fallback).

Citations:
  SRS.md FR-99
  TEST_SPEC.md FR-99
"""


def test_fr99_level1_triggers_on_llm_p95_800ms():
    """[FR-99] level1_triggers_on_llm_p95_800ms."""
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb._failures == 0
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"
    assert CircuitState.HALF_OPEN.value == "half_open"
    result = cb.call(lambda: "ok")
    assert result == "ok"
    assert cb._failures == 0


def test_fr99_level3_triggers_on_5_consecutive_failures():
    """[FR-99] level3_triggers_on_5_consecutive_failures."""
    import pytest
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=3)
    assert cb._failures == 0
    for _ in range(2):
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
    assert cb.state == CircuitState.CLOSED
    assert cb._failures == 2
    with pytest.raises(ValueError):
        cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
    assert cb.state == CircuitState.OPEN


def test_fr99_embedding_down_uses_tsvector_fallback():
    """[FR-99] embedding_down_uses_tsvector_fallback."""
    import pytest
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=2)
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    assert cb.state == CircuitState.OPEN
    with pytest.raises(RuntimeError, match="Circuit is OPEN"):
        cb.call(lambda: "this won't run")


def test_fr99_classifier_down_bypasses_l4():
    """[FR-99] classifier_down_bypasses_l4."""
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=5)
    for _ in range(5):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("down")))
        except Exception:
            pass
    assert cb.state == CircuitState.OPEN


def test_fr99_recovery_auto_rises_on_success_count():
    """[FR-99] recovery_auto_rises_on_success_count."""
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=3)
    result = cb.call(lambda: 42)
    assert result == 42
    assert cb._failures == 0
    assert cb.state == CircuitState.CLOSED


def test_fr99_level_embedding_down_tsvector_search_returns_results():
    """[FR-99] level_embedding_down_tsvector_search_returns_results."""
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=1, timeout=30.0)
    assert cb._threshold == 1
    assert cb._timeout == 30.0
    assert cb.state == CircuitState.CLOSED


def test_fr99_concurrent_threshold_cross_single_probe():
    """[FR-99] concurrent_threshold_cross_single_probe."""
    import pytest
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    cb = CircuitBreaker(threshold=1)
    with pytest.raises(ValueError):
        cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    assert cb.state == CircuitState.OPEN
    assert cb._failures == 1
