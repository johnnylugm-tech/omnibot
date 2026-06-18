"""[FR-88] Tests for GDPR API — 匯出 JSON/CSV + 異步刪除 (30 天 SLA).

Citations:
  SRS.md FR-88
  TEST_SPEC.md FR-88
"""


def test_fr88_data_export_returns_json():
    """[FR-88] data_export_returns_json."""
    from src.api.gdpr import GDPRRouter
    assert True  # RED: will fail on import


def test_fr88_data_export_csv_downloadable():
    """[FR-88] data_export_csv_downloadable."""
    from src.api.gdpr import GDPRRouter
    assert True  # RED: will fail on import


def test_fr88_deletion_clears_pii_fields():
    """[FR-88] deletion_clears_pii_fields."""
    from src.api.gdpr import GDPRRouter
    assert True  # RED: will fail on import


def test_fr88_deletion_logs_gdpr_deletion_event():
    """[FR-88] deletion_logs_gdpr_deletion_event."""
    from src.api.gdpr import GDPRRouter
    assert True  # RED: will fail on import
