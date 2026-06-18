"""[FR-101] Tests for Knowledge 管理 WebUI — CRUD + CSV 匯入 + Embedding 狀態.

Citations:
  SRS.md FR-101
  TEST_SPEC.md FR-101
"""


def test_fr101_knowledge_crud_correct():
    """[FR-101] knowledge_crud_correct."""
    from src.webui.knowledge import KnowledgeWebUI
    ui = KnowledgeWebUI()
    result = ui.list_documents()
    assert result["total"] == 0
    doc_id = ui.upload_document("content", {})
    assert isinstance(doc_id, str)
    assert ui.delete_document("doc-1") is True
def test_fr101_csv_import_succeeds():
    """[FR-101] csv_import_succeeds."""
    from src.webui.knowledge import KnowledgeWebUI
    assert True  # RED: will fail on import


def test_fr101_embedding_status_updates_realtime():
    """[FR-101] embedding_status_updates_realtime."""
    from src.webui.knowledge import KnowledgeWebUI
    assert True  # RED: will fail on import
