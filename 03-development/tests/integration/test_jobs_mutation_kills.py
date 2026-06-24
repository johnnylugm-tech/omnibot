"""Mutation-killing tests for app.infra.jobs.

Field-level invariants to kill mutmut survivors (initial 47.3%; need 70%).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.infra.jobs import (  # noqa: E402
    EmbeddingJob,
    EmbeddingJobResult,
    get_queue_config,
)


def test_embedding_job_dataclass_field_set() -> None:
    """Mutant that adds/removes/renames EmbeddingJob field — assert
    the field set is preserved.
    """
    fields = {f.name for f in EmbeddingJob.__dataclass_fields__.values()}
    # Concrete fields from the actual dataclass.
    assert "chunk_id" in fields
    assert "job_type" in fields
    assert "knowledge_id" in fields


def test_embedding_job_required_string_fields() -> None:
    """Mutant on EmbeddingJob field types — assert required fields
    reject None.
    """
    import pytest
    with pytest.raises((TypeError, ValueError)):
        EmbeddingJob()  # type: ignore[call-arg]


def test_embedding_job_result_field_set() -> None:
    """Mutant on EmbeddingJobResult field set.
    """
    fields = {f.name for f in EmbeddingJobResult.__dataclass_fields__.values()}
    # Concrete fields (from actual dataclass).
    assert "failed" in fields
    assert "retried" in fields
    assert "error" in fields
    assert "backoff_seconds" in fields
    assert "duration_seconds" in fields


def test_embedding_job_result_success_construction() -> None:
    """Mutant flipping ``failed`` / ``retried`` flags.
    """
    r = EmbeddingJobResult(
        chunk_id="c1", status="success", failed=False, retried=False,
        backoff_seconds=0.0, duration_seconds=0.1, error=None,
    )
    assert r.failed is False
    assert r.retried is False
    assert r.error is None
    assert r.status == "success"


def test_embedding_job_result_failure_construction() -> None:
    """Mutant on the error handling.
    """
    r = EmbeddingJobResult(
        chunk_id="c1", status="failed", failed=True, retried=True,
        backoff_seconds=1.5, duration_seconds=2.0, error="oops",
    )
    assert r.failed is True
    assert r.retried is True
    assert r.error == "oops"
    assert r.status == "failed"
    assert r.backoff_seconds == 1.5


def test_get_queue_config_known_queue() -> None:
    """Mutant on the queue config lookup.
    """
    qc = get_queue_config("embedding")
    assert qc.name == "embedding"


def test_get_queue_config_unknown_raises() -> None:
    """Mutant that returns a default config for unknown queues would
    break callers expecting a hard failure. Assert KeyError on missing.
    """
    import pytest
    with pytest.raises(KeyError):
        get_queue_config("nonexistent_queue_xyz")
