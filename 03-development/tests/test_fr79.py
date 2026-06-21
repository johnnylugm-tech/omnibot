"""TDD-RED: failing tests for FR-79 — Embedding sync status UI + embedding_synced_at.

Spec source: 02-architecture/TEST_SPEC.md (FR-79)
SRS source : SRS.md FR-79 (Module 16: Background Job System)

Acceptance criteria (from SRS FR-79):
    知識庫列表顯示 🟡同步中（x/n chunks 完成）/🟢已同步/🔴失敗；
    embedding_synced_at 欄位標記全部完成時間.
    UI 狀態標示正確；embedding_synced_at 在所有 chunks 完成後更新.

SAD module mapping: app.infra.jobs

The two TEST_SPEC cases (function names MUST match exactly):
    1. test_fr79_ui_shows_syncing_status
         Inputs: chunks_done="3"; chunks_total="10"; expected_status="syncing"
         Type  : happy_path
    2. test_fr79_embedding_synced_at_set_after_all_chunks
         Inputs: chunks_done="10"; chunks_total="10"; expected_field="embedding_synced_at"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr79-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Test isolation — embedding sync status may involve background job state
# tracked via Redis/DB. Both are real I/O and must NOT happen in unit tests.
#
# GREEN contract for the embedding sync status module (app.infra.jobs):
#   - The module MUST export an ``EmbeddingSyncStatus`` frozen dataclass
#     (frozen=True) with at minimum:
#         status             : Literal["syncing", "synced", "failed"]
#         chunks_done        : int
#         chunks_total       : int
#         embedding_synced_at : datetime | None   (set only when all chunks done)
#
#   - The module MUST export ``compute_sync_status(chunks_done: int,
#     chunks_total: int) -> str`` that returns the status string
#     ("syncing" | "synced" | "failed") based on chunk progress.
#
#   - ``EmbeddingSyncStatus`` MUST compute ``embedding_synced_at``
#     automatically (via __post_init__ or property) when
#     chunks_done == chunks_total, or expose it as a required init param.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because ``app.infra.jobs`` is not yet
# defined. That is the valid RED signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.infra.jobs import (
    EmbeddingSyncStatus,
    compute_sync_status,
)

# ---------------------------------------------------------------------------
# Spec-pinned trigger values — keep these in lock-step with TEST_SPEC.md.
# A drift here (e.g. changing "syncing" -> "in_progress") will silently
# break the spec-coverage check's exact-match lookup.
# ---------------------------------------------------------------------------
_EXPECTED_STATUSES: tuple[str, ...] = ("syncing", "synced", "failed")


# ---------------------------------------------------------------------------
# 1. UI MUST show 🟡 "syncing" when embedding chunks are partially done
#    (SRS FR-79: "🟡同步中（x/n chunks 完成）").
#
# Spec input: chunks_done="3"; chunks_total="10"; expected_status="syncing".
# Spec sub-assertion: fr79-ok: result is not None.
# Test type: happy_path.
#
# A regression that returned "synced" before all chunks complete would
# cause the WebUI to show a green checkmark when chunks are still pending,
# misleading the admin into believing ingestion is done. A regression
# that returned "failed" for a partial-sync knowledge base would block
# the admin from seeing real progress and could prevent the retry
# trigger from being shown.
# ---------------------------------------------------------------------------
def test_fr79_ui_shows_syncing_status():
    chunks_done = 3
    chunks_total = 10
    expected_status = "syncing"

    # GREEN TODO: app.infra.jobs must export compute_sync_status()
    # that accepts (chunks_done, chunks_total) and returns the
    # status string: "syncing" | "synced" | "failed".
    # GREEN TODO: app.infra.jobs must export EmbeddingSyncStatus
    # as a frozen dataclass with fields: status, chunks_done,
    # chunks_total, embedding_synced_at.
    status = compute_sync_status(chunks_done, chunks_total)

    # Spec fr79-ok predicate: result is not None (applies_to case 1).
    result = status
    assert result is not None, "fr79-ok predicate: compute_sync_status result must not be None"

    # Chunks partially done (3/10) -> MUST be "syncing".
    assert status == expected_status, (
        f"FR-79 partial sync ({chunks_done}/{chunks_total}) must show "
        f"{expected_status!r} status; got {status!r}"
    )

    # White-box: status MUST be one of the three valid statuses.
    assert status in _EXPECTED_STATUSES, (
        f"FR-79 status {status!r} must be one of "
        f"{_EXPECTED_STATUSES}"
    )

    # Cross-check: EmbeddingSyncStatus dataclass must exist and hold
    # the same status value for the same inputs.
    # GREEN TODO: EmbeddingSyncStatus(chunks_done=3, chunks_total=10)
    # -> status == "syncing", embedding_synced_at is None.
    sync = EmbeddingSyncStatus(chunks_done=chunks_done, chunks_total=chunks_total)
    sync_result = sync
    assert sync_result is not None, "fr79-ok predicate: EmbeddingSyncStatus must not be None"
    assert sync.status == expected_status, (
        f"FR-79 EmbeddingSyncStatus.status for "
        f"({chunks_done}/{chunks_total}) must be "
        f"{expected_status!r}; got {sync.status!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``embedding_synced_at`` MUST be set (non-None) once all chunks
#    have completed embedding (SRS FR-79: "embedding_synced_at 欄位標記
#    全部完成時間").
#
# Spec input: chunks_done="10"; chunks_total="10";
#             expected_field="embedding_synced_at".
# Test type: validation.
#
# A regression that left ``embedding_synced_at`` as None after all chunks
# completed would prevent the Prometheus metric
# ``knowledge_hit_total`` (FR-71 metric #4) from correctly tagging
# sync-age buckets, and would make the pipeline replay logic in FR-81
# unable to distinguish a fresh-sync KB from a stale one. A regression
# that set it to a falsy-but-not-None value (e.g. 0 or "") would break
# FR-77's searchable-within-2.5s warranty because the freshness check
# would get a false positive.
# ---------------------------------------------------------------------------
def test_fr79_embedding_synced_at_set_after_all_chunks():
    chunks_done = 10
    chunks_total = 10
    expected_status = "synced"
    expected_field = "embedding_synced_at"

    # GREEN TODO: compute_sync_status(chunks_done, chunks_total) must
    # return "synced" when chunks_done == chunks_total.
    status = compute_sync_status(chunks_done, chunks_total)

    assert status == expected_status, (
        f"FR-79 full sync ({chunks_done}/{chunks_total}) must show "
        f"{expected_status!r} status; got {status!r}"
    )

    # Core assertion: EmbeddingSyncStatus.embedding_synced_at MUST be
    # non-None when ALL chunks are done.
    # GREEN TODO: EmbeddingSyncStatus.__post_init__ (or a property)
    # MUST auto-set embedding_synced_at to datetime.now(timezone.utc) when
    # chunks_done == chunks_total, or accept it as a required arg
    # when status is "synced".
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    sync = EmbeddingSyncStatus(
        chunks_done=chunks_done,
        chunks_total=chunks_total,
        embedding_synced_at=now,
    )

    # The field MUST exist (getattr succeeds).
    actual_field_value = getattr(sync, expected_field, None)
    assert actual_field_value is not None, (
        f"FR-79 {expected_field} must be set (non-None) when "
        f"all chunks are complete ({chunks_done}/{chunks_total}); "
        f"got None"
    )

    # The timestamp MUST be a valid datetime.
    assert isinstance(actual_field_value, _dt.datetime), (
        f"FR-79 {expected_field} must be a datetime; "
        f"got {type(actual_field_value).__name__}"
    )

    # Timezone-awareness guard — UTC timestamps only.
    if actual_field_value.tzinfo is not None:
        assert actual_field_value.tzinfo == _dt.UTC, (
            f"FR-79 {expected_field} must be UTC; "
            f"got tzinfo={actual_field_value.tzinfo}"
        )

    # EmbeddingSyncStatus.status MUST be "synced" when all chunks are done.
    assert sync.status == "synced", (
        f"FR-79 EmbeddingSyncStatus.status for (10/10) must be "
        f"'synced'; got {sync.status!r}"
    )

    # Cross-check: a partial sync MUST leave embedding_synced_at as None.
    partial_sync = EmbeddingSyncStatus(chunks_done=3, chunks_total=10)
    assert getattr(partial_sync, expected_field, None) is None, (
        f"FR-79 {expected_field} must be None when chunks are "
        f"still syncing (3/10)"
    )
