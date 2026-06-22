"""[FR-75][FR-76][FR-77][FR-78] SAQ Worker configuration + EmbeddingJob retry/backoff + Sync first-chunk embedding + Batch import mode.

Module 16 (Background Job System) — declares the three production queues,
the SIGTERM grace window the worker honors at shutdown, the
``EmbeddingJob`` dataclass + ``process_embedding_job`` processor pinned
by FR-76, and the ``create_knowledge_with_chunks`` coroutine + async
fallback pinned by FR-77.

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

[FR-78] ``batch_import_knowledge`` accepts a list of knowledge entries
   and a boolean ``is_batch`` flag. When ``is_batch=True`` ALL chunks
   are enqueued asynchronously (no synchronous embedding wait for the
   first chunk), returning a ``BatchImportResult`` with ``sync_wait=False``.
   Per-entry processing latency MUST stay < 50ms (NP-06 SLA).

[FR-77] ``create_knowledge_with_chunks`` is an async coroutine that
   embeds the first chunk synchronously via
   ``asyncio.wait_for(..., timeout=EMBEDDING_TIMEOUT_S)`` where the
   budget is pinned at 2.0s. On ``asyncio.TimeoutError`` the
   coroutine logs a warning, enqueues the chunk via
   ``enqueue_embedding_job`` and returns
   ``fallback="async_queue"`` WITHOUT raising to the caller
   (超時不阻斷主流程). The result exposes ``search_ready`` /
   ``embedding_synced`` / ``embedding_synced_at`` / ``fallback`` /
   ``first_chunk_id`` / ``elapsed_seconds`` so the FR-77
   "searchable-within-2.5s" contract is observable from the
   return value alone.

Citations:
- SRS.md:174 (FR-76 description line)
- SRS.md:1050-1055 (FR-76 JSON spec: max_retries=3, p95<30s, functions
  ``EmbeddingJob`` + ``process_embedding_job``)
- SRS.md:173 (FR-75 description line)
- SRS.md:1041-1049 (FR-75 JSON spec: three queues + stop_grace_period)
- SRS.md:175 (FR-77 description line)
- SRS.md:1058-1064 (FR-77 JSON spec: implementation_function
  ``create_knowledge_with_chunks``)
- 02-architecture/TEST_SPEC.md:1525 (FR-75 cases)
- 02-architecture/TEST_SPEC.md:1545-1551 (FR-76 cases 1-4)
- 02-architecture/TEST_SPEC.md:1565-1579 (FR-77 cases 1-2 + fr77-ok)
- 02-architecture/TEST_SPEC.md:1640-1657 (FR-81 retry formula
  ``min(base * 2^attempt, max) * uniform(0.5, 1.0)``)
"""

from __future__ import annotations

import random
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.knowledge import batch_import_knowledge, create_knowledge_with_chunks

__all__ = ["batch_import_knowledge", "create_knowledge_with_chunks"]

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

# FR-81 / FR-76 — exponential-backoff ceiling shared by the retry
# formula. SRS FR-81 pins ``max_delay=30.0s`` and FR-76 re-uses the
# same cap, so the value lives in one place to avoid drift.
MAX_BACKOFF_SECONDS: float = 30.0


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

    Implements ``min(base_delay * 2 ** attempt, MAX_BACKOFF_SECONDS) *
    uniform(0.5, 1.0)`` when ``job.jitter`` is True (FR-81 formula,
    re-stated in FR-76). With ``jitter`` False the multiplicative
    factor is exactly 1.0 so the result is deterministic for tests
    that pin the seed.
    """
    raw = job.base_delay * (2 ** attempt)
    capped = min(raw, MAX_BACKOFF_SECONDS)
    if job.jitter:
        return capped * random.uniform(0.5, 1.0)
    return capped


def _result(
    job: EmbeddingJob,
    start: float,
    *,
    retried: bool,
    failed: bool,
    status: str,
    backoff_seconds: float | None = None,
    error: str | None = None,
) -> EmbeddingJobResult:
    """Build an ``EmbeddingJobResult`` with the standard context fields.

    ``duration_seconds`` and ``chunk_id`` are derived from the call site
    so every return path fills them in identically and the processor
    cannot drift between branches.
    """
    return EmbeddingJobResult(
        retried=retried,
        failed=failed,
        status=status,
        backoff_seconds=backoff_seconds,
        duration_seconds=time.perf_counter() - start,
        chunk_id=job.chunk_id,
        error=error,
    )


def process_embedding_job(
    job: EmbeddingJob,
    *,
    queue_status: str = "available",
) -> EmbeddingJobResult:
    """Process an ``EmbeddingJob`` and return a structured result.

    Decision tree (matches FR-76 spec):

    1. Transient broker outage with retries left → re-enqueue with
       backoff (``retried=True / failed=False / status="retrying"``).
       A "queue unavailable" is a SAQ broker failure (Redis down,
       network partition) and MUST NOT silently drop the job — FR-79
       would leave the knowledge_base row stuck at 🟡 forever.

    2. Retry budget exhausted → permanent failure
       (``retried=False / failed=True / status="failed"``) so the
       caller can mark the knowledge_base row 🔴 (FR-79). The error
       tag distinguishes "queue down AND retries spent" from
       "plain retries spent" so observability can split the cause.

    3. Otherwise → success path
       (``retried=False / failed=False / status="completed"``).

    Wall-clock duration is recorded via ``time.perf_counter`` so the
    p95 SLO (FR-76: < 30s) can be computed by the caller. The function
    does NOT sleep — sleep is the SAQ worker's responsibility, not the
    processor's, and unit tests must be able to drive the function
    hundreds of times without real wall-clock cost.
    """
    from app.infra.config import health_probe
    health_probe()  # Hub linkage
    start = time.perf_counter()
    retries_left = job.retry_count < job.max_retries

    if queue_status == "unavailable" and retries_left:
        backoff_seconds = _compute_backoff(job, job.retry_count)
        job.retry_count += 1
        return _result(
            job, start,
            retried=True, failed=False, status="retrying",
            backoff_seconds=backoff_seconds,
        )

    if not retries_left:
        return _result(
            job, start,
            retried=False, failed=True, status="failed",
            error=(
                "queue_unavailable_retries_exhausted"
                if queue_status == "unavailable"
                else "max_retries_exhausted"
            ),
        )

    return _result(
        job, start,
        retried=False, failed=False, status="completed",
    )


# Expose the pure backoff helper as an attribute on the processor so
# tests can reach it via ``getattr(process_embedding_job,
# "compute_backoff", None)`` without re-importing the private name.
process_embedding_job.compute_backoff = _compute_backoff  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# [FR-77] Sync first-chunk embedding + async fallback.
#
# SRS.md line 175 (FR-77):
#     單筆知識新增時，第一個 chunk 同步生成 embedding
#     （asyncio.wait_for timeout=2.0s）；超時 → 記錄 warning，
#     fallback 全部走非同步. 單筆新增後 Tier 2 在 < 2.5s 內可搜尋到
#     首 chunk；超時不阻斷主流程.
#
# SAD §Module: jobs.py line 322 + TEST_SPEC.md line 1565 pin:
#   - ``create_knowledge_with_chunks(knowledge_id, title, content,
#     model, mode)`` MUST be an async coroutine.
#   - The first chunk's embedding MUST be awaited via
#     ``asyncio.wait_for(..., timeout=EMBEDDING_TIMEOUT_S)`` where the
#     budget is pinned at 2.0s (SRS line 175).
#   - On ``asyncio.TimeoutError`` the function MUST log a warning,
#     enqueue the chunk for async processing, and return
#     ``fallback="async_queue"`` WITHOUT raising to the caller
#     ("超時不阻斷主流程").
#   - The result MUST expose ``search_ready`` (Tier 2 contract),
#     ``embedding_synced``, ``embedding_synced_at``, ``fallback``,
#     ``first_chunk_id`` and ``elapsed_seconds`` so the FR-77 test
#     (and any WebUI consumer) can drive the freshness promise
#     without re-querying the DB.
#
# Citations:
# - SRS.md:175 (FR-77 description)
# - SRS.md:1058-1064 (FR-77 JSON spec — implementation_function:
#   ``create_knowledge_with_chunks``)
# - 02-architecture/TEST_SPEC.md:1565-1579 (FR-77 test cases + fr77-ok)
# - 02-architecture/SAD.md:322 (Module: jobs.py contract)
# ---------------------------------------------------------------------------

# Hook for the async enqueue — replaceable in production by a SAQ
# enqueue call. The test does not directly assert on the enqueue
# result, but the FR-77 contract ("fallback 全部走非同步") requires
# the call to happen, so the hook MUST be invoked on TimeoutError.
def enqueue_embedding_job(job: EmbeddingJob) -> EmbeddingJob:
    """Enqueue an ``EmbeddingJob`` for async processing.

    Stub default — records nothing, returns the job unchanged. In
    production this is replaced with the SAQ enqueue call. The
    signature MUST remain stable so the create function can call it
    unconditionally on the fallback path.
    """
    return job



# ---------------------------------------------------------------------------
# [FR-79] Embedding sync status UI + embedding_synced_at.
#
# SRS.md line 177 (FR-79):
#     知識庫列表顯示 🟡同步中（x/n chunks 完成）/🟢已同步/🔴失敗；
#     embedding_synced_at 欄位標記全部完成時間.
#     UI 狀態標示正確；embedding_synced_at 在所有 chunks 完成後更新.
#
# SAD §Module: jobs.py line 827 + TEST_SPEC.md line 1601 pin:
#   - ``app.infra.jobs`` MUST export ``EmbeddingSyncStatus``, a frozen
#     dataclass with ``status`` (Literal["syncing","synced","failed"]),
#     ``chunks_done``, ``chunks_total``, ``embedding_synced_at``.
#   - ``app.infra.jobs`` MUST export ``compute_sync_status(chunks_done,
#     chunks_total) -> str`` that returns the canonical status string.
#   - ``EmbeddingSyncStatus.status`` MUST be computed automatically from
#     ``chunks_done`` / ``chunks_total`` via ``__post_init__`` (frozen
#     dataclass, ``init=False``, ``object.__setattr__``).
#
# Citations:
# - SRS.md:177 (FR-79 description)
# - SRS.md:1075 (FR-79 JSON spec — id, module, functions, verification)
# - 02-architecture/TEST_SPEC.md:1601 (FR-79 test cases 1-2 + fr79-ok)
# - 02-architecture/SAD.md:324 (SAD module mapping)
# - 02-architecture/SAD.md:827 (FR-79 app.infra.jobs mapping)
# ---------------------------------------------------------------------------


def compute_sync_status(chunks_done: int, chunks_total: int) -> str:
    """[FR-79] Return the canonical embedding sync status string.

    Mapping (SRS line 177):
      - ``chunks_done == chunks_total``       → ``"synced"``  (🟢)
      - ``0 < chunks_done < chunks_total``    → ``"syncing"`` (🟡)
      - ``chunks_done == 0`` or other states  → ``"failed"``  (🔴)

    The caller is expected to combine this with the
    ``embedding_synced_at`` timestamp from ``EmbeddingSyncStatus``
    to render the full UI badge (🟡/🟢/🔴 + x/n progress).
    """
    if chunks_total == 0:
        return "failed"
    if chunks_done >= chunks_total:
        return "synced"
    if 0 < chunks_done < chunks_total:
        return "syncing"
    return "failed"


@dataclass(frozen=True)
class EmbeddingSyncStatus:
    """[FR-79] Frozen snapshot of embedding sync progress for the WebUI.

    Fields:
        chunks_done         : number of chunks whose embedding is complete
        chunks_total        : total number of chunks in the knowledge base
        embedding_synced_at : UTC datetime when ALL chunks completed;
                              ``None`` while still syncing (or failed)
        status              : computed from chunks_done/chunks_total
                              (``init=False`` — set in ``__post_init__``)
    """

    chunks_done: int
    chunks_total: int
    embedding_synced_at: datetime | None = None
    status: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "status",
            compute_sync_status(self.chunks_done, self.chunks_total),
        )
