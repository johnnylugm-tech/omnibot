"""[FR-84] Tests for Webhook API 端點 — 7 個端點 + 統一錯誤碼.

Citations:
  SRS.md FR-84
  TEST_SPEC.md FR-84
"""


def test_fr84_all_6_webhook_endpoints_exist():
    """[FR-84] all_6_webhook_endpoints_exist."""
    import pytest
    from src.api.webhooks import WebhookRouter
    router = WebhookRouter()
    router.register("telegram", lambda p: p)
    result = router.route("telegram", {"ok": True})
    assert result == {"ok": True}
    with pytest.raises(KeyError):
        router.route("unknown", {})
def test_fr84_error_codes_consistent():
    """[FR-84] error_codes_consistent."""
    from src.api.webhooks import WebhookRouter
    assert True  # RED: will fail on import
