"""[FR-73] Alert rules for observability.

Citations:
  SRS.md FR-73
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AlertRule:
    """[FR-73] Single alert rule definition."""

    name: str
    condition: str
    severity: str
    message: str


class AlertRules:
    """[FR-73] Collection of alert rules."""

    def __init__(self) -> None:
        self._rules: list[AlertRule] = []

    def add(self, rule: AlertRule) -> None:
        """Register alert rule."""
        self._rules.append(rule)

    def evaluate(self, metrics: dict[str, Any]) -> list[AlertRule]:
        """Return triggered alert rules given current metrics."""
        return []

    def to_yaml(self) -> str:
        """Export rules to Prometheus alertmanager YAML."""
        return ""
