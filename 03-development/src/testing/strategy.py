"""[FR-107] Testing strategy definitions.

Citations:
  SRS.md FR-107
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TestLayer:
    """[FR-107] Single layer of the testing strategy."""

    name: str
    coverage_target: float
    tools: list[str]


class TestingStrategy:
    """[FR-107] Defines the overall testing strategy (unit/integration/e2e)."""

    LAYERS = [
        TestLayer("unit", 70.0, ["pytest", "pytest-cov"]),
        TestLayer("integration", 20.0, ["pytest", "testcontainers"]),
        TestLayer("e2e", 10.0, ["playwright"]),
    ]

    def get_layer(self, name: str) -> TestLayer | None:
        """Return layer by name."""
        return next((layer for layer in self.LAYERS if layer.name == name), None)

    def coverage_summary(self) -> dict[str, Any]:
        """Return coverage targets by layer."""
        return {layer.name: layer.coverage_target for layer in self.LAYERS}
