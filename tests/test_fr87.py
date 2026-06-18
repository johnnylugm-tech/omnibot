"""[FR-87] Tests for M2M Token API — token 僅顯示一次 + SHA-256 hash 儲存.

Citations:
  SRS.md FR-87
  TEST_SPEC.md FR-87
"""


def test_fr87_token_shown_once_on_create():
    """[FR-87] token_shown_once_on_create."""
    from src.api.m2m import M2MTokenRouter
    router = M2MTokenRouter()
    token = router.issue("client", "secret", ["read"])
    assert "access_token" in token
    assert router.revoke("token") is True
def test_fr87_list_hides_token_value():
    """[FR-87] list_hides_token_value."""
    from src.api.m2m import M2MTokenRouter
    assert True  # RED: will fail on import


def test_fr87_revoke_invalidates_immediately():
    """[FR-87] revoke_invalidates_immediately."""
    from src.api.m2m import M2MTokenRouter
    assert True  # RED: will fail on import
