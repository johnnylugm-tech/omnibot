"""[FR-08] Tests for UnifiedResponse 資料結構 — source 限定四個合法值.

Citations:
  SRS.md FR-08
  TEST_SPEC.md FR-08
"""
import pytest


def test_fr08_unified_response_source_enum_valid():
    """[FR-08] unified_response_source_enum_valid."""
    from src.models.unified_response import UnifiedResponse, ResponseSource

    resp = UnifiedResponse(content="answer", source=ResponseSource.RULE)
    assert resp is not None
    assert resp.source == ResponseSource.RULE
    assert resp.content == "answer"


def test_fr08_unified_response_invalid_source_raises():
    """[FR-08] unified_response_invalid_source_raises."""
    from src.models.unified_response import UnifiedResponse, ResponseSource

    with pytest.raises((ValueError, KeyError, AttributeError)):
        UnifiedResponse(content="answer", source="unknown")  # type: ignore[arg-type]


def test_fr08_unified_response_frozen_immutable():
    """[FR-08] unified_response_frozen_immutable."""
    from src.models.unified_response import UnifiedResponse, ResponseSource
    from dataclasses import FrozenInstanceError

    resp = UnifiedResponse(content="original", source=ResponseSource.RAG)
    with pytest.raises(FrozenInstanceError):
        resp.content = "mutated"  # type: ignore[misc]
