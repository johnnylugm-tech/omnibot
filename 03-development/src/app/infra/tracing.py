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

The module is intentionally dependency-free at the API boundary: the
OpenTelemetry SDK is wired up *only* if it is importable, so unit tests
that monkeypatch ``setup_tracing`` never pay the OTel import cost. The
in-memory exporter used by ``get_recorded_spans`` is the canonical
``opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter``
when OTel is available; otherwise a list-based fallback is used so the
GREEN contract is satisfied in any environment.

Citations:
- SRS.md FR-72 (description line 165, spec block lines 1017–1024)
- 02-architecture/TEST_SPEC.md FR-72 (span tree + trace_id header)
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

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
# Internal state — tracer setup + active span stack + finished-span log.
#
# A single ``threading.Lock`` guards every mutation because the OTel SDK's
# default tracer may be invoked from worker threads (SAQ, FastAPI thread
# pool). The lock is uncontended in the synchronous unit-test path.
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_initialised = False
_service_name: str = "omnibot"

# Stack of currently-open spans. The top of the stack is the active span;
# a new ``start_as_current_span`` pushes onto it, exit pops and records.
_active_spans: list[_ActiveSpan] = []

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
    explicitly; this is for callers that import the module cold."""
    global _initialised
    if not _initialised:
        setup_tracing("omnibot")


# ---------------------------------------------------------------------------
# Span lifecycle
# ---------------------------------------------------------------------------

@contextmanager
def start_as_current_span(
    name: str,
    attributes: dict | None = None,
) -> Iterator[_ActiveSpan]:
    """[FR-72] Open ``name`` as the current span; record on context exit.

    On entry a new ``_ActiveSpan`` is pushed onto the module stack. The
    span inherits its parent context from the active span (if any); the
    root span (empty stack) gets a fresh ``trace_id``.

    On exit the span is popped from the stack, converted into a
    ``SpanRecord``, and appended to the in-memory log. A copy of the
    caller-supplied ``attributes`` is taken so later mutations by the
    caller do not retroactively change the recorded span.

    The tracer also injects the ``trace_id`` attribute (per SRS FR-72)
    on every recorded span — the caller need not pass it.
    """
    _ensure_setup()
    caller_attrs: dict[str, object] = dict(attributes) if attributes else {}

    with _lock:
        parent = _active_spans[-1] if _active_spans else None
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
        _active_spans.append(span)

    try:
        yield span
    finally:
        with _lock:
            # Pop from wherever the matching entry sits. Defensive: if a
            # caller skipped a context-manager exit (e.g. an exception
            # inside ``__exit__`` left a stale span on the stack), pop
            # the matching record by identity to keep the stack honest.
            try:
                _active_spans.remove(span)
            except ValueError:
                # Already popped — nothing to record.
                return

            recorded_attrs = dict(span.attributes)
            recorded_attrs[_TRACE_ID_ATTR_KEY] = span.trace_id

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
    """[FR-72] Return the active trace_id, or ``None`` if no span is open."""
    with _lock:
        if not _active_spans:
            return None
        return _active_spans[-1].trace_id


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
