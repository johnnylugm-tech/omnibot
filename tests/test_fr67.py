"""[FR-67] Tests for Accuracy 聚合 — min(primary, secondary).

Citations:
  SRS.md FR-67
  TEST_SPEC.md FR-67
"""


def test_fr67_accuracy_equals_min_of_both_judges():
    """[FR-67] accuracy_equals_min_of_both_judges."""
    from src.judge.llm_judge import LLMJudge
    assert True  # RED: will fail on import


def test_fr67_primary_higher_secondary_lower_uses_secondary():
    """[FR-67] primary_higher_secondary_lower_uses_secondary."""
    from src.judge.llm_judge import LLMJudge
    assert True  # RED: will fail on import


def test_fr67_must_not_use_max_for_accuracy_aggregation():
    """[FR-67] must_not_use_max_for_accuracy_aggregation."""
    from src.judge.llm_judge import LLMJudge
    assert True  # RED: will fail on import
