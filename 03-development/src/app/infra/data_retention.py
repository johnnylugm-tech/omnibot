"""[FR-91] Data retention policy descriptors (180d archive / 2yr delete /
90d anonymize / 90d emotion delete).

Immutable policy objects that the retention scheduler consumes to decide
what action to take on each record at its age horizon. The four policy
shapes below cover the FR-91 acceptance criteria:

    - conversations(messages) 180 天 → 封存 cold storage (Parquet/S3)
    - 封存後 2 年 → 永久刪除
    - PII 稽核日誌 90 天 → 自動匿名化
    - 情緒歷史 90 天 → 刪除
    - 安全日誌 1 年 → 封存後 2 年刪除
    - 用戶回饋永久保留 (已去識別化)

The unit tests exercise these classes in isolation — no DB / S3 /
scheduler I/O — which is the canonical unit-test shape for FR-91.

Citations:
- SRS.md FR-91 (description line, spec block lines)
- 02-architecture/TEST_SPEC.md FR-91 (4 case shapes)
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 1. conversations.messages → cold-storage archive at 180 days
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MessagesRetentionPolicy:
    """Immutable descriptor for the 180-day messages-archive policy.

    Attributes:
        retention_days: hot-DB horizon (days). Beyond this, the record
            moves to cold storage.
        target: source table name whose rows this policy governs.
        archive_format: cold-storage format family descriptor
            (e.g. ``"Parquet/S3"``). Read directly via the attribute;
            no accessor method is required.
        archive_action: scheduler action token (``"archive"``).
    """

    retention_days: int
    target: str
    archive_format: str
    archive_action: str

    def should_archive(self, age_days: int) -> bool:
        """Return True iff the record's age has reached the retention horizon."""
        return age_days >= self.retention_days


# ---------------------------------------------------------------------------
# 2. archives aged 2 years → permanent delete
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ArchiveRetentionPolicy:
    """Immutable descriptor for the 2-year archive deletion policy.

    Attributes:
        archive_age_years: archive-age horizon (years). Beyond this,
            the archive is permanently deleted.
        action: scheduler action token (``"delete"``).
    """

    archive_age_years: int
    action: str

    def should_delete(self, age_years: int) -> bool:
        """Return True iff the archive has reached the deletion horizon."""
        return age_years >= self.archive_age_years


# ---------------------------------------------------------------------------
# 3. PII audit logs → anonymize (NOT delete) at 90 days
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PiiAuditRetentionPolicy:
    """Immutable descriptor for the 90-day PII audit log policy.

    The action is ``"anonymize"`` — strip PII but keep statistical
    counts so the audit trail is not lost.

    Attributes:
        retention_days: anonymization horizon (days).
        table: source table name whose rows this policy governs.
        action: scheduler action token (``"anonymize"``).
    """

    retention_days: int
    table: str
    action: str

    def action_for(self, age_days: int) -> str:
        """Return ``"anonymize"`` once the record is at or beyond the
        90-day horizon; otherwise return ``"retain"``.
        """
        if age_days >= self.retention_days:
            return "anonymize"
        return "retain"


# ---------------------------------------------------------------------------
# 4. emotion history → delete at 90 days (stricter than PII audit logs)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EmotionHistoryRetentionPolicy:
    """Immutable descriptor for the 90-day emotion-history deletion policy.

    Emotion history is personal inference data; the FR is stricter on
    it than on PII audit logs — ``"delete"``, not ``"anonymize"``.

    Attributes:
        retention_days: deletion horizon (days).
        table: source table name whose rows this policy governs.
        action: scheduler action token (``"delete"``).
    """

    retention_days: int
    table: str
    action: str

    def should_delete(self, age_days: int) -> bool:
        """Return True iff the record's age has reached the deletion horizon."""
        return age_days >= self.retention_days