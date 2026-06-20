"""TDD-RED: failing tests for FR-76 — EmbeddingJob retry/backoff.

Spec source: 02-architecture/TEST_SPEC.md (FR-76)
SRS source : SRS.md FR-76 (Module 16: Background Job System)

Acceptance criteria (from SRS FR-76):
    EmbeddingJob carries chunk_id, knowledge_id, content, model,
    retry_count, max_retries=3. On failure: exponential backoff with
    jitter, re-enqueued. p95 completion time < 30s.

The four TEST_SPEC cases (function names MUST match exactly):
    1. test_fr76_max_retries_3_then_stop
         Inputs: max_retries="3"; attempt="4"; expected_retried="false"
         Type  : boundary
    2. test_fr76_backoff_has_jitter
         Inputs: attempt="2"; base_delay="1.0"; expected_jitter="true"
         Type  : validation
    3. test_fr76_p95_under_30s
         Inputs: job_type="embedding"; p95_limit_seconds="30"
         Type  : nfr_pattern
    4. test_fr76_queue_unavailable_job_retried_with_backoff
         Inputs: queue_status="unavailable"; max_retries="3"; jitter="true"
         Type  : fault_injection

Sub-assertion (per TEST_SPEC):
    fr76-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test isolation — ``process_embedding_job`` is invoked by the SAQ worker
# which connects to a live Redis broker, and the EmbeddingJob may make a
# real network call to an embedding provider (OpenAI / Anthropic / etc.).
# Both side effects MUST be eliminated from unit tests so a test can fail
# only because the retry/backoff logic is missing, not because Redis is
# unreachable or the LLM endpoint timed out.
#
# GREEN contract for the EmbeddingJob module:
#   - ``EmbeddingJob`` MUST be a dataclass / pydantic model that exposes
#     the six SRS-pinned fields: ``chunk_id``, ``knowledge_id``,
#     ``content``, ``model``, ``retry_count``, ``max_retries``.
#   - ``process_embedding_job(job)`` MUST accept an EmbeddingJob and
#     return a non-None result. The function MUST consult ``retry_count``
#     against ``max_retries`` to decide whether to re-enqueue. Network
#     I/O and LLM calls MUST be injected so tests can stub them.
#   - The retry policy MUST use exponential backoff with jitter — the
#     same formula documented in ``app.infra.retry.RetryStrategy``.
#   - Queue-availability checks MUST distinguish "queue down" from
#     "embedding model error" — the former triggers a retry, the latter
#     is propagated to the caller.
#
# The autouse fixture below is a no-op during RED (the import below
# raises Collection Error before the fixture runs) and patches any
# real Redis / HTTP construction once GREEN has landed.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_embedding_io(monkeypatch):
    """Prevent real Redis / embedding-provider I/O during FR-76 unit tests.

    The SAQ library normally constructs its own Redis connection from a
    URL passed at startup, and ``process_embedding_job`` will eventually
    call out to an embedding provider. Both MUST be replaceable with a
    stub so the test can never escape into a real socket.
    """
    yield


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-76 (SRS.md line 174) requires:
#
#   1. ``app.infra.jobs`` MUST export a dataclass ``EmbeddingJob`` with
#      the SRS-pinned fields:
#         chunk_id      : str
#         knowledge_id  : str
#         content       : str
#         model         : str
#         retry_count   : int   (default 0; incremented on each failure)
#         max_retries   : int   (default 3; SRS pinned)
#
#   2. ``app.infra.jobs`` MUST export ``process_embedding_job(job)``,
#      a callable that returns a non-None result on success. The
#      callable MUST consult ``job.retry_count`` against
#      ``job.max_retries`` and decide whether to retry on failure:
#         - retry_count < max_retries   ->  re-enqueue with backoff
#         - retry_count >= max_retries  ->  stop retrying, return result
#
#   3. The retry delay MUST be computed via the exponential-backoff +
#      jitter formula documented in SRS FR-81 (and re-stated in FR-76):
#         delay = min(base_delay * 2 ** retry_count, max_delay)
#                 * uniform(0.5, 1.0)
#      The ``jitter`` flag MUST be True by default so the FR-81
#      thundering-herd protection is always on.
#
#   4. ``process_embedding_job`` MUST accept an optional ``queue_status``
#      (or expose ``is_queue_available()``) so the test can simulate
#      "queue unavailable" → must trigger retry-with-backoff rather than
#      than silently dropping the job.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the EmbeddingJob symbols are
# not yet defined in ``app.infra.jobs``. That is the valid RED signal —
# GREEN adds the dataclass and the processor.
# ---------------------------------------------------------------------------
from app.infra.jobs import (  # noqa: E402
    EmbeddingJob,
    process_embedding_job,
)

# ---------------------------------------------------------------------------
# Spec-pinned trigger values — keep these in lock-step with TEST_SPEC.md.
# A drift here (e.g. changing "3" -> "4") will silently break the
# spec-coverage check's exact-match lookup.
# ---------------------------------------------------------------------------
_FR76_MAX_RETRIES: int = 3
_FR76_BASE_DELAY: float = 1.0
_FR76_P95_LIMIT_SECONDS: float = 30.0


# ---------------------------------------------------------------------------
# 1. After ``max_retries=3`` unsuccessful attempts the job MUST stop
#    retrying (SRS FR-76: "max_retries=3 後停止重試").
#
# Spec input: max_retries="3"; attempt="4"; expected_retried="false".
# Spec sub-assertion: fr76-ok: result is not None.
# Test type: boundary.
#
# The EmbeddingJob carries a ``retry_count`` field. When a job has
# already failed ``max_retries`` times, ``process_embedding_job`` MUST
# NOT enqueue another retry — it MUST return a result (with status
# "failed" or equivalent) and surface the failure to the caller so the
# knowledge_base row can be marked 🔴 (FR-79).
#
# Boundary semantics: ``attempt=4`` means "we are about to make the 4th
# invocation"; since max_retries=3 the 4th invocation MUST be rejected.
# A regression that allowed unlimited retries would silently loop
# forever in the SAQ worker and starve every other queue (FR-75
# embedding concurrency=3 cap would never free a worker).
# ---------------------------------------------------------------------------
def test_fr76_max_retries_3_then_stop():
    max_retries = _FR76_MAX_RETRIES
    attempt = 4
    expected_retried = False

    # Build a job that has already failed ``max_retries`` times.
    # GREEN TODO: EmbeddingJob(...) must be a dataclass / pydantic model
    # accepting chunk_id, knowledge_id, content, model, retry_count,
    # max_retries — see app/infra/jobs.py.
    job = EmbeddingJob(
        chunk_id="chunk_fr76_red",
        knowledge_id="kb_fr76_red",
        content="boundary retry-stop fixture",
        model="text-embedding-3-small",
        retry_count=attempt,  # already retried 4x
        max_retries=max_retries,
    )

    # Spec fr76-ok predicate 'result is not None' applies_to case 1.
    # GREEN TODO: process_embedding_job(job) must return a non-None
    # result (e.g. an EmbeddingJobResult) and MUST refuse to re-enqueue
    # when retry_count >= max_retries.
    result = process_embedding_job(job)

    # Spec fr76-ok predicate.
    assert result is not None, "fr76-ok predicate: result must not be None"

    # The job MUST NOT be re-enqueued — retry_count already hit the cap.
    # GREEN TODO: the result must expose either ``.retried`` (bool) or
    # ``.status`` (str in {"completed", "failed", "retrying"}) so the
    # test can assert the retry decision.
    actual_retried = _read_retry_decision(result)
    assert actual_retried is not None, (
        "FR-76 process_embedding_job result must expose a retry "
        "decision (e.g. ``retried`` attribute or ``status`` field); "
        "got neither"
    )
    assert actual_retried == expected_retried, (
        f"FR-76 retry_count={attempt} >= max_retries={max_retries}: "
        f"job MUST NOT be re-enqueued (expected retried="
        f"{expected_retried}); got retried={actual_retried}"
    )

    # Cross-check: EmbeddingJob MUST expose retry_count and max_retries
    # as attributes so the processor can compare them.
    assert getattr(job, "retry_count", None) == attempt, (
        f"FR-76 EmbeddingJob.retry_count must be {attempt}; "
        f"got {getattr(job, 'retry_count', None)!r}"
    )
    assert getattr(job, "max_retries", None) == max_retries, (
        f"FR-76 EmbeddingJob.max_retries must be {max_retries}; "
        f"got {getattr(job, 'max_retries', None)!r}"
    )

    # Defensive: result should signal permanent failure (not "success")
    # when retries are exhausted. Tests must not assume the exact shape
    # of the status field — accept either ``status`` or ``failed``.
    failed = _read_failure_flag(result)
    assert failed is True, (
        f"FR-76 retry_count={attempt} >= max_retries={max_retries}: "
        f"result must signal permanent failure; got "
        f"failed={failed!r}"
    )


# ---------------------------------------------------------------------------
# 2. The exponential backoff MUST include jitter so concurrent retries
#    do not synchronise (SRS FR-76: "指數退避含 jitter").
#
# Spec input: attempt="2"; base_delay="1.0"; expected_jitter="true".
# Test type: validation.
#
# A non-jittered retry schedule would let a fleet of 3 embedding workers
# all wake up at exactly the same instant and stampede the embedding
# provider — exactly the thundering-herd collapse FR-81 explicitly
# guards against. With base_delay=1.0 and attempt=2 the raw exponential
# value is 1.0 * 2**2 = 4.0s; with jitter the realised delay MUST land
# in [2.0s, 4.0s] (jitter factor uniform on [0.5, 1.0]).
#
# The test draws the delay several times and asserts:
#   (a) it is strictly non-deterministic across draws (jitter is on),
#   (b) every draw is within the SRS-mandated jitter window.
# ---------------------------------------------------------------------------
def test_fr76_backoff_has_jitter():
    attempt = 2
    base_delay = _FR76_BASE_DELAY
    expected_jitter = True

    # GREEN TODO: EmbeddingJob must carry (or expose via a helper)
    # the parameters needed to compute the backoff — at minimum
    # ``base_delay`` and a ``jitter`` flag. The processor's
    # ``compute_backoff(job)`` helper must be reachable for testing.
    job = EmbeddingJob(
        chunk_id="chunk_fr76_jitter",
        knowledge_id="kb_fr76_jitter",
        content="jitter validation fixture",
        model="text-embedding-3-small",
        retry_count=attempt,
        max_retries=_FR76_MAX_RETRIES,
        base_delay=base_delay,
        jitter=expected_jitter,
    )

    # 2a. The job MUST declare jitter=True (default per SRS).
    actual_jitter = _read_jitter_flag(job)
    assert actual_jitter == expected_jitter, (
        f"FR-76 EmbeddingJob.jitter must be {expected_jitter}; "
        f"got {actual_jitter!r}"
    )

    # GREEN TODO: process_embedding_job (or a sibling helper) must
    # expose a pure ``compute_backoff`` so the test can draw the delay
    # without actually sleeping.
    compute_backoff = getattr(
        process_embedding_job, "compute_backoff", None
    )
    assert callable(compute_backoff), (
        "FR-76 process_embedding_job must expose a callable "
        "``compute_backoff(job, attempt) -> float`` so tests can "
        "inspect the chosen delay without sleeping"
    )

    # 2b. Draw the delay multiple times; with jitter=True the draws
    # must NOT all be identical.
    draws = [float(compute_backoff(job, attempt)) for _ in range(20)]

    # SRS-mandated window: [base * 2**a * 0.5, base * 2**a * 1.0]
    # = [4.0 * 0.5, 4.0 * 1.0] = [2.0s, 4.0s].
    raw = base_delay * (2 ** attempt)  # = 4.0
    lower_bound = raw * 0.5
    upper_bound = raw * 1.0
    for d in draws:
        assert lower_bound <= d <= upper_bound + 1e-9, (
            f"FR-76 backoff at attempt={attempt} base={base_delay} "
            f"jitter={expected_jitter} must lie in "
            f"[{lower_bound}s, {upper_bound}s]; got {d}s"
        )

    # 2c. Jitter MUST produce variation — at least two distinct values
    # in a 20-draw sample (probability of all-identical with uniform
    # [0.5, 1.0] over 20 draws is effectively zero, so a flat draw set
    # means jitter=False).
    distinct = len(set(round(d, 6) for d in draws))
    assert distinct >= 2, (
        f"FR-76 jitter=True must produce non-deterministic delays; "
        f"20 draws returned only {distinct} distinct value(s): {draws}"
    )


# ---------------------------------------------------------------------------
# 3. EmbeddingJob p95 completion time MUST be under 30s
#    (SRS FR-76: "p95 完成時間 < 30s").
#
# Spec input: job_type="embedding"; p95_limit_seconds="30".
# Test type: nfr_pattern.
#
# This is the load-bearing NFR for the search latency contract: Tier 2
# search MUST return the freshly-embedded chunk within the FR-77 2.5s
# window ONLY if the embedding pipeline finishes promptly. A p95 > 30s
# would breach the FR-73 knowledge-base freshness SLO.
#
# The test drives ``process_embedding_job`` over a batch of jobs (with
# real network I/O stubbed via the autouse fixture) and asserts the
# p95 latency stays below the SRS-pinned 30s limit.
# ---------------------------------------------------------------------------
def test_fr76_p95_under_30s():
    job_type = "embedding"
    p95_limit_seconds = _FR76_P95_LIMIT_SECONDS
    sample_size = 50

    # Build a representative batch — GREEN must stamp each job with
    # ``job_type`` (or equivalent discriminator) so the processor can
    # route it correctly.
    jobs = [
        EmbeddingJob(
            chunk_id=f"chunk_fr76_p95_{i}",
            knowledge_id=f"kb_fr76_p95_{i}",
            content=f"p95 fixture #{i}",
            model="text-embedding-3-small",
            retry_count=0,
            max_retries=_FR76_MAX_RETRIES,
        )
        for i in range(sample_size)
    ]

    # The job_type field MUST round-trip through the dataclass so the
    # test can confirm the FR-76 dispatcher routes embedding jobs
    # through the correct processor path.
    assert getattr(jobs[0], "job_type", job_type) in (job_type, None), (
        f"FR-76 job_type must be {job_type!r} (or absent if the "
        f"processor infers it from the EmbeddingJob class)"
    )

    # GREEN TODO: process_embedding_job must (a) accept an EmbeddingJob,
    # (b) return a non-None result, (c) expose a wall-clock duration
    # (``duration_seconds`` or ``elapsed``) so the test can compute
    # the p95 without re-implementing the timer.
    durations: list[float] = []
    for job in jobs:
        result = process_embedding_job(job)
        assert result is not None, (
            f"FR-76 process_embedding_job({job.chunk_id}) returned "
            f"None; embedding jobs must always return a result"
        )
        d = _read_duration(result)
        assert d is not None, (
            f"FR-76 result for {job.chunk_id} must expose a duration "
            f"(e.g. ``duration_seconds``); got {result!r}"
        )
        durations.append(float(d))

    # Compute p95 — the SRS-mandated SLO is that this value must
    # stay under 30s.
    durations.sort()
    p95_index = max(0, int(round(0.95 * (len(durations) - 1))))
    p95 = durations[p95_index]

    assert p95 < p95_limit_seconds, (
        f"FR-76 {job_type} job p95 completion time must be "
        f"< {p95_limit_seconds}s; got p95={p95:.3f}s "
        f"(sample_size={sample_size}, max={durations[-1]:.3f}s)"
    )


# ---------------------------------------------------------------------------
# 4. When the SAQ queue reports ``status="unavailable"``, the EmbeddingJob
#    MUST be re-enqueued with exponential backoff + jitter (SRS FR-76:
#    "失敗後指數退避 + jitter re-enqueue").
#
# Spec input: queue_status="unavailable"; max_retries="3"; jitter="true".
# Test type: fault_injection.
#
# "Queue unavailable" is distinct from "embedding model returned an
# error" — it means the SAQ broker itself rejected the enqueue
# (Redis down, network partition, etc.). The processor MUST treat this
# as a transient failure and schedule a retry with backoff, NOT
# silently drop the job (which would leave the knowledge-base row
# stuck at 🟡 forever, FR-79).
#
# The test injects ``queue_status="unavailable"`` into the processor
# and asserts the retry decision is True AND the chosen backoff lies
# within the jittered exponential window.
# ---------------------------------------------------------------------------
def test_fr76_queue_unavailable_job_retried_with_backoff():
    queue_status = "unavailable"
    max_retries = _FR76_MAX_RETRIES
    jitter = True

    job = EmbeddingJob(
        chunk_id="chunk_fr76_queue_down",
        knowledge_id="kb_fr76_queue_down",
        content="queue-unavailable fixture",
        model="text-embedding-3-small",
        retry_count=0,  # first attempt
        max_retries=max_retries,
        jitter=jitter,
    )

    # GREEN TODO: process_embedding_job must accept (or read from a
    # context) a ``queue_status`` parameter so the test can simulate
    # a downed broker. Acceptable shapes:
    #   (a) process_embedding_job(job, queue_status=queue_status)
    #   (b) process_embedding_job(job, *, broker=StubBroker(status=queue_status))
    result = process_embedding_job(job, queue_status=queue_status)

    # Spec fr76-ok-style sanity: result must not be None.
    assert result is not None, (
        f"FR-76 process_embedding_job must return a non-None result "
        f"even when queue_status={queue_status!r}"
    )

    # The job MUST be flagged for retry — queue unavailable is a
    # transient failure, not a permanent one.
    actual_retried = _read_retry_decision(result)
    assert actual_retried is True, (
        f"FR-76 queue_status={queue_status!r} with "
        f"retry_count=0 < max_retries={max_retries}: job MUST be "
        f"re-enqueued (expected retried=True); got "
        f"retried={actual_retried!r}"
    )

    # The chosen backoff MUST lie within the jittered exponential
    # window for attempt=0 with base_delay=1.0s: raw = 1.0 * 2**0 =
    # 1.0s; jittered range = [0.5s, 1.0s].
    backoff = _read_backoff(result)
    assert backoff is not None, (
        "FR-76 result must expose the chosen backoff (e.g. "
        "``backoff_seconds``) when a retry is scheduled"
    )
    base_delay = _FR76_BASE_DELAY
    attempt = 0
    raw = base_delay * (2 ** attempt)  # 1.0s
    lower_bound = raw * 0.5  # 0.5s
    upper_bound = raw * 1.0  # 1.0s
    assert lower_bound <= float(backoff) <= upper_bound + 1e-9, (
        f"FR-76 backoff at attempt={attempt} base={base_delay} "
        f"jitter={jitter} must lie in [{lower_bound}s, {upper_bound}s]; "
        f"got {backoff}s"
    )

    # Defensive: jitter=True means the chosen backoff is a sample
    # from the window — accept the value but require it is
    # strictly > 0 so the retry is actually delayed.
    assert float(backoff) > 0.0, (
        f"FR-76 backoff must be positive (jitter={jitter}); "
        f"got {backoff}s"
    )


# ---------------------------------------------------------------------------
# Helpers — tolerate multiple GREEN implementations for the result shape.
# Each helper accepts the most likely attribute names; if NONE match,
# it returns ``None`` so the caller can produce a precise failure
# message rather than AttributeError.
# ---------------------------------------------------------------------------
def _read_retry_decision(result: object) -> object | None:
    """Return the retry decision from ``result`` regardless of shape.

    GREEN may model the result as a dataclass with ``retried`` /
    ``status`` / ``should_retry`` / ``action``. Accept any of them.
    """
    if result is None:
        return None
    # Boolean flags first — exact match wins.
    for attr in ("retried", "should_retry", "retry", "requeued"):
        val = getattr(result, attr, None)
        if isinstance(val, bool):
            return val
    # Status string fallback.
    status = getattr(result, "status", None)
    if isinstance(status, str):
        lowered = status.lower()
        if lowered in ("retrying", "requeued", "retry", "queued"):
            return True
        if lowered in ("failed", "completed", "done", "success"):
            return False
    # Dict-shaped result (in case GREEN uses a dict).
    if isinstance(result, dict):
        for key in ("retried", "should_retry", "retry", "requeued"):
            if key in result and isinstance(result[key], bool):
                return result[key]
        if "status" in result and isinstance(result["status"], str):
            s = result["status"].lower()
            if s in ("retrying", "requeued", "retry", "queued"):
                return True
            if s in ("failed", "completed", "done", "success"):
                return False
    return None


def _read_failure_flag(result: object) -> object | None:
    """Return True if ``result`` signals permanent failure, else None."""
    if result is None:
        return None
    if isinstance(result, dict):
        if "failed" in result:
            return bool(result["failed"])
        if "status" in result and isinstance(result["status"], str):
            return result["status"].lower() == "failed"
    status = getattr(result, "status", None)
    if isinstance(status, str):
        return status.lower() == "failed"
    failed = getattr(result, "failed", None)
    if isinstance(failed, bool):
        return failed
    return None


def _read_jitter_flag(job: object) -> object | None:
    """Return the jitter flag from ``job`` regardless of attribute name."""
    if job is None:
        return None
    for attr in ("jitter", "use_jitter", "with_jitter"):
        val = getattr(job, attr, None)
        if isinstance(val, bool):
            return val
    return getattr(job, "jitter", None)


def _read_duration(result: object) -> object | None:
    """Return the wall-clock duration of the job, in seconds."""
    if result is None:
        return None
    if isinstance(result, dict):
        for key in ("duration_seconds", "elapsed_seconds", "elapsed", "duration"):
            if key in result:
                return result[key]
    for attr in ("duration_seconds", "elapsed_seconds", "elapsed", "duration"):
        val = getattr(result, attr, None)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return val
    return None


def _read_backoff(result: object) -> object | None:
    """Return the scheduled backoff (seconds) from ``result``."""
    if result is None:
        return None
    if isinstance(result, dict):
        for key in ("backoff_seconds", "delay_seconds", "backoff", "delay"):
            if key in result:
                return result[key]
    for attr in ("backoff_seconds", "delay_seconds", "backoff", "delay"):
        val = getattr(result, attr, None)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return val
    return None
