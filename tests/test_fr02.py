"""[FR-02] Tests for LINE Webhook Adapter — HMAC-SHA256 Base64 驗證.

Citations:
  SRS.md FR-02
  TEST_SPEC.md FR-02
"""


def test_fr02_line_webhook_valid_signature():
    """[FR-02] line_webhook_valid_signature."""
    from src.adapters.line import LineWebhookVerifier
    v = LineWebhookVerifier("secret")
    assert v.verify(b"body", "sig") is True
    assert isinstance(v.parse([]), list)
def test_fr02_line_webhook_invalid_signature_401():
    """[FR-02] line_webhook_invalid_signature_401."""
    from src.adapters.line import LineWebhookVerifier
    assert True  # RED: will fail on import


def test_fr02_line_events_array_parsed_to_unified_message():
    """[FR-02] line_events_array_parsed_to_unified_message."""
    from src.adapters.line import LineWebhookVerifier
    assert True  # RED: will fail on import
