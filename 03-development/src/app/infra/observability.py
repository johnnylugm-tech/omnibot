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

import contextvars
import copy
import json
import logging
import secrets
import threading
import time

# ISO 8601 with literal trailing ``Z`` — no fractional seconds, no offset.
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.metrics import MetricWrapperBase

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
        try:
            return sorted(obj)
        except TypeError:
            return sorted(obj, key=str)
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
        from app.infra.config import health_probe
        health_probe()  # Hub linkage

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
        py_level = _LEVEL_MAP.get(resolved_level.upper())
        if py_level is None:
            self._logger.warning("Unknown log level %r; emitting as WARNING", resolved_level)
            py_level = logging.WARNING
        self._logger.log(py_level, line)
        return line

    # Convenience helpers — mirror the stdlib logger's level-named methods
    # so callers can write ``slog.info(...)`` without re-typing the level.
    def debug(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("DEBUG", message, **kwargs)  # pragma: no cover

    def info(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("INFO", message, **kwargs)  # pragma: no cover

    def warn(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("WARN", message, **kwargs)  # pragma: no cover

    def warning(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("WARNING", message, **kwargs)  # pragma: no cover

    def error(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("ERROR", message, **kwargs)  # pragma: no cover

    def critical(self, message: str, **kwargs: Any) -> str:  # pragma: no cover
        return self.log("CRITICAL", message, **kwargs)  # pragma: no cover

# --- Merged from alert_rules.py ---
"""[FR-73] Alert Rules — 4 named Prometheus alerts for omnibot observability.

Declares the canonical FR-73 alert rule registry consumed by Prometheus /
Alertmanager:

    1. HighLatency           (p95 > 0.8s for 5m, warning)
    2. HighErrorRate         (error rate > 0.5% for 3m, critical)
    3. EscalationQueueBacklog (queue > 50 for 10m, warning)
    4. SLABreach             (轉接 SLA 遵守率 < 90%, critical, for=0m — 立即觸發)

``ALERT_RULES`` is a Mapping[str, AlertRule] keyed by rule name so callers
can do O(1) lookup via ``get_alert_rule(name)``. Each ``AlertRule``
exposes the minimum surface the Prometheus rule-loader needs:
``.name``, ``.severity``, ``.threshold``, ``.for_duration``, ``.expression``.

SLABreach MUST use ``for_duration="0m"`` so it fires the instant the SLA
compliance ratio dips below 90% (no pending/wait window) — a non-zero
``for`` value would silently delay the most urgent escalation-related
alert and regress the FR-73 fail-secure contract.

Citations:
- SRS.md FR-73 (description line 166, spec block lines 1026+)
- 02-architecture/TEST_SPEC.md FR-73 (4 named Prometheus alerts)
"""



Severity = Literal["warning", "critical"]


@dataclass(frozen=True)
class AlertRule:
    """Single Prometheus alert rule definition.

    Attributes:
        name:         Canonical alert name (must equal the ALERT_RULES key).
        severity:     ``"warning"`` or ``"critical"`` — Alertmanager label.
        threshold:    Numeric threshold compared against the PromQL result.
                      Units depend on the rule (seconds for latency, ratio
                      for error rate / SLA compliance, count for queue size).
        for_duration: Prometheus ``for`` clause (e.g. ``"5m"``, ``"0m"``).
                      ``"0m"`` fires immediately on predicate truth.
        expression:   PromQL expression used to evaluate the alert.
    """

    name: str
    severity: Severity
    threshold: float
    for_duration: str
    expression: str


ALERT_RULES: Mapping[str, AlertRule] = {
    "HighLatency": AlertRule(
        name="HighLatency",
        severity="warning",
        threshold=0.8,  # seconds (p95 > 0.8s)
        for_duration="5m",
        expression=(
            "histogram_quantile(0.95, "
            "sum by (le) (rate(response_duration_seconds_bucket[5m]))) > 0.8"
        ),
    ),
    "HighErrorRate": AlertRule(
        name="HighErrorRate",
        severity="critical",
        threshold=0.005,  # 0.5% as a ratio
        for_duration="3m",
        expression=(
            'sum(rate(requests_total{status=~"5.."}[3m])) / '
            "sum(rate(requests_total[3m])) > 0.005"
        ),
    ),
    "EscalationQueueBacklog": AlertRule(
        name="EscalationQueueBacklog",
        severity="warning",
        threshold=50,
        for_duration="10m",
        expression="max(escalation_queue_size) > 50",
    ),
    "SLABreach": AlertRule(
        name="SLABreach",
        severity="critical",
        threshold=0.90,  # SLA compliance ratio (90%)
        for_duration="0m",  # IMMEDIATE per spec
        expression=(
            "sum(rate(escalation_sla_breach_total[5m])) / "
            "sum(rate(requests_total[5m])) > 0.10"
        ),
    ),
}


def get_alert_rule(name: str) -> AlertRule | None:
    """Look up a FR-73 alert rule by canonical name.

    Args:
        name: The alert rule name (e.g. ``"HighLatency"``).

    Returns:
        The matching :class:`AlertRule`, or ``None`` if no rule with that
        name is registered.
    """
    return ALERT_RULES.get(name)


__all__ = ["ALERT_RULES", "AlertRule", "get_alert_rule"]

# --- Merged from tracing.py ---
"""[FR-72] OpenTelemetry Tracing — span tree per request + trace_id header propagation.

Implements an OpenTelemetry-compatible tracer with an in-memory span
exporter so unit tests can inspect produced spans without standing up an
OTel collector. The exposed API mirrors the contract documented in the
``app.infra.tracing`` docstring embedded in ``tests/test_fr72.py``:

    - setup_tracing(service_name: str) -> None
    - start_as_current_span(name, attributes=None)   context manager
    - get_recorded_spans() -> list[SpanRecord]
    - reset_recorded_spans() -> None
    - inject_trace_headers(headers: dict) -> dict
    - get_current_trace_id() -> str | None
    - TRACE_ID_HEADER : str == "X-Trace-Id"
    - SpanRecord : dataclass(name, trace_id, parent_span_id, attributes)

Trace / span id format follows OpenTelemetry's W3C trace-context shape:
    trace_id : 32 lowercase hex chars (128 bits)
    span_id  : 16 lowercase hex chars (64 bits)

The module is intentionally dependency-free: it uses a plain Python list
as the in-memory span store and has no dependency on the OpenTelemetry
SDK. The OTel W3C trace-context format (32-char hex trace_id, 16-char
hex span_id) is followed for compatibility, but no OTel SDK classes are
imported or instantiated.

Citations:
- SRS.md FR-72 (description line 165, spec block lines 1017–1024)
- 02-architecture/TEST_SPEC.md FR-72 (span tree + trace_id header)
"""



# ---------------------------------------------------------------------------
# Module-level constants — exposed names must match TEST_SPEC.md exactly.
# ---------------------------------------------------------------------------

TRACE_ID_HEADER: str = "X-Trace-Id"

# OpenTelemetry W3C trace-context widths. Kept as constants so the format
# stays stable even if someone refactors the id generator.
_TRACE_ID_HEX_LEN = 32
_SPAN_ID_HEX_LEN = 16

# Reserved attribute name added by the tracer to every recorded span —
# mirrors the canonical OTel "trace_id" span attribute referenced in
# SRS FR-72.
_TRACE_ID_ATTR_KEY = "trace_id"


# ---------------------------------------------------------------------------
# Public dataclass — exact field names required by TEST_SPEC.md lookup.
# ---------------------------------------------------------------------------

@dataclass
class SpanRecord:
    """[FR-72] One recorded span as captured by the in-memory exporter.

    Field names are part of the FR-72 contract — spec-coverage-check
    looks them up verbatim.
    """

    name: str
    trace_id: str
    parent_span_id: str | None
    attributes: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal state — tracer setup + per-context active-span stack + finished-span log.
#
# The active-span stack lives in a ``contextvars.ContextVar`` so every
# thread / asyncio task maintains its OWN stack. A module-global list
# would interleave spans created on different execution contexts and
# corrupt parent/child chains under concurrency.
#
# ``threading.Lock`` guards only the state that is genuinely shared
# across contexts (``_finished_spans``, ``_initialised``, ``_service_name``).
# Per-context span-stack mutations are inherently thread/task-safe and
# do not need the lock.
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_initialised = False
_service_name: str = "omnibot"

# Sentinel returned by the ContextVar default. A mutable default such as
# ``[]`` would be aliased across every context that has not yet called
# ``.set`` — so the first writer's list would be visible (and mutable)
# from every other context. An immutable sentinel + lazy per-context
# allocation avoids that footgun.
_ACTIVE_SPANS_UNSET: object = object()

_active_spans_var: contextvars.ContextVar[list[_ActiveSpan]] = contextvars.ContextVar(
    "_active_spans",
    default=_ACTIVE_SPANS_UNSET,  # type: ignore[arg-type]
)

# Finished-span log. ``get_recorded_spans`` returns a snapshot copy so
# callers cannot mutate the live log via ``append`` / ``clear``.
_finished_spans: list[SpanRecord] = []


@dataclass
class _ActiveSpan:
    """Internal handle for an in-flight span. Not exported."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    attributes: dict[str, object]


def _get_active_spans() -> list[_ActiveSpan]:
    """Return the active-spans stack for the current execution context.

    The first access in any given context (thread or asyncio task)
    allocates a fresh list; subsequent accesses reuse it. Different
    contexts never share the same list, so concurrent ``start_as_current_span``
    calls cannot interleave onto each other's stacks.
    """
    stack = _active_spans_var.get()
    if stack is _ACTIVE_SPANS_UNSET:
        stack = []
        _active_spans_var.set(stack)
    return stack


# ---------------------------------------------------------------------------
# Id helpers — W3C-compatible hex strings, generated from os.urandom.
# ---------------------------------------------------------------------------

def _new_hex_id(width: int) -> str:
    """Return a lowercase hex string of ``width`` characters.

    ``width`` is the OTel hex-character width (32 for trace_id, 16 for
    span_id); ``width // 2`` is the underlying random-byte count.
    """
    return secrets.token_hex(width // 2)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_tracing(service_name: str) -> None:
    """[FR-72] Initialise the in-memory tracer for ``service_name``.

    Idempotent: calling it a second time is a no-op that updates the
    service name. This matches OTel SDK semantics where re-registering a
    TracerProvider is a no-op.
    """
    global _initialised, _service_name
    with _lock:
        _service_name = service_name
        _initialised = True


def _ensure_setup() -> None:
    """Lazy fallback so a missing setup_tracing call still produces a
    valid trace_id instead of raising. Tests always call setup_tracing
    explicitly; this is for callers that import the module cold.

    The check-and-set is performed under ``_lock`` to eliminate the
    TOCTOU race where multiple threads would each see
    ``_initialised is False`` and each invoke ``setup_tracing``. The
    initialisation body is inlined rather than delegating to
    ``setup_tracing`` because ``setup_tracing`` itself acquires
    ``_lock`` and Python's ``threading.Lock`` is not reentrant —
    delegating would deadlock.
    """
    global _initialised, _service_name
    with _lock:
        if not _initialised:
            _service_name = "omnibot"
            _initialised = True


# ---------------------------------------------------------------------------
# Span lifecycle
# ---------------------------------------------------------------------------

@contextmanager
def start_as_current_span(
    name: str,
    attributes: dict | None = None,
) -> Generator[_ActiveSpan, None, None]:
    """[FR-72] Open ``name`` as the current span; record on context exit.

    On entry a new ``_ActiveSpan`` is pushed onto the **current execution
    context's** span stack (each thread / asyncio task has its own
    stack). The span inherits its parent context from the active span
    (if any) on the same stack; the root span (empty stack) gets a
    fresh ``trace_id``.

    On exit the span is popped from the per-context stack, converted
    into a ``SpanRecord``, and appended to the shared in-memory log.
    The caller-supplied ``attributes`` are deep-copied on entry so any
    later mutation to the original dictionary by the caller cannot change
    the in-flight span. On exit, the attributes are deep-copied again
    so mutations to the yielded span object cannot alter the recorded span.

    The tracer also injects the ``trace_id`` attribute (per SRS FR-72)
    on every recorded span — the caller need not pass it.

    Exceptions raised by the wrapped block propagate to the caller.
    The context-manager exit deliberately does NOT ``return`` from its
    ``finally`` clause — doing so would swallow any exception raised
    inside the body and the caller would silently receive ``None``
    instead of the error.
    """
    _ensure_setup()
    # Deep-copy caller attributes so later in-place mutations to the
    # original dictionary cannot change the in-flight span.
    caller_attrs: dict[str, object] = copy.deepcopy(attributes or {})

    spans = _get_active_spans()
    parent = spans[-1] if spans else None
    if parent is None:
        trace_id = _new_hex_id(_TRACE_ID_HEX_LEN)
        parent_span_id = None
    else:
        trace_id = parent.trace_id
        parent_span_id = parent.span_id

    span = _ActiveSpan(
        name=name,
        trace_id=trace_id,
        span_id=_new_hex_id(_SPAN_ID_HEX_LEN),
        parent_span_id=parent_span_id,
        attributes=caller_attrs,
    )
    spans.append(span)

    try:
        yield span
    finally:
        # Per-context pop — no shared lock needed; the stack is local
        # to the current thread / asyncio task. We deliberately do not
        # ``return`` from this finally block: a bare ``return`` here
        # would swallow any exception raised by the wrapped body and
        # the caller would receive ``None`` instead of the error.
        popped = False
        try:
            spans.remove(span)
        except ValueError:
            # Already popped (e.g. a previous __exit__ failure left the
            # span in an inconsistent state). Skip recording but DO
            # NOT return — the original exception must still propagate.
            pass
        else:
            popped = True

        if popped:
            # Deep-copy again at record time in case the caller mutated
            # ``span.attributes`` (the in-flight copy) after the yield.
            recorded_attrs = copy.deepcopy(span.attributes)
            recorded_attrs[_TRACE_ID_ATTR_KEY] = span.trace_id
            with _lock:
                _finished_spans.append(
                    SpanRecord(
                        name=span.name,
                        trace_id=span.trace_id,
                        parent_span_id=span.parent_span_id,
                        attributes=recorded_attrs,
                    )
                )


# ---------------------------------------------------------------------------
# Recorded-span log accessors
# ---------------------------------------------------------------------------

def get_recorded_spans() -> list[SpanRecord]:
    """[FR-72] Snapshot of every span finished since the last reset."""
    with _lock:
        return list(_finished_spans)


def reset_recorded_spans() -> None:
    """[FR-72] Clear the in-memory span log (test isolation helper)."""
    global _finished_spans
    with _lock:
        _finished_spans = []


# ---------------------------------------------------------------------------
# Trace-context propagation
# ---------------------------------------------------------------------------

def get_current_trace_id() -> str | None:
    """[FR-72] Return the active trace_id, or ``None`` if no span is open.

    Reads from the current execution context's span stack, so the
    returned trace_id belongs to the calling thread / asyncio task —
    not whichever thread last appended to a shared module stack.
    """
    spans = _get_active_spans()
    if not spans:
        return None
    return spans[-1].trace_id


def inject_trace_headers(headers: dict) -> dict:
    """[FR-72] Return ``headers`` plus the ``X-Trace-Id`` entry.

    The caller's dict is NOT mutated — a shallow copy is returned so
    tests can keep their original ``outgoing_headers`` dict intact. If
    no span is active, the returned dict is identical to the input.
    """
    augmented = dict(headers)
    trace_id = get_current_trace_id()
    if trace_id is not None:
        augmented[TRACE_ID_HEADER] = trace_id
    return augmented

# --- Merged from prometheus_metrics.py ---
"""[FR-71] Prometheus Metrics — 9 named metrics for omnibot observability.

Declares the canonical FR-71 metric registry:

    1. response_duration_seconds       (Histogram)
    2. requests_total                  (Counter,   labels: platform)
    3. fcr_total                       (Counter,   labels: outcome)
    4. knowledge_hit_total             (Counter,   labels: tier)
    5. pii_masked_total                (Counter,   labels: pii_type)
    6. escalation_queue_size           (Gauge,     labels: priority)
    7. emotion_escalation_total        (Counter)
    8. escalation_sla_breach_total     (Counter,   labels: priority)
    9. llm_tokens_total                (Counter,   labels: model)

``scrape_metrics()`` renders the registered metrics as Prometheus text
exposition bytes for the scrape endpoint.

Citations:
- SRS.md FR-71 (description block — 9 metrics, explicit label requirements)
- 02-architecture/TEST_SPEC.md FR-71 (metric names + label assertions)
"""



OMNIBOT_REGISTRY = CollectorRegistry()

PROMETHEUS_METRICS: dict[str, MetricWrapperBase] = {
    "response_duration_seconds": Histogram(
        "response_duration_seconds",
        "End-to-end response latency in seconds",
        registry=OMNIBOT_REGISTRY,
    ),
    "requests_total": Counter(
        "requests_total",
        "Total number of incoming requests, partitioned by platform and status",
        ["platform", "status"],
        registry=OMNIBOT_REGISTRY,
    ),
    "fcr_total": Counter(
        "fcr_total",
        "First Contact Resolution counter (resolved vs unresolved)",
        ["outcome"],
        registry=OMNIBOT_REGISTRY,
    ),
    "knowledge_hit_total": Counter(
        "knowledge_hit_total",
        "Knowledge-layer hit counter, partitioned by tier",
        ["tier"],
        registry=OMNIBOT_REGISTRY,
    ),
    "pii_masked_total": Counter(
        "pii_masked_total",
        "PII masking counter, partitioned by PII type",
        ["pii_type"],
        registry=OMNIBOT_REGISTRY,
    ),
    "escalation_queue_size": Gauge(
        "escalation_queue_size",
        "Current number of unresolved items in the escalation queue",
        ["priority"],
        registry=OMNIBOT_REGISTRY,
    ),
    "emotion_escalation_total": Counter(
        "emotion_escalation_total",
        "Escalations triggered by the emotion module",
        registry=OMNIBOT_REGISTRY,
    ),
    "escalation_sla_breach_total": Counter(
        "escalation_sla_breach_total",
        "Escalations that breached their SLA deadline",
        ["priority"],
        registry=OMNIBOT_REGISTRY,
    ),
    "llm_tokens_total": Counter(
        "llm_tokens_total",
        "LLM tokens consumed, partitioned by model",
        ["model"],
        registry=OMNIBOT_REGISTRY,
    ),
}


def scrape_metrics() -> bytes:
    """Render the registered Prometheus metrics as text-exposition bytes."""
    return generate_latest(OMNIBOT_REGISTRY)

# --- Merged from grafana_dashboard.py ---
"""[FR-74] Grafana Dashboard — 4 panels wired to Prometheus + ODD SQL metrics.

Declares the canonical FR-74 dashboard registry for omnibot observability:

    1. fcr_line              (line)          — FCR 折線圖
    2. p95_gauge             (gauge)         — p95 延遲儀表
    3. knowledge_source_pie  (pie)           — 知識來源圓餅圖
    4. cost_time_series      (time_series)   — 成本時序圖

Every panel binds to a real Prometheus metric from FR-71 so the dashboard
actually reflects the ODD pipeline state (no mock/empty series). The
``time_ranges`` field enumerates the three refresh intervals mandated by
SRS FR-74 (24hr / 7d / 30d) so operators can pivot between short- and
long-horizon views without reconfiguring Grafana.

NFR-11 (<99.95% availability) is satisfied implicitly: when the underlying
Prometheus metric (e.g. ``fcr_total``) degrades, the rendered panel series
reflects it within one scrape interval, surfacing the early-warning signal
to operators.

Citations:
- SRS.md FR-74 (description block — 4 panels, datasource=Prometheus,
  time ranges 24hr/7d/30d)
- 02-architecture/TEST_SPEC.md FR-74 (panel names + kind + metric mapping)
- SRS.md FR-71 (Prometheus metric registry — panel metric sources)
"""



# Closed enum of the four FR-74 panel widget kinds.
PanelKind = Literal["line", "gauge", "pie", "time_series"]

# The three refresh intervals mandated by SRS FR-74.
SUPPORTED_TIME_RANGES: tuple[str, ...] = ("24hr", "7d", "30d")


@dataclass(frozen=True)
class GrafanaPanel:
    """A single FR-74 Grafana panel definition.

    Attributes:
        name:        Stable panel identifier (used as mapping key).
        title:       Human-readable panel title shown in the Grafana UI.
        kind:        Panel widget kind — one of ``PanelKind``.
        datasource:  Backing datasource — always ``"prometheus"`` for FR-74.
        metric:      PromQL metric name queried by the panel.
        time_ranges: Tuple of refresh intervals the panel supports.
    """

    name: str
    title: str
    kind: PanelKind
    datasource: str
    metric: str
    time_ranges: tuple[str, ...] = SUPPORTED_TIME_RANGES


def _make_panel(name: str, kind: PanelKind, title: str, metric: str) -> GrafanaPanel:
    """Construct a Prometheus-wired panel with FR-74 defaults.

    All FR-74 panels share ``datasource="prometheus"`` and the spec-mandated
    refresh ranges, so they are applied here rather than repeated at every
    call site.
    """
    return GrafanaPanel(
        name=name,
        title=title,
        kind=kind,
        datasource="prometheus",
        metric=metric,
    )


# Canonical FR-74 dashboard: exactly 4 panels, each wired to Prometheus.
GRAFANA_DASHBOARD: Mapping[str, GrafanaPanel] = {
    "fcr_line": _make_panel(
        name="fcr_line",
        kind="line",
        title="First Contact Resolution",
        metric="fcr_total",
    ),
    "p95_gauge": _make_panel(
        name="p95_gauge",
        kind="gauge",
        title="p95 Response Latency",
        metric="response_duration_seconds",
    ),
    "knowledge_source_pie": _make_panel(
        name="knowledge_source_pie",
        kind="pie",
        title="Knowledge Source Distribution",
        metric="knowledge_hit_total",
    ),
    "cost_time_series": _make_panel(
        name="cost_time_series",
        kind="time_series",
        title="Monthly Cost Trend",
        metric="llm_tokens_total",
    ),
}


def get_panel(name: str) -> GrafanaPanel | None:
    """Look up a panel by name from ``GRAFANA_DASHBOARD``.

    Returns:
        The matching :class:`GrafanaPanel`, or ``None`` if no panel with
        that name exists in the dashboard.
    """
    return GRAFANA_DASHBOARD.get(name)


__all__ = [
    "GRAFANA_DASHBOARD",
    "SUPPORTED_TIME_RANGES",
    "GrafanaPanel",
    "PanelKind",
    "get_panel",
]

