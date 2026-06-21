"""TDD-RED: failing tests for FR-71 — Prometheus Metrics (9 metrics, labels).

Spec source: 02-architecture/TEST_SPEC.md (FR-71)
SRS source : SRS.md FR-71 (Module 15: Observability)

Acceptance criteria (from SRS FR-71):
    Prometheus Metrics（9 種，全部顯式列出）：
    1. response_duration_seconds(histogram)
    2. requests_total(counter)
    3. fcr_total(counter)
    4. knowledge_hit_total(counter, labels: tier)
    5. pii_masked_total(counter)
    6. escalation_queue_size(gauge)
    7. emotion_escalation_total(counter)
    8. escalation_sla_breach_total(counter)
    9. llm_tokens_total(counter, labels: model)

    All 9 metric names correctly defined; each metric type
    (histogram/counter/gauge) correct; labels complete; Prometheus scrape
    endpoint returns all 9 metrics.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``PROMETHEUS_METRICS`` is intentionally NOT YET
# exported by ``app.infra.prometheus_metrics``. The import below is
# unguarded: pytest MUST fail with Collection Error (Exit Code 2) because
# the module does not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/prometheus_metrics.py`` exporting
# ``PROMETHEUS_METRICS`` (a dict mapping each of the 9 metric names to a
# ``prometheus_client.Counter`` / ``Histogram`` / ``Gauge`` instance with
# the correct label set) plus a ``scrape_metrics() -> bytes`` helper that
# returns the Prometheus text-exposition payload for the registered
# metrics.
# ---------------------------------------------------------------------------
from app.infra.prometheus_metrics import PROMETHEUS_METRICS

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/prometheus_metrics.py
#   from prometheus_client import Counter, Gauge, Histogram
#
#   PROMETHEUS_METRICS = {
#       "response_duration_seconds": Histogram(
#           "response_duration_seconds",
#           "End-to-end response latency in seconds",
#       ),
#       "requests_total": Counter(
#           "requests_total",
#           "Total number of incoming requests",
#           ["platform"],
#       ),
#       "fcr_total": Counter(
#           "fcr_total",
#           "First Contact Resolution counter (resolved vs unresolved)",
#           ["outcome"],  # resolved | unresolved
#       ),
#       "knowledge_hit_total": Counter(
#           "knowledge_hit_total",
#           "Knowledge-layer hit counter, partitioned by tier",
#           ["tier"],     # FR-71 explicit label
#       ),
#       "pii_masked_total": Counter(
#           "pii_masked_total",
#           "PII masking counter, partitioned by PII type",
#           ["pii_type"],
#       ),
#       "escalation_queue_size": Gauge(
#           "escalation_queue_size",
#           "Current number of unresolved items in the escalation queue",
#           ["priority"],
#       ),
#       "emotion_escalation_total": Counter(
#           "emotion_escalation_total",
#           "Escalations triggered by the emotion module",
#       ),
#       "escalation_sla_breach_total": Counter(
#           "escalation_sla_breach_total",
#           "Escalations that breached their SLA deadline",
#           ["priority"],
#       ),
#       "llm_tokens_total": Counter(
#           "llm_tokens_total",
#           "LLM tokens consumed, partitioned by model",
#           ["model"],    # FR-71 explicit label
#       ),
#   }
#
#   def scrape_metrics() -> bytes:
#       from prometheus_client import generate_latest
#       return generate_latest()
#
# GREEN may also add convenience helpers (inc/metric_name(**labels)) but
# the dict above is the minimum required surface for the FR-71 RED tests.
# ---------------------------------------------------------------------------


# Canonical FR-71 metric names in declaration order.
_FR71_METRIC_NAMES: tuple[str, ...] = (
    "response_duration_seconds",
    "requests_total",
    "fcr_total",
    "knowledge_hit_total",
    "pii_masked_total",
    "escalation_queue_size",
    "emotion_escalation_total",
    "escalation_sla_breach_total",
    "llm_tokens_total",
)


def _scrape_payload() -> str:
    """Render the registered Prometheus metrics as text.

    The harness expects FR-71 to expose a real Prometheus scrape endpoint,
    so we render the metric registry via the prometheus_client text
    exposition format. ``generate_latest`` is only available if GREEN has
    imported ``prometheus_client`` at module load time — which it will
    because the GREEN module defines the metric objects directly.
    """
    from app.infra.prometheus_metrics import scrape_metrics

    raw = scrape_metrics()
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


# ---------------------------------------------------------------------------
# 1. All 9 FR-71 metrics are registered and scraped (happy_path).
#
# Spec input: expected_metrics="response_duration_seconds,requests_total,
# fcr_total,knowledge_hit_total,pii_masked_total,escalation_queue_size,
# emotion_escalation_total,escalation_sla_breach_total,llm_tokens_total".
#
# The GREEN module MUST expose a ``PROMETHEUS_METRICS`` dict whose keys are
# EXACTLY these 9 names, and a Prometheus scrape (text exposition) MUST
# mention every one of them — so a registry with only some of them, or a
# scrape endpoint that returns nothing, will not satisfy this test.
# ---------------------------------------------------------------------------
def test_fr71_all_9_metrics_scraped():
    expected_metrics = (
        "response_duration_seconds",
        "requests_total",
        "fcr_total",
        "knowledge_hit_total",
        "pii_masked_total",
        "escalation_queue_size",
        "emotion_escalation_total",
        "escalation_sla_breach_total",
        "llm_tokens_total",
    )

    # GREEN TODO: PROMETHEUS_METRICS must be a Mapping[str, Metric] whose
    # keys are exactly the 9 FR-71 metric names (no aliases, no extras).
    # The dict MUST also include the histogram for response_duration_seconds
    # and the gauge for escalation_queue_size — types matter.
    metrics_dict = PROMETHEUS_METRICS

    # Spec fr71-ok predicate 'result is not None' applies_to case 1.
    # The trigger value for case 1 is the comma-joined expected_metrics
    # string. The assertion variable name MUST match the predicate free
    # variable (`result`), so alias `metrics_dict` → `result`.
    result = metrics_dict
    if (
        expected_metrics
        == "response_duration_seconds,requests_total,fcr_total,"
        "knowledge_hit_total,pii_masked_total,escalation_queue_size,"
        "emotion_escalation_total,escalation_sla_breach_total,"
        "llm_tokens_total"
    ):
        assert result is not None, "fr71-ok predicate: result must not be None"

    # The dict must contain ALL 9 FR-71 metrics.
    missing = [m for m in expected_metrics if m not in metrics_dict]
    assert not missing, (
        f"FR-71 PROMETHEUS_METRICS is missing required metrics: {missing}; "
        f"got keys={sorted(metrics_dict.keys())}"
    )

    # And no extras sneak in — every key must be one of the 9 names.
    extra = [k for k in metrics_dict if k not in expected_metrics]
    assert not extra, (
        f"FR-71 PROMETHEUS_METRICS has unexpected extra keys: {extra}; "
        f"only {expected_metrics} are allowed"
    )

    # Sanity: must have exactly 9 entries.
    assert len(metrics_dict) == 9, (
        f"FR-71 requires exactly 9 metrics; got {len(metrics_dict)} entries"
    )

    # The Prometheus scrape payload (text exposition format) MUST mention
    # every one of the 9 metric names. We touch each metric with a no-op
    # increment so label-less counters actually appear in the payload,
    # then render the registry.
    from prometheus_client import REGISTRY  # local: only GREEN-side

    for name, metric in metrics_dict.items():
        # For label-bearing metrics, use a representative label sample so
        # the metric surfaces a sample line in the scrape output.
        sample_labels = _FR71_LABELS.get(name, ())
        try:
            if sample_labels:
                metric.labels(*sample_labels).inc(0)
            else:
                # Counter / Gauge / Histogram without labels → .inc(0).
                metric.inc(0)  # type: ignore[attr-defined]
        except Exception:
            # Histogram.observe is the no-op sample shape; fall back to it.
            if hasattr(metric, "observe"):
                metric.observe(0.0)  # type: ignore[attr-defined]

    payload = _scrape_payload()
    assert isinstance(payload, str), (
        f"FR-71 scrape payload must be text; got {type(payload).__name__}"
    )

    not_in_payload = [m for m in expected_metrics if m not in payload]
    assert not not_in_payload, (
        f"FR-71 scrape payload is missing required metrics: {not_in_payload}; "
        f"got payload (first 400 chars): {payload[:400]!r}"
    )

    # Each metric must be of the correct prometheus_client type.
    # response_duration_seconds → Histogram
    # requests_total / fcr_total / knowledge_hit_total / pii_masked_total /
    # emotion_escalation_total / escalation_sla_breach_total /
    # llm_tokens_total → Counter
    # escalation_queue_size → Gauge
    from prometheus_client import Counter, Gauge, Histogram  # local

    assert isinstance(metrics_dict["response_duration_seconds"], Histogram), (
        "FR-71 response_duration_seconds must be a Histogram"
    )
    counter_names = (
        "requests_total",
        "fcr_total",
        "knowledge_hit_total",
        "pii_masked_total",
        "emotion_escalation_total",
        "escalation_sla_breach_total",
        "llm_tokens_total",
    )
    for cname in counter_names:
        assert isinstance(metrics_dict[cname], Counter), (
            f"FR-71 {cname} must be a Counter; "
            f"got {type(metrics_dict[cname]).__name__}"
        )
    assert isinstance(metrics_dict["escalation_queue_size"], Gauge), (
        "FR-71 escalation_queue_size must be a Gauge"
    )

    # Reference REGISTRY to silence linters about the import being unused
    # (REGISTRY is the global default registry that all metrics register
    # against when constructed without an explicit registry arg).
    assert REGISTRY is not None


# ---------------------------------------------------------------------------
# Label-set lookup table — used by test 1 to ensure each metric surfaces a
# sample line in the scrape payload. Maps metric name → tuple of label
# values in the order the metric was declared with ``labels=[...]``.
# ---------------------------------------------------------------------------
_FR71_LABELS: dict[str, tuple[str, ...]] = {
    # No-label metrics: leave an empty tuple.
    "response_duration_seconds": (),
    "requests_total": ("telegram",),
    "fcr_total": ("resolved",),
    "knowledge_hit_total": ("rule",),
    "pii_masked_total": ("phone",),
    "escalation_queue_size": ("normal",),
    "emotion_escalation_total": (),
    "escalation_sla_breach_total": ("normal",),
    "llm_tokens_total": ("gpt-4o",),
}


# ---------------------------------------------------------------------------
# 2. knowledge_hit_total exposes the ``tier`` label (validation).
#
# Spec input: metric="knowledge_hit_total"; expected_label="tier".
# SRS FR-71 explicitly requires the ``tier`` label on knowledge_hit_total
# so the Knowledge Layer hit distribution can be partitioned by
# rule / rag / wiki / escalate at scrape time.
# ---------------------------------------------------------------------------
def test_fr71_knowledge_hit_total_has_tier_label():
    metric = "knowledge_hit_total"
    expected_label = "tier"

    # GREEN TODO: PROMETHEUS_METRICS["knowledge_hit_total"] must be a
    # prometheus_client.Counter constructed with labels=["tier"] (and
    # nothing else required, though extra labels are allowed). The
    # ``_labelnames`` attribute exposes the declared label set; the
    # ``_label_values`` dict on a child sample shows actual observed
    # label keys.
    kh_metric = PROMETHEUS_METRICS[metric]

    # Spec fr71-ok predicate applies_to case 1 only; this is case 2 so the
    # predicate assertion is not redeclared here (would trigger_mismatch on
    # the harness check since case 1 inputs don't include `metric`).
    # Local sanity: the metric object must exist (top-level check).
    assert kh_metric is not None, (
        "FR-71 PROMETHEUS_METRICS['knowledge_hit_total'] must be defined"
    )

    # The declared label set MUST include "tier".
    label_names = set(getattr(kh_metric, "_labelnames", ()))
    assert expected_label in label_names, (
        f"FR-71 {metric} must declare label {expected_label!r}; "
        f"got declared labelnames={sorted(label_names)}"
    )

    # Touching the counter with a sample must surface a sample line in the
    # scrape payload that includes labelname="tier" and a label value.
    kh_metric.labels(tier="rule").inc(0)  # type: ignore[attr-defined]
    payload = _scrape_payload()
    assert expected_label in payload, (
        f"FR-71 scrape payload must contain label {expected_label!r} "
        f"for {metric}; got payload (first 400 chars): {payload[:400]!r}"
    )


# ---------------------------------------------------------------------------
# 3. llm_tokens_total exposes the ``model`` label (validation).
#
# Spec input: metric="llm_tokens_total"; expected_label="model".
# SRS FR-71 explicitly requires the ``model`` label on llm_tokens_total
# so token usage can be partitioned by primary / fallback LLM at scrape
# time (e.g. gpt-4o vs gemini-1.5-flash).
# ---------------------------------------------------------------------------
def test_fr71_llm_tokens_total_has_model_label():
    metric = "llm_tokens_total"
    expected_label = "model"

    # GREEN TODO: PROMETHEUS_METRICS["llm_tokens_total"] must be a
    # prometheus_client.Counter constructed with labels=["model"] (and
    # nothing else required). GREEN may also add additional labels, but
    # "model" MUST be present.
    llm_metric = PROMETHEUS_METRICS[metric]

    # Spec fr71-ok predicate applies_to case 1 only; this is case 3 so the
    # predicate assertion is not redeclared here.
    # Local sanity: the metric object must exist (top-level check).
    assert llm_metric is not None, (
        "FR-71 PROMETHEUS_METRICS['llm_tokens_total'] must be defined"
    )

    label_names = set(getattr(llm_metric, "_labelnames", ()))
    assert expected_label in label_names, (
        f"FR-71 {metric} must declare label {expected_label!r}; "
        f"got declared labelnames={sorted(label_names)}"
    )

    # Touching the counter with a sample must surface a sample line in the
    # scrape payload that includes labelname="model" and a label value.
    llm_metric.labels(model="gpt-4o").inc(0)  # type: ignore[attr-defined]
    payload = _scrape_payload()
    assert expected_label in payload, (
        f"FR-71 scrape payload must contain label {expected_label!r} "
        f"for {metric}; got payload (first 400 chars): {payload[:400]!r}"
    )
