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

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.metrics import MetricWrapperBase

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
