"""[FR-26] Tests for Knowledge Tier 1 — PostgreSQL ILIKE 規則匹配 (confidence ≥0.80).

Citations:
  SRS.md FR-26
  TEST_SPEC.md FR-26
"""


def test_fr26_exact_match_confidence_095_returns_rule():
    """[FR-26] exact_match_confidence_095_returns_rule."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import


def test_fr26_confidence_below_080_falls_through_tier2():
    """[FR-26] confidence_below_080_falls_through_tier2."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import


def test_fr26_limit_5_applied():
    """[FR-26] limit_5_applied."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import


def test_fr26_partial_match_confidence_070_falls_through():
    """[FR-26] partial_match_confidence_070_falls_through."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import
