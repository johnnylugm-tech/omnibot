"""[FR-71] Prometheus metrics and Grafana dashboard.

Citations:
  SRS.md FR-71
"""
from __future__ import annotations

from typing import Any


class PrometheusMetrics:
    """[FR-71] Prometheus metrics registry."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}

    def inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment counter."""
        self._counters[name] = self._counters.get(name, 0.0) + value

    def get(self, name: str) -> float:
        """Return counter value."""
        return self._counters.get(name, 0.0)


class GrafanaDashboard:
    """[FR-71] Grafana dashboard configuration helper."""

    def __init__(self, title: str) -> None:
        self._title = title
        self._panels: list[dict[str, Any]] = []

    def add_panel(self, panel: dict[str, Any]) -> None:
        """Add a panel to the dashboard."""
        self._panels.append(panel)

    def to_json(self) -> dict[str, Any]:
        """Return Grafana dashboard JSON."""
        return {"title": self._title, "panels": self._panels}
