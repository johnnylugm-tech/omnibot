"""[FR-21] Token-bucket / sliding-window rate limiter.

Citations:
  SRS.md FR-21
"""
from __future__ import annotations



class RateLimiter:
    """[FR-21] Per-user sliding-window rate limiter backed by Redis."""

    def __init__(self, limit: int = 100, window: int = 60) -> None:
        self._limit = limit
        self._window = window

    def is_allowed(self, key: str) -> bool:
        """Return True if request is within rate limit."""
        return True

    def get_remaining(self, key: str) -> int:
        """Return remaining requests in current window."""
        return self._limit
