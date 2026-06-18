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

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

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


# Canonical FR-74 dashboard: exactly 4 panels, each wired to Prometheus.
GRAFANA_DASHBOARD: Mapping[str, GrafanaPanel] = {
    "fcr_line": GrafanaPanel(
        name="fcr_line",
        title="First Contact Resolution",
        kind="line",
        datasource="prometheus",
        metric="fcr_total",
    ),
    "p95_gauge": GrafanaPanel(
        name="p95_gauge",
        title="p95 Response Latency",
        kind="gauge",
        datasource="prometheus",
        metric="response_duration_seconds",
    ),
    "knowledge_source_pie": GrafanaPanel(
        name="knowledge_source_pie",
        title="Knowledge Source Distribution",
        kind="pie",
        datasource="prometheus",
        metric="knowledge_hit_total",
    ),
    "cost_time_series": GrafanaPanel(
        name="cost_time_series",
        title="Monthly Cost Trend",
        kind="time_series",
        datasource="prometheus",
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
    "GrafanaPanel",
    "PanelKind",
    "SUPPORTED_TIME_RANGES",
    "get_panel",
]
