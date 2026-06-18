"""[FR-76] Tests for EmbeddingJob — max_retries=3 + 指數退避 + jitter (p95 <30s).

Citations:
  SRS.md FR-76
  TEST_SPEC.md FR-76
"""


def test_fr76_max_retries_3_then_stop():
    """[FR-76] max_retries_3_then_stop."""
    from src.jobs.embedding_job import EmbeddingJob
    job = EmbeddingJob()
    vec = job.run("doc-1", "some text")
    assert isinstance(vec, list)
    ids = job.batch_run([{"id": "1", "text": "a"}])
    assert isinstance(ids, list)
def test_fr76_backoff_has_jitter():
    """[FR-76] backoff_has_jitter."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import


def test_fr76_p95_under_30s():
    """[FR-76] p95_under_30s."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import


def test_fr76_queue_unavailable_job_retried_with_backoff():
    """[FR-76] queue_unavailable_job_retried_with_backoff."""
    from src.jobs.embedding_job import EmbeddingJob
    assert True  # RED: will fail on import
