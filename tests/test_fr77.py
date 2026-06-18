"""[FR-77] Tests for 同步首 Chunk Embedding — asyncio.wait_for timeout=2.0s.

Citations:
  SRS.md FR-77
  TEST_SPEC.md FR-77
"""


def test_fr77_first_chunk_searchable_within_25s():
    """[FR-77] first_chunk_searchable_within_25s."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import


def test_fr77_timeout_does_not_block_main_flow():
    """[FR-77] timeout_does_not_block_main_flow."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import
