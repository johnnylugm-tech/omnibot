"""[FR-20] Tests for PII 稽核日誌 — pii_audit_log + 90天自動匿名化.

Citations:
  SRS.md FR-20
  TEST_SPEC.md FR-20
"""


def test_fr20_mask_event_writes_audit_log():
    """[FR-20] mask_event_writes_audit_log."""
    from src.pii.masking import PIIAuditLogger
    assert True  # RED: will fail on import


def test_fr20_audit_log_has_conversation_id():
    """[FR-20] audit_log_has_conversation_id."""
    from src.pii.masking import PIIAuditLogger
    assert True  # RED: will fail on import


def test_fr20_90day_anonymize_scheduled():
    """[FR-20] 90day_anonymize_scheduled."""
    from src.pii.masking import PIIAuditLogger
    assert True  # RED: will fail on import
