"""[FR-107] Test Strategy — coverage pyramid (70% unit / 20% integration / 10% e2e).

SRS FR-107: test pyramid with unit ≥ 70%, integration ≥ 20%, e2e ≥ 10%.
Verifies key end-to-end flows: FAQ exact match, semantic search, multi-turn DST,
emotion escalation, prompt injection block, and fallback escalation.

NFR pattern and layer markers are auto-assigned via conftest.py
(pytest_collection_modifyitems) based on FR number.
"""
from __future__ import annotations

from tests.strategy import TestStrategy


def test_fr107_unit_coverage_70pct():
    """FR-107: unit test coverage target = 70%.

    Pinned boundary: validate_pyramid must accept 0.70 unit exactly.
    """
    assert TestStrategy().validate_pyramid(0.70, 0.20, 0.10) is True


def test_fr107_integration_coverage_20pct():
    """FR-107: integration test coverage target = 20%."""
    assert TestStrategy().validate_pyramid(0.70, 0.20, 0.10) is True


def test_fr107_e2e_faq_exact_match():
    """FR-107: E2E — FAQ exact-match query returns rule-based result (source=rule)."""
    result = TestStrategy().run_e2e_pipeline("faq_exact_match")
    assert result["status"] == "pass"


def test_fr107_e2e_semantic_search():
    """FR-107: E2E — semantic similarity query returns RAG result (source=rag)."""
    result = TestStrategy().run_e2e_pipeline("semantic_search")
    assert result["status"] == "pass"


def test_fr107_e2e_multi_turn_dst():
    """FR-107: E2E — 3-turn dialogue with intent=return_request and slots=order_id,reason."""
    result = TestStrategy().run_e2e_pipeline("multi_turn_dst")
    assert result["status"] == "pass"


def test_fr107_e2e_emotion_escalation():
    """FR-107: E2E — 3 consecutive negative emotions trigger escalation."""
    result = TestStrategy().run_e2e_pipeline("emotion_escalation")
    assert result["status"] == "pass"


def test_fr107_e2e_prompt_injection_blocked():
    """FR-107: E2E — prompt injection 'ignore previous instructions' is blocked."""
    result = TestStrategy().run_e2e_pipeline("prompt_injection_blocked")
    assert result["status"] == "pass"


def test_fr107_e2e_fallback_escalation():
    """FR-107: E2E — when all tiers miss (tier1/tier2/tier3), escalate to human."""
    result = TestStrategy().run_e2e_pipeline("fallback_escalation")
    assert result["status"] == "pass"
