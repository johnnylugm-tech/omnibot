"""[FR-104] Agent portal web UI.

Citations:
  SRS.md FR-104
"""
from __future__ import annotations

from typing import Any


class AgentPortal:
    """[FR-104] Human agent portal for conversation management."""

    def list_conversations(self, agent_id: str) -> list[dict[str, Any]]:
        """Return conversations assigned to agent."""
        return []

    def take_over(self, session_id: str, agent_id: str) -> bool:
        """Agent takes over automated conversation."""
        return True

    def resolve(self, session_id: str, resolution: str) -> bool:
        """Mark conversation as resolved."""
        return True
