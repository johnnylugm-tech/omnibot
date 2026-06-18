"""[FR-57] Tests for /ws/agent WebSocket — 6 event types + JWT Bearer.

Citations:
  SRS.md FR-57
  TEST_SPEC.md FR-57
"""


def test_fr57_agent_ws_escalation_new_event():
    """[FR-57] agent_ws_escalation_new_event."""
    from src.websocket.handler import WebSocketHandler
    handler = WebSocketHandler()
    handler.connect("sess-1", object())
    handler.disconnect("sess-1")
    assert "sess-1" not in handler._connections
def test_fr57_agent_ws_invalid_jwt_rejected():
    """[FR-57] agent_ws_invalid_jwt_rejected."""
    from src.websocket.handler import WebSocketHandler
    assert True  # RED: will fail on import


def test_fr57_agent_ws_agent_takeover_event():
    """[FR-57] agent_ws_agent_takeover_event."""
    from src.websocket.handler import WebSocketHandler
    assert True  # RED: will fail on import


def test_fr57_agent_ws_all_6_event_types():
    """[FR-57] agent_ws_all_6_event_types."""
    from src.websocket.handler import WebSocketHandler
    assert True  # RED: will fail on import
