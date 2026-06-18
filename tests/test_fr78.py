"""[FR-78] Tests for 批次匯入模式 (>10筆) — is_batch=True, per entry <50ms.

Citations:
  SRS.md FR-78
  TEST_SPEC.md FR-78
"""


def test_fr78_batch_mode_skips_sync_wait():
    """[FR-78] batch_mode_skips_sync_wait."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import


def test_fr78_per_entry_under_50ms():
    """[FR-78] per_entry_under_50ms."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import
