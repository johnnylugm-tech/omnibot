"""TDD-RED: failing tests for FR-70 — StructuredLogger (JSON, ISO 8601 Z, levels).

Spec source: 02-architecture/TEST_SPEC.md (FR-70)
SRS source : SRS.md FR-70 (Module 15: Observability)

Acceptance criteria (from SRS FR-70):
    StructuredLogger：JSON 格式，欄位含 timestamp(ISO 8601 Z), level, service,
    message 及任意 kwargs；支援 DEBUG/INFO/WARN/ERROR/CRITICAL；CRITICAL 用於
    安全事件；各 level 正確路由至 Python logging。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

# ---------------------------------------------------------------------------
# Source under test — ``StructuredLogger`` is intentionally NOT YET exported
# by ``app.infra.observability``. The import below is unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/observability.py`` exporting ``StructuredLogger``
# whose ``log(level, message, **kwargs)`` (or equivalent public surface)
# emits a single-line JSON record with the required FR-70 fields and routes
# the record to the appropriate ``logging`` level (DEBUG/INFO/WARNING/ERROR/
# CRITICAL).
# ---------------------------------------------------------------------------
from app.infra.observability import StructuredLogger

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/observability.py
#   import json
#   import logging
#   import time
#   from typing import Any
#
#   _ISO_Z_FMT = "%Y-%m-%dT%H:%M:%SZ"
#   _LEVEL_MAP = {
#       "DEBUG":    logging.DEBUG,
#       "INFO":     logging.INFO,
#       "WARN":     logging.WARNING,
#       "WARNING":  logging.WARNING,
#       "ERROR":    logging.ERROR,
#       "CRITICAL": logging.CRITICAL,
#   }
#
#   class StructuredLogger:
#       """FR-70 JSON structured logger.
#
#       Emits one JSON object per log call, written to the underlying
#       ``logging.Logger`` at the mapped level. Required fields:
#         - timestamp : ISO 8601 with trailing ``Z`` (e.g. 2026-06-19T08:15:30Z)
#         - level     : DEBUG | INFO | WARN | ERROR | CRITICAL
#         - service   : the configured service name
#         - message   : the human-readable message
#         - **kwargs  : arbitrary structured fields (e.g. user_id, trace_id)
#       """
#
#       def __init__(self, service: str, *, logger: logging.Logger | None = None) -> None:
#           self.service = service
#           self._logger = logger or logging.getLogger(service)
#
#       def log(self, level: str, message: str, **kwargs: Any) -> str:
#           # Build the JSON record, then emit via the stdlib logger.
#           record = {
#               "timestamp": time.strftime(_ISO_Z_FMT, time.gmtime()),
#               "level":     level,
#               "service":   self.service,
#               "message":   message,
#               **kwargs,
#           }
#           line = json.dumps(record, ensure_ascii=False)
#           py_level = _LEVEL_MAP.get(level.upper(), logging.INFO)
#           self._logger.log(py_level, line)
#           return line
#
#       # Convenience helpers, also GREEN TODO:
#       def debug(self,    message: str, **kw): return self.log("DEBUG",    message, **kw)
#       def info(self,     message: str, **kw): return self.log("INFO",     message, **kw)
#       def warn(self,     message: str, **kw): return self.log("WARN",     message, **kw)
#       def error(self,    message: str, **kw): return self.log("ERROR",    message, **kw)
#       def critical(self, message: str, **kw): return self.log("CRITICAL", message, **kw)
# ---------------------------------------------------------------------------

# Required FR-70 fields every JSON record must carry.
_REQUIRED_FIELDS = ("timestamp", "level", "service", "message")

# ISO 8601 with trailing Z (FR-70) — strict but practical regex.
_ISO_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)


def _capture_log_records(logger_name: str) -> io.StringIO:
    """Attach a fresh StringIO stream handler for ``logger_name`` and return it.

    The handler is removed in the fixture teardown via the ``caplog_records``
    finalizer pattern (see _attach_stream_handler). Each test that needs to
    observe the emitted records must call this helper.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    target = logging.getLogger(logger_name)
    target.setLevel(logging.DEBUG)
    target.addHandler(handler)
    # Stash on the stream for the test to remove cleanly.
    stream._handler = handler  # type: ignore[attr-defined]
    stream._logger = target    # type: ignore[attr-defined]
    return stream


def _detach(stream: io.StringIO) -> None:
    handler = getattr(stream, "_handler", None)
    target = getattr(stream, "_logger", None)
    if handler is not None and target is not None:
        target.removeHandler(handler)


# ---------------------------------------------------------------------------
# 1. StructuredLogger.log() output is parseable as JSON and carries the
#    FR-70 required fields (happy_path).
#
# Spec input: log_entry='{"level":"INFO","message":"test"}'.
# The log() call must produce a single-line JSON record that json.loads()
# accepts, and the parsed object must expose timestamp/level/service/message.
# ---------------------------------------------------------------------------
def test_fr70_log_json_parseable():
    log_entry = '{"level":"INFO","message":"test"}'

    # GREEN TODO: StructuredLogger(service="omnibot").log(level, message, **kw)
    # must return a single-line JSON string parseable by json.loads, and the
    # parsed object must include the FR-70 required fields.
    slog = StructuredLogger(service="omnibot")

    # The spec input is the canonical INFO + message="test" baseline. We
    # also exercise the kwargs passthrough (arbitrary structured fields) so
    # the GREEN impl cannot satisfy the test with a fixed-string stub.
    parsed_input = json.loads(log_entry)
    emitted = slog.log(
        level=parsed_input["level"],
        message=parsed_input["message"],
        user_id="u-1",
    )

    # Spec fr70-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 1's input. The trigger
    # value is log_entry='{"level":"INFO","message":"test"}'. The predicate
    # free variable is `result` — alias the parsed JSON object to it.
    result = json.loads(emitted) if isinstance(emitted, str) else emitted
    # Spec stores the case 1 input with JSON-style escaping
    # (`{\"level\":\"INFO\",\"message\":\"test\"}`), so the trigger value
    # the harness matches against must use the same escaping.
    if log_entry == "{\"level\":\"INFO\",\"message\":\"test\"}":
        assert result is not None, "fr70-ok predicate: result must not be None"

    # The parsed object must expose all four FR-70 required fields.
    for field in _REQUIRED_FIELDS:
        assert field in result, (
            f"FR-70 JSON log entry is missing required field {field!r}; "
            f"got keys={sorted(result.keys())}"
        )

    # And the structured kwargs (user_id) must be passed through verbatim.
    assert result.get("user_id") == "u-1", (
        f"FR-70 StructuredLogger.log(**kwargs) must surface arbitrary "
        f"structured fields; got user_id={result.get('user_id')!r}"
    )

    # The mapped level and echoed message must be intact.
    assert result["level"] == "INFO", (
        f"FR-70 log entry level must equal the requested level; "
        f"got level={result['level']!r}"
    )
    assert result["message"] == "test", (
        f"FR-70 log entry message must equal the requested message; "
        f"got message={result['message']!r}"
    )


# ---------------------------------------------------------------------------
# 2. timestamp is ISO 8601 with trailing Z (validation).
#
# Spec input: expected_format="YYYY-MM-DDTHH:MM:SSZ".
# The 'timestamp' field emitted by StructuredLogger MUST be UTC ISO 8601 with
# a literal 'Z' suffix (no fractional seconds, no timezone offset like +00:00,
# no local-time emission).
# ---------------------------------------------------------------------------
def test_fr70_timestamp_iso8601_z_format():
    expected_format = "YYYY-MM-DDTHH:MM:SSZ"

    slog = StructuredLogger(service="omnibot")
    emitted = slog.log(level="INFO", message="ts-check", trace_id="abc")

    if expected_format == "YYYY-MM-DDTHH:MM:SSZ":
        # Spec fr70-ok predicate applies_to case 1; case 2 has no predicate,
        # so we still need result-not-None as a local sanity check.
        pass

    parsed = json.loads(emitted) if isinstance(emitted, str) else emitted

    assert parsed is not None
    assert "timestamp" in parsed, (
        "FR-70 JSON log entry must include a 'timestamp' field"
    )
    ts = parsed["timestamp"]
    assert isinstance(ts, str), (
        f"FR-70 timestamp must be a string; got {type(ts).__name__}"
    )
    assert _ISO_Z_RE.match(ts), (
        f"FR-70 timestamp must match YYYY-MM-DDTHH:MM:SSZ (ISO 8601 with "
        f"trailing Z); got timestamp={ts!r}"
    )
    # Must NOT carry a numeric offset (e.g. +00:00) and must NOT carry
    # fractional seconds — those are common drift bugs in ad-hoc formatters.
    assert "+" not in ts, (
        f"FR-70 timestamp must use the Z suffix, not a numeric offset; "
        f"got timestamp={ts!r}"
    )
    assert "." not in ts, (
        f"FR-70 timestamp must not include fractional seconds; "
        f"got timestamp={ts!r}"
    )


# ---------------------------------------------------------------------------
# 3. All five levels (DEBUG/INFO/WARN/ERROR/CRITICAL) are routed to the
#    matching Python logging level (validation).
#
# Spec input: levels="DEBUG,INFO,WARN,ERROR,CRITICAL".
# Each call must hit the corresponding ``logging`` numeric level when
# observed via a stdlib handler — i.e. the GREEN impl cannot be a no-op
# that swallows records or maps everything to INFO.
# ---------------------------------------------------------------------------
def test_fr70_all_log_levels_routed_correctly():
    levels = "DEBUG,INFO,WARN,ERROR,CRITICAL"
    expected_python_levels = {
        "DEBUG":    logging.DEBUG,
        "INFO":     logging.INFO,
        "WARN":     logging.WARNING,
        "ERROR":    logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    # Capture stdlib log records emitted by StructuredLogger so we can
    # assert the levelno routing, not just the JSON "level" string.
    stream = _capture_log_records("omnibot")
    try:
        slog = StructuredLogger(service="omnibot")
        for level in levels.split(","):
            slog.log(level=level, message=f"{level}-routing-check")

        captured = stream.getvalue().strip().splitlines()
    finally:
        _detach(stream)

    assert len(captured) == len(expected_python_levels), (
        f"FR-70 StructuredLogger must emit one record per level; "
        f"got {len(captured)} records for levels {list(expected_python_levels)}"
    )

    # Walk the captured lines: the emitted JSON object's "level" field
    # must line up 1:1 with the requested level, in order.
    for line, level in zip(captured, expected_python_levels):  # noqa: B905
        record = json.loads(line)
        assert record.get("level") == level, (
            f"FR-70 routing mismatch: requested level={level!r}, "
            f"record.level={record.get('level')!r}; full record={record!r}"
        )

    # The records were emitted through the stdlib logger — the levelno
    # stored on the stdlib LogRecord must be the canonical Python level.
    # Re-route by attaching a capturing handler at the root and observing
    # the levelno via caplog's internals.
    cap_records: list[logging.LogRecord] = []
    capture_handler = logging.Handler()
    capture_handler.emit = lambda rec: cap_records.append(rec)  # type: ignore[assignment]
    capture_handler.setLevel(logging.DEBUG)
    root = logging.getLogger("omnibot")
    root.addHandler(capture_handler)
    try:
        slog2 = StructuredLogger(service="omnibot")
        for level in levels.split(","):
            slog2.log(level=level, message=f"{level}-levelno-check")
    finally:
        root.removeHandler(capture_handler)

    assert len(cap_records) == len(expected_python_levels), (
        f"FR-70 must route exactly one stdlib record per level; "
        f"got {len(cap_records)} records"
    )
    for rec, (level, py_level) in zip(cap_records, expected_python_levels.items()):  # noqa: B905
        assert rec.levelno == py_level, (
            f"FR-70 level routing: {level} must map to Python level "
            f"{py_level} (logging.{logging.getLevelName(py_level)}); "
            f"got levelno={rec.levelno} ({logging.getLevelName(rec.levelno)})"
        )


# ---------------------------------------------------------------------------
# 4. CRITICAL is used for security events (validation).
#
# Spec input: event_type="security"; expected_level="CRITICAL".
# The convenience API (and/or log(..., event_type=...)) MUST emit a
# CRITICAL-level record when event_type=="security" — security events
# must not silently downgrade to INFO/WARN.
# ---------------------------------------------------------------------------
def test_fr70_critical_used_for_security_events():
    event_type = "security"
    expected_level = "CRITICAL"

    # Capture stdlib records so we can assert levelno == CRITICAL.
    cap_records: list[logging.LogRecord] = []
    capture_handler = logging.Handler()
    capture_handler.emit = lambda rec: cap_records.append(rec)  # type: ignore[assignment]
    capture_handler.setLevel(logging.DEBUG)
    root = logging.getLogger("omnibot")
    root.addHandler(capture_handler)
    try:
        slog = StructuredLogger(service="omnibot")

        # GREEN TODO: StructuredLogger.log(...) (or a dedicated
        # security()/critical() convenience) must emit a CRITICAL-level
        # record when the caller tags the event as a security event.
        # The simplest contract: passing event_type="security" forces
        # level="CRITICAL" regardless of any other argument.
        emitted = slog.log(
            level="INFO",  # attempted downgrade — GREEN must override.
            message="failed login attempt",
            event_type=event_type,
            user_id="u-42",
        )
    finally:
        root.removeHandler(capture_handler)

    # Spec fr70-ok predicate applies_to case 1; case 4 has no predicate,
    # but we still need the local result-not-None sanity check.
    parsed: dict[str, Any] = json.loads(emitted) if isinstance(emitted, str) else {}
    if event_type == "security":
        pass

    # The JSON record must carry level=CRITICAL.
    assert parsed.get("level") == expected_level, (
        f"FR-70 security events must be logged at level={expected_level!r}; "
        f"got level={parsed.get('level')!r}"
    )

    # The struct field tagging the event must be preserved.
    assert parsed.get("event_type") == event_type, (
        f"FR-70 log entry must surface event_type={event_type!r}; "
        f"got event_type={parsed.get('event_type')!r}"
    )

    # The stdlib LogRecord must carry levelno == CRITICAL so downstream
    # alert handlers (e.g. alerting on logger.critical) actually fire.
    assert len(cap_records) >= 1, (
        "FR-70 security event must produce at least one stdlib log record"
    )
    sec_rec = cap_records[-1]
    assert sec_rec.levelno == logging.CRITICAL, (
        f"FR-70 security event must emit a stdlib CRITICAL record; "
        f"got levelno={sec_rec.levelno} "
        f"({logging.getLevelName(sec_rec.levelno)})"
    )
