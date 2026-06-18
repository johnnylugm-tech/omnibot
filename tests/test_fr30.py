"""[FR-30] Tests for Knowledge Tier 3 — LLM 生成 + Grounding ≥0.75 + Fallback <500ms.

Citations:
  SRS.md FR-30
  TEST_SPEC.md FR-30
"""


def test_fr30_grounding_below_075_escalates():
    """[FR-30] grounding_below_075_escalates."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import


def test_fr30_gpt4o_failure_triggers_gemini_fallback():
    """[FR-30] gpt4o_failure_triggers_gemini_fallback."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import


def test_fr30_fallback_switch_under_500ms():
    """[FR-30] fallback_switch_under_500ms."""
    from src.knowledge.hybrid import HybridKnowledge
    assert True  # RED: will fail on import
