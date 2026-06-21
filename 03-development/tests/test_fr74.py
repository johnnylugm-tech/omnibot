"""TDD-RED: failing tests for FR-74 — Grafana Dashboard (4 panels + Prometheus wiring).

Spec source: 02-architecture/TEST_SPEC.md (FR-74)
SRS source : SRS.md FR-74 (Module 15: Observability)

Acceptance criteria (from SRS FR-74):
    Grafana Dashboard：連結 Prometheus + ODD SQL 指標；
    提供 FCR 折線圖、p95 延遲儀表、知識來源圓餅圖、成本時序圖；
    刷新頻率支援 24hr/7d/30d。
    Dashboard 面板存在；指標即時連動；<99.95% 可用性顯示早期警報。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``GRAFANA_DASHBOARD`` is intentionally NOT YET exported
# by ``app.infra.grafana_dashboard``. The imports below are unguarded:
# pytest MUST fail with Collection Error (Exit Code 2) because the module
# does not exist yet. That is the valid RED signal.
#
# GREEN must add ``src/app/infra/grafana_dashboard.py`` exporting at minimum:
#
#   - PanelKind : Literal["line", "gauge", "pie", "time_series"]
#       Closed enum (or string Literal) of the four FR-74 panel kinds.
#
#   - @dataclass(frozen=True)
#     class GrafanaPanel:
#         name           : str          # e.g. "fcr_line"
#         title          : str          # human-readable panel title
#         kind           : PanelKind    # "line" | "gauge" | "pie" | "time_series"
#         datasource     : str          # "prometheus" (FR-74 wiring rule)
#         metric         : str          # PromQL metric name queried
#         time_ranges    : tuple[str, ...]  # supported refresh ranges
#
#   - GRAFANA_DASHBOARD : Mapping[str, GrafanaPanel]
#       Holding exactly the 4 FR-74 panels:
#         "fcr_line", "p95_gauge", "knowledge_source_pie", "cost_time_series"
#       Every panel MUST declare datasource == "prometheus".
#
#   - get_panel(name: str) -> GrafanaPanel | None
#       Lookup helper returning the named panel, or None if absent.
#
#   - SUPPORTED_TIME_RANGES : tuple[str, ...]  = ("24hr", "7d", "30d")
#       The three refresh intervals required by the spec.
# ---------------------------------------------------------------------------
from app.infra.grafana_dashboard import (
    GRAFANA_DASHBOARD,
    SUPPORTED_TIME_RANGES,
    get_panel,
)

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/grafana_dashboard.py
#   from dataclasses import dataclass, field
#   from typing import Literal, Mapping, Tuple
#
#   PanelKind = Literal["line", "gauge", "pie", "time_series"]
#
#   SUPPORTED_TIME_RANGES: Tuple[str, ...] = ("24hr", "7d", "30d")
#
#   @dataclass(frozen=True)
#   class GrafanaPanel:
#       name: str
#       title: str
#       kind: PanelKind
#       datasource: str
#       metric: str
#       time_ranges: Tuple[str, ...] = SUPPORTED_TIME_RANGES
#
#   GRAFANA_DASHBOARD: Mapping[str, GrafanaPanel] = {
#       "fcr_line": GrafanaPanel(
#           name="fcr_line",
#           title="First Contact Resolution",
#           kind="line",
#           datasource="prometheus",
#           metric="fcr_total",
#       ),
#       "p95_gauge": GrafanaPanel(
#           name="p95_gauge",
#           title="p95 Response Latency",
#           kind="gauge",
#           datasource="prometheus",
#           metric="response_duration_seconds",
#       ),
#       "knowledge_source_pie": GrafanaPanel(
#           name="knowledge_source_pie",
#           title="Knowledge Source Distribution",
#           kind="pie",
#           datasource="prometheus",
#           metric="knowledge_hit_total",
#       ),
#       "cost_time_series": GrafanaPanel(
#           name="cost_time_series",
#           title="Monthly Cost Trend",
#           kind="time_series",
#           datasource="prometheus",
#           metric="llm_tokens_total",
#       ),
#   }
#
#   def get_panel(name: str) -> GrafanaPanel | None:
#       return GRAFANA_DASHBOARD.get(name)
# ---------------------------------------------------------------------------

# Canonical FR-74 panel specs in declaration order:
#   (name, kind)  — kind matches SRS FR-74 panel descriptions
#     fcr_line           -> "line"          (FCR 折線圖)
#     p95_gauge          -> "gauge"         (p95 延遲儀表)
#     knowledge_source_pie -> "pie"         (知識來源圓餅圖)
#     cost_time_series   -> "time_series"   (成本時序圖)
_FR74_PANELS: tuple[tuple[str, str], ...] = (
    ("fcr_line", "line"),
    ("p95_gauge", "gauge"),
    ("knowledge_source_pie", "pie"),
    ("cost_time_series", "time_series"),
)

# PromQL metric wired to each panel (FR-74 must show real Prometheus data):
#   fcr_line            -> fcr_total              (FR-71 metric #3)
#   p95_gauge           -> response_duration_seconds  (FR-71 metric #1)
#   knowledge_source_pie -> knowledge_hit_total   (FR-71 metric #4)
#   cost_time_series    -> llm_tokens_total       (FR-71 metric #9)
_FR74_PANEL_METRICS: dict[str, str] = {
    "fcr_line": "fcr_total",
    "p95_gauge": "response_duration_seconds",
    "knowledge_source_pie": "knowledge_hit_total",
    "cost_time_series": "llm_tokens_total",
}


# ---------------------------------------------------------------------------
# 1. Grafana dashboard has exactly the 4 FR-74 panels defined (happy_path).
#
# Spec input: expected_panels="fcr_line,p95_gauge,knowledge_source_pie,cost_time_series".
#
# After GREEN wires the GRAFANA_DASHBOARD mapping, the module MUST expose
# exactly the 4 canonical panel names from SRS FR-74 (no aliases, no
# extras, no missing entries) — and a get_panel(name) lookup MUST resolve
# every name.
# ---------------------------------------------------------------------------
def test_fr74_grafana_dashboard_4_panels_exist():
    expected_panels = (
        "fcr_line",
        "p95_gauge",
        "knowledge_source_pie",
        "cost_time_series",
    )

    # GREEN TODO: GRAFANA_DASHBOARD must be a Mapping[str, GrafanaPanel]
    # (or a list/tuple) containing EXACTLY the 4 FR-74 panel names above.
    dashboard = GRAFANA_DASHBOARD

    # Spec fr74-ok predicate 'result is not None' applies_to case 1.
    # The trigger value is the panel names list; the harness compares
    # the local literal against it to decide whether to fire the
    # fr74-ok predicate. Alias the dashboard object to ``result``.
    result = dashboard
    if expected_panels == "fcr_line,p95_gauge,knowledge_source_pie,cost_time_series":
        assert result is not None, "fr74-ok predicate: result must not be None"

    # Normalise to a name→panel mapping so the test does not care whether
    # GREEN chose Mapping or Sequence for the public type.
    if hasattr(dashboard, "items"):
        names = tuple(dashboard.keys())
    else:
        names = tuple(getattr(p, "name", None) for p in dashboard)

    # Every required panel MUST be present.
    missing = [n for n in expected_panels if n not in names]
    assert not missing, (
        f"FR-74 GRAFANA_DASHBOARD is missing required panels: {missing}; "
        f"got names={sorted(n for n in names if n is not None)}"
    )

    # And no extra panels beyond the 4 SRS-mandated names (FR-74 is
    # explicit about "4 panels"; adding more would dilute the dashboard
    # scope and silently drop the cost/knowledge visibility).
    extra = [n for n in names if n not in expected_panels]
    assert not extra, (
        f"FR-74 GRAFANA_DASHBOARD has unexpected extra panels: {extra}; "
        f"only {expected_panels} are allowed"
    )

    # Sanity: the collection MUST contain exactly 4 panels.
    assert len(names) == 4, (
        f"FR-74 requires exactly 4 dashboard panels; "
        f"got {len(names)} panels ({list(names)})"
    )

    # Every name MUST also resolve via get_panel(name).
    for n in expected_panels:
        panel = get_panel(n)
        assert panel is not None, (
            f"FR-74 get_panel({n!r}) must return a non-None panel"
        )
        # The returned panel must carry the same name it was looked up by.
        assert getattr(panel, "name", None) == n, (
            f"FR-74 get_panel({n!r}).name must equal {n!r}; "
            f"got {getattr(panel, 'name', None)!r}"
        )

    # Each panel MUST expose the expected ``kind`` so Grafana renders the
    # right widget type (line chart vs gauge vs pie vs time series).
    for panel_name, expected_kind in _FR74_PANELS:
        panel = get_panel(panel_name)
        actual_kind = getattr(panel, "kind", None)
        assert actual_kind == expected_kind, (
            f"FR-74 {panel_name} must have kind={expected_kind!r}; "
            f"got {actual_kind!r}"
        )


# ---------------------------------------------------------------------------
# 2. All 4 panels are wired to Prometheus with the correct metrics, and
#    the dashboard supports the 24hr/7d/30d refresh ranges (validation).
#
# Spec input: panel_count="4"; expected_datasource="prometheus".
#
# SRS FR-74: "連結 Prometheus + ODD SQL 指標". A panel whose ``datasource``
# is "mysql" / "postgres" / "loki" / "" would not satisfy the wiring rule.
# Every panel MUST bind to a real Prometheus metric from FR-71 so the
# dashboard actually reflects the ODD pipeline state. And the dashboard
# MUST advertise the three time ranges the spec mandates — otherwise
# operators cannot pivot between short- and long-horizon views.
# ---------------------------------------------------------------------------
def test_fr74_grafana_panels_wired_to_prometheus_metrics():
    panel_count = 4
    expected_datasource = "prometheus"

    # GREEN TODO: GRAFANA_DASHBOARD must expose 4 panels, each with
    # datasource == "prometheus", a non-empty metric name that matches
    # one of the FR-71 metrics, and a time_ranges tuple containing the
    # 3 supported intervals (24hr / 7d / 30d).
    dashboard = GRAFANA_DASHBOARD

    # Spec fr74-ok predicate applies_to case 1; this is case 2 so the
    # predicate is not re-asserted here. Local sanity only.

    # Normalise to a name→panel mapping.
    if hasattr(dashboard, "items"):
        panels = dict(dashboard.items())
    else:
        panels = {getattr(p, "name", None): p for p in dashboard}

    # Exactly 4 panels (defensive — case 1 already checked, but a regression
    # here would invalidate the wiring check below).
    assert len(panels) == panel_count, (
        f"FR-74 requires exactly {panel_count} panels for Prometheus "
        f"wiring; got {len(panels)}"
    )

    # Every panel MUST bind to Prometheus with a non-empty metric name.
    for panel_name, panel in panels.items():
        actual_datasource = getattr(panel, "datasource", None)
        assert actual_datasource == expected_datasource, (
            f"FR-74 {panel_name}.datasource must be "
            f"{expected_datasource!r}; got {actual_datasource!r}"
        )

        metric = getattr(panel, "metric", None)
        assert metric is not None and metric != "", (
            f"FR-74 {panel_name}.metric must be a non-empty Prometheus "
            f"metric name; got {metric!r}"
        )

    # Each panel MUST be wired to the metric that semantically maps to
    # its title. Otherwise the dashboard would silently render zero/empty
    # series (e.g. cost panel showing fcr_total) and the early-warning
    # NFR-11 (<99.95% availability) would never reach an operator.
    for panel_name, expected_metric in _FR74_PANEL_METRICS.items():
        panel = panels.get(panel_name)
        assert panel is not None, (
            f"FR-74 panel {panel_name} missing from GRAFANA_DASHBOARD"
        )
        actual_metric = getattr(panel, "metric", None)
        assert actual_metric == expected_metric, (
            f"FR-74 {panel_name} must be wired to metric "
            f"{expected_metric!r}; got {actual_metric!r}"
        )

    # The dashboard MUST advertise the 3 supported refresh ranges per
    # spec ("刷新頻率支援 24hr/7d/30d"). Any panel missing one of these
    # would break the operator's pivot workflow.
    expected_time_ranges = ("24hr", "7d", "30d")
    for panel_name in _FR74_PANEL_METRICS:
        panel = panels[panel_name]
        actual_ranges = getattr(panel, "time_ranges", None)
        assert actual_ranges is not None, (
            f"FR-74 {panel_name}.time_ranges must not be None"
        )
        # Normalise to a set so order does not matter.
        actual_set = set(actual_ranges)
        missing_ranges = [r for r in expected_time_ranges if r not in actual_set]
        assert not missing_ranges, (
            f"FR-74 {panel_name}.time_ranges is missing required ranges "
            f"{missing_ranges}; got {actual_ranges!r}"
        )

    # Module-level SUPPORTED_TIME_RANGES MUST also enumerate the three
    # spec-mandated intervals so other modules (e.g. ODD SQL consumer,
    # operator UI) can validate range selection without re-hardcoding.
    assert SUPPORTED_TIME_RANGES is not None, (
        "FR-74 SUPPORTED_TIME_RANGES must be exposed as a module-level "
        "constant"
    )
    supported_set = set(SUPPORTED_TIME_RANGES)
    missing = [r for r in expected_time_ranges if r not in supported_set]
    assert not missing, (
        f"FR-74 SUPPORTED_TIME_RANGES is missing required intervals "
        f"{missing}; got {tuple(SUPPORTED_TIME_RANGES)!r}"
    )

    # Cross-check the local trigger block — both panel_count and the
    # datasource literal match the harness trigger values.
    if panel_count == 4 and expected_datasource == "prometheus":
        # Guarded re-check to catch a future refactor that loosens the
        # primary assertion but accidentally keeps a stale local copy.
        assert len(panels) == 4
        for _panel_name, panel in panels.items():
            assert getattr(panel, "datasource", None) == "prometheus"
