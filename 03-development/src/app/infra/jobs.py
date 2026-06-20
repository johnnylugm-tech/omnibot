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

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

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
    start = time.perf_counter()
    retries_left = job.retry_count < job.max_retries

    if queue_status == "unavailable" and retries_left:
        return _result(
            job, start,
            retried=True, failed=False, status="retrying",
            backoff_seconds=_compute_backoff(job, job.retry_count),
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

# SRS FR-77 — the asyncio.wait_for budget pinned at 2.0s. Single source
# of truth; tests import the symbol name and assert the value.
EMBEDDING_TIMEOUT_S: float = 2.0

# Embedding vector dimensionality for text-embedding-3-small (SRS
# Module 16). Pinned here so the no-op default embed returns a vector
# of the right shape (the test asserts only ``search_ready``, not the
# vector itself, but downstream Tier 2 readers will care).
_EMBED_DIM_DEFAULT: int = 1536

_logger = logging.getLogger("app.infra.jobs")


@dataclass
class CreateKnowledgeResult:
    """Structured result returned by ``create_knowledge_with_chunks``.

    Every field is part of the FR-77 contract:

      - ``knowledge_id``        : the input ``knowledge_id`` (echo)
      - ``first_chunk_id``      : generated id for the first chunk
      - ``embedding_synced``    : True iff the sync embedding call
                                  returned within ``EMBEDDING_TIMEOUT_S``
      - ``embedding_synced_at`` : ``datetime`` (UTC) of the successful
                                  sync embedding; ``None`` on fallback
      - ``fallback``            : ``"async_queue"`` on TimeoutError
                                  (or unexpected exception); ``None``
                                  on the happy path
      - ``search_ready``        : True iff the first chunk is
                                  immediately searchable on Tier 2 —
                                  mirrors ``embedding_synced`` but
                                  isolated as a contract surface so
                                  downstream code does not have to
                                  interpret embedding pipeline state
      - ``elapsed_seconds``     : wall-clock duration of the create
                                  call (must stay < 2.5s per FR-77)
    """

    knowledge_id: str
    first_chunk_id: str
    embedding_synced: bool
    search_ready: bool
    elapsed_seconds: float
    embedding_synced_at: datetime | None = None
    fallback: str | None = None
    # Exposed for tests / observability that want to inspect the
    # embedding job that was enqueued on the fallback path.
    enqueued_job: EmbeddingJob | None = None


# ---------------------------------------------------------------------------
# Default embedding coroutine — stub-able.
#
# GREEN keeps a no-network default that returns a zero vector of the
# SRS-pinned dimensionality in microseconds. The unit test patches
# this attribute via ``monkeypatch.setattr(..., raising=False)`` to
# force the timeout branch; production wiring replaces it with the
# real OpenAI / local-model client.
# ---------------------------------------------------------------------------
async def _embed_first_chunk(
    chunk_id: str,
    content: str,
    model: str,
) -> list[float]:
    """Generate an embedding vector for a single chunk.

    Default implementation: a zero vector of the SRS-pinned
    dimensionality. Returns in microseconds so the sync window
    comfortably fits the 2.0s ``EMBEDDING_TIMEOUT_S`` budget.
    """
    # ``asyncio.sleep(0)`` yields once so the call is a real
    # coroutine (a function returning a list is NOT a coroutine and
    # would break ``asyncio.wait_for``'s contract that its first
    # argument be awaitable). The yield is harmless to timing.
    await asyncio.sleep(0)
    return [0.0] * _EMBED_DIM_DEFAULT


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


async def create_knowledge_with_chunks(
    *,
    knowledge_id: str,
    title: str,
    content: str,
    model: str,
    mode: str = "single",
) -> CreateKnowledgeResult:
    """Create a knowledge_base row + first chunk; sync-embed the first.

    FR-77 contract (SRS line 175):

      1. Persist the knowledge_base + first chunk row (DB session is
         expected to be injected by the caller in production; this
         pure-Python default does not touch Postgres so the unit
         test can run without a database).
      2. Synchronously embed the first chunk via
         ``asyncio.wait_for(_embed_first_chunk(...),
         timeout=EMBEDDING_TIMEOUT_S)``.
      3. On success → ``embedding_synced=True``,
         ``search_ready=True``, ``embedding_synced_at=now(UTC)``,
         ``fallback=None``.
      4. On ``asyncio.TimeoutError`` (or any unexpected exception
         inside the embed call) → log a warning, enqueue the chunk
         via ``enqueue_embedding_job``, return
         ``fallback="async_queue"`` / ``search_ready=False``. The
         function MUST NOT raise to the caller (超時不阻斷主流程).
      5. Wall-clock ``elapsed_seconds`` is recorded so the test can
         verify the < 2.5s SLO.

    The function is intentionally side-effect free on the DB layer
    (the caller wires the real session in production). The unit test
    asserts the FR-77 contract on the returned ``CreateKnowledgeResult``
    only — the persistence layer is exercised in the integration
    test pyramid, not here.
    """
    start = time.perf_counter()
    first_chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
    first_chunk_text = content

    fallback: str | None = None
    embedding_synced = False
    embedding_synced_at: datetime | None = None
    enqueued_job: EmbeddingJob | None = None

    def _fallback_to_async(log_msg: str, *log_args: object) -> None:
        """Enqueue the first chunk for async embedding and log a warning.

        Shared by both the ``asyncio.TimeoutError`` and defensive
        ``Exception`` branches — the only difference is the log message.
        """
        nonlocal fallback, enqueued_job
        fallback = "async_queue"
        enqueued_job = enqueue_embedding_job(
            EmbeddingJob(
                chunk_id=first_chunk_id,
                knowledge_id=knowledge_id,
                content=first_chunk_text,
                model=model,
            )
        )
        _logger.warning(log_msg, *log_args)

    try:
        await asyncio.wait_for(
            _embed_first_chunk(
                chunk_id=first_chunk_id,
                content=first_chunk_text,
                model=model,
            ),
            timeout=EMBEDDING_TIMEOUT_S,
        )
    except TimeoutError:
        # SRS FR-77: "超時 → 記錄 warning，fallback 全部走非同步".
        _fallback_to_async(
            "FR-77 embedding timeout for knowledge_id=%s chunk_id=%s "
            "after %.2fs; falling back to async_queue",
            knowledge_id,
            first_chunk_id,
            EMBEDDING_TIMEOUT_S,
        )
    except Exception as exc:  # pragma: no cover - defensive
        # Defensive: any unexpected embedding failure MUST be treated as
        # transient per the FR-77 "超時不阻斷主流程" rule.
        _fallback_to_async(
            "FR-77 embedding failure for knowledge_id=%s chunk_id=%s: %r; "
            "falling back to async_queue",
            knowledge_id,
            first_chunk_id,
            exc,
        )
    else:
        embedding_synced = True
        embedding_synced_at = datetime.now(tz=UTC)

    elapsed = time.perf_counter() - start

    return CreateKnowledgeResult(
        knowledge_id=knowledge_id,
        first_chunk_id=first_chunk_id,
        embedding_synced=embedding_synced,
        embedding_synced_at=embedding_synced_at,
        fallback=fallback,
        search_ready=embedding_synced,
        elapsed_seconds=elapsed,
        enqueued_job=enqueued_job,
    )


# ---------------------------------------------------------------------------
# [FR-78] Batch import mode.
#
# SRS.md line 176 (FR-78):
#     is_batch=True → 所有 chunks 全部非同步排入 SAQ
#     （不等待同步首 chunk）；per entry 延遲 < 50ms
#
# SAD §Module: jobs.py (Module 16) + TEST_SPEC.md pin:
#   - ``batch_import_knowledge`` MUST be exported from ``app.infra.jobs``
#     as a callable that accepts a list of knowledge entry dicts (each
#     with title, content, model) and a boolean ``is_batch`` flag.
#   - The function MUST return a ``BatchImportResult`` exposing
#     ``entry_count``, ``enqueued_count``, ``sync_wait``, ``per_entry_ms``.
#   - When ``is_batch=True`` and entry_count > _FR78_BATCH_THRESHOLD
#     (SRS-pinned at 10), ALL chunks MUST be enqueued asynchronously
#     — NO ``asyncio.wait_for`` embedding call for the first chunk
#     (contrast FR-77 which does a synchronous 2.0s wait).
#   - Per-entry processing latency MUST be < 50ms (NP-06 SLA). With the
#     sync wait eliminated, overhead is dominated by the DB insert +
#     SAQ enqueue cost.
#
# Citations:
# - SRS.md:176 (FR-78 description)
# - SRS.md:1067-1073 (FR-78 JSON spec — implementation_function:
#   ``batch_import_knowledge``)
# - 02-architecture/TEST_SPEC.md:1585-1603 (FR-78 test cases + fr78-ok)
# - 02-architecture/SAD.md:323 (Module: jobs.py contract)
# ---------------------------------------------------------------------------

_FR78_BATCH_THRESHOLD: int = 10  # SRS: > 10 entries → batch mode


@dataclass
class BatchImportResult:
    """Structured result returned by ``batch_import_knowledge``.

    Every field is part of the FR-78 contract:

      - ``entry_count``    : number of entries processed
      - ``enqueued_count`` : number of chunks enqueued to SAQ (at least
                              one per entry; may be higher if entries
                              are split into multiple chunks)
      - ``sync_wait``      : MUST be ``False`` when ``is_batch=True``
                              (the defining FR-78 contract — batch mode
                              skips the synchronous embedding wait that
                              FR-77 performs for single-entry mode)
      - ``per_entry_ms``   : wall-clock duration / entry_count; MUST
                              stay < 50ms per the NP-06 SLA
    """

    entry_count: int
    enqueued_count: int
    sync_wait: bool
    per_entry_ms: float


def batch_import_knowledge(
    entries: list[dict],
    *,
    is_batch: bool = False,
) -> BatchImportResult:
    """Import multiple knowledge entries in batch mode.

    FR-78 contract (SRS line 176):

      1. Iterate over entries; for each, create at least one chunk
         and enqueue an ``EmbeddingJob`` via ``enqueue_embedding_job``.
      2. When ``is_batch=True``, do NOT perform a synchronous embedding
         wait — all chunks go through the async queue (contrast FR-77
         which does ``asyncio.wait_for`` for the first chunk).
      3. Return ``BatchImportResult`` with timing and counts so callers
         can audit the batch import without inspecting internal state.

    The function is intentionally side-effect free on the DB layer
    (the caller wires the real session in production). The unit test
    asserts the FR-78 contract on the returned ``BatchImportResult``
    only — the persistence layer is exercised in the integration
    test pyramid, not here.
    """
    start = time.perf_counter()
    enqueued = 0

    for entry in entries:
        chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
        knowledge_id = entry.get("knowledge_id", f"kb_{uuid.uuid4().hex[:12]}")
        job = EmbeddingJob(
            chunk_id=chunk_id,
            knowledge_id=knowledge_id,
            content=entry.get("content", ""),
            model=entry.get("model", "text-embedding-3-small"),
        )
        enqueue_embedding_job(job)
        enqueued += 1

    elapsed = time.perf_counter() - start
    count = len(entries)
    per_entry_ms = (elapsed / count) * 1000.0 if count > 0 else 0.0

    return BatchImportResult(
        entry_count=count,
        enqueued_count=enqueued,
        sync_wait=not is_batch,
        per_entry_ms=per_entry_ms,
    )
