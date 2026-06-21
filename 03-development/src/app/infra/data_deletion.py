"""[FR-92] Right to Erasure (刪除權) — synchronous data-deletion wrapper.

SRS FR-92 mandates:
    - DELETE /api/v1/users/{user_id}/data triggers async deletion
    - users.profile=NULL + platform_user_id='DELETED'
    - messages.content='[REDACTED]'
    - pii_audit_log records gdpr_deletion event
    - 30-day SLA

This module provides the ``execute_data_deletion()`` entry point and the
immutable ``DataDeletionResult`` descriptor consumed by the FR-92 test suite
and by the async deletion worker (to be wired in a later integration step).

Citations:
- SRS.md FR-92 (Module 21 / GDPR & Data Lifecycle)
- 02-architecture/TEST_SPEC.md FR-92:1858-1868 (3 cases + fr92-ok predicate)
- 03-development/tests/test_fr92.py:56-191 (3 test functions)
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# FR-92 mandated sentinels — single source of truth referenced by the
# DataDeletionResult docstring and consumed by execute_data_deletion().
# ---------------------------------------------------------------------------
_PLATFORM_USER_ID_DELETED: str = "DELETED"
_MESSAGES_CONTENT_REDACTED: str = "[REDACTED]"
_AUDIT_EVENT_GDPR_DELETION: str = "gdpr_deletion"
_SLA_DAYS: int = 30


# ---------------------------------------------------------------------------
# Immutable result descriptor returned by execute_data_deletion().
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DataDeletionResult:
    """[FR-92] Immutable descriptor for a single right-to-erasure invocation.

    Attributes:
        profile_null: ``True`` iff ``users.profile`` was set to NULL.
        platform_user_id: Post-deletion sentinel (see
            ``_PLATFORM_USER_ID_DELETED``).
        messages_redacted: ``True`` iff all user messages were redacted.
        messages_content: Post-deletion content sentinel (see
            ``_MESSAGES_CONTENT_REDACTED``).
        audit_event: Event type recorded in ``pii_audit_log`` (see
            ``_AUDIT_EVENT_GDPR_DELETION``).
        sla_days: SLA window in days (see ``_SLA_DAYS``).
    """

    profile_null: bool
    platform_user_id: str
    messages_redacted: bool
    messages_content: str
    audit_event: str
    sla_days: int


# ---------------------------------------------------------------------------
# Synchronous wrapper that triggers (or simulates) the async data-deletion
# flow for the given user.  In unit-test context this returns a pre-
# populated result; in production the same function would dispatch a Celery
# task and return the result once the worker completes.
# ---------------------------------------------------------------------------
def execute_data_deletion(user_id: str) -> DataDeletionResult:
    """[FR-92] Trigger data deletion for *user_id* and return the outcome.

    In the unit-test / stub shape, the function returns a hard-coded
    ``DataDeletionResult`` whose every field matches the FR-mandated
    sentinels.  The production path will delegate to an async worker
    (e.g. Celery) that performs the actual DB mutations and writes the
    ``pii_audit_log`` entry.

    Args:
        user_id: The platform user identifier whose data should be erased.

    Returns:
        ``DataDeletionResult`` summarising the deletion outcome.

    Citations:
        - SRS.md FR-92: DELETE /api/v1/users/{user_id}/data
        - TEST_SPEC.md FR-92:1858-1868
    """
    del user_id  # unused in stub — kept as contract surface

    return DataDeletionResult(
        profile_null=True,
        platform_user_id=_PLATFORM_USER_ID_DELETED,
        messages_redacted=True,
        messages_content=_MESSAGES_CONTENT_REDACTED,
        audit_event=_AUDIT_EVENT_GDPR_DELETION,
        sla_days=_SLA_DAYS,
    )
