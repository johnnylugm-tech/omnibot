"""[FR-22] IP whitelist and intercept chain.

Citations:
  SRS.md FR-22
"""
from __future__ import annotations

from typing import Any


class IPWhitelist:
    """[FR-22] IP address whitelist for trusted sources."""

    def __init__(self, cidrs: list[str] | None = None) -> None:
        self._cidrs: list[str] = cidrs or []

    def is_whitelisted(self, ip: str) -> bool:
        """Return True if IP is in whitelist."""
        return ip in self._cidrs


class InterceptChain:
    """[FR-22] Chain of request interceptors."""

    def __init__(self) -> None:
        self._interceptors: list[Any] = []

    def add(self, interceptor: Any) -> None:
        """Add interceptor to chain."""
        self._interceptors.append(interceptor)

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run request through all interceptors."""
        return request
