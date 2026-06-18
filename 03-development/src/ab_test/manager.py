"""[FR-63] A/B test manager.

Citations:
  SRS.md FR-63
"""
from __future__ import annotations

from typing import Any
import random


class ABTestManager:
    """[FR-63] Manages A/B experiments and variant assignment."""

    def __init__(self) -> None:
        self._experiments: dict[str, dict[str, Any]] = {}

    def create(self, name: str, variants: list[str], weights: list[float] | None = None) -> None:
        """Create a new experiment."""
        self._experiments[name] = {"variants": variants, "weights": weights}

    def assign(self, experiment: str, user_id: str) -> str:
        """Return assigned variant for user."""
        exp = self._experiments.get(experiment)
        if not exp:
            return ""
        return random.choice(exp["variants"])
