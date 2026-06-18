"""[FR-70] Structured logging.

Citations:
  SRS.md FR-70
"""
from __future__ import annotations

import json
import sys
from typing import Any


class StructuredLogger:
    """[FR-70] JSON structured logger for observability."""

    def __init__(self, name: str) -> None:
        self._name = name

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info-level structured event."""
        self._emit("INFO", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error-level structured event."""
        self._emit("ERROR", message, **kwargs)

    def _emit(self, level: str, message: str, **kwargs: Any) -> None:
        record = {"level": level, "logger": self._name, "message": message, **kwargs}
        print(json.dumps(record), file=sys.stderr)
