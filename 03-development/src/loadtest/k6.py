"""[FR-106] k6 load test configuration.

Citations:
  SRS.md FR-106
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class K6Scenario:
    """[FR-106] k6 load test scenario."""

    name: str
    vus: int
    duration: str
    target_rps: int


@dataclass
class K6LoadTest:
    """[FR-106] k6 load test suite configuration."""

    scenarios: list[K6Scenario] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)

    def add_scenario(self, scenario: K6Scenario) -> None:
        """Add a test scenario."""
        self.scenarios.append(scenario)

    def to_script(self) -> str:
        """Return k6 JavaScript test script."""
        return "export default function() {}"
