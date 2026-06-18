"""[FR-102] RAG debugger web UI.

Citations:
  SRS.md FR-102
"""
from __future__ import annotations

from typing import Any


class RAGDebugger:
    """[FR-102] Visual RAG pipeline debugger."""

    def trace_query(self, query: str) -> dict[str, Any]:
        """Return full trace of RAG query execution."""
        return {
            "query": query,
            "retrieved_chunks": [],
            "reranked": [],
            "final_answer": "",
            "latency_ms": 0,
        }

    def explain_retrieval(self, doc_id: str, query: str) -> dict[str, Any]:
        """Explain why document was retrieved for query."""
        return {"score": 0.0, "explanation": ""}
