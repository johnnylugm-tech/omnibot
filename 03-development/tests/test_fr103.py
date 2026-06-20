"""TDD-RED: failing tests for FR-103 — Operations Dashboard
(FCR/p95/知識來源/成本 + 告警 + 24hr/7d/30d 時序切換).

Spec source: 02-architecture/TEST_SPEC.md (FR-103)
SRS source : SRS.md FR-103 (Module 25: 管理 WebUI)
            "Operations Dashboard：FCR 折線圖（< 90% 觸發黃色警報）；
             p95 延遲儀表（< 1.0s 綠色/> 1.0s 紅色）；
             知識來源圓餅圖（Tier 1/2/3/4 分布）；
             成本累計時序圖（月度上限 $500）；24hr/7d/30d 時序切換"

Acceptance criteria (from SRS FR-103):
    - FCR 折線圖，FCR < 90% 觸發黃色警報
    - p95 延遲儀表（< 1.0s 綠色/> 1.0s 紅色）
    - 知識來源圓餅圖（Tier 1/2/3/4 分布）
    - 成本累計時序圖（月度上限 $500）
    - 24hr/7d/30d 時序切換

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr103_fcr_below_90_triggers_yellow_alert
         Inputs: fcr="0.88"; threshold="0.90"; expected_color="yellow"
         Type  : validation
    2. test_fr103_time_range_switching_works
         Inputs: time_range="7d"; expected_data_updated="true"
         Type  : happy_path

Sub-assertion (per TEST_SPEC):
    fr103-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test isolation — Operations Dashboard fetches FCR, p95 latency, cost,
# and knowledge-source distribution metrics from the database. The
# autouse fixture stubs the data provider seam so tests fail because the
# dashboard feature logic is absent, not because of a missing DB
# connection.
#
# GREEN must expose a ``_fetch_metrics(self, time_range: str) -> dict``
# method on OperationsDashboard as the injectable seam for DB queries.
# The fixture patches it with ``raising=False`` so that if the seam is
# renamed in GREEN, the patch is silently skipped rather than erroring.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_dashboard_io(monkeypatch):
    """Stub DB metric fetching to avoid real database connections."""

    def _stub_fetch_metrics(self, time_range: str) -> dict:
        return {
            "fcr": 0.88,
            "p95_latency_ms": 500,
            "knowledge_distribution": {
                "tier1": 40,
                "tier2": 30,
                "tier3": 20,
                "tier4": 10,
            },
            "monthly_cost_usd": 200.0,
            "time_range": time_range,
        }

    monkeypatch.setattr(
        "app.admin.webui.OperationsDashboard._fetch_metrics",
        _stub_fetch_metrics,
        raising=False,
    )
    yield


# ---------------------------------------------------------------------------
# Source under test — ``OperationsDashboard`` and its companion constants
# are intentionally NOT YET exported by ``app.admin.webui``. These
# imports are unguarded: pytest MUST fail with Collection Error (Exit
# Code 2 / ImportError). That is the valid RED signal.
#
# GREEN must add to ``app/admin/webui.py``:
#
#   Constants:
#       FCR_ALERT_THRESHOLD   = 0.90         # < 90% triggers yellow alert
#       ALERT_COLOR_YELLOW    = "yellow"
#       ALERT_COLOR_GREEN     = "green"
#       VALID_TIME_RANGES     = ("24hr", "7d", "30d")
#
#   OperationsDashboard:
#       get_fcr_alert_color(self, fcr: float) -> str
#           Returns ALERT_COLOR_YELLOW when fcr < FCR_ALERT_THRESHOLD,
#           ALERT_COLOR_GREEN when fcr >= FCR_ALERT_THRESHOLD.
#       get_dashboard_data(self, time_range: str) -> object
#           Fetches metrics via _fetch_metrics(time_range) and returns
#           an object (dataclass or dict) whose ``time_range``
#           attribute/key equals the requested time_range string.
#           Valid time_ranges: "24hr", "7d", "30d".
#       _fetch_metrics(self, time_range: str) -> dict
#           Injectable seam for DB metric queries. The autouse fixture
#           above patches this to avoid real DB connections in tests.
# ---------------------------------------------------------------------------
from app.admin.webui import (  # noqa: E402
    OperationsDashboard,
    FCR_ALERT_THRESHOLD,
    ALERT_COLOR_YELLOW,
    ALERT_COLOR_GREEN,
    VALID_TIME_RANGES,
)


# ---------------------------------------------------------------------------
# 1. FCR below 90% triggers a yellow alert (validation).
#
# Spec input: fcr="0.88"; threshold="0.90"; expected_color="yellow"
# SRS FR-103: "FCR 折線圖（< 90% 觸發黃色警報）". A regression that used
# "amber" or "orange" instead of "yellow" would break the dashboard's
# KPI alert colour contract; a regression that fired at < 0.88 instead
# of < 0.90 would miss FCR values between 0.88 and 0.89.
# ---------------------------------------------------------------------------
def test_fr103_fcr_below_90_triggers_yellow_alert():
    # Spec input literals.
    fcr = 0.88          # spec: fcr="0.88"
    threshold = 0.90    # spec: threshold="0.90"
    expected_color = "yellow"  # spec: expected_color="yellow"

    # Anchor: the canonical threshold constant MUST match the spec value.
    assert FCR_ALERT_THRESHOLD == threshold, (
        f"FR-103 FCR_ALERT_THRESHOLD must be {threshold}; "
        f"got {FCR_ALERT_THRESHOLD!r}"
    )

    # Anchor: the yellow colour constant MUST use the canonical string.
    assert ALERT_COLOR_YELLOW == expected_color, (
        f"FR-103 ALERT_COLOR_YELLOW must be 'yellow'; "
        f"got {ALERT_COLOR_YELLOW!r}"
    )

    # GREEN TODO: OperationsDashboard must have
    #   get_fcr_alert_color(self, fcr: float) -> str
    dashboard = OperationsDashboard()
    assert hasattr(dashboard, "get_fcr_alert_color") and callable(
        dashboard.get_fcr_alert_color
    ), "FR-103 OperationsDashboard must expose ``get_fcr_alert_color(fcr: float) -> str``"

    result = dashboard.get_fcr_alert_color(fcr)

    # fr103-ok predicate: result is not None (applies_to case 1).
    assert result is not None, (
        "fr103-ok: get_fcr_alert_color() must not return None"
    )

    # Core assertion: FCR=0.88 < threshold=0.90 → yellow.
    assert result == ALERT_COLOR_YELLOW, (
        f"FR-103 FCR={fcr} < threshold={threshold} must trigger alert "
        f"color '{expected_color}'; got {result!r}. "
        f"SRS FR-103: 'FCR 折線圖（< 90% 觸發黃色警報）'"
    )

    # Companion invariant: FCR above threshold MUST return green so the
    # alert does not fire spuriously on healthy metrics.
    above_threshold = dashboard.get_fcr_alert_color(0.95)
    assert above_threshold == ALERT_COLOR_GREEN, (
        f"FR-103 FCR=0.95 >= threshold={threshold} must return "
        f"ALERT_COLOR_GREEN ('{ALERT_COLOR_GREEN}'); got {above_threshold!r}"
    )

    # Boundary: FCR exactly at threshold (0.90) MUST NOT trigger yellow.
    at_threshold = dashboard.get_fcr_alert_color(0.90)
    assert at_threshold == ALERT_COLOR_GREEN, (
        f"FR-103 FCR=0.90 (at threshold) must NOT trigger yellow; "
        f"got {at_threshold!r}. SRS: alert fires only when FCR < 0.90."
    )


# ---------------------------------------------------------------------------
# 2. Time range switching updates the dashboard data (happy_path).
#
# Spec input: time_range="7d"; expected_data_updated="true"
# SRS FR-103: "24hr/7d/30d 時序切換". A regression that ignored the
# time_range parameter and always returned 24hr data would silently
# break the 7d and 30d dashboard views; a regression that crashed on
# "7d" would break the most common operations view.
# ---------------------------------------------------------------------------
def test_fr103_time_range_switching_works():
    # Spec input literals.
    time_range = "7d"               # spec: time_range="7d"
    expected_data_updated = "true"  # spec: expected_data_updated="true"

    # Anchor: all three SRS-mandated time ranges MUST be in VALID_TIME_RANGES.
    for required_range in ("24hr", "7d", "30d"):
        assert required_range in VALID_TIME_RANGES, (
            f"FR-103 VALID_TIME_RANGES must include '{required_range}'; "
            f"got {VALID_TIME_RANGES!r}. SRS: '24hr/7d/30d 時序切換'"
        )

    # GREEN TODO: OperationsDashboard must have
    #   get_dashboard_data(self, time_range: str) -> object
    #   where the result has a ``time_range`` attribute or dict key.
    dashboard = OperationsDashboard()
    assert hasattr(dashboard, "get_dashboard_data") and callable(
        dashboard.get_dashboard_data
    ), "FR-103 OperationsDashboard must expose ``get_dashboard_data(time_range: str)``"

    result = dashboard.get_dashboard_data(time_range=time_range)

    # Spec fr103-ok predicate: result is not None.
    assert result is not None, (
        f"FR-103 get_dashboard_data('{time_range}') must return a non-None "
        f"result; expected_data_updated='{expected_data_updated}'"
    )

    # Core assertion: the returned data MUST echo the requested time_range,
    # proving the switch actually updated the data source.
    observed_time_range = (
        result.get("time_range")
        if isinstance(result, dict)
        else getattr(result, "time_range", None)
    )
    if expected_data_updated == "true":
        assert observed_time_range == time_range, (
            f"FR-103 get_dashboard_data('{time_range}') result must reflect "
            f"time_range='{time_range}'; got {observed_time_range!r}. "
            f"SRS FR-103: '24hr/7d/30d 時序切換'"
        )

    # Companion invariant: "24hr" and "30d" must also work — confirming
    # the switch is not hard-coded to "7d".
    for other_range in ("24hr", "30d"):
        other_result = dashboard.get_dashboard_data(time_range=other_range)
        assert other_result is not None, (
            f"FR-103 get_dashboard_data('{other_range}') must return "
            f"a non-None result"
        )
        observed_other = (
            other_result.get("time_range")
            if isinstance(other_result, dict)
            else getattr(other_result, "time_range", None)
        )
        assert observed_other == other_range, (
            f"FR-103 get_dashboard_data('{other_range}') must echo "
            f"time_range='{other_range}'; got {observed_other!r}"
        )
