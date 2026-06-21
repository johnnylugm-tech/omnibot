from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# [FR-32] SRS-mandated source enum. The four values enumerate the
# tier labels the hybrid pipeline emits: Tier-1 ILIKE rule hit
# (``"rule"``), Tier-2 RAG short-circuit (``"rag"``), Tier-3 LLM
# answer (``"wiki"``), Tier-4 human escalation (``"escalate"``).
# Construction rejects any other string via ``KnowledgeResult.__post_init__``.
VALID_SOURCES: frozenset[str] = frozenset(
    {"rule", "rag", "wiki", "escalate"}
)


@dataclass(frozen=True)
class KnowledgeResult:
    """[FR-26/FR-32] Single knowledge hit returned by the hybrid pipeline.

    The frozen dataclass shape is the contract Tier 2/3/4 callers read
    from. ``source`` identifies which tier produced the hit and is
    restricted to ``VALID_SOURCES`` (``{"rule", "rag", "wiki",
    "escalate"}``) — any other string raises ``ValueError`` at
    construction so a typo at the call site cannot silently produce a
    row with a bogus source label that downstream routing fails to
    dispatch. ``knowledge_id`` is optional because ``id == -1`` is the
    SRS-mandated "non-knowledge-base" marker (escalation sentinel) and
    the upstream row id is meaningless in that case.

    Citations:
        - SRS.md FR-32 (line 75) — KnowledgeResult 資料結構：
          immutable frozen dataclass (id, content, confidence, source,
          knowledge_id(Optional))；id=-1 代表非知識庫來源；source
          限定 rule|rag|wiki|escalate.
    """

    id: int
    content: str
    confidence: float
    source: str  # MUST be in VALID_SOURCES
    knowledge_id: int | None = None

    def __post_init__(self) -> None:
        """[FR-32] Reject any ``source`` outside the SRS-mandated enum."""
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"FR-32: KnowledgeResult.source must be one of "
                f"{sorted(VALID_SOURCES)}; got source={self.source!r}"
            )


@dataclass(frozen=True)
class ParentChunk:
    """[FR-27] Parent chunk returned by ``_get_parent``.

    A parent chunk is the 500-token context block that surrounds a
    150-token child chunk; only the child is vector-indexed, and a hit
    on the child walks ``parent_id`` to fetch the wider context the
    LLM (Tier 3) actually needs. ``is_parent=True`` is the explicit
    marker callers may assert on; ``chunk_id`` differs from the child
    id by construction.
    """

    chunk_id: str
    content: str
    knowledge_id: int
    is_parent: bool = True


@dataclass(frozen=True)
class RAGFallback:
    """[FR-27] Sentinel returned by ``_rag_search_with_fallback``.

    Encodes the lateral-degradation contract: when the embedding API is
    down the Tier-2 RAG path returns ``degraded_to="tier1_ilike_only"``
    so the orchestrator can fall through to Tier-1 ILIKE; when the
    embedding call exceeds the 2.0s timeout threshold the path returns
    ``search_path="tsvector"`` so the caller knows the GIN-indexed
    full-text path was used instead.
    """

    search_path: str = "vector"  # vector | tsvector | ilike
    degraded_to: str | None = None


