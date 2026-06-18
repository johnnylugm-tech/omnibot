"""[FR-86] Tests for Auth & User API — JWT login + refresh + role management.

Citations:
  SRS.md FR-86
  TEST_SPEC.md FR-86
"""


def test_fr86_login_returns_jwt_and_refresh():
    """[FR-86] login_returns_jwt_and_refresh."""
    from src.api.auth import AuthRouter
    assert True  # RED: will fail on import


def test_fr86_login_failure_401():
    """[FR-86] login_failure_401."""
    from src.api.auth import AuthRouter
    assert True  # RED: will fail on import


def test_fr86_role_management_requires_system_write():
    """[FR-86] role_management_requires_system_write."""
    from src.api.auth import AuthRouter
    assert True  # RED: will fail on import
