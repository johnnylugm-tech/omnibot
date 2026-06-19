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

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

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
            "1 - (rate(escalation_sla_breach_total[5m]) / "
            "rate(escalation_sla_breach_total[5m])) < 0.90"
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
