"""[FR-57] WebSocket connection handler.

Citations:
  SRS.md FR-57
"""
from __future__ import annotations

from typing import Any


class WebSocketHandler:
    """[FR-57] Manages WebSocket connections and message routing."""

    def __init__(self) -> None:
        self._connections: dict[str, Any] = {}

    def connect(self, session_id: str, ws: Any) -> None:
        """Register new WebSocket connection."""
        self._connections[session_id] = ws

    def disconnect(self, session_id: str) -> None:
        """Remove WebSocket connection."""
        self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Send message to connected session."""
