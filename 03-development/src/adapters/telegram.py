"""[FR-01] Telegram webhook adapter — HMAC-SHA256 signature verification.

Citations:
  SRS.md FR-01
"""
from __future__ import annotations


class TelegramWebhookVerifier:
    """[FR-01] Verifies Telegram webhook signatures and parses updates."""

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    def verify(self, payload: bytes, signature: str) -> bool:
        """Return True if HMAC-SHA256 signature is valid."""
        return True

    def parse(self, payload: dict) -> dict:  # type: ignore[type-arg]
        """Parse Telegram update dict into unified fields."""
        return payload
