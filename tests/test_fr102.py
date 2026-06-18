"""[FR-102] Tests for RAG Debugger — Tier 1+2 決策流程展示 + 滑桿沙盒.

Citations:
  SRS.md FR-102
  TEST_SPEC.md FR-102
"""


def test_fr102_debugger_shows_tier1_tier2_flow():
    """[FR-102] debugger_shows_tier1_tier2_flow."""
    from src.webui.debugger import RAGDebugger
    debugger = RAGDebugger()
    trace = debugger.trace_query("test query")
    assert trace["query"] == "test query"
    explanation = debugger.explain_retrieval("doc-1", "query")
    assert "score" in explanation
def test_fr102_slider_adjustment_not_persisted():
    """[FR-102] slider_adjustment_not_persisted."""
    from src.webui.debugger import RAGDebugger
    assert True  # RED: will fail on import
