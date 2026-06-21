"""[FR-70] StructuredLogger — JSON-formatted observability with level routing.

Emits one JSON object per ``log()`` call to the underlying ``logging.Logger``
at the mapped level. Required fields on every record:
    - timestamp : ISO 8601 UTC with trailing ``Z`` (e.g. ``2026-06-19T08:15:30Z``)
    - level     : ``DEBUG`` | ``INFO`` | ``WARN`` | ``ERROR`` | ``CRITICAL``
    - service   : the configured service name
    - message   : the human-readable message
    - **kwargs  : arbitrary structured fields (e.g. ``user_id``, ``trace_id``)

Level routing:
    DEBUG    -> logging.DEBUG
    INFO     -> logging.INFO
    WARN     -> logging.WARNING
    WARNING  -> logging.WARNING
    ERROR    -> logging.ERROR
    CRITICAL -> logging.CRITICAL

Security events: passing ``event_type="security"`` forces the emitted level
to ``CRITICAL`` regardless of the ``level`` argument, so downstream alert
handlers firing on ``logger.critical`` (e.g. SIEM bridges) cannot be
silently downgraded by a caller passing ``level="INFO"``.

Citations:
- SRS.md FR-70 (description line 163, spec block lines 1001+)
- 02-architecture/TEST_SPEC.md FR-70 (StructuredLogger JSON shape)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

# ISO 8601 with literal trailing ``Z`` — no fractional seconds, no offset.
_ISO_Z_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Caller-facing level string -> stdlib ``logging`` numeric level.
_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# Security-tagged events are always emitted at CRITICAL, never downgraded.
_SECURITY_EVENT_TYPE = "security"
_SECURITY_LEVEL = "CRITICAL"


def _json_default(obj: Any) -> Any:
    """Serializer for values ``json.dumps`` cannot encode by default.

    Handles the common non-JSON-native types a logger is likely to receive
    via kwargs (datetime/date, Decimal, UUID, sets, bytes, Path, Enum,
    Exception) and raises ``TypeError`` for anything else so callers see
    the real encoding error instead of a silently mangled record.
    """
    if isinstance(obj, datetime):
        # Preserve ISO 8601 round-trip; strftime would lose tzinfo.
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        # str() keeps precision; float() would silently round.
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        # JSON has no set — emit as sorted list for deterministic output.
        return sorted(obj)
    if isinstance(obj, bytes):
        # Prefer UTF-8 text; fall back to hex so binary payloads are still
        # representable as a JSON string instead of crashing the log call.
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, BaseException):
        return str(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable"
    )


class StructuredLogger:
    """[FR-70] JSON structured logger with level routing to ``logging``.

    Usage::

        slog = StructuredLogger(service="omnibot")
        slog.log(level="INFO", message="user signed in", user_id="u-1")
        slog.log(level="WARN", message="retried", trace_id="t-9")
        # Security event — forces CRITICAL even if level="INFO" is passed.
        slog.log(level="INFO", message="failed login",
                 event_type="security", user_id="u-42")
    """

    def __init__(
        self,
        service: str,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.service = service
        self._logger = logger or logging.getLogger(service)

    def log(self, level: str, message: str, **kwargs: Any) -> str:
        """Emit one JSON record at the resolved level.

        Resolution rules:
          * If ``event_type="security"`` is in kwargs, the emitted level is
            forced to ``CRITICAL`` regardless of ``level``.
          * Otherwise the caller-provided ``level`` is used as-is.

        Returns the single-line JSON string that was emitted, so callers
        can also assert on the exact serialized record in tests.
        """
        # Security events must not be downgraded by the caller.
        resolved_level = (
            _SECURITY_LEVEL
            if kwargs.get("event_type") == _SECURITY_EVENT_TYPE
            else level
        )

        record: dict[str, Any] = {
            "timestamp": time.strftime(_ISO_Z_FMT, time.gmtime()),
            "level": resolved_level,
            "service": self.service,
            "message": message,
            **kwargs,
        }
        line = json.dumps(record, ensure_ascii=False, default=_json_default)
        py_level = _LEVEL_MAP.get(resolved_level.upper(), logging.INFO)
        self._logger.log(py_level, line)
        return line

    # Convenience helpers — mirror the stdlib logger's level-named methods
    # so callers can write ``slog.info(...)`` without re-typing the level.
    def debug(self, message: str, **kwargs: Any) -> str:
        return self.log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> str:
        return self.log("INFO", message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> str:
        return self.log("WARN", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> str:
        return self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> str:
        return self.log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> str:
        return self.log("CRITICAL", message, **kwargs)
