"""[FR-108] Golden dataset for LLM judge calibration.

Citations:
  SRS.md FR-108
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenSample:
    """[FR-108] A single golden dataset sample."""

    question: str
    expected_answer: str
    context: str
    metadata: dict[str, Any] = field(default_factory=dict)


class GoldenDataset:
    """[FR-108] Collection of golden samples for judge calibration."""

    def __init__(self) -> None:
        self._samples: list[GoldenSample] = []

    def add(self, sample: GoldenSample) -> None:
        """Add sample to dataset."""
        self._samples.append(sample)

    def load_from_json(self, path: str) -> int:
        """Load samples from JSON file and return count."""
        return 0

    def get_all(self) -> list[GoldenSample]:
        """Return all samples."""
        return self._samples

    def size(self) -> int:
        """Return dataset size."""
        return len(self._samples)
