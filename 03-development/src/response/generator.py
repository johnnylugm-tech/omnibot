"""[FR-50] Response generator — selects and renders bot response.

Citations:
  SRS.md FR-50
"""
from __future__ import annotations

from typing import Any


class ResponseGenerator:
    """[FR-50] Generates bot response from knowledge results and context."""

    def generate(self, query: str, context: list[dict[str, Any]]) -> str:
        """Return generated response text."""
        return ""

    def render(self, template: str, variables: dict[str, Any]) -> str:
        """Render response template with variables."""
        return template.format(**variables)
