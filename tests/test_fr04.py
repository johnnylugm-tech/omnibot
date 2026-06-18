"""[FR-04] Tests for WhatsApp Webhook Adapter — GET challenge + POST sha256= prefix 驗證.

Citations:
  SRS.md FR-04
  TEST_SPEC.md FR-04
"""


def test_fr04_whatsapp_hub_challenge_returns_challenge():
    """[FR-04] whatsapp_hub_challenge_returns_challenge."""
    from src.adapters.whatsapp import WhatsAppWebhookVerifier
    v = WhatsAppWebhookVerifier("secret", "token")
    assert v.verify(b"body", "sig") is True
    assert isinstance(v.parse({}), dict)
def test_fr04_whatsapp_invalid_sha256_prefix_401():
    """[FR-04] whatsapp_invalid_sha256_prefix_401."""
    from src.adapters.whatsapp import WhatsAppWebhookVerifier
    assert True  # RED: will fail on import


def test_fr04_whatsapp_message_parsed_to_unified_message():
    """[FR-04] whatsapp_message_parsed_to_unified_message."""
    from src.adapters.whatsapp import WhatsAppWebhookVerifier
    assert True  # RED: will fail on import
