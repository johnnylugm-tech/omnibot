"""TDD-RED: failing tests for FR-78 — Batch import mode.

Spec source: 02-architecture/TEST_SPEC.md (FR-78)
SRS source : SRS.md FR-78 (Module 16: Background Job System)
SAD source : SAD.md § app.infra.jobs → FR-78

Acceptance criteria (from SRS FR-78):
    is_batch=True → 所有 chunks 全部非同步排入 SAQ
    （不等待同步首 chunk）；per entry 延遲 < 50ms

The two TEST_SPEC cases (function names MUST match exactly):
    1. test_fr78_batch_mode_skips_sync_wait
         Inputs: is_batch="true"; entry_count="11"; expected_sync_wait="false"
         Type  : happy_path
    2. test_fr78_per_entry_under_50ms
         Inputs: entry_count="100"; expected_per_entry_ms="50"
         Type  : nfr_pattern

Sub-assertion (per TEST_SPEC):
    fr78-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Test isolation — ``batch_import_knowledge`` performs real DB writes
# (PostgreSQL) and enqueues jobs to SAQ (Redis). Both side-effects MUST
# be eliminated from unit tests so a test can fail only because the
# batch-import logic is missing, not because Postgres is unreachable
# or Redis is down.
#
# GREEN contract for the batch_import_knowledge module:
#   - ``app.infra.jobs`` MUST export ``batch_import_knowledge``
#     as a callable (async or sync) that accepts a list of knowledge
#     entry dicts (each with title, content, model) and a boolean
#     ``is_batch`` flag, and returns a structured
#     ``BatchImportResult`` exposing:
#         entry_count    : int      (entries processed)
#         enqueued_count : int      (chunks enqueued to SAQ)
#         sync_wait      : bool     (MUST be False when is_batch=True)
#         per_entry_ms   : float    (wall-clock duration / entry_count)
#   - When ``is_batch=True`` and entry_count > 10, the function MUST
#     NOT perform a synchronous embedding wait for the first chunk
#     (contrast FR-77 single-entry mode).
#   - The DB session and the SAQ enqueue hook MUST be injectable
#     (constructor arg or module-level patchable callable) so tests
#     can supply in-memory fakes.
#
# The autouse fixture below is a no-op during RED (the import below
# raises Collection Error before the fixture runs) and patches any
# real Postgres / Redis construction once GREEN has landed.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_batch_io(monkeypatch):
    """Prevent real Postgres / SAQ I/O during FR-78 unit tests.

    ``batch_import_knowledge`` will eventually write knowledge_base
    rows + knowledge_chunks rows and enqueue EmbeddingJob entries
    via SAQ. Both MUST be replaceable with a stub so the test can
    never escape into a real socket. During RED the module is not
    yet defined; once GREEN lands, monkeypatch the DB session factory
    and the SAQ enqueue callable here.
    """
    yield


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-78 (SRS.md line 176 + SAD line 323) requires:
#
#   1. ``app.infra.jobs`` MUST export ``batch_import_knowledge``
#      as a callable that accepts:
#         entries   : list[dict]   (each with title, content, model)
#         is_batch  : bool         (True → skip sync embedding wait)
#
#   2. The function MUST return a ``BatchImportResult`` exposing:
#         entry_count    : int    (entries processed)
#         enqueued_count : int    (chunks enqueued to SAQ)
#         sync_wait      : bool   (MUST be False when is_batch=True;
#                                  True only in FR-77 single-entry path)
#         per_entry_ms   : float  (wall-clock elapsed / entry_count)
#
#   3. When ``is_batch=True`` and entry_count > the SRS batch
#      threshold of 10, ALL chunks MUST be enqueued asynchronously
#      — NO ``asyncio.wait_for`` embedding call for the first chunk
#      (contrast FR-77 which does a synchronous 2.0s wait).
#
#   4. Per-entry processing latency MUST be < 50ms. With the sync
#      wait eliminated, overhead is dominated by the DB insert +
#      SAQ enqueue cost.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because ``batch_import_knowledge``
# is not yet defined in ``app.infra.jobs``. That is the valid RED
# signal — GREEN adds the callable.
# ---------------------------------------------------------------------------
from app.core.knowledge import batch_import_knowledge  # noqa: E402

# ---------------------------------------------------------------------------
# Spec-pinned trigger values — keep these in lock-step with TEST_SPEC.md.
# ---------------------------------------------------------------------------
_FR78_BATCH_THRESHOLD: int = 10  # SRS: > 10 entries → batch mode
_FR78_PER_ENTRY_MS_LIMIT: float = 50.0  # SRS SLA: per entry < 50ms


# ===================================================================
# 1. test_fr78_batch_mode_skips_sync_wait
# ===================================================================
# Spec input: is_batch="true"; entry_count="11"; expected_sync_wait="false".
# Spec sub-assertion: fr78-ok: result is not None (applies_to case 1).
# Test type: happy_path.
#
# This is the defining FR-78 contract: when is_batch=True with more than
# 10 entries, the function MUST enqueue all chunks asynchronously and
# MUST NOT block on a synchronous embedding call for the first chunk.
# That synchronous wait is exclusively the FR-77 single-entry path.
#
# The result MUST expose ``sync_wait=False`` so callers can distinguish
# batch mode from single-entry mode without inspecting internal state.
# ===================================================================
def test_fr78_batch_mode_skips_sync_wait():
    is_batch = True
    entry_count = 11
    expected_sync_wait = False

    # Build entries — each carries the minimum fields needed to create
    # a knowledge_base row + at least one chunk. The values are
    # deliberately lightweight so the test exercises the batch decision
    # logic, not I/O throughput.
    entries = [
        {
            "title": f"batch {i:03d}",
            "content": f"batch fixture #{i}",
            "model": "text-embedding-3-small",
        }
        for i in range(entry_count)
    ]

    # GREEN TODO: batch_import_knowledge(entries, is_batch=bool) -> BatchImportResult
    # Must accept an iterable of entry dicts and return a structured result
    # with at least ``sync_wait``, ``entry_count``, and ``enqueued_count``.
    # May be async (coroutine) or sync; the test handles both via the
    # _call helper.
    result = _call(batch_import_knowledge, entries, is_batch=is_batch)

    # Spec fr78-ok predicate 'result is not None' applies_to case 1.
    assert result is not None, (
        "fr78-ok predicate: batch_import_knowledge must return a "
        "non-None result"
    )

    # The result MUST confirm the entry count so callers can audit.
    actual_count = _read_entry_count(result)
    assert actual_count == entry_count, (
        f"FR-78 entry_count: expected {entry_count}, got {actual_count}"
    )

    # The critical FR-78 contract — batch mode MUST NOT perform a
    # synchronous embedding wait for the first chunk.
    sync_wait = _read_sync_wait(result)
    assert sync_wait is not None, (
        "FR-78 result must expose a ``sync_wait`` flag (bool) to "
        "distinguish batch mode from single-entry mode"
    )
    assert sync_wait == expected_sync_wait, (
        f"FR-78 is_batch={is_batch}: batch mode MUST skip synchronous "
        f"embedding wait (expected sync_wait={expected_sync_wait}); "
        f"got sync_wait={sync_wait}"
    )

    # All entries must be enqueued — batch mode MUST NOT silently drop
    # any chunk. At minimum one chunk per entry is enqueued.
    enqueued = _read_enqueued_count(result)
    assert enqueued is not None, (
        "FR-78 result must expose ``enqueued_count`` so callers can "
        "verify all chunks were scheduled"
    )
    assert enqueued >= entry_count, (
        f"FR-78: {entry_count} entries imported, at least {entry_count} "
        f"chunks must be enqueued; got enqueued_count={enqueued}"
    )


# ===================================================================
# 2. test_fr78_per_entry_under_50ms
# ===================================================================
# Spec input: entry_count="100"; expected_per_entry_ms="50".
# Test type: nfr_pattern (NP-06 latency SLA).
#
# The FR-78 batch SLA: each entry MUST be processed in < 50ms. Since
# is_batch=True eliminates the synchronous embedding wait, per-entry
# overhead is dominated by the DB insert + SAQ enqueue cost, both of
# which MUST stay well under 50ms even at modest batch sizes.
#
# The test measures wall-clock from the caller's perspective — a
# pure-Python timing with no external I/O thanks to the autouse
# isolation fixture — and divides by entry_count. The result's own
# ``per_entry_ms`` field (if exposed) is also cross-checked.
# ===================================================================
def test_fr78_per_entry_under_50ms():
    entry_count = 100
    expected_per_entry_ms = _FR78_PER_ENTRY_MS_LIMIT

    entries = [
        {
            "title": f"perf {i:03d}",
            "content": f"latency fixture #{i}",
            "model": "text-embedding-3-small",
        }
        for i in range(entry_count)
    ]

    # GREEN TODO: batch_import_knowledge(entries, is_batch=True) must
    # enqueue all chunks and return. All I/O is stubbed — the measured
    # wall-clock reflects pure enqueue logic overhead.
    t0 = time.monotonic()
    result = _call(batch_import_knowledge, entries, is_batch=True)
    wall_elapsed = time.monotonic() - t0

    assert result is not None, (
        "fr78-ok predicate: batch_import_knowledge must not return None"
    )

    wall_per_entry_ms = (wall_elapsed / entry_count) * 1000.0

    # Wall-clock per-entry MUST stay under the SRS 50ms SLA.
    assert wall_per_entry_ms < expected_per_entry_ms, (
        f"FR-78 per-entry latency must be < {expected_per_entry_ms}ms; "
        f"wall per_entry={wall_per_entry_ms:.2f}ms "
        f"(total={wall_elapsed*1000:.2f}ms / {entry_count} entries)"
    )

    # Self-reported per_entry_ms cross-check (if exposed by GREEN).
    reported_ms = _read_per_entry_ms(result)
    if reported_ms is not None:
        assert float(reported_ms) < expected_per_entry_ms, (
            f"FR-78 self-reported per_entry_ms={reported_ms}ms exceeds "
            f"the {expected_per_entry_ms}ms limit"
        )

    # Verify all entries accounted for (no silent data loss).
    enqueued = _read_enqueued_count(result)
    if enqueued is not None:
        assert enqueued >= entry_count, (
            f"FR-78 {entry_count} entries: at least {entry_count} "
            f"chunks must be enqueued; got enqueued_count={enqueued}"
        )


# ===================================================================
# Helpers — tolerate multiple GREEN implementations for result shape
# and callable flavour (async vs sync).
# ===================================================================

def _call(fn, entries, *, is_batch):
    """Invoke ``fn`` whether it is sync or async.

    During RED ``fn`` is undefined and the import above raises
    Collection Error. Once GREEN lands, this helper transparently
    awaits or calls as appropriate.
    """
    import asyncio
    import inspect

    # Async callable → run via asyncio.run() (matches FR-77 pattern).
    if inspect.iscoroutinefunction(fn):
        return asyncio.run(fn(entries, is_batch=is_batch))
    # Sync callable → direct invocation.
    return fn(entries, is_batch=is_batch)


def _read_sync_wait(result: object) -> object | None:
    """Return the ``sync_wait`` flag from ``result`` regardless of shape."""
    if result is None:
        return None
    for attr in ("sync_wait", "synchronous", "is_sync_wait", "sync_embedding"):
        val = getattr(result, attr, None)
        if isinstance(val, bool):
            return val
    if isinstance(result, dict):
        for key in ("sync_wait", "synchronous", "is_sync_wait", "sync_embedding"):
            if key in result and isinstance(result[key], bool):
                return result[key]
    return None


def _read_entry_count(result: object) -> object | None:
    """Return the number of entries processed."""
    if result is None:
        return None
    for attr in ("entry_count", "total_entries", "count", "processed"):
        val = getattr(result, attr, None)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    if isinstance(result, dict):
        for key in ("entry_count", "total_entries", "count", "processed"):
            if key in result and isinstance(result[key], int):
                return result[key]
    return None


def _read_enqueued_count(result: object) -> object | None:
    """Return the number of chunks enqueued to SAQ."""
    if result is None:
        return None
    for attr in ("enqueued_count", "enqueued", "jobs_enqueued", "queued"):
        val = getattr(result, attr, None)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    if isinstance(result, dict):
        for key in ("enqueued_count", "enqueued", "jobs_enqueued", "queued"):
            if key in result and isinstance(result[key], int):
                return result[key]
    return None


def _read_per_entry_ms(result: object) -> object | None:
    """Return the self-reported per-entry latency in milliseconds."""
    if result is None:
        return None
    for attr in ("per_entry_ms", "avg_latency_ms", "latency_ms",
                 "duration_per_entry"):
        val = getattr(result, attr, None)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return val
    if isinstance(result, dict):
        for key in ("per_entry_ms", "avg_latency_ms", "latency_ms",
                     "duration_per_entry"):
            if key in result and isinstance(result[key], (int, float)):
                return result[key]
    return None
