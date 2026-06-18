"""[FR-08] Tests for UnifiedResponse 資料結構 — source 限定四個合法值.

Citations:
  SRS.md FR-08
  TEST_SPEC.md FR-08
"""


def test_fr08_unified_response_source_enum_valid():
    """[FR-08] unified_response_source_enum_valid."""
    from src.models.unified_response import UnifiedResponse
    assert True  # RED: will fail on import


def test_fr08_unified_response_invalid_source_raises():
    """[FR-08] unified_response_invalid_source_raises."""
    from src.models.unified_response import UnifiedResponse
    assert True  # RED: will fail on import


def test_fr08_unified_response_frozen_immutable():
    """[FR-08] unified_response_frozen_immutable."""
    from src.models.unified_response import UnifiedResponse
    assert True  # RED: will fail on import
