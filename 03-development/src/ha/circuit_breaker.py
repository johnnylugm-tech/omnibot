"""[FR-99] Circuit breaker for external service calls.

Citations:
  SRS.md FR-99
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """[FR-99] Circuit breaker pattern implementation."""

    def __init__(self, threshold: int = 5, timeout: float = 60.0) -> None:
        self._threshold = threshold
        self._timeout = timeout
        self._state = CircuitState.CLOSED
        self._failures = 0

    @property
    def state(self) -> CircuitState:
        """Return current circuit state."""
        return self._state

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute fn through circuit breaker."""
        if self._state == CircuitState.OPEN:
            raise RuntimeError("Circuit is OPEN")
        try:
            result = fn(*args, **kwargs)
            self._failures = 0
            return result
        except Exception:
            self._failures += 1
            if self._failures >= self._threshold:
                self._state = CircuitState.OPEN
            raise
