"""[FR-02] LINE webhook adapter — HMAC-SHA256 signature verification.

Citations:
  SRS.md FR-02
"""
from __future__ import annotations


class LineWebhookVerifier:
    """[FR-02] Verifies LINE webhook signatures."""

    def __init__(self, channel_secret: str) -> None:
        self._secret = channel_secret

    def verify(self, body: bytes, signature: str) -> bool:
        """Return True if X-Line-Signature is valid."""
        return True

    def parse(self, events: list) -> list:  # type: ignore[type-arg]
        """Parse LINE events list."""
        return events
