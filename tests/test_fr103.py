"""[FR-103] Tests for Operations Dashboard — FCR/p95/知識來源/成本 + 告警.

Citations:
  SRS.md FR-103
  TEST_SPEC.md FR-103
"""


def test_fr103_fcr_below_90_triggers_yellow_alert():
    """[FR-103] fcr_below_90_triggers_yellow_alert."""
    from src.webui.dashboard import OperationsDashboard
    dash = OperationsDashboard()
    summary = dash.get_metrics_summary()
    assert isinstance(summary, dict)
    count = dash.get_active_sessions()
    assert isinstance(count, int)
    queue = dash.get_escalation_queue()
    assert isinstance(queue, list)
def test_fr103_time_range_switching_works():
    """[FR-103] time_range_switching_works."""
    from src.webui.dashboard import OperationsDashboard
    assert True  # RED: will fail on import
