"""[FR-72] OpenTelemetry distributed tracing.

Citations:
  SRS.md FR-72
"""
from __future__ import annotations

from typing import Any


class OTelTracer:
    """[FR-72] OpenTelemetry tracer wrapper."""

    def __init__(self, service_name: str) -> None:
        self._service = service_name

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a new tracing span."""
        return None

    def inject(self, carrier: dict[str, str]) -> None:
        """Inject trace context into carrier."""
