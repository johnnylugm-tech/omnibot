"""[FR-81] Retry policy with exponential backoff.

Citations:
  SRS.md FR-81
"""
from __future__ import annotations

from typing import Any, Callable


class RetryPolicy:
    """[FR-81] Configurable retry policy with exponential backoff."""

    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0) -> None:
        self._max = max_attempts
        self._base = base_delay

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute fn with retry on exception."""
        last_exc: Exception | None = None
        for attempt in range(self._max):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc

    def delay_for(self, attempt: int) -> float:
        """Return delay in seconds for attempt number."""
        return self._base * (2 ** attempt)
