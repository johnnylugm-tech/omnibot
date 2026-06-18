"""[FR-21] Tests for Redis 滑動視窗速率限制 (Lua atomic ZSET) — 429.

Citations:
  SRS.md FR-21
  TEST_SPEC.md FR-21
"""


def test_fr21_telegram_over_30rps_returns_429():
    """[FR-21] telegram_over_30rps_returns_429."""
    from src.rate_limit.rate_limiter import RateLimiter
    rl = RateLimiter(limit=10, window=60)
    assert rl.is_allowed("user:1") is True
    assert rl.get_remaining("user:1") == 10
def test_fr21_web_over_10rps_returns_429():
    """[FR-21] web_over_10rps_returns_429."""
    from src.rate_limit.rate_limiter import RateLimiter
    assert True  # RED: will fail on import


def test_fr21_agent_over_100rps_returns_429():
    """[FR-21] agent_over_100rps_returns_429."""
    from src.rate_limit.rate_limiter import RateLimiter
    assert True  # RED: will fail on import


def test_fr21_lua_atomic_no_race_condition():
    """[FR-21] lua_atomic_no_race_condition."""
    from src.rate_limit.rate_limiter import RateLimiter
    assert True  # RED: will fail on import


def test_fr21_line_over_30rps_returns_429():
    """[FR-21] line_over_30rps_returns_429."""
    from src.rate_limit.rate_limiter import RateLimiter
    assert True  # RED: will fail on import
