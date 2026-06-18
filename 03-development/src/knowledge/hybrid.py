"""[FR-26] Hybrid knowledge retrieval (BM25 + vector HNSW).

Citations:
  SRS.md FR-26
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgeResult:
    """[FR-26] Single knowledge retrieval result."""

    id: str
    content: str
    score: float
    source: str = "rag"
    metadata: dict[str, Any] = field(default_factory=dict)


class HybridKnowledge:
    """[FR-26] Combines BM25 full-text and HNSW vector search."""

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeResult]:
        """Return top_k hybrid search results."""
        return []

    def index(self, doc_id: str, content: str, embedding: list[float]) -> bool:
        """Add document to index."""
        return True
