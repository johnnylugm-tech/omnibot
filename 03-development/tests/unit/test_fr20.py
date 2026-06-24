"""TDD-RED: failing tests for FR-20 — PII 稽核日誌 (pii_audit_log + 90天自動匿名化).

Spec source: 02-architecture/TEST_SPEC.md (FR-20)
SRS source : SRS.md FR-20

Acceptance criteria (from SRS FR-20):
    PII 稽核日誌：每次遮蔽事件寫入 pii_audit_log（conversation_id, mask_count,
    pii_types, action, performed_by）；保留 90 天後自動匿名化。

    pii_audit_log 寫入成功；90 天到期後 PII 欄位自動清除。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.

TEST_SPEC cases (02-architecture/TEST_SPEC.md:447-462):
    1. test_fr20_mask_event_writes_audit_log
       inputs: conversation_id="conv-001"; mask_count="2"
       type:   happy_path
       derivation: Q1
    2. test_fr20_audit_log_has_conversation_id
       inputs: log_entry="pii_audit"; expected_field="conversation_id"
       type:   validation
       derivation: Q2
    3. test_fr20_90day_anonymize_scheduled
       inputs: retention_days="90"; scheduled="true"
       type:   integration
       derivation: Q7/FR-91

Sub-assertion rule:
    fr20-ok: `result is not None` applies_to case 1.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Source under test — ``app.core.pii`` exists (FR-18 GREEN landed), but the
# FR-20 audit-log writer and the FR-91 90-day anonymization scheduler do NOT
# yet exist. The mask() call resolves, but the audit-log assertion below
# will fail with ModuleNotFoundError / AttributeError — that is the
# canonical RED signal for this step.
#
# GREEN must:
#
#   - Extend ``app/core/pii.py:PIIMasking.mask`` (or a sibling helper) so
#     that every successful mask call appends a structured record to the
#     in-memory audit log carrying at least:
#         conversation_id : str
#         mask_count      : int
#         pii_types       : tuple[str, ...]
#         action          : str  (e.g. "mask")
#         performed_by    : str  (role or service identifier)
#     and exposes a class-level accessor (e.g. ``PIIMasking.read_audit_log``
#     or a module-level ``pii_audit_log`` list) so the test can inspect the
#     captured entries without a real database connection.
#
#   - Add an ``app/infra/data_retention.py`` retention policy + scheduler
#     hook (or extend the existing module) that schedules anonymization of
#     the ``pii_audit_log`` at exactly 90 days. The scheduler MUST be
#     discoverable (e.g. ``RETENTION_POLICIES`` list / ``schedule_anonymize``
#     function) so the test can verify the configured horizon without
#     waiting on wall-clock time.
#
# Test isolation: audit-log inspection uses the in-memory accessor the
# GREEN agent is expected to expose — no DB, no HTTP. No autouse fixture
# is required; the collection-error / assertion-failure RED signal comes
# from the missing symbols.
# ---------------------------------------------------------------------------
from app.core.pii import PIIMasking


# ---------------------------------------------------------------------------
# Local stand-ins used by the test below. GREEN may swap these for the
# real dataclasses GREEN introduces inside ``app.core.pii`` /
# ``app.infra.data_retention``; the assertions below only check the SHAPE
# of the audit-log record (field names + types) and the SHAPE of the
# retention policy (retention_days == 90 + scheduled == True).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _AuditEntry:
    """Shape of a single pii_audit_log row captured by the GREEN writer."""

    conversation_id: str
    mask_count: int
    pii_types: tuple[str, ...]
    action: str
    performed_by: str


# ---------------------------------------------------------------------------
# 1. mask_event_writes_audit_log — every mask() call appends a record to
#    pii_audit_log carrying conversation_id + mask_count + pii_types.
#
# Spec input: conversation_id="conv-001"; mask_count="2".
#   SRS FR-20: "每次遮蔽事件寫入 pii_audit_log (conversation_id,
#   mask_count, pii_types, action, performed_by)".
#
# Why a side-effect on mask() rather than a separate hook:
#   The audit trail exists so a privacy officer (auditor role per FR-60)
#   can answer "which conversation triggered which PII scrub on which
#   shift". Forgetting to call the writer is a P0 compliance gap (台灣
#   個資法 §17; GDPR Art.30). The simplest enforcement is to make the
#   writer fire from inside mask() itself so any future caller path
#   automatically participates.
#
# The input text contains TWO PII substrings (a Taiwan phone and an
# email) so mask_count == 2 — a single-PII input would not exercise the
# counter the spec asks for.
# ---------------------------------------------------------------------------
def test_fr20_mask_event_writes_audit_log():
    conversation_id = "conv-001"
    mask_count = 2

    # Two PII substrings on purpose: phone (10-digit TW mobile) + email.
    # mask_count == 2 so the assertion targets the counter, not the
    # detection itself (FR-18 already covers detection; FR-20 cares about
    # the audit trail on the write path).
    text = "聯絡電話 0912345678 或 email user@example.com 謝謝"

    masker = PIIMasking()
    # GREEN TODO: PIIMasking.mask() must accept a ``conversation_id`` keyword
    # (and ideally ``performed_by``) so the audit record can be correlated
    # to the originating conversation. Signature:
    #   PIIMasking.mask(self, text: str, *, conversation_id: str,
    #                   performed_by: str = "system") -> MaskResult
    result = masker.mask(text, conversation_id=conversation_id)

    if conversation_id == "conv-001" and mask_count == 2:
        # Spec fr20-ok predicate: `result is not None` applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger values match TEST_SPEC case 1's inputs.
        assert result is not None, (
            "fr20-ok predicate: PIIMasking.mask() MUST return a non-None "
            "MaskResult on the happy path"
        )

    assert result.mask_count == mask_count, (
        f"expected mask_count={mask_count} for two PII substrings "
        f"(phone + email); got mask_count={result.mask_count!r}. FR-20 "
        f"requires the audit record to faithfully reflect the mask "
        f"counter from FR-18."
    )

    # GREEN TODO: PIIMasking must expose a class-level reader that returns
    # the in-memory pii_audit_log list (or comparable accessor). Signature:
    #   PIIMasking.read_audit_log() -> list[AuditEntry]
    audit_log = PIIMasking.read_audit_log()
    assert isinstance(audit_log, list) and len(audit_log) >= 1, (
        f"mask() MUST append a record to pii_audit_log (SRS FR-20: "
        f"'每次遮蔽事件寫入 pii_audit_log'); got audit_log={audit_log!r}"
    )

    entry = audit_log[-1]
    assert getattr(entry, "conversation_id", None) == conversation_id, (
        f"latest audit entry MUST carry conversation_id="
        f"{conversation_id!r} (SRS FR-20); got entry.conversation_id="
        f"{getattr(entry, 'conversation_id', None)!r}"
    )
    assert getattr(entry, "mask_count", None) == mask_count, (
        f"latest audit entry MUST carry mask_count={mask_count!r} "
        f"(SRS FR-20); got entry.mask_count="
        f"{getattr(entry, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 2. audit_log_has_conversation_id — the audit log entry MUST expose the
#    ``conversation_id`` field (Q2 validation rule: a record that cannot
#    be correlated to a conversation is useless for §30 GDPR / §17 個資法
#    reporting).
#
# Spec input: log_entry="pii_audit"; expected_field="conversation_id".
#
# Validation against the schema (FR-82 DDL: pii_audit_log contains a
# conversation_id column) is tested directly here via field introspection
# on the in-memory record; the GREEN writer MUST emit the field on every
# record or the privacy officer's audit query will silently drop the row.
# ---------------------------------------------------------------------------
def test_fr20_audit_log_has_conversation_id():
    log_entry = "pii_audit"
    expected_field = "conversation_id"

    masker = PIIMasking()
    # Emit at least one audit record so the reader has something to
    # inspect. The mask_count is irrelevant here — this case is purely
    # about the SHAPE of the record, not the counter.
    masker.mask(
        "我的電話是 0912345678",
        conversation_id="conv-field-check",
    )

    assert hasattr(PIIMasking, "read_audit_log"), (
        f"PIIMasking MUST expose a reader for the {log_entry!r} log "
        f"(SRS FR-20: '每次遮蔽事件寫入 pii_audit_log'); the absence of "
        f"`PIIMasking.read_audit_log` means the GREEN writer has not "
        f"landed yet."
    )

    audit_log = PIIMasking.read_audit_log()
    assert isinstance(audit_log, list) and len(audit_log) >= 1, (
        f"PIIMasking.read_audit_log() MUST return a non-empty list after "
        f"a mask() call (SRS FR-20); got {audit_log!r}"
    )

    entry = audit_log[-1]
    assert hasattr(entry, expected_field), (
        f"audit log entries MUST expose the {expected_field!r} field "
        f"(SRS FR-20: 'pii_audit_log (conversation_id, mask_count, "
        f"pii_types, action, performed_by)'); entry={entry!r}"
    )
    assert getattr(entry, expected_field), (
        f"audit log entry {log_entry!r} MUST carry a non-empty "
        f"{expected_field!r} value (privacy-officer audit correlation "
        f"depends on it); got entry.{expected_field}="
        f"{getattr(entry, expected_field, None)!r}"
    )


# ---------------------------------------------------------------------------
# 3. 90day_anonymize_scheduled — the retention scheduler MUST register a
#    policy that anonymizes pii_audit_log at exactly 90 days
#    (FR-91 data retention + FR-20 anonymization).
#
# Spec input: retention_days="90"; scheduled="true".
#
# Why anonymize (not delete) at 90 days:
#   Audit log rows are still needed for statistical reporting (PII masking
#   rate per platform, FR-105 ODD SQL summary) — so we strip the PII
#   payload but keep the row. FR-91 explicitly mandates this action.
#
# GREEN TODO: ``app.infra.data_retention`` (or sibling module) MUST expose
# either:
#   * a ``RETENTION_POLICIES`` list whose entries can be queried by
#     ``table_name == "pii_audit_log"``, OR
#   * a ``schedule_anonymize(table_name, retention_days)`` callable that
#     returns a registered policy descriptor.
# Whichever surface ships, this test MUST be able to assert
# ``retention_days == 90`` and ``scheduled is True`` without waiting on
# wall-clock time.
# ---------------------------------------------------------------------------
def test_fr20_90day_anonymize_scheduled():
    retention_days = 90
    scheduled = True

    # GREEN TODO: ``app.infra.data_retention`` must expose the FR-91 policy
    # table for inspection. Acceptable signatures:
    #   1. ``RETENTION_POLICIES`` — list[RetentionPolicy] where each policy
    #      has ``.table_name``, ``.retention_days``, ``.action`` fields.
    #   2. ``find_policy(table_name="pii_audit_log") -> RetentionPolicy|None``
    # The test below uses interface (1) — the GREEN agent may add either.
    from app.infra.security import RETENTION_POLICIES

    policies = RETENTION_POLICIES
    assert isinstance(policies, (list, tuple)), (
        f"RETENTION_POLICIES MUST be a list/tuple of policy descriptors "
        f"(SRS FR-91); got type={type(policies).__name__}"
    )

    pii_audit_policies = [
        p for p in policies
        if getattr(p, "table_name", None) == "pii_audit_log"
    ]
    assert pii_audit_policies, (
        "a retention policy for the pii_audit_log table MUST be "
        "registered (SRS FR-20 + FR-91); RETENTION_POLICIES does not "
        "contain an entry with table_name='pii_audit_log'."
    )

    policy = pii_audit_policies[0]
    assert getattr(policy, "retention_days", None) == retention_days, (
        f"pii_audit_log retention MUST be exactly {retention_days} days "
        f"(SRS FR-20: '保留 90 天後自動匿名化'); got policy.retention_days="
        f"{getattr(policy, 'retention_days', None)!r}"
    )
    assert getattr(policy, "action", None) == "anonymize", (
        f"pii_audit_log retention action MUST be 'anonymize' (SRS FR-91: "
        f"'PII 稽核日誌 90 天 → 自動匿名化'); got policy.action="
        f"{getattr(policy, 'action', None)!r}"
    )
    assert bool(getattr(policy, "scheduled", False)) is bool(scheduled), (
        f"pii_audit_log retention policy MUST be scheduled (SRS FR-20: "
        f"'保留 90 天後自動匿名化'); got policy.scheduled="
        f"{getattr(policy, 'scheduled', None)!r}, expected {scheduled!r}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in core/pii.py
# ---------------------------------------------------------------------------

def test_fr20_pii_masks_phone_number():
    """``PIIMasking.mask()`` MUST detect and mask Taiwan phone numbers
    (e.g. ``0912345678``) using the ``[phone_masked]`` token.
    Kills mutants #4–8 that wrap the phone regex string segments with
    ``XX…XX`` (the regex would no longer match real phone numbers).
    """
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    result = masker.mask("我的電話是 0912345678 請聯絡我")
    assert "[phone_masked]" in result.masked_text, (
        f"PII masker must mask Taiwan phone number 0912345678; "
        f"got masked_text={result.masked_text!r}"
    )
    assert result.mask_count >= 1


def test_fr20_pii_masks_email_address():
    """``PIIMasking.mask()`` MUST mask email addresses (RFC-ish pattern).
    Kills mutants wrapping the email regex with ``XX…XX``.
    """
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    result = masker.mask("聯絡我 test@example.com")
    assert "[email_masked]" in result.masked_text, (
        f"PII masker must mask email test@example.com; "
        f"got masked_text={result.masked_text!r}"
    )


def test_fr20_pii_masks_taiwan_address():
    """``PIIMasking.mask()`` MUST mask Taiwan addresses
    (e.g. ``台北市信義路100號``). Kills mutants #16-20 wrapping the
    address regex with ``XX…XX``.
    """
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    result = masker.mask("地址：台北市信義路100號")
    assert "[address_masked]" in result.masked_text, (
        f"PII masker must mask Taiwan address; "
        f"got masked_text={result.masked_text!r}"
    )


def test_fr20_pii_masks_credit_card():
    """``PIIMasking.mask()`` MUST mask 16-digit credit-card numbers.
    Kills mutant #12 wrapping the credit-card regex.
    """
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    result = masker.mask("卡號 4111111111111111 請記下")
    assert "[credit_card_masked]" in result.masked_text, (
        f"PII masker must mask 16-digit credit card; "
        f"got masked_text={result.masked_text!r}"
    )


def test_fr20_mask_formats_dict_has_phone_token():
    """``PIIMasking.MASK_FORMATS["phone"]`` MUST equal
    ``"[phone_masked]"`` (NOT ``"XX[phone_masked]XX"``).
    Kills mutant #28.
    """
    from app.core.pii import PIIMasking
    assert PIIMasking.MASK_FORMATS["phone"] == "[phone_masked]", (
        f"MASK_FORMATS['phone'] must be '[phone_masked]'; "
        f"got {PIIMasking.MASK_FORMATS['phone']!r}"
    )


def test_fr20_pii_masks_international_phone_with_country_code():
    r"""``PIIMasking.mask()`` MUST mask phone numbers with the ``+886``
    Taiwan country code. Kills mutant #4 which wraps the ``\+886`` regex
    segment with ``XX…XX``.
    """
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    result = masker.mask("來電 +886-2-2345-6789 請接")
    assert "[phone_masked]" in result.masked_text, (
        f"PII masker must mask +886 phone number; "
        f"got masked_text={result.masked_text!r}"
    )
