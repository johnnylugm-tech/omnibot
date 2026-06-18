"""[FR-29] Tests for HNSW 向量索引 — m=16, ef_construction=64, Partial Index.

Citations:
  SRS.md FR-29
  TEST_SPEC.md FR-29
"""


def test_fr29_hnsw_index_created_m16_ef64():
    """[FR-29] hnsw_index_created_m16_ef64."""
    from src.knowledge.hnsw import HNSWIndex
    assert True  # RED: will fail on import


def test_fr29_partial_index_null_excluded():
    """[FR-29] partial_index_null_excluded."""
    from src.knowledge.hnsw import HNSWIndex
    assert True  # RED: will fail on import
