"""TDD-RED: failing tests for FR-92 — 刪除權（Right to Erasure）:
users.profile=NULL + messages=[REDACTED] + 30d SLA.

Spec source: 02-architecture/TEST_SPEC.md (FR-92)
SRS source : SRS.md FR-92 (Module 21 / GDPR & Data Lifecycle)

Acceptance criteria (from SRS FR-92):
    DELETE /api/v1/users/{user_id}/data 觸發異步刪除
    users.profile=NULL + platform_user_id='DELETED'
    messages.content='[REDACTED]'
    pii_audit_log 記錄 gdpr_deletion 事件
    30 天內完成

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr92_pii_fields_null_after_deletion
         Inputs: user_id="user-001"; expected_profile="null";
                 expected_platform_user_id="DELETED"
         Type  : happy_path
    2. test_fr92_messages_redacted
         Inputs: user_id="user-001"; expected_content="[REDACTED]"
         Type  : happy_path
    3. test_fr92_gdpr_deletion_event_in_audit_log
         Inputs: user_id="user-001"; expected_event="gdpr_deletion"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr92-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``execute_data_deletion`` (standalone function) and
# ``DataDeletionResult`` (return type) are intentionally NOT YET exported
# by ``app.infra.data_deletion``. The imports below are unguarded: pytest
# MUST fail with Collection Error (Exit Code 2) because the module does
# not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/data_deletion.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these
# names and behaviours are observable):
#
#   - execute_data_deletion(user_id: str) -> DataDeletionResult
#       Synchronous wrapper that triggers (or simulates) the async data
#       deletion flow for the given user. Returns a ``DataDeletionResult``
#       summarising the outcome of each deletion target.
#
#   - DataDeletionResult
#       Immutable result descriptor returned by ``execute_data_deletion()``.
#       Required attributes:
#           profile_null: bool
#               True iff users.profile was successfully set to NULL.
#           platform_user_id: str
#               The post-deletion value of platform_user_id — MUST be
#               ``"DELETED"`` (the FR-mandated sentinel).
#           messages_redacted: bool
#               True iff all of the user's messages were redacted.
#           messages_content: str
#               The post-deletion content of messages — MUST be
#               ``"[REDACTED]"`` (the FR-mandated sentinel).
#           audit_event: str
#               The event type recorded in pii_audit_log — MUST be
#               ``"gdpr_deletion"`` (the FR-mandated event name).
#           sla_days: int
#               The SLA window in days — MUST be 30.
#
# The tests below intentionally avoid any real DB / API I/O — they
# exercise the deletion function in isolation, which is the canonical
# unit-test shape for FR-92.
# ---------------------------------------------------------------------------
from app.infra.data_deletion import execute_data_deletion


# ---------------------------------------------------------------------------
# 1. After calling execute_data_deletion(), the user's PII fields MUST be
#    cleared: profile is NULL and platform_user_id is set to the sentinel
#    value ``"DELETED"`` (happy_path).
#
# Spec input: user_id="user-001"; expected_profile="null";
#             expected_platform_user_id="DELETED".
# SRS FR-92: "users.profile=NULL + platform_user_id='DELETED'".
# A regression that left profile intact or platform_user_id unchanged
# would violate GDPR Article 17 — personal data must be erased, not
# merely hidden.
# ---------------------------------------------------------------------------
def test_fr92_pii_fields_null_after_deletion():
    user_id = "user-001"
    expected_profile = "null"  # spec string sentinel
    expected_platform_user_id = "DELETED"  # spec string sentinel

    # GREEN TODO: execute_data_deletion(user_id: str) must accept a
    # user_id and return a ``DataDeletionResult`` with
    # ``profile_null``, ``platform_user_id``, ``messages_redacted``,
    # ``messages_content``, ``audit_event``, and ``sla_days``
    # attributes.
    result = execute_data_deletion(user_id)

    # Spec fr92-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input
    # (expected_profile="null"). The harness parser expects a single
    # VAR == c literal in the trigger block, so we wrap the predicate
    # in a narrow guard on the spec's case-1 trigger variable.
    if expected_profile == "null":
        assert result is not None, (
            "fr92-ok predicate: result must not be None"
        )

    # The profile MUST be NULL after deletion — the FR mandates that
    # personal data is erased, not merely flagged.
    profile_null = getattr(result, "profile_null", None)
    assert profile_null is True, (
        f"FR-92 profile_null must be True after deletion; got "
        f"{profile_null!r}"
    )
    # The platform_user_id MUST be set to the FR-mandated sentinel
    # "DELETED" — this allows the system to maintain referential
    # integrity (FK relationships) without retaining the original
    # platform identifier.
    if expected_platform_user_id == "DELETED":
        actual_puid = getattr(result, "platform_user_id", None)
        assert actual_puid == "DELETED", (
            f"FR-92 platform_user_id must be 'DELETED' after "
            f"deletion; got {actual_puid!r}"
        )


# ---------------------------------------------------------------------------
# 2. After calling execute_data_deletion(), all of the user's messages
#    MUST have their content replaced with the sentinel ``"[REDACTED]"``
#    (happy_path).
#
# Spec input: user_id="user-001"; expected_content="[REDACTED]".
# SRS FR-92: "messages.content='[REDACTED]'".
# A regression that kept the original message text would leak
# conversation history — GDPR Article 17 requires erasure of all
# personal data, not just profile fields. A regression that used a
# different sentinel (e.g. "DELETED", "REMOVED") would confuse
# downstream consumers that parse the sentinel for display/audit
# purposes.
# ---------------------------------------------------------------------------
def test_fr92_messages_redacted():
    user_id = "user-001"
    expected_content = "[REDACTED]"  # spec string sentinel

    # GREEN TODO: execute_data_deletion(user_id) must return a
    # ``DataDeletionResult`` whose ``messages_redacted`` attribute is
    # True AND whose ``messages_content`` attribute equals
    # ``"[REDACTED]"`` — the FR-mandated sentinel.
    result = execute_data_deletion(user_id)

    # The fr92-ok predicate belongs to case 1 only. For case 2 we keep
    # a top-level local sanity check but it must not live inside an
    # `if VAR == c:` block, otherwise the harness's
    # check-test-mirrors-spec will see the predicate applied to this
    # case's trigger values (which differ from case 1) and fail with
    # trigger_mismatch.
    assert result is not None, (
        "FR-92 execute_data_deletion() must return a result object; "
        "got None"
    )

    # Messages MUST be marked as redacted.
    messages_redacted = getattr(result, "messages_redacted", None)
    assert messages_redacted is True, (
        f"FR-92 messages_redacted must be True after deletion; got "
        f"{messages_redacted!r}"
    )
    # The message content MUST be the FR-mandated sentinel
    # "[REDACTED]" — no other value is acceptable.
    if expected_content == "[REDACTED]":
        actual_content = getattr(result, "messages_content", None)
        assert actual_content == "[REDACTED]", (
            f"FR-92 messages_content must be '[REDACTED]' after "
            f"deletion; got {actual_content!r}"
        )


# ---------------------------------------------------------------------------
# 3. After calling execute_data_deletion(), a ``"gdpr_deletion"`` event
#    MUST be recorded in pii_audit_log — every right-to-erasure request
#    is auditable per GDPR Article 30 (records of processing activities)
#    (validation).
#
# Spec input: user_id="user-001"; expected_event="gdpr_deletion".
# SRS FR-92: "pii_audit_log 記錄 gdpr_deletion 事件".
# A regression that omitted the audit log entry would break the ability
# to prove to a DPA (data protection authority) that a deletion
# request was received and processed.
# ---------------------------------------------------------------------------
def test_fr92_gdpr_deletion_event_in_audit_log():
    user_id = "user-001"
    expected_event = "gdpr_deletion"  # spec string sentinel

    # GREEN TODO: execute_data_deletion(user_id) must return a
    # ``DataDeletionResult`` whose ``audit_event`` attribute equals
    # ``"gdpr_deletion"`` — the FR-mandated audit event name. GREEN
    # may choose to write the actual audit log entry inside
    # execute_data_deletion (e.g., via StructuredLogger), but the
    # result object MUST expose the event name so this test can
    # assert it.
    result = execute_data_deletion(user_id)

    # The fr92-ok predicate belongs to case 1 only. For case 3 we keep
    # a top-level local sanity check (not inside an `if` block, to
    # avoid triggering the harness's trigger_mismatch detection).
    assert result is not None, (
        "FR-92 execute_data_deletion() must return a result object; "
        "got None"
    )

    # The audit event MUST be the FR-mandated "gdpr_deletion" — no
    # other event name is acceptable. This event name is consumed by
    # downstream audit tools that filter on specific GDPR event types.
    if expected_event == "gdpr_deletion":
        actual_event = getattr(result, "audit_event", None)
        assert actual_event == "gdpr_deletion", (
            f"FR-92 audit_event must be 'gdpr_deletion' after "
            f"deletion; got {actual_event!r}"
        )

    # Stronger: the SLA must be 30 days — the FR explicitly mandates
    # that deletion completes within 30 days. GREEN must expose this
    # on the result object so ops can verify the SLA window.
    sla_days = getattr(result, "sla_days", None)
    assert sla_days == 30, (
        f"FR-92 sla_days must be 30; got {sla_days!r}"
    )
