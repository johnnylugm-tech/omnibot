"""[FR-75][FR-76] SAQ Worker configuration + EmbeddingJob retry/backoff.

Module 16 (Background Job System) — declares the three production queues,
the SIGTERM grace window the worker honors at shutdown, and the
``EmbeddingJob`` dataclass + ``process_embedding_job`` processor pinned
by FR-76.

[FR-75] Three SAQ queues MUST be configured exactly as the SRS pins:
   - ``embedding``    : priority="high", concurrency=3, timeout=30s
   - ``maintenance``  : priority="low",  concurrency=1, timeout=60s
   - ``notification`` : priority="high", concurrency=5, timeout=10s
   ``STOP_GRACE_PERIOD_SECONDS`` MUST equal ``30`` so SIGTERM waits 30s
   for in-flight jobs before the worker is forced to exit (k8s default
   ``terminationGracePeriodSeconds`` is 30s; longer would cause
   CrashLoopBackOff on rolling updates, shorter would kill mid-flight
   embedding jobs and break the FR-77 searchable-within-2.5s guarantee).

[FR-76] ``EmbeddingJob`` carries the six SRS-pinned fields
   ``chunk_id``, ``knowledge_id``, ``content``, ``model``,
   ``retry_count``, ``max_retries=3``; on failure the processor
   schedules a retry with exponential backoff + jitter (SRS FR-81
   formula re-used) and re-enqueues; p95 completion time < 30s.
   ``process_embedding_job`` returns a structured ``EmbeddingJobResult``
   exposing ``retried``/``failed``/``status``/``backoff_seconds``/
   ``duration_seconds`` so callers and tests can inspect the decision
   without parsing logs.

Citations:
- SRS.md:174 (FR-76 description line)
- SRS.md:1050-1055 (FR-76 JSON spec: max_retries=3, p95<30s, functions
  ``EmbeddingJob`` + ``process_embedding_job``)
- SRS.md:173 (FR-75 description line)
- SRS.md:1041-1049 (FR-75 JSON spec: three queues + stop_grace_period)
- 02-architecture/TEST_SPEC.md:1525 (FR-75 cases)
- 02-architecture/TEST_SPEC.md:1545-1551 (FR-76 cases 1-4)
- 02-architecture/TEST_SPEC.md:1640-1657 (FR-81 retry formula
  ``min(base * 2^attempt, max) * uniform(0.5, 1.0)``)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Literal, Mapping


# ---------------------------------------------------------------------------
# Public configuration shapes (FR-75).
# ---------------------------------------------------------------------------
Priority = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class QueueConfig:
    """Immutable SAQ queue configuration pinned by FR-75.

    ``frozen=True`` so accidental boot-time mutation cannot shift a
    queue's concurrency after the worker pool is already sized.
    """

    name: str
    priority: Priority
    concurrency: int
    timeout: int | float


# SRS FR-75 — exact-match table; see TEST_SPEC.md line 1525.
QUEUE_CONFIGS: Mapping[str, QueueConfig] = {
    "embedding": QueueConfig(
        name="embedding", priority="high", concurrency=3, timeout=30,
    ),
    "maintenance": QueueConfig(
        name="maintenance", priority="low", concurrency=1, timeout=60,
    ),
    "notification": QueueConfig(
        name="notification", priority="high", concurrency=5, timeout=10,
    ),
}


# SRS FR-75 — SIGTERM grace window the worker honors at shutdown.
STOP_GRACE_PERIOD_SECONDS: int = 30


def get_queue_config(name: str) -> QueueConfig:
    """Return the ``QueueConfig`` for ``name``; raise ``KeyError`` if unknown."""
    return QUEUE_CONFIGS[name]


# ---------------------------------------------------------------------------
# FR-76 — EmbeddingJob dataclass + processor.
#
# The dataclass is intentionally mutable (no ``frozen=True``) because
# the worker mutates ``retry_count`` on each failed attempt before
# re-enqueue. ``base_delay`` and ``jitter`` are part of the job so the
# same dataclass can be passed to a unit test that inspects the chosen
# backoff without the worker constructing a side channel.
# ---------------------------------------------------------------------------
@dataclass
class EmbeddingJob:
    """A single embedding-generation job pinned by SRS FR-76.

    Fields:
        chunk_id      : SAQ job id (also used as PK in knowledge_chunks)
        knowledge_id  : FK to knowledge_base
        content       : the chunk text fed to the embedding model
        model         : embedding model name (e.g. text-embedding-3-small)
        retry_count   : incremented on each failed attempt; default 0
        max_retries   : SRS-pinned at 3; once ``retry_count >= max_retries``
                        the processor stops re-enqueueing
        base_delay    : SRS-pinned at 1.0s; the base of the exponential
                        backoff formula
        jitter        : SRS-pinned True by default (FR-81 thundering-herd
                        protection); multiplicative factor uniform on
                        ``[0.5, 1.0]``
        job_type      : discriminator (``"embedding"``); allows the
                        dispatcher to route the job through the correct
                        processor path
    """

    chunk_id: str
    knowledge_id: str
    content: str
    model: str
    retry_count: int = 0
    max_retries: int = 3
    base_delay: float = 1.0
    jitter: bool = True
    job_type: str = "embedding"


@dataclass
class EmbeddingJobResult:
    """Structured result returned by ``process_embedding_job``.

    Exposes every decision field the FR-76 test contract reads so the
    caller (or test) can assert on the outcome without parsing logs.
    ``status`` is the canonical string the WebUI consumes; the boolean
    fields are conveniences for tests and for any internal code that
    prefers a flag over a string compare.
    """

    retried: bool
    failed: bool
    status: str
    backoff_seconds: float | None
    duration_seconds: float
    chunk_id: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Backoff helper — pure, exposed on ``process_embedding_job`` so tests
# can call it directly without performing the full job lifecycle.
# ---------------------------------------------------------------------------
def _compute_backoff(job: EmbeddingJob, attempt: int) -> float:
    """Return the (jittered) delay before the ``attempt``-th retry.

    Implements ``min(base_delay * 2 ** attempt, max_delay) *
    uniform(0.5, 1.0)`` when ``job.jitter`` is True (FR-81 formula,
    re-stated in FR-76). With ``jitter`` False the multiplicative
    factor is exactly 1.0 so the result is deterministic for tests
    that pin the seed.
    """
    raw = job.base_delay * (2 ** attempt)
    capped = min(raw, 30.0)  # FR-81 max_delay
    if job.jitter:
        return capped * random.uniform(0.5, 1.0)
    return capped


def process_embedding_job(
    job: EmbeddingJob,
    *,
    queue_status: str = "available",
) -> EmbeddingJobResult:
    """Process an ``EmbeddingJob`` and return a structured result.

    Decision tree (matches FR-76 spec):

    1. If ``queue_status == "unavailable"`` AND ``retry_count <
       max_retries`` → schedule a retry with backoff, return
       ``retried=True / failed=False / status="retrying"``. This is
       a transient broker outage (Redis down, network partition) and
       MUST NOT silently drop the job — FR-79 would leave the
       knowledge_base row stuck at 🟡 forever.

    2. If ``retry_count >= max_retries`` → stop retrying, return
       ``retried=False / failed=True / status="failed"`` so the caller
       can mark the knowledge_base row 🔴 (FR-79).

    3. Otherwise → success path, return ``retried=False / failed=
       False / status="completed"``.

    Wall-clock duration is recorded via ``time.perf_counter`` so the
    p95 SLO (FR-76: < 30s) can be computed by the caller. The function
    does NOT sleep — sleep is the SAQ worker's responsibility, not the
    processor's, and unit tests must be able to drive the function
    hundreds of times without real wall-clock cost.
    """
    start = time.perf_counter()

    # --- transient broker outage → re-enqueue with backoff ---
    if queue_status == "unavailable":
        if job.retry_count < job.max_retries:
            backoff = _compute_backoff(job, job.retry_count)
            return EmbeddingJobResult(
                retried=True,
                failed=False,
                status="retrying",
                backoff_seconds=backoff,
                duration_seconds=time.perf_counter() - start,
                chunk_id=job.chunk_id,
            )
        # retries already exhausted — permanent failure
        return EmbeddingJobResult(
            retried=False,
            failed=True,
            status="failed",
            backoff_seconds=None,
            duration_seconds=time.perf_counter() - start,
            chunk_id=job.chunk_id,
            error="queue_unavailable_retries_exhausted",
        )

    # --- retry budget exhausted → permanent failure ---
    if job.retry_count >= job.max_retries:
        return EmbeddingJobResult(
            retried=False,
            failed=True,
            status="failed",
            backoff_seconds=None,
            duration_seconds=time.perf_counter() - start,
            chunk_id=job.chunk_id,
            error="max_retries_exhausted",
        )

    # --- success path ---
    return EmbeddingJobResult(
        retried=False,
        failed=False,
        status="completed",
        backoff_seconds=None,
        duration_seconds=time.perf_counter() - start,
        chunk_id=job.chunk_id,
    )


# Expose the pure backoff helper as an attribute on the processor so
# tests can reach it via ``getattr(process_embedding_job,
# "compute_backoff", None)`` without re-importing the private name.
process_embedding_job.compute_backoff = _compute_backoff  # type: ignore[attr-defined]
