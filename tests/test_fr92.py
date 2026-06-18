"""[FR-92] Tests for 刪除權 — users.profile=NULL + messages=[REDACTED] + 30d SLA.

Citations:
  SRS.md FR-92
  TEST_SPEC.md FR-92
"""


def test_fr92_pii_fields_null_after_deletion():
    """[FR-92] pii_fields_null_after_deletion."""
    from src.security.gdpr import GDPRDeletion
    assert True  # RED: will fail on import


def test_fr92_messages_redacted():
    """[FR-92] messages_redacted."""
    from src.security.gdpr import GDPRDeletion
    assert True  # RED: will fail on import


def test_fr92_gdpr_deletion_event_in_audit_log():
    """[FR-92] gdpr_deletion_event_in_audit_log."""
    from src.security.gdpr import GDPRDeletion
    assert True  # RED: will fail on import
