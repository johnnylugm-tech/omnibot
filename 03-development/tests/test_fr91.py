"""TDD-RED: failing tests for FR-91 — 資料保留政策 (180d 封存 / 2yr 刪除
/ 90d 匿名化 / 90d 情緒刪除).

Spec source: 02-architecture/TEST_SPEC.md (FR-91)
SRS source : SRS.md FR-91 (Module 21 / GDPR & Data Lifecycle)

Acceptance criteria (from SRS FR-91):
    conversations(messages) 180 天 → 封存 cold storage (Parquet/S3)
    封存後 2 年 → 永久刪除
    PII 稽核日誌 90 天 → 自動匿名化
    情緒歷史 90 天 → 刪除
    安全日誌 1 年 → 封存後 2 年刪除
    用戶回饋永久保留（已去識別化）

The four TEST_SPEC cases (function names MUST match exactly):
    1. test_fr91_180d_messages_archived
         Inputs: retention_days="180"; target="conversations";
                 expected_format="Parquet/S3"
         Type  : happy_path
    2. test_fr91_2yr_archive_deleted
         Inputs: archive_age_years="2"; expected_action="delete"
         Type  : happy_path
    3. test_fr91_pii_audit_90d_anonymized
         Inputs: retention_days="90"; table="pii_audit_log";
                 expected_action="anonymize"
         Type  : happy_path
    4. test_fr91_emotion_90d_deleted
         Inputs: retention_days="90"; table="emotion_history";
                 expected_action="delete"
         Type  : happy_path

Sub-assertion (per TEST_SPEC):
    fr91-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``MessagesRetentionPolicy`` /
# ``ArchiveRetentionPolicy`` / ``PiiAuditRetentionPolicy`` /
# ``EmotionHistoryRetentionPolicy`` are intentionally NOT YET exported by
# ``app.infra.data_retention``. The imports below are unguarded: pytest
# MUST fail with Collection Error (Exit Code 2) because the module does
# not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/data_retention.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these
# names and behaviours are observable):
#
#   - MessagesRetentionPolicy
#       Immutable descriptor for the 180-day messages-archive policy.
#       Required attributes:
#           retention_days: int        # 180
#           target: str                # "conversations"
#           archive_format: str        # "Parquet/S3"
#           archive_action: str        # "archive"  (i.e. NOT "delete")
#       Required methods:
#           should_archive(age_days: int) -> bool
#               Returns True iff the record's age exceeds retention_days.
#           archive_target() -> str
#               Returns the cold-storage target descriptor (e.g.
#               "s3://cold-storage/..." or simply "Parquet/S3"). The
#               FR only cares that the format family is Parquet/S3.
#
#   - ArchiveRetentionPolicy
#       Immutable descriptor for the 2-year archive deletion policy.
#       Required attributes:
#           archive_age_years: int     # 2
#           action: str                # "delete"
#
#   - PiiAuditRetentionPolicy
#       Immutable descriptor for the 90-day PII audit log policy.
#       Required attributes:
#           retention_days: int        # 90
#           table: str                 # "pii_audit_log"
#           action: str                # "anonymize"
#       Required methods:
#           action_for(age_days: int) -> str
#               Returns "anonymize" iff age_days >= retention_days;
#               returns "retain" otherwise.
#
#   - EmotionHistoryRetentionPolicy
#       Immutable descriptor for the 90-day emotion-history deletion
#       policy. Required attributes:
#           retention_days: int        # 90
#           table: str                 # "emotion_history"
#           action: str                # "delete"
#
# The tests below intentionally avoid any real DB / S3 / scheduler I/O —
# they exercise the policy objects in isolation, which is the canonical
# unit-test shape for FR-91.
# ---------------------------------------------------------------------------
from app.infra.data_retention import (
    ArchiveRetentionPolicy,
    EmotionHistoryRetentionPolicy,
    MessagesRetentionPolicy,
    PiiAuditRetentionPolicy,
)


# ---------------------------------------------------------------------------
# 1. conversations.messages are archived to cold storage (Parquet/S3) after
#    180 days (happy_path).
#
# Spec input: retention_days="180"; target="conversations";
#             expected_format="Parquet/S3".
# SRS FR-91: "conversations(messages) 180 天 → 封存 cold storage
#             (Parquet/S3)".
# A regression that picked a shorter retention horizon (e.g. 30/90 days)
# would balloon the hot-DB footprint; a regression that picked JSON/CSV
# would lose the columnar compression that makes cold-storage scans
# affordable.
# ---------------------------------------------------------------------------
def test_fr91_180d_messages_archived():
    retention_days = 180
    target = "conversations"
    expected_format = "Parquet/S3"  # spec string sentinel

    # GREEN TODO: MessagesRetentionPolicy must accept ``retention_days``,
    # ``target``, ``archive_format`` kwargs (or positional args) and
    # expose them as attributes. The class MUST also expose
    # ``should_archive(age_days) -> bool`` returning True iff
    # age_days >= retention_days, and ``archive_target() -> str``
    # returning the cold-storage descriptor in the "Parquet/S3" family.
    policy = MessagesRetentionPolicy(
        retention_days=retention_days,
        target=target,
        archive_format=expected_format,
        archive_action="archive",
    )
    result = policy  # so the spec's fr91-ok predicate ``result is not None``
                     # has a meaningful binding in this test.

    # Spec fr91-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input
    # (retention_days="180"). The harness parser expects a single
    # VAR == c literal in the trigger block, so we wrap the predicate
    # in a narrow guard on the spec's case-1 trigger variable.
    if retention_days == 180:
        assert result is not None, (
            "fr91-ok predicate: result must not be None"
        )

    # The retention horizon MUST be 180 days — the FR-mandated value.
    # A shorter cycle (e.g. 30 / 90) would prematurely archive
    # active conversations; a longer one (e.g. 365) would balloon
    # the hot-DB footprint and defeat the FR's intent.
    assert getattr(policy, "retention_days", None) == retention_days, (
        f"FR-91 messages retention_days must be {retention_days}; got "
        f"{getattr(policy, 'retention_days', None)!r}"
    )
    # The target MUST be the conversations table — the FR-mandated
    # source for messages.
    assert getattr(policy, "target", None) == target, (
        f"FR-91 messages target must be {target!r}; got "
        f"{getattr(policy, 'target', None)!r}"
    )
    # The archive format MUST be in the Parquet/S3 family — JSON/CSV
    # would lose columnar compression and fail the cold-storage
    # cost model.
    fmt_attr = getattr(policy, "archive_format", None)
    assert fmt_attr is not None, (
        "FR-91 MessagesRetentionPolicy must expose an "
        "``archive_format`` attribute"
    )
    if expected_format == "Parquet/S3":
        assert "Parquet" in str(fmt_attr) and "S3" in str(fmt_attr), (
            f"FR-91 messages archive_format must be in the "
            f"Parquet/S3 family; got {fmt_attr!r}"
        )

    # Stronger: ``should_archive(age)`` MUST return True iff the
    # record is at or beyond the 180-day horizon. This catches a
    # GREEN implementation that hard-codes the attribute but
    # forgets the gating logic that the scheduler actually consumes.
    should_archive = getattr(policy, "should_archive", None)
    assert callable(should_archive), (
        "FR-91 MessagesRetentionPolicy must expose "
        "``should_archive(age_days: int) -> bool``"
    )
    assert should_archive(retention_days) is True, (
        f"FR-91 should_archive({retention_days}) must return True "
        f"at-or-beyond the 180-day horizon"
    )
    assert should_archive(retention_days - 1) is False, (
        f"FR-91 should_archive({retention_days - 1}) must return "
        f"False one day before the horizon"
    )

    # Stronger: archive_target() MUST return a non-empty string in
    # the Parquet/S3 family. GREEN may also expose this via
    # ``archive_format`` — accept either spelling.
    archive_target = getattr(policy, "archive_target", None)
    target_str: str | None = None
    if callable(archive_target):
        target_str = archive_target()
    if target_str is None:
        target_str = str(fmt_attr)
    assert "Parquet" in target_str and "S3" in target_str, (
        f"FR-91 archive_target must be in the Parquet/S3 family; "
        f"got {target_str!r}"
    )


# ---------------------------------------------------------------------------
# 2. Archives that have aged 2 years are permanently deleted (happy_path).
#
# Spec input: archive_age_years="2"; expected_action="delete".
# SRS FR-91: "封存後 2 年永久刪除".
# A regression that used "anonymize" or "retain" here would
# permanently keep cold-storage growing without bound; "delete" is
# the only action that bounds the storage cost.
# ---------------------------------------------------------------------------
def test_fr91_2yr_archive_deleted():
    archive_age_years = 2
    expected_action = "delete"  # spec string sentinel

    # GREEN TODO: ArchiveRetentionPolicy must accept
    # ``archive_age_years`` and ``action`` kwargs (or positional args)
    # and expose them as attributes. The class MUST also expose
    # ``should_delete(age_years: int) -> bool`` returning True iff
    # age_years >= archive_age_years.
    policy = ArchiveRetentionPolicy(
        archive_age_years=archive_age_years,
        action=expected_action,
    )
    result = policy  # so the harness sees a bound ``result`` object

    # The fr91-ok predicate belongs to case 1 only. For case 2 we keep
    # a top-level local sanity check but it must not live inside an
    # `if VAR == c:` block, otherwise the harness's
    # check-test-mirrors-spec will see the predicate applied to this
    # case's trigger values (which differ from case 1) and fail with
    # trigger_mismatch.
    assert result is not None, (
        "FR-91 ArchiveRetentionPolicy() must return a policy object; "
        "got None"
    )

    # The archive-age horizon MUST be 2 years — the FR-mandated value.
    # A shorter horizon (e.g. 1 year) would force frequent re-archives
    # and lose audit continuity; a longer one (e.g. 7 years) would
    # silently violate the FR's storage-cost envelope.
    assert getattr(policy, "archive_age_years", None) == archive_age_years, (
        f"FR-91 archive_age_years must be {archive_age_years}; got "
        f"{getattr(policy, 'archive_age_years', None)!r}"
    )
    # The action MUST be "delete" — the FR explicitly forbids
    # indefinite retention of the archive.
    if expected_action == "delete":
        action_attr = getattr(policy, "action", None)
        assert action_attr == "delete", (
            f"FR-91 archive action must be 'delete'; got "
            f"{action_attr!r}"
        )

    # Stronger: ``should_delete(age_years)`` MUST return True iff the
    # archive is at or beyond the 2-year horizon. This catches a
    # GREEN implementation that hard-codes ``action='delete'`` but
    # forgets the gating logic that the scheduler actually consumes.
    should_delete = getattr(policy, "should_delete", None)
    assert callable(should_delete), (
        "FR-91 ArchiveRetentionPolicy must expose "
        "``should_delete(age_years: int) -> bool``"
    )
    assert should_delete(archive_age_years) is True, (
        f"FR-91 should_delete({archive_age_years}) must return True "
        f"at-or-beyond the 2-year horizon"
    )
    assert should_delete(archive_age_years - 1) is False, (
        f"FR-91 should_delete({archive_age_years - 1}) must return "
        f"False one year before the horizon"
    )


# ---------------------------------------------------------------------------
# 3. PII audit logs are anonymized (NOT deleted) after 90 days — preserving
#    statistical counts but stripping PII (happy_path).
#
# Spec input: retention_days="90"; table="pii_audit_log";
#             expected_action="anonymize".
# SRS FR-91: "PII 稽核日誌 90 天 → 自動匿名化".
# A regression that picked "delete" here would lose audit traceability;
# a regression that picked "retain" would violate GDPR data-minimisation.
# "anonymize" preserves statistical counts while stripping PII — that
# is exactly what the FR mandates.
# ---------------------------------------------------------------------------
def test_fr91_pii_audit_90d_anonymized():
    retention_days = 90
    table = "pii_audit_log"
    expected_action = "anonymize"  # spec string sentinel

    # GREEN TODO: PiiAuditRetentionPolicy must accept ``retention_days``,
    # ``table``, and ``action`` kwargs (or positional args) and expose
    # them as attributes. The class MUST also expose
    # ``action_for(age_days: int) -> str`` returning "anonymize" iff
    # age_days >= retention_days, and "retain" otherwise.
    policy = PiiAuditRetentionPolicy(
        retention_days=retention_days,
        table=table,
        action=expected_action,
    )
    result = policy  # so the harness sees a bound ``result`` object

    # The fr91-ok predicate belongs to case 1 only. For case 3 we keep
    # a top-level local sanity check (not inside an `if` block, to
    # avoid triggering the harness's trigger_mismatch detection).
    assert result is not None, (
        "FR-91 PiiAuditRetentionPolicy() must return a policy object; "
        "got None"
    )

    # The retention horizon MUST be 90 days — the FR-mandated value.
    assert getattr(policy, "retention_days", None) == retention_days, (
        f"FR-91 pii_audit retention_days must be {retention_days}; got "
        f"{getattr(policy, 'retention_days', None)!r}"
    )
    # The table MUST be pii_audit_log — the FR-mandated source table.
    assert getattr(policy, "table", None) == table, (
        f"FR-91 pii_audit table must be {table!r}; got "
        f"{getattr(policy, 'table', None)!r}"
    )
    # The action MUST be "anonymize" — NOT "delete" (which would lose
    # audit traceability) and NOT "retain" (which would violate
    # GDPR data-minimisation).
    if expected_action == "anonymize":
        action_attr = getattr(policy, "action", None)
        assert action_attr == "anonymize", (
            f"FR-91 pii_audit action must be 'anonymize'; got "
            f"{action_attr!r}"
        )

    # Stronger: ``action_for(age_days)`` MUST return "anonymize" once
    # the record is at or beyond the 90-day horizon, and "retain"
    # before that. This catches a GREEN implementation that
    # hard-codes the attribute but forgets the gating logic that
    # the scheduler actually consumes.
    action_for = getattr(policy, "action_for", None)
    assert callable(action_for), (
        "FR-91 PiiAuditRetentionPolicy must expose "
        "``action_for(age_days: int) -> str``"
    )
    assert action_for(retention_days) == "anonymize", (
        f"FR-91 action_for({retention_days}) must return 'anonymize' "
        f"at-or-beyond the 90-day horizon; got "
        f"{action_for(retention_days)!r}"
    )
    assert action_for(retention_days - 1) == "retain", (
        f"FR-91 action_for({retention_days - 1}) must return "
        f"'retain' before the 90-day horizon; got "
        f"{action_for(retention_days - 1)!r}"
    )


# ---------------------------------------------------------------------------
# 4. Emotion history records are deleted (NOT anonymized) after 90 days —
#    these are personal inferences and the FR is stricter on them than on
#    PII audit logs (happy_path).
#
# Spec input: retention_days="90"; table="emotion_history";
#             expected_action="delete".
# SRS FR-91: "情緒歷史 90 天 → 刪除".
# A regression that picked "anonymize" here would keep personal
# inference data indefinitely; "delete" is the FR's strict choice for
# emotion data because it is personal and inferential.
# ---------------------------------------------------------------------------
def test_fr91_emotion_90d_deleted():
    retention_days = 90
    table = "emotion_history"
    expected_action = "delete"  # spec string sentinel

    # GREEN TODO: EmotionHistoryRetentionPolicy must accept
    # ``retention_days``, ``table``, and ``action`` kwargs (or
    # positional args) and expose them as attributes. The class MUST
    # also expose ``should_delete(age_days: int) -> bool`` returning
    # True iff age_days >= retention_days.
    policy = EmotionHistoryRetentionPolicy(
        retention_days=retention_days,
        table=table,
        action=expected_action,
    )
    result = policy  # so the harness sees a bound ``result`` object

    # The fr91-ok predicate belongs to case 1 only. For case 4 we keep
    # a top-level local sanity check (not inside an `if` block, to
    # avoid triggering the harness's trigger_mismatch detection).
    assert result is not None, (
        "FR-91 EmotionHistoryRetentionPolicy() must return a policy "
        "object; got None"
    )

    # The retention horizon MUST be 90 days — the FR-mandated value.
    assert getattr(policy, "retention_days", None) == retention_days, (
        f"FR-91 emotion retention_days must be {retention_days}; got "
        f"{getattr(policy, 'retention_days', None)!r}"
    )
    # The table MUST be emotion_history — the FR-mandated source table.
    assert getattr(policy, "table", None) == table, (
        f"FR-91 emotion table must be {table!r}; got "
        f"{getattr(policy, 'table', None)!r}"
    )
    # The action MUST be "delete" — NOT "anonymize" (which would
    # keep personal inference data) and NOT "retain" (which would
    # violate the FR entirely).
    if expected_action == "delete":
        action_attr = getattr(policy, "action", None)
        assert action_attr == "delete", (
            f"FR-91 emotion action must be 'delete'; got "
            f"{action_attr!r}"
        )

    # Stronger: ``should_delete(age_days)`` MUST return True iff the
    # record is at or beyond the 90-day horizon. This catches a
    # GREEN implementation that hard-codes ``action='delete'`` but
    # forgets the gating logic that the scheduler actually consumes.
    should_delete = getattr(policy, "should_delete", None)
    assert callable(should_delete), (
        "FR-91 EmotionHistoryRetentionPolicy must expose "
        "``should_delete(age_days: int) -> bool``"
    )
    assert should_delete(retention_days) is True, (
        f"FR-91 emotion should_delete({retention_days}) must return "
        f"True at-or-beyond the 90-day horizon"
    )
    assert should_delete(retention_days - 1) is False, (
        f"FR-91 emotion should_delete({retention_days - 1}) must "
        f"return False one day before the horizon"
    )
