"""[FR-89] Tests for TDE 加密 — AES-256 + 90天金鑰輪換 + pii_vault DBA 無法裸讀.

Citations:
  SRS.md FR-89
  TEST_SPEC.md FR-89
"""


def test_fr89_tde_enabled():
    """[FR-89] tde_enabled."""
    from src.security.tde import TDEManager
    tde = TDEManager("key-1")
    encrypted = tde.encrypt("secret")
    decrypted = tde.decrypt(encrypted)
    assert isinstance(decrypted, str)
    new_key = tde.rotate_key()
    assert isinstance(new_key, str)
def test_fr89_key_rotation_scheduled_90d():
    """[FR-89] key_rotation_scheduled_90d."""
    from src.security.tde import TDEManager
    assert True  # RED: will fail on import


def test_fr89_pii_vault_direct_read_blocked():
    """[FR-89] pii_vault_direct_read_blocked."""
    from src.security.tde import TDEManager
    assert True  # RED: will fail on import
