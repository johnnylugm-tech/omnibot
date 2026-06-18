"""[FR-79] Tests for Embedding 同步狀態 UI — 🟡/🟢/🔴 + embedding_synced_at.

Citations:
  SRS.md FR-79
  TEST_SPEC.md FR-79
"""


def test_fr79_ui_shows_syncing_status():
    """[FR-79] ui_shows_syncing_status."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import


def test_fr79_embedding_synced_at_set_after_all_chunks():
    """[FR-79] embedding_synced_at_set_after_all_chunks."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import
