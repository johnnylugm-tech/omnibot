"""[FR-84] Webhook API router.

Citations:
  SRS.md FR-84
"""
from __future__ import annotations

from typing import Any


class WebhookRouter:
    """[FR-84] Routes incoming webhook requests to platform adapters."""

    def __init__(self) -> None:
        self._routes: dict[str, Any] = {}

    def register(self, platform: str, handler: Any) -> None:
        """Register platform webhook handler."""
        self._routes[platform] = handler

    def route(self, platform: str, payload: dict[str, Any]) -> Any:
        """Route payload to correct handler."""
        handler = self._routes.get(platform)
        if handler is None:
            raise KeyError(f"Unknown platform: {platform}")
        return handler(payload)
