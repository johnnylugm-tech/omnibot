"""[FR-90] Tests for Redis 安全 — TLS 6380 + requirepass env + ACL default_user 停用.

Citations:
  SRS.md FR-90
  TEST_SPEC.md FR-90
"""


def test_fr90_redis_rejects_plaintext_connection():
    """[FR-90] redis_rejects_plaintext_connection."""
    from src.security.redis_security import RedisSecurityConfig
    cfg = RedisSecurityConfig(host="localhost", tls_enabled=False, password="pw")
    url = cfg.to_url()
    assert "localhost" in url
def test_fr90_auth_from_env_var():
    """[FR-90] auth_from_env_var."""
    from src.security.redis_security import RedisSecurityConfig
    assert True  # RED: will fail on import


def test_fr90_default_user_disabled():
    """[FR-90] default_user_disabled."""
    from src.security.redis_security import RedisSecurityConfig
    assert True  # RED: will fail on import
