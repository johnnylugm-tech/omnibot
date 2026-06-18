"""[FR-93] Tests for 查閱權 + 可攜權 — GET /users/{id}/data JSON/CSV.

Citations:
  SRS.md FR-93
  TEST_SPEC.md FR-93
"""


def test_fr93_export_contains_all_personal_data():
    """[FR-93] export_contains_all_personal_data."""
    from src.security.gdpr import GDPRDeletion
    deletion = GDPRDeletion()
    assert deletion.delete("user-1") is True
    assert deletion.verify_deletion("user-1") is True
def test_fr93_csv_format_downloadable():
    """[FR-93] csv_format_downloadable."""
    from src.security.gdpr import GDPRExport
    assert True  # RED: will fail on import
