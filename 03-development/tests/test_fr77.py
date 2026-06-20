"""TDD-RED: failing tests for FR-77 — Sync first chunk embedding.

Spec source: 02-architecture/TEST_SPEC.md (FR-77)
SRS source : SRS.md FR-77 (Module 16: Background Job System)

Acceptance criteria (from SRS FR-77):
    單筆知識新增時，第一個 chunk 同步生成 embedding
    （asyncio.wait_for timeout=2.0s）；超時 → 記錄 warning，
    fallback 全部走非同步. 單筆新增後 Tier 2 在 < 2.5s 內可搜尋到
    首 chunk；超時不阻斷主流程.

The two TEST_SPEC cases (function names MUST match exactly):
    1. test_fr77_first_chunk_searchable_within_25s
         Inputs: mode="single"; expected_searchable_after="2.5s"
         Type  : happy_path
    2. test_fr77_timeout_does_not_block_main_flow
         Inputs: embedding_timeout_ms="2000"; expected_fallback="async_queue"
         Type  : fault_injection

Sub-assertion (per TEST_SPEC):
    fr77-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import asyncio
import time

import pytest


# ---------------------------------------------------------------------------
# Test isolation — ``create_knowledge_with_chunks`` performs real DB writes
# (PostgreSQL) and a synchronous embedding API call wrapped in
# ``asyncio.wait_for`` (the SRS-mandated 2.0s timeout). Both side effects
# MUST be eliminated from unit tests so a test can fail only because the
# sync-first-chunk logic is missing, not because Postgres is unreachable
# or the OpenAI embedding endpoint timed out.
#
# GREEN contract for the create_knowledge_with_chunks module:
#   - ``app.infra.jobs`` MUST export ``create_knowledge_with_chunks``
#     as a coroutine that accepts a knowledge record (title, content,
#     optional chunks list, embedding model name) and returns a
#     structured ``CreateKnowledgeResult`` exposing:
#         knowledge_id : str
#         first_chunk_id : str
#         embedding_synced : bool       (True when first chunk's
#                                        embedding completed during the
#                                        sync window)
#         embedding_synced_at : datetime|None
#         fallback : str|None           (one of {"async_queue", None})
#         search_ready : bool           (mirrors FR-77 contract: when
#                                        True, Tier 2 search MUST be
#                                        able to return this chunk)
#         elapsed_seconds : float
#   - The function MUST call the embedding provider via
#     ``asyncio.wait_for(coro, timeout=EMBEDDING_TIMEOUT_S)`` where
#     ``EMBEDDING_TIMEOUT_S`` is a module-level constant pinned at
#     ``2.0`` (SRS line 175). On ``asyncio.TimeoutError`` the function
#     MUST log a warning and enqueue the chunk for async processing,
#     never raising back to the caller.
#   - The async enqueue MUST go through a stub-able hook
#     (``enqueue_embedding_job(job)`` or a class method) so the test
#     can verify the fallback path without booting SAQ.
#   - The DB session and the embedding provider MUST be injectable
#     (constructor arg or module-level patchable callable) so tests
#     can supply in-memory fakes.
#
# The autouse fixture below is a no-op during RED (the import below
# raises Collection Error before the fixture runs) and patches any
# real Postgres / OpenAI construction once GREEN has landed.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_kb_io(monkeypatch):
    """Prevent real Postgres / OpenAI I/O during FR-77 unit tests.

    ``create_knowledge_with_chunks`` will eventually write a
    ``knowledge_base`` row + child ``knowledge_chunks`` rows and call
    the OpenAI embedding API. Both MUST be replaceable with a stub so
    the test can never escape into a real socket. During RED the
    module is not yet defined; once GREEN lands, monkeypatch the DB
    session factory and the embedding coroutine here.
    """
    yield


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-77 (SRS.md line 175 + SAD §Module: jobs.py line 322) requires:
#
#   1. ``app.infra.jobs`` MUST export ``create_knowledge_with_chunks``
#      as an ``async def`` (or sync wrapper that internally awaits an
#      event loop) callable that:
#         (a) persists a ``knowledge_base`` row + at least one
#             ``knowledge_chunks`` row,
#         (b) synchronously embeds the FIRST chunk via
#             ``asyncio.wait_for(embed(...), timeout=2.0)``,
#         (c) on success marks ``first_chunk.embedding_synced_at``
#             and returns ``embedding_synced=True``,
#         (d) on ``asyncio.TimeoutError`` (or any embedding exception
#             whose wall-clock exceeds 2.0s) logs a warning, enqueues
#             the chunk for async processing, and returns
#             ``fallback="async_queue"`` WITHOUT raising.
#
#   2. The function MUST return a result that exposes
#      ``embedding_synced`` and ``fallback`` (or equivalent) so the
#      test can assert the FR-77 contract without parsing logs.
#
#   3. The synchronous window from "create_knowledge_with_chunks
#      returns" to "Tier 2 search returns this chunk" MUST be
#      < 2.5s. The test asserts this by reading
#      ``result.elapsed_seconds`` and comparing to a wall-clock
#      measurement.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because ``create_knowledge_with_chunks``
# is not yet defined in ``app.infra.jobs``. That is the valid RED
# signal — GREEN adds the coroutine.
# ---------------------------------------------------------------------------
from app.infra.jobs import create_knowledge_with_chunks  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Spec-pinned trigger values — keep these in lock-step with TEST_SPEC.md.
# A drift here (e.g. changing 2.5 -> 3.0) will silently break the
# spec-coverage check's exact-match lookup.
# ---------------------------------------------------------------------------
_FR77_SYNC_TIMEOUT_S: float = 2.0
_FR77_SEARCHABLE_WINDOW_S: float = 2.5
_FR77_FALLBACK_MODE: str = "async_queue"


# ---------------------------------------------------------------------------
# 1. Happy path — single-insert mode (mode="single") MUST result in
#    the first chunk being searchable within 2.5s
#    (SRS FR-77: "單筆新增後 Tier 2 在 < 2.5s 內可搜尋到首 chunk").
#
# Spec input: mode="single"; expected_searchable_after="2.5s".
# Spec sub-assertion: fr77-ok: result is not None.
# Test type: happy_path.
#
# The function performs:
#    (1) DB write of the knowledge_base + first chunk row,
#    (2) synchronous embedding call bounded by
#        ``asyncio.wait_for(timeout=2.0s)``,
#    (3) returns a structured result with ``search_ready=True`` and
#        ``elapsed_seconds < 2.5s``.
#
# The test drives the function in event-loop mode (it is an
# ``async def`` per SAD), then asserts the FR-77 2.5s SLO from a
# wall-clock measurement AND from the result's own ``elapsed_seconds``
# (defence-in-depth: a result that says "elapsed=10s" while the
# wall-clock says "0.05s" is a lie and must be caught).
# ---------------------------------------------------------------------------
def test_fr77_first_chunk_searchable_within_25s():
    mode = "single"
    expected_searchable_after_s = _FR77_SEARCHABLE_WINDOW_S

    knowledge_id = "kb_fr77_red_single"
    title = "sync-first-chunk happy path"
    content = "first chunk fixture — must be searchable within 2.5s"
    model = "text-embedding-3-small"

    # GREEN TODO: create_knowledge_with_chunks must be an async callable
    # accepting (knowledge_id, title, content, model=...) and returning
    # a CreateKnowledgeResult with ``search_ready`` and ``elapsed_seconds``
    # attributes. See app/infra/jobs.py.
    coro = create_knowledge_with_chunks(
        knowledge_id=knowledge_id,
        title=title,
        content=content,
        model=model,
        mode=mode,
    )

    t0 = time.monotonic()
    result = asyncio.run(coro)
    wall_elapsed = time.monotonic() - t0

    # Spec fr77-ok predicate 'result is not None' applies_to case 1.
    assert result is not None, (
        "fr77-ok predicate: create_knowledge_with_chunks must return "
        "a non-None result"
    )

    # The function MUST signal that the first chunk is searchable
    # (Tier 2 contract: search MUST be able to return it).
    # GREEN TODO: the result must expose ``search_ready`` (bool) or
    # ``embedding_synced`` (bool) so the test can pin the FR-77
    # "searchable" promise without parsing the chunk row directly.
    search_ready = _read_search_ready(result)
    assert search_ready is not None, (
        "FR-77 result must expose a ``search_ready`` (or "
        "``embedding_synced``) flag; got neither"
    )
    assert search_ready is True, (
        f"FR-77 mode={mode!r}: first chunk must be immediately "
        f"searchable; got search_ready={search_ready!r}"
    )

    # Self-reported elapsed time MUST stay under the 2.5s SLO. A
    # regression that performs the embedding asynchronously while
    # still reporting ``search_ready=True`` would silently break the
    # FR-77 freshness contract.
    elapsed = _read_elapsed_seconds(result)
    assert elapsed is not None, (
        "FR-77 result must expose ``elapsed_seconds`` so callers and "
        "tests can verify the <2.5s SLO"
    )
    assert float(elapsed) < expected_searchable_after_s, (
        f"FR-77 mode={mode!r}: first chunk must be searchable within "
        f"{expected_searchable_after_s}s; got elapsed_seconds="
        f"{elapsed}s"
    )

    # Defence-in-depth — wall-clock check. The self-reported
    # ``elapsed_seconds`` field could be forged; the wall-clock
    # value comes from outside the function and cannot be.
    assert wall_elapsed < expected_searchable_after_s, (
        f"FR-77 mode={mode!r}: wall-clock elapsed {wall_elapsed:.3f}s "
        f"exceeds the {expected_searchable_after_s}s SLO"
    )

    # In the happy path the synchronous window MUST succeed — the
    # function MUST NOT have fallen back to the async queue.
    fallback = _read_fallback(result)
    assert fallback in (None, "", "none"), (
        f"FR-77 mode={mode!r} happy path: first chunk embedded "
        f"synchronously; expected no fallback, got fallback="
        f"{fallback!r}"
    )

    # The result MUST identify the first chunk so the caller can
    # immediately schedule a Tier 2 search against it.
    first_chunk_id = _read_first_chunk_id(result)
    assert first_chunk_id, (
        "FR-77 result must expose ``first_chunk_id`` so the caller "
        "can drive a Tier 2 search without re-querying the DB"
    )


# ---------------------------------------------------------------------------
# 2. Fault injection — when the embedding provider exceeds the 2.0s
#    ``asyncio.wait_for`` budget, ``create_knowledge_with_chunks`` MUST
#    log a warning, enqueue the chunk for async processing, and return
#    a result with ``fallback="async_queue"`` WITHOUT raising
#    (SRS FR-77: "超時 → 記錄 warning，fallback 全部走非同步" +
#                "超時不阻斷主流程").
#
# Spec input: embedding_timeout_ms="2000"; expected_fallback="async_queue".
# Test type: fault_injection.
#
# The function MUST treat any embedding call whose wall-clock exceeds
# the SRS-pinned 2.0s ``asyncio.wait_for`` budget as a transient
# failure — it MUST NOT propagate the TimeoutError to the caller
# (which would break the main create-knowledge flow and leave the
# knowledge_base row in an inconsistent state). Instead, the function
# MUST mark the chunk for async processing and return
# ``fallback="async_queue"``.
#
# The test forces the embedding coroutine to sleep for longer than
# the 2.0s budget by monkeypatching the (yet-to-exist) internal
# ``_embed`` helper. During RED the import itself fails (Collection
# Error); during GREEN the autouse fixture + this monkeypatch will
# route the test through the timeout branch.
# ---------------------------------------------------------------------------
def test_fr77_timeout_does_not_block_main_flow(monkeypatch):
    embedding_timeout_ms = 2000
    expected_fallback = _FR77_FALLBACK_MODE

    knowledge_id = "kb_fr77_red_timeout"
    title = "sync-first-chunk timeout path"
    content = "first chunk fixture — embedding will time out"
    model = "text-embedding-3-small"

    # Force the (future) internal embedding coroutine to overshoot
    # the 2.0s ``asyncio.wait_for`` budget so the function exercises
    # the timeout branch. The sleep uses a value strictly greater
    # than 2.0s (e.g. 5.0s) so the timeout always fires regardless
    # of scheduler jitter.
    #
    # GREEN TODO: app.infra.jobs MUST expose an internal embed helper
    # (e.g. ``_embed_first_chunk(chunk)``) so the test can patch it.
    # Acceptable shapes:
    #   (a) module-level ``_embed_first_chunk`` coroutine function
    #   (b) a class method on an injected ``EmbeddingClient``
    #   (c) a hook passed as a constructor arg to the function
    # The test attempts the (a) shape first; GREEN may move it.
    sleep_seconds = (_FR77_SYNC_TIMEOUT_S + 3.0)  # 5.0s

    async def _slow_embed(*args, **kwargs):
        # Sleep well past the 2.0s budget so ``asyncio.wait_for`` is
        # guaranteed to raise ``TimeoutError``. The exception is the
        # trigger the function is contracted to handle gracefully.
        await asyncio.sleep(sleep_seconds)
        return [0.0] * 1536  # would-be embedding vector

    # Patch the (yet-to-exist) module attribute. If the attribute
    # does not exist (RED state), AttributeError propagates — the
    # import above will have already raised Collection Error first.
    try:
        monkeypatch.setattr(
            "app.infra.jobs._embed_first_chunk",
            _slow_embed,
            raising=False,
        )
    except Exception:
        # RED: module not importable; let the test fail at the
        # ``create_knowledge_with_chunks`` import above.
        pass

    # GREEN TODO: the function must invoke the embedding coroutine
    # via ``asyncio.wait_for(..., timeout=2.0)`` (the SRS-pinned
    # budget) and on ``asyncio.TimeoutError`` MUST return a result
    # with ``fallback=expected_fallback`` and MUST NOT raise.
    coro = create_knowledge_with_chunks(
        knowledge_id=knowledge_id,
        title=title,
        content=content,
        model=model,
        mode="single",
    )

    # The function MUST NOT raise — "超時不阻斷主流程". A regression
    # that lets ``asyncio.TimeoutError`` bubble up would block the
    # entire create-knowledge flow.
    try:
        t0 = time.monotonic()
        result = asyncio.run(coro)
        wall_elapsed = time.monotonic() - t0
    except asyncio.TimeoutError as exc:  # pragma: no cover - GREEN must avoid
        pytest.fail(
            f"FR-77: create_knowledge_with_chunks MUST NOT raise "
            f"asyncio.TimeoutError to the caller (got {exc!r})"
        )

    # Spec fr77-ok-style sanity: result must not be None.
    assert result is not None, (
        "FR-77: even on embedding timeout, "
        "create_knowledge_with_chunks must return a non-None result"
    )

    # The fallback mode MUST be the async queue.
    fallback = _read_fallback(result)
    assert fallback is not None, (
        "FR-77: result must expose ``fallback`` (e.g. via "
        "``result.fallback`` or ``result.mode``); got neither"
    )
    assert fallback == expected_fallback, (
        f"FR-77 embedding timeout at "
        f"embedding_timeout_ms={embedding_timeout_ms}: expected "
        f"fallback={expected_fallback!r}; got fallback={fallback!r}"
    )

    # search_ready MUST be False in the fallback path — the chunk
    # is NOT synchronously embedded, so a Tier 2 search would
    # return zero hits until the async job completes.
    search_ready = _read_search_ready(result)
    assert search_ready is not None, (
        "FR-77: result must expose ``search_ready`` even on the "
        "fallback path so callers can decide whether to refresh"
    )
    assert search_ready is False, (
        f"FR-77 fallback path: search_ready must be False (chunk "
        f"is not yet embedded); got search_ready={search_ready!r}"
    )

    # The 2.0s ``asyncio.wait_for`` budget MUST have fired — wall
    # clock MUST be < 5.0s (the overshoot), proving the function
    # did not actually sleep for the full 5.0s. We allow generous
    # slack for the asyncio loop teardown and the warning log,
    # but anything close to 5.0s means the timeout never fired.
    max_acceptable_wall_s = _FR77_SYNC_TIMEOUT_S + 2.0  # 4.0s
    assert wall_elapsed < max_acceptable_wall_s, (
        f"FR-77: asyncio.wait_for(timeout=2.0s) budget must trip "
        f"before the {sleep_seconds}s sleep finishes; got "
        f"wall_elapsed={wall_elapsed:.3f}s — the timeout branch "
        f"never fired"
    )


# ---------------------------------------------------------------------------
# Helpers — tolerate multiple GREEN implementations for the result shape.
# Each helper accepts the most likely attribute names; if NONE match,
# it returns ``None`` so the caller can produce a precise failure
# message rather than AttributeError.
# ---------------------------------------------------------------------------
def _read_search_ready(result: object) -> object | None:
    """Return the ``search_ready`` (or equivalent) flag from ``result``."""
    if result is None:
        return None
    for attr in ("search_ready", "is_searchable", "searchable", "first_chunk_searchable"):
        val = getattr(result, attr, None)
        if isinstance(val, bool):
            return val
    # embedding_synced is an acceptable proxy: when True the chunk
    # is searchable; when False the fallback path was taken.
    synced = getattr(result, "embedding_synced", None)
    if isinstance(synced, bool):
        return synced
    # Dict-shaped result (in case GREEN uses a dict).
    if isinstance(result, dict):
        for key in ("search_ready", "is_searchable", "searchable", "first_chunk_searchable"):
            if key in result and isinstance(result[key], bool):
                return result[key]
        if "embedding_synced" in result and isinstance(result["embedding_synced"], bool):
            return result["embedding_synced"]
    return None


def _read_fallback(result: object) -> object | None:
    """Return the fallback mode from ``result`` (e.g. ``"async_queue"``)."""
    if result is None:
        return None
    for attr in ("fallback", "fallback_mode", "mode", "embedding_mode"):
        val = getattr(result, attr, None)
        if isinstance(val, str):
            return val
    # Dict-shaped result.
    if isinstance(result, dict):
        for key in ("fallback", "fallback_mode", "mode", "embedding_mode"):
            if key in result and isinstance(result[key], str):
                return result[key]
    return None


def _read_elapsed_seconds(result: object) -> object | None:
    """Return the self-reported wall-clock duration of the create call."""
    if result is None:
        return None
    if isinstance(result, dict):
        for key in ("elapsed_seconds", "duration_seconds", "elapsed", "duration"):
            if key in result:
                return result[key]
    for attr in ("elapsed_seconds", "duration_seconds", "elapsed", "duration"):
        val = getattr(result, attr, None)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return val
    return None


def _read_first_chunk_id(result: object) -> object | None:
    """Return the first chunk id from ``result`` regardless of shape."""
    if result is None:
        return None
    for attr in ("first_chunk_id", "first_chunk", "chunk_id"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val:
            return val
    if isinstance(result, dict):
        for key in ("first_chunk_id", "first_chunk", "chunk_id"):
            if key in result and isinstance(result[key], str) and result[key]:
                return result[key]
    return None
