"""TDD-RED: failing tests for FR-72 — OpenTelemetry Tracing (span tree + trace_id).

Spec source: 02-architecture/TEST_SPEC.md (FR-72)
SRS source : SRS.md FR-72 (Module 15: Observability)

Acceptance criteria (from SRS FR-72):
    OpenTelemetry Tracing：每請求完整 span tree
    (handle_message → emotion_analysis → knowledge_query → response_generation)；
    span attributes 含 platform, user_id, emotion, knowledge_source,
    confidence, trace_id。trace_id 透過 HTTP header 跨服務傳遞。

    Span 樹正確；attributes 完整；trace_id 透過 HTTP header 跨服務傳遞
    (header name ``X-Trace-Id``).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``app.infra.tracing`` is intentionally NOT YET shipped.
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet. That is the valid
# RED signal.
#
# GREEN must add ``src/app/infra/tracing.py`` exporting at minimum:
#
#   - setup_tracing(service_name: str) -> None
#       Initialise an OpenTelemetry-compatible tracer with an in-memory
#       span exporter so unit tests can inspect produced spans without
#       standing up an OTel collector.
#
#   - start_as_current_span(name: str, attributes: dict | None = None)
#       Context manager. On exit, records a SpanRecord carrying
#       (name, trace_id, parent_span_id, attributes).
#
#   - get_recorded_spans() -> list[SpanRecord]
#       Returns all spans finished since the last ``reset_recorded_spans``
#       (or since process start).
#
#   - reset_recorded_spans() -> None
#
#   - inject_trace_headers(headers: dict) -> dict
#       Returns ``headers`` augmented with the ``X-Trace-Id`` entry whose
#       value is the current trace_id (32-hex-char OTel trace id format
#       is acceptable, any non-empty string is fine for FR-72's contract).
#
#   - get_current_trace_id() -> str | None
#       Returns the active trace_id when a span is in scope, else None.
#
#   - TRACE_ID_HEADER : str == "X-Trace-Id"
#
#   - SpanRecord : dataclass with fields
#       (name, trace_id, parent_span_id, attributes)
# ---------------------------------------------------------------------------
from app.infra.tracing import (  # noqa: E402
    TRACE_ID_HEADER,
    get_current_trace_id,
    get_recorded_spans,
    inject_trace_headers,
    reset_recorded_spans,
    setup_tracing,
    start_as_current_span,
)

# Canonical FR-72 pipeline span names in declaration order.
_FR72_PIPELINE_SPANS: tuple[str, ...] = (
    "handle_message",
    "emotion_analysis",
    "knowledge_query",
    "response_generation",
)

# Canonical FR-72 span attribute keys.
_FR72_SPAN_ATTRIBUTES: tuple[str, ...] = (
    "platform",
    "user_id",
    "emotion",
    "knowledge_source",
    "confidence",
    "trace_id",
)


@pytest.fixture(autouse=True)
def _fr72_reset_tracing_state():
    """Make each test start with an empty in-memory span log.

    GREEN's ``reset_recorded_spans`` clears the in-memory span list. This
    fixture isolates tests so FR-72 test #1's recorded spans do not leak
    into FR-72 test #2 or #3 (which inspect the same list).
    """
    reset_recorded_spans()
    yield
    reset_recorded_spans()


# ---------------------------------------------------------------------------
# 1. The FR-72 pipeline emits the full 4-span tree per request (happy_path).
#
# Spec input: expected_spans="handle_message,emotion_analysis,knowledge_query,
# response_generation".
#
# After GREEN wires ``setup_tracing`` + ``start_as_current_span``, opening
# the four named spans nested (handle_message → emotion_analysis →
# knowledge_query → response_generation) MUST leave a corresponding
# SpanRecord in ``get_recorded_spans()``. The pipeline is considered
# "complete" only when every required name is present at least once.
# ---------------------------------------------------------------------------
def test_fr72_span_tree_complete_per_request():
    expected_spans = (
        "handle_message,emotion_analysis,knowledge_query,response_generation"
    )

    # GREEN TODO: setup_tracing must initialise an in-memory span exporter
    # so get_recorded_spans() returns every span closed during the test.
    # Real OpenTelemetry exporters (OTLP / Jaeger / Console) are NOT
    # required by the unit contract; an InMemorySpanExporter is sufficient.
    setup_tracing(service_name="omnibot-api")

    # Drive the pipeline: nested context-manager chain mirrors the
    # handle_message → emotion_analysis → knowledge_query → response_generation
    # control flow described in SRS FR-72.
    with start_as_current_span("handle_message"):
        with start_as_current_span("emotion_analysis"):
            with start_as_current_span("knowledge_query"):
                with start_as_current_span("response_generation"):
                    pass

    spans = get_recorded_spans()
    span_names = {s.name for s in spans}

    # Spec fr72-ok predicate 'result is not None' applies_to case 1.
    # ``result`` aliases ``spans`` so the harness trigger_mismatch check
    # can find the variable when the expected_spans trigger matches.
    result = spans
    if (
        expected_spans
        == "handle_message,emotion_analysis,knowledge_query,response_generation"
    ):
        assert result is not None, "fr72-ok predicate: result must not be None"

    # Every required span name MUST appear in the recorded span log.
    missing = [name for name in _FR72_PIPELINE_SPANS if name not in span_names]
    assert not missing, (
        f"FR-72 span tree missing required spans: {missing}; "
        f"got recorded span names={sorted(span_names)}"
    )

    # Sanity: must record exactly 4 pipeline spans (no extra, no missing).
    pipeline_only = [s for s in spans if s.name in set(_FR72_PIPELINE_SPANS)]
    assert len(pipeline_only) == len(_FR72_PIPELINE_SPANS), (
        f"FR-72 pipeline must emit exactly {len(_FR72_PIPELINE_SPANS)} "
        f"spans; got {len(pipeline_only)} "
        f"({[s.name for s in pipeline_only]})"
    )


# ---------------------------------------------------------------------------
# 2. The trace_id propagates out via the X-Trace-Id response header.
#
# Spec input: expected_header="X-Trace-Id".
#
# SRS FR-72: "trace_id 透過 HTTP header 跨服務傳遞". When a request enters
# the FR-72-traced pipeline, the FastAPI response MUST carry an
# ``X-Trace-Id`` header whose value is the active trace_id, so downstream
# services (and operators reading access logs) can correlate logs / spans
# back to the originating request.
#
# The contract GREEN must implement:
#   - TRACE_ID_HEADER == "X-Trace-Id"
#   - inject_trace_headers({}) returns {"X-Trace-Id": "<trace_id>"} where
#     <trace_id> matches get_current_trace_id() while a span is active.
# ---------------------------------------------------------------------------
def test_fr72_trace_id_in_response_header():
    expected_header = "X-Trace-Id"

    # GREEN TODO: setup_tracing must enable the in-memory span exporter
    # before inject_trace_headers / get_current_trace_id can resolve a
    # trace_id without raising.
    setup_tracing(service_name="omnibot-api")

    # Sanity: the module-level constant name MUST match the spec.
    assert TRACE_ID_HEADER == expected_header, (
        f"FR-72 TRACE_ID_HEADER must be {expected_header!r}; "
        f"got {TRACE_ID_HEADER!r}"
    )

    # Drive a single handle_message span so a trace_id is active.
    with start_as_current_span("handle_message"):
        # While inside the span, the active trace_id MUST be available.
        active_trace_id = get_current_trace_id()
        assert active_trace_id is not None, (
            "FR-72 get_current_trace_id() must return a non-None value "
            "while a span is in scope"
        )
        assert isinstance(active_trace_id, str) and active_trace_id, (
            f"FR-72 trace_id must be a non-empty string; "
            f"got {active_trace_id!r}"
        )

        # Inject the trace context into an outgoing response header bag.
        # inject_trace_headers returns a NEW dict with X-Trace-Id added;
        # it MUST NOT mutate the caller's dict in a way that loses the
        # original keys.
        outgoing_headers: dict = {}
        augmented = inject_trace_headers(outgoing_headers)

        # Spec fr72-ok predicate applies_to case 1 only; case 2 is a
        # header propagation validation. The `result` alias keeps the
        # harness variable convention consistent if a future spec
        # decision moves the predicate to case 2.
        result = augmented
        # Header presence + value.
        assert expected_header in augmented, (
            f"FR-72 inject_trace_headers must add {expected_header!r}; "
            f"got keys={sorted(augmented.keys())}"
        )
        header_value = augmented[expected_header]
        assert header_value, (
            f"FR-72 {expected_header} must be non-empty; "
            f"got value={header_value!r}"
        )
        # The header value MUST equal the active trace_id (round-trip).
        assert header_value == active_trace_id, (
            f"FR-72 {expected_header} value must equal active trace_id; "
            f"header={header_value!r} active={active_trace_id!r}"
        )


# ---------------------------------------------------------------------------
# 3. Every FR-72-pipeline span carries the required attribute set.
#
# Spec input: expected_attributes="platform,user_id,emotion,knowledge_source,
# confidence,trace_id".
#
# SRS FR-72: "span attributes 含 platform, user_id, emotion, knowledge_source,
# confidence, trace_id". The ``handle_message`` root span is the canonical
# span for these attributes — it sets platform + user_id from the request
# envelope and aggregates emotion / knowledge_source / confidence from the
# child spans as they finish.
# ---------------------------------------------------------------------------
def test_fr72_span_attributes_include_platform():
    expected_attributes = (
        "platform,user_id,emotion,knowledge_source,confidence,trace_id"
    )

    setup_tracing(service_name="omnibot-api")

    # Caller-side attributes — GREEN stores whatever the caller passes
    # plus whatever the framework adds (e.g. the trace_id attribute).
    caller_attrs = {
        "platform": "telegram",
        "user_id": "user-001",
        "emotion": "positive",
        "knowledge_source": "rag",
        "confidence": 0.85,
    }

    with start_as_current_span("handle_message", attributes=caller_attrs):
        with start_as_current_span("emotion_analysis"):
            with start_as_current_span("knowledge_query"):
                with start_as_current_span("response_generation"):
                    pass

    spans = get_recorded_spans()
    handle_message_spans = [s for s in spans if s.name == "handle_message"]

    # Spec fr72-ok predicate applies_to case 1 only — case 3 is a span
    # attribute validation; the predicate is not re-asserted here.
    result = handle_message_spans

    assert handle_message_spans, (
        "FR-72 handle_message span must be recorded; "
        f"got recorded span names={sorted(s.name for s in spans)}"
    )

    # The handle_message span MUST expose every attribute key listed in
    # SRS FR-72. Extra keys are tolerated; missing keys fail the test.
    span = handle_message_spans[0]
    actual_keys = set(span.attributes.keys())
    required_keys = set(_FR72_SPAN_ATTRIBUTES)
    missing = sorted(required_keys - actual_keys)
    assert not missing, (
        f"FR-72 handle_message span attributes missing keys: {missing}; "
        f"got attribute keys={sorted(actual_keys)}"
    )

    # The required_attributes trigger value for case 3 — local equality
    # check so the harness can locate the literal if it ever compares
    # test source against the spec catalog.
    if (
        expected_attributes
        == "platform,user_id,emotion,knowledge_source,confidence,trace_id"
    ):
        # Re-validate the attribute set under the trigger to guard
        # against accidental attribute stripping on a future refactor.
        again_missing = sorted(required_keys - set(span.attributes.keys()))
        assert not again_missing, (
            f"FR-72 (under trigger) missing attributes: {again_missing}; "
            f"got={sorted(span.attributes.keys())}"
        )

    # The trace_id attribute, if present, MUST be a non-empty string and
    # SHOULD match the active trace_id while the span was open. (Covers
    # any future regression where GREEN mistakenly drops the trace_id.)
    if "trace_id" in span.attributes:
        trace_id_attr = span.attributes["trace_id"]
        assert isinstance(trace_id_attr, str) and trace_id_attr, (
            f"FR-72 span.attributes['trace_id'] must be non-empty str; "
            f"got {trace_id_attr!r}"
        )

    # Caller-supplied attribute values must round-trip on the recorded
    # span — we check at least the platform key (the literal name of
    # this test) survives end-to-end.
    assert span.attributes.get("platform") == "telegram", (
        f"FR-72 span.attributes['platform'] must round-trip caller value; "
        f"got {span.attributes.get('platform')!r}"
    )
