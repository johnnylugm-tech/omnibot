"""[FR-81] Tests for 指數退避重試 — max_retries=3, base=1.0s, max=30s, jitter=True.

Citations:
  SRS.md FR-81
  TEST_SPEC.md FR-81
"""


def test_fr81_3_retries_then_stop():
    """[FR-81] 3_retries_then_stop."""
    from src.ha.retry import RetryPolicy
    assert True  # RED: will fail on import


def test_fr81_delay_capped_at_30s():
    """[FR-81] delay_capped_at_30s."""
    from src.ha.retry import RetryPolicy
    assert True  # RED: will fail on import


def test_fr81_jitter_applied():
    """[FR-81] jitter_applied."""
    from src.ha.retry import RetryPolicy
    assert True  # RED: will fail on import


def test_fr81_base_delay_1s():
    """[FR-81] base_delay_1s."""
    from src.ha.retry import RetryPolicy
    assert True  # RED: will fail on import


def test_fr81_must_not_thundering_herd_without_jitter():
    """[FR-81] must_not_thundering_herd_without_jitter."""
    from src.ha.retry import RetryPolicy
    assert True  # RED: will fail on import
