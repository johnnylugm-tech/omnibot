"""[FR-91] Data Retention Policy — per-table retention schedule.

SRS FR-91: conversations 180d → Parquet/S3 archive → 2yr delete;
PII audit 90d → anonymize; emotion history 90d → delete.
"""
from __future__ import annotations


def test_fr91_180d_messages_archived():
    """FR-91: conversations table — messages older than 180 days are archived to Parquet/S3."""
    from app.admin.gdpr import RetentionPolicy

    policy = RetentionPolicy()
    result = policy.should_archive("conversations", days_old=181, retention_days=180)
    assert result.action == "archive"
    assert result.format == "Parquet/S3"


def test_fr91_2yr_archive_deleted():
    """FR-91: archived data older than 2 years is permanently deleted."""
    from app.admin.gdpr import RetentionPolicy

    policy = RetentionPolicy()
    result = policy.should_delete("archive", years_old=3, archive_age_years=2)
    assert result.action == "delete"


def test_fr91_pii_audit_90d_anonymized():
    """FR-91: PII audit log entries older than 90 days are anonymized (not deleted)."""
    from app.admin.gdpr import RetentionPolicy

    policy = RetentionPolicy()
    result = policy.should_anonymize("pii_audit_log", days_old=91, retention_days=90)
    assert result.action == "anonymize"


def test_fr91_emotion_90d_deleted():
    """FR-91: emotion history older than 90 days is deleted."""
    from app.admin.gdpr import RetentionPolicy

    policy = RetentionPolicy()
    result = policy.should_delete("emotion_history", days_old=91, retention_days=90)
    assert result.action == "delete"
