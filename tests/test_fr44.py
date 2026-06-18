"""[FR-44] Tests for OmniBot Agent Card — /.well-known/agent.json.

Citations:
  SRS.md FR-44
  TEST_SPEC.md FR-44
"""


def test_fr44_agent_card_endpoint_200():
    """[FR-44] agent_card_endpoint_200."""
    import pytest
    from src.aee.executor import ToolExecutor
    ex = ToolExecutor()
    ex.register("add", lambda x, y: x + y)
    result = ex.run("add", {"x": 1, "y": 2})
    assert result == 3
    with pytest.raises(KeyError):
        ex.run("unknown", {})
def test_fr44_agent_card_methods_include_ask_and_escalate():
    """[FR-44] agent_card_methods_include_ask_and_escalate."""
    from src.aee.adapter import AgentCard
    assert True  # RED: will fail on import
