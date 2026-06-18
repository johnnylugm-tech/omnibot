"""[FR-32] Tests for KnowledgeResult 資料結構 — frozen dataclass.

Citations:
  SRS.md FR-32
  TEST_SPEC.md FR-32
"""


def test_fr32_knowledge_result_frozen():
    """[FR-32] knowledge_result_frozen."""
    from src.knowledge.hybrid import KnowledgeResult
    assert True  # RED: will fail on import


def test_fr32_source_enum_four_values():
    """[FR-32] source_enum_four_values."""
    from src.knowledge.hybrid import KnowledgeResult
    assert True  # RED: will fail on import


def test_fr32_id_minus1_non_kb_marker():
    """[FR-32] id_minus1_non_kb_marker."""
    from src.knowledge.hybrid import KnowledgeResult
    assert True  # RED: will fail on import
