"""[FR-101] Knowledge base web UI.

Citations:
  SRS.md FR-101
"""
from __future__ import annotations

from typing import Any


class KnowledgeWebUI:
    """[FR-101] Web UI for knowledge base management."""

    def list_documents(self, page: int = 1) -> dict[str, Any]:
        """Return paginated document list."""
        return {"items": [], "total": 0, "page": page}

    def upload_document(self, content: str, metadata: dict[str, Any]) -> str:
        """Upload document and return document ID."""
        return ""

    def delete_document(self, doc_id: str) -> bool:
        """Soft-delete document."""
        return True
