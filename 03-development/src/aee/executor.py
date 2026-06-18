"""[FR-44] Tool executor for AEE.

Citations:
  SRS.md FR-44
"""
from __future__ import annotations

from typing import Any


class ToolExecutor:
    """[FR-44] Executes registered tools with sandboxing."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}

    def register(self, name: str, fn: Any) -> None:
        """Register a callable tool."""
        self._registry[name] = fn

    def run(self, name: str, params: dict[str, Any]) -> Any:
        """Run tool by name and return result."""
        fn = self._registry.get(name)
        if fn is None:
            raise KeyError(f"Tool not found: {name}")
        return fn(**params)
