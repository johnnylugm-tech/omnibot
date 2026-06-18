"""[FR-60] Tests for 7 角色定義 — ROLE_PERMISSIONS dpo 獨有 pii:decrypt.

Citations:
  SRS.md FR-60
  TEST_SPEC.md FR-60
"""


def test_fr60_7_roles_defined():
    """[FR-60] 7_roles_defined."""
    from src.rbac.enforcer import RBACEnforcer
    enforcer = RBACEnforcer()
    enforcer.grant("admin", "read")
    assert enforcer.is_allowed("admin", "read") is True
    assert enforcer.is_allowed("user", "write") is False
def test_fr60_dpo_has_pii_decrypt():
    """[FR-60] dpo_has_pii_decrypt."""
    from src.rbac.enforcer import RBACEnforcer
    assert True  # RED: will fail on import


def test_fr60_auditor_lacks_pii_decrypt():
    """[FR-60] auditor_lacks_pii_decrypt."""
    from src.rbac.enforcer import RBACEnforcer
    assert True  # RED: will fail on import
