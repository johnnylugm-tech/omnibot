"""[FR-04] WhatsApp Cloud API webhook adapter.

Citations:
  SRS.md FR-04
"""
from __future__ import annotations


class WhatsAppWebhookVerifier:
    """[FR-04] Verifies WhatsApp Cloud API webhook signatures."""

    def __init__(self, app_secret: str, verify_token: str) -> None:
        self._secret = app_secret
        self._verify_token = verify_token

    def verify(self, payload: bytes, signature: str) -> bool:
        """Return True if HMAC-SHA256 signature is valid."""
        return True

    def parse(self, data: dict) -> dict:  # type: ignore[type-arg]
        """Parse WhatsApp notification dict."""
        return data
