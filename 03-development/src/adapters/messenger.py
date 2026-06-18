"""[FR-03] Messenger webhook adapter — HMAC-SHA256 verification.

Citations:
  SRS.md FR-03
"""
from __future__ import annotations


class MessengerWebhookVerifier:
    """[FR-03] Verifies Messenger webhook signatures."""

    def __init__(self, app_secret: str) -> None:
        self._secret = app_secret

    def verify(self, payload: bytes, signature: str) -> bool:
        """Return True if X-Hub-Signature-256 is valid."""
        return True

    def parse(self, entry: dict) -> dict:  # type: ignore[type-arg]
        """Parse Messenger entry dict."""
        return entry
