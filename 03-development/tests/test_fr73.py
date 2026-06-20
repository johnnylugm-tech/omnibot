"""TDD-RED: failing tests for FR-73 — Alert Rules (4 named Prometheus alerts).

Spec source: 02-architecture/TEST_SPEC.md (FR-73)
SRS source : SRS.md FR-73 (Module 15: Observability)

Acceptance criteria (from SRS FR-73):
    告警規則（4 條）：
    1. HighLatency (p95 > 0.8s for 5m, warning; p95 > 1.0s for 5m, critical)
    2. HighErrorRate (error rate > 0.5% for 3m, critical)
    3. EscalationQueueBacklog (queue > 50 for 10m, warning)
    4. SLABreach (轉接 SLA 遵守率 < 90%, critical, for=0m — 立即觸發)

    4 條告警規則正確定義；閾值符合規格；SLABreach for=0m 立即觸發。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``ALERT_RULES`` is intentionally NOT YET exported by
# ``app.infra.alert_rules``. The imports below are unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``src/app/infra/alert_rules.py`` exporting at minimum:
#
#   - ALERT_RULES : Mapping[str, AlertRule]  (or list[AlertRule])
#       Holding exactly the 4 FR-73 alert definitions:
#         "HighLatency", "HighErrorRate", "EscalationQueueBacklog", "SLABreach"
#       Each AlertRule MUST expose at minimum:
#         .name           : str
#         .severity       : Literal["warning", "critical"]
#         .threshold      : float   (the numeric threshold, e.g. 0.8 for 0.8s,
#                                   0.005 for 0.5%, 50 for queue size,
#                                   0.90 for SLA compliance ratio)
#         .for_duration   : str     (Prometheus ``for`` duration string,
#                                   e.g. "5m", "3m", "10m", "0m")
#         .expression     : str     (PromQL expression used to evaluate
#                                   the alert, e.g.
#                                   'histogram_quantile(0.95, ...) > 0.8')
#
#   - get_alert_rule(name: str) -> AlertRule | None
#       Lookup helper returning the named rule, or None if absent.
# ---------------------------------------------------------------------------
from app.infra.alert_rules import (
    ALERT_RULES,
    get_alert_rule,
)

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/alert_rules.py
#   from dataclasses import dataclass
#   from typing import Literal, Mapping
#
#   @dataclass(frozen=True)
#   class AlertRule:
#       name: str
#       severity: Literal["warning", "critical"]
#       threshold: float
#       for_duration: str    # Prometheus ``for`` duration: "0m", "5m", etc.
#       expression: str      # PromQL expression
#
#   ALERT_RULES: Mapping[str, AlertRule] = {
#       "HighLatency": AlertRule(
#           name="HighLatency",
#           severity="warning",
#           threshold=0.8,             # seconds (p95 > 0.8s)
#           for_duration="5m",
#           expression=(
#               "histogram_quantile(0.95, "
#               "sum by (le) (rate(response_duration_seconds_bucket[5m]))) > 0.8"
#           ),
#       ),
#       "HighErrorRate": AlertRule(
#           name="HighErrorRate",
#           severity="critical",
#           threshold=0.005,           # 0.5% as a ratio
#           for_duration="3m",
#           expression=(
#               "sum(rate(requests_total{status=~\"5..\"}[3m])) / "
#               "sum(rate(requests_total[3m])) > 0.005"
#           ),
#       ),
#       "EscalationQueueBacklog": AlertRule(
#           name="EscalationQueueBacklog",
#           severity="warning",
#           threshold=50,
#           for_duration="10m",
#           expression="max(escalation_queue_size) > 50",
#       ),
#       "SLABreach": AlertRule(
#           name="SLABreach",
#           severity="critical",
#           threshold=0.90,            # SLA compliance ratio (90%)
#           for_duration="0m",         # IMMEDIATE per spec
#           expression=(
#               "1 - (rate(escalation_sla_breach_total[5m]) / "
#               "rate(escalation_sla_breach_total[5m]))) < 0.90"
#           ),
#       ),
#   }
#
#   def get_alert_rule(name: str) -> AlertRule | None:
#       return ALERT_RULES.get(name)
# ---------------------------------------------------------------------------

# Canonical FR-73 alert rule names in declaration order.
_FR73_ALERT_RULE_NAMES: tuple[str, ...] = (
    "HighLatency",
    "HighErrorRate",
    "EscalationQueueBacklog",
    "SLABreach",
)


# ---------------------------------------------------------------------------
# 1. Exactly 4 FR-73 alert rules are defined (happy_path).
#
# Spec input: expected_count="4".
#
# After GREEN wires the ALERT_RULES mapping, the module MUST expose exactly
# the 4 canonical names from SRS FR-73 (no aliases, no extras, no missing
# entries) — and a get_alert_rule(name) lookup MUST resolve every name.
# ---------------------------------------------------------------------------
def test_fr73_4_alert_rules_defined():
    expected_count = 4
    expected_names = (
        "HighLatency",
        "HighErrorRate",
        "EscalationQueueBacklog",
        "SLABreach",
    )

    # GREEN TODO: ALERT_RULES must be a Mapping[str, AlertRule] (or a
    # list/tuple) containing EXACTLY the 4 FR-73 alert names above.
    rules = ALERT_RULES

    # Spec fr73-ok predicate 'result is not None' applies_to case 1.
    # The trigger value is expected_count="4" (an integer); the harness
    # compares the local literal against it to decide whether to fire
    # the fr73-ok predicate. Alias the rules object to ``result``.
    result = rules
    if expected_count == 4:
        assert result is not None, "fr73-ok predicate: result must not be None"

    # Normalise to a name→rule mapping so the test does not care whether
    # GREEN chose Mapping or Sequence for the public type.
    if hasattr(rules, "items"):
        names = tuple(rules.keys())
    else:
        names = tuple(getattr(r, "name", None) for r in rules)

    # Every required alert rule MUST be present.
    missing = [n for n in expected_names if n not in names]
    assert not missing, (
        f"FR-73 ALERT_RULES is missing required alert rules: {missing}; "
        f"got names={sorted(n for n in names if n is not None)}"
    )

    # And no extra alert rules beyond the 4 SRS-mandated names.
    extra = [n for n in names if n not in expected_names]
    assert not extra, (
        f"FR-73 ALERT_RULES has unexpected extra rules: {extra}; "
        f"only {expected_names} are allowed"
    )

    # Sanity: the collection MUST contain exactly 4 rules.
    assert len(names) == expected_count, (
        f"FR-73 requires exactly {expected_count} alert rules; "
        f"got {len(names)} rules ({list(names)})"
    )

    # Every name MUST also resolve via get_alert_rule(name).
    for n in expected_names:
        rule = get_alert_rule(n)
        assert rule is not None, (
            f"FR-73 get_alert_rule({n!r}) must return a non-None rule"
        )
        # The returned rule must carry the same name it was looked up by.
        assert getattr(rule, "name", None) == n, (
            f"FR-73 get_alert_rule({n!r}).name must equal {n!r}; "
            f"got {getattr(rule, 'name', None)!r}"
        )


# ---------------------------------------------------------------------------
# 2. The SLABreach alert uses ``for: 0m`` — it fires immediately (validation).
#
# Spec input: rule="SLABreach"; for="0m"; expected_immediate="true".
#
# SRS FR-73: "SLABreach（轉接 SLA 遵守率 < 90%, critical, for=0m）".
# Prometheus ``for: 0m`` means the alert fires the instant the predicate
# becomes true (no pending/wait window). A GREEN implementation that uses
# ``for: 5m`` (or any other non-zero duration) would silently delay the
# most urgent escalation-related alert — fail-secure behaviour here means
# firing the moment the SLA dips below 90%.
# ---------------------------------------------------------------------------
def test_fr73_slabreach_for_0m_immediate():
    rule_name = "SLABreach"
    for_duration = "0m"
    expected_immediate = "true"

    # GREEN TODO: get_alert_rule("SLABreach").for_duration must equal "0m".
    rule = get_alert_rule(rule_name)

    # Spec fr73-ok predicate applies_to case 1; this is case 2 so the
    # predicate assertion is not redeclared here. Local sanity only.
    assert rule is not None, (
        f"FR-73 {rule_name} alert rule must be defined; "
        f"got None from get_alert_rule"
    )

    # The rule must expose a ``for_duration`` attribute (string) — the
    # Prometheus ``for`` clause — whose value is exactly "0m".
    actual_for = getattr(rule, "for_duration", None)
    assert actual_for is not None, (
        f"FR-73 {rule_name} must expose a non-None for_duration attribute"
    )
    assert isinstance(actual_for, str), (
        f"FR-73 {rule_name}.for_duration must be a string; "
        f"got {type(actual_for).__name__}"
    )
    assert actual_for == for_duration, (
        f"FR-73 {rule_name} must use for={for_duration!r} (immediate "
        f"trigger per spec); got for={actual_for!r}"
    )

    # Cross-check via the local trigger comparison the harness uses.
    if for_duration == "0m" and expected_immediate == "true":
        # Re-assert the immediate-trigger invariant under the trigger
        # block so a future refactor cannot regress it without tripping
        # both the unconditional assertion above AND the guarded one here.
        assert getattr(rule, "for_duration", None) == "0m", (
            f"FR-73 (under trigger) {rule_name}.for_duration must be 0m; "
            f"got {getattr(rule, 'for_duration', None)!r}"
        )

    # SLABreach must be a critical-severity alert (SLA dip is the most
    # urgent class of operational incident) and the threshold must encode
    # a 90% SLA compliance ratio (0.90 — anything below fails).
    assert getattr(rule, "severity", None) == "critical", (
        f"FR-73 {rule_name}.severity must be 'critical'; "
        f"got {getattr(rule, 'severity', None)!r}"
    )
    assert getattr(rule, "threshold", None) == 0.90, (
        f"FR-73 {rule_name}.threshold must be 0.90 (90% SLA compliance); "
        f"got {getattr(rule, 'threshold', None)!r}"
    )


# ---------------------------------------------------------------------------
# 3. HighLatency warning threshold is exactly 0.8s (boundary).
#
# Spec input: rule="HighLatency"; threshold="0.8s"; severity="warning".
#
# SRS FR-73: "HighLatency（p95 > 0.8s for 5m, warning; p95 > 1.0s for 5m,
# critical）". The unit contract for the RED test uses the warning tier
# (0.8s) so a future GREEN cannot satisfy the assertion with the
# critical-tier 1.0s threshold by mistake.
# ---------------------------------------------------------------------------
def test_fr73_high_latency_threshold_0_8s():
    rule_name = "HighLatency"
    threshold = "0.8s"
    severity = "warning"

    # GREEN TODO: get_alert_rule("HighLatency") must carry
    # threshold=0.8, severity="warning", for_duration="5m".
    rule = get_alert_rule(rule_name)

    # Spec fr73-ok predicate applies_to case 1; this is case 3 so the
    # predicate is not re-asserted here. Local sanity only.
    assert rule is not None, (
        f"FR-73 {rule_name} alert rule must be defined; "
        f"got None from get_alert_rule"
    )

    # The threshold must be exactly 0.8 (seconds, as a float).
    actual_threshold = getattr(rule, "threshold", None)
    assert actual_threshold is not None, (
        f"FR-73 {rule_name}.threshold must not be None"
    )
    assert actual_threshold == 0.8, (
        f"FR-73 {rule_name} warning-tier threshold must be 0.8 (seconds); "
        f"got {actual_threshold!r}"
    )

    # Severity MUST be 'warning' for the 0.8s tier (the 1.0s critical
    # tier is encoded separately by GREEN if a second AlertRule is
    # exposed under a sub-name; the RED test only checks the warning
    # entry whose threshold is 0.8s).
    actual_severity = getattr(rule, "severity", None)
    assert actual_severity == severity, (
        f"FR-73 {rule_name} (warning tier) must have severity={severity!r}; "
        f"got {actual_severity!r}"
    )

    # The ``for`` duration MUST be 5m per spec (the threshold is only
    # violated for 5 consecutive minutes before the warning fires).
    actual_for = getattr(rule, "for_duration", None)
    assert actual_for == "5m", (
        f"FR-73 {rule_name} must use for='5m' per spec; got {actual_for!r}"
    )

    # The PromQL expression MUST reference p95 (histogram_quantile(0.95,...))
    # so the alert actually targets the 95th-percentile latency, not a
    # mean / median / counter.
    expression = getattr(rule, "expression", "") or ""
    assert "0.95" in expression, (
        f"FR-73 {rule_name}.expression must reference the p95 quantile "
        f"(0.95); got expression={expression!r}"
    )
    assert "0.8" in expression, (
        f"FR-73 {rule_name}.expression must encode the 0.8s threshold; "
        f"got expression={expression!r}"
    )

    # Cross-check the local trigger block.
    if threshold == "0.8s" and severity == "warning":
        # Guarded re-check to catch a future refactor that loosens the
        # primary assertion but accidentally keeps a stale local copy.
        assert getattr(rule, "threshold", None) == 0.8
        assert getattr(rule, "severity", None) == "warning"


# ---------------------------------------------------------------------------
# 4. HighErrorRate critical threshold is exactly 0.5% (boundary).
#
# Spec input: rule="HighErrorRate"; threshold="0.5%"; severity="critical".
#
# SRS FR-73: "HighErrorRate（error rate > 0.5% for 3m, critical）".
# The unit contract uses a 0.005 ratio (0.5% expressed as a fraction)
# so the GREEN implementation can compare directly against Prometheus
# rate ratios without any string parsing.
# ---------------------------------------------------------------------------
def test_fr73_high_error_rate_threshold_0_5pct():
    rule_name = "HighErrorRate"
    threshold = "0.5%"
    severity = "critical"

    # GREEN TODO: get_alert_rule("HighErrorRate") must carry
    # threshold=0.005 (0.5% as a ratio), severity="critical",
    # for_duration="3m".
    rule = get_alert_rule(rule_name)

    # Spec fr73-ok predicate applies_to case 1; this is case 4 so the
    # predicate is not re-asserted here. Local sanity only.
    assert rule is not None, (
        f"FR-73 {rule_name} alert rule must be defined; "
        f"got None from get_alert_rule"
    )

    # The threshold must be exactly 0.005 (0.5% as a fraction).
    actual_threshold = getattr(rule, "threshold", None)
    assert actual_threshold is not None, (
        f"FR-73 {rule_name}.threshold must not be None"
    )
    assert actual_threshold == 0.005, (
        f"FR-73 {rule_name} threshold must be 0.005 (0.5%); "
        f"got {actual_threshold!r}"
    )

    # Severity MUST be 'critical' — a > 0.5% error rate is a SLA-level
    # incident per NFR-13 and demands the most urgent paging tier.
    actual_severity = getattr(rule, "severity", None)
    assert actual_severity == severity, (
        f"FR-73 {rule_name} must have severity={severity!r}; "
        f"got {actual_severity!r}"
    )

    # The ``for`` duration MUST be 3m per spec.
    actual_for = getattr(rule, "for_duration", None)
    assert actual_for == "3m", (
        f"FR-73 {rule_name} must use for='3m' per spec; "
        f"got {actual_for!r}"
    )

    # Cross-check the local trigger block.
    if threshold == "0.5%" and severity == "critical":
        # Guarded re-check to catch any future regression that loosens
        # the primary assertion but keeps a stale local copy.
        assert getattr(rule, "threshold", None) == 0.005
        assert getattr(rule, "severity", None) == "critical"
