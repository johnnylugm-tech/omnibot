"""[FR-39 to FR-43] Agent Execution Engine adapters.

Citations:
  SRS.md FR-39: ActionAdapter
  SRS.md FR-40: A2AAdapter
  SRS.md FR-41: CLIAdapter
  SRS.md FR-42: MCPAdapter
  SRS.md FR-43: ToolDefinition / AgentCard
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """[FR-43] Describes an executable tool."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCard:
    """[FR-43] Agent capability manifest."""

    agent_id: str
    tools: list[ToolDefinition] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)


class ActionAdapter:
    """[FR-39] Base adapter for action execution."""

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute action and return result."""
        return None


class A2AAdapter(ActionAdapter):
    """[FR-40] Agent-to-agent action adapter."""

    def __init__(self, remote_url: str) -> None:
        self._url = remote_url


class CLIAdapter(ActionAdapter):
    """[FR-41] CLI command execution adapter."""

    def __init__(self, allowed_commands: list[str] | None = None) -> None:
        self._allowed = set(allowed_commands or [])


class MCPAdapter(ActionAdapter):
    """[FR-42] Model Context Protocol adapter."""

    def __init__(self, server_url: str) -> None:
        self._url = server_url
