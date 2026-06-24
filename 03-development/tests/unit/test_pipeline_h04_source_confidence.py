"""[H-04] Pipeline source/confidence derivation from KnowledgeResult.

Pins that Pipeline.handle_message derives source + confidence from
``KnowledgeResult`` rather than hardcoding ``ResponseSource.RULE / 1.0``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.core.pipeline import Pipeline
from app.core.response import ResponseSource


class _StubKnowledge:
    def __init__(self, source: str, confidence: float):
        self.source = source
        self.confidence = confidence

    def query(self, text: str):
        return SimpleNamespace(
            id="stub",
            content=text,
            confidence=self.confidence,
            source=self.source,
            knowledge_id=None,
        )


class _Msg:
    def __init__(self, content: str, platform: str = "telegram") -> None:
        self.content = content
        self.platform = platform


@pytest.mark.unit
@pytest.mark.parametrize(
    "tier,expected_source",
    [
        ("rule", ResponseSource.RULE),
        ("rag", ResponseSource.RAG),
        ("wiki", ResponseSource.WIKI),
        ("escalate", ResponseSource.ESCALATE),
    ],
)
def test_pipeline_source_derived_from_knowledge(tier, expected_source):
    """H-04: source comes from KnowledgeResult.source, not hardcoded."""
    knowledge = _StubKnowledge(source=tier, confidence=0.7)
    pipeline = Pipeline(knowledge=knowledge)
    response = pipeline.handle_message(_Msg("hi"))
    assert response.source == expected_source, (
        f"expected {expected_source!r}, got {response.source!r} for tier {tier}"
    )


@pytest.mark.unit
def test_pipeline_confidence_propagates_from_knowledge():
    """H-04: confidence is the KnowledgeResult.confidence, not 1.0."""
    knowledge = _StubKnowledge(source="rag", confidence=0.42)
    pipeline = Pipeline(knowledge=knowledge)
    response = pipeline.handle_message(_Msg("hi"))
    assert response.confidence == pytest.approx(0.42), (
        f"expected 0.42, got {response.confidence}"
    )


@pytest.mark.unit
def test_pipeline_no_knowledge_returns_zero_confidence():
    """H-04: no knowledge layer → confidence 0.0 (not the historical 1.0 lie)."""
    pipeline = Pipeline(knowledge=None)
    response = pipeline.handle_message(_Msg("hi"))
    assert response.confidence == 0.0, (
        f"expected 0.0 (no knowledge consulted), got {response.confidence}"
    )
