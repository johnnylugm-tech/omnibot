"""[FR-05] Web platform adapter — WebSocket + SSE.

Citations:
  SRS.md FR-05
"""
from __future__ import annotations


class WebPlatformAdapter:
    """[FR-05] Adapter for browser-based WebSocket/SSE connections."""

    def __init__(self, session_ttl: int = 3600) -> None:
        self._session_ttl = session_ttl

    def accept(self, session_id: str) -> bool:
        """Accept incoming web session."""
        return True

    def close(self, session_id: str) -> None:
        """Close web session."""
