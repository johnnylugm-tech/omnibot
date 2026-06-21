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

from __future__ import annotations

import contextvars
import copy
import secrets
import threading
from collections.abc import Generator
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
