"""[FR-26] Tier-1 rule matching for the HybridKnowledge orchestrator.

This module implements the FR-26 acceptance criteria from the SRS:
"Knowledge Tier 1 — 規則匹配：PostgreSQL ILIKE + keywords 精確比對；
confidence ≥ 0.80 時直接回傳（exact match 0.95，partial 0.7）；LIMIT 5".

Tier 1 is the fast-path: a single ILIKE query against ``knowledge_base``
capped at ``LIMIT 5`` so a generic term like "訂單" cannot blow the
result-set size. When the best row's confidence is at least 0.80 the
caller short-circuits Tier 2 (RAG + RRF); otherwise it falls through
to ``_rag_match`` / ``_wiki_match``.

Confidence scoring per SRS FR-26:
    - exact match (row matches the entire query) → 0.95
    - partial match (substring / keyword hit)    → 0.70
Both are derived from the row's ``match_type`` column when present;
when the column is missing we infer the same shape from the row's
content so the scoring stays consistent.

Citations:
    - SRS.md FR-26 — "Knowledge Tier 1 — 規則匹配：PostgreSQL ILIKE +
      keywords 精確比對；confidence ≥ 0.80 時直接回傳（exact match 0.95，
      partial 0.7）；LIMIT 5"
    - SRS.md FR-26 fallback clause — "未達閾值 → 繼續 Tier 2（_rule_match
      回傳 None）"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeResult:
    """[FR-26/FR-32] Single knowledge hit returned by the hybrid pipeline.

    The frozen dataclass shape is the contract Tier 2/3/4 callers read
    from. ``source`` identifies which tier produced the hit and is one
    of ``{"rule", "rag", "wiki", "escalate"}`` per FR-32; ``knowledge_id``
    is the upstream ID in the ``knowledge_base`` table so callers can
    re-fetch or audit the row.
    """

    id: int
    content: str
    confidence: float
    source: str  # rule | rag | wiki | escalate
    knowledge_id: int


class HybridKnowledge:
    """[FR-26] Tier-1 ILIKE rule matcher with confidence-gated fall-through.

    Holds an injected SQLAlchemy-style ``session`` so tests can swap in a
    fake without standing up Postgres; no engine / socket is constructed
    inside ``__init__``.
    """

    # FR-26 thresholds. Kept as class constants so the wiring layer can
    # read them (e.g. for metrics labels) without hard-coding the numbers.
    CONFIDENCE_THRESHOLD: float = 0.80
    CONFIDENCE_EXACT: float = 0.95
    CONFIDENCE_PARTIAL: float = 0.70
    RULE_LIMIT: int = 5

    def __init__(self, session: Any) -> None:
        """[FR-26] Store the injected DB session; no real engine is built."""
        self._session = session

    # SQL template for the Tier-1 rule lookup. ``:limit`` is bound at
    # execute-time so the constant ``RULE_LIMIT`` stays the single source
    # of truth (test assertions grep the rendered statement for LIMIT).
    _RULE_SQL = (
        "SELECT id, knowledge_id, content, match_type "
        "FROM knowledge_base "
        "WHERE content ILIKE :pattern "
        "   OR :query = ANY(keywords) "
        "ORDER BY id "
        "LIMIT :limit"
    )

    def _rule_match(self, query: str) -> KnowledgeResult | None:
        """[FR-26] Tier-1 ILIKE search, capped at LIMIT ``RULE_LIMIT``.

        Issues a single SQL statement against ``knowledge_base`` using
        an ILIKE substring pattern plus a keywords-array overlap, applies
        ``RULE_LIMIT`` so a generic term cannot over-fetch, then scores
        the best row by ``match_type`` (``exact`` → 0.95, ``partial`` →
        0.70) and returns a ``KnowledgeResult`` only when the score is
        at least ``CONFIDENCE_THRESHOLD`` (0.80). A weaker hit returns
        ``None`` so the orchestrator falls through to Tier 2.
        """
        if not query:
            return None

        result = self._session.execute(
            self._RULE_SQL,
            {
                "pattern": f"%{query}%",
                "query": query,
                "limit": self.RULE_LIMIT,
            },
        )
        rows = result.fetchall()
        if not rows:
            return None

        best = rows[0]
        confidence = self._score(best, query)
        if confidence < self.CONFIDENCE_THRESHOLD:
            return None
        return self._to_result(best, confidence)

    @staticmethod
    def _to_result(row: Any, confidence: float) -> KnowledgeResult:
        """[FR-26] Build a Tier-1 ``KnowledgeResult`` from the best row."""
        return KnowledgeResult(
            id=row.id,
            content=row.content,
            confidence=confidence,
            source="rule",
            knowledge_id=row.knowledge_id,
        )

    @classmethod
    def _score(cls, row: Any, query: str) -> float:
        """[FR-26] Map a row to an exact (0.95) or partial (0.70) score.

        Prefers the explicit ``match_type`` column when present (the
        ``knowledge_base`` schema records it on insert); falls back to
        an exact-equality check on the row's content so the same scoring
        rule applies to fakes / rows that omit the column.
        """
        match_type = getattr(row, "match_type", None)
        if match_type == "exact":
            return cls.CONFIDENCE_EXACT
        if match_type == "partial":
            return cls.CONFIDENCE_PARTIAL
        return (
            cls.CONFIDENCE_EXACT if row.content == query else cls.CONFIDENCE_PARTIAL
        )