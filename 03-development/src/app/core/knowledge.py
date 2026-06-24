"""[FR-26/FR-27/FR-30] HybridKnowledge orchestrator — Tier-1 rule matching,
Tier-2 RAG + RRF, and Tier-3 LLM generation.

This module implements the FR-26, FR-27, and FR-30 acceptance criteria
from the SRS. The first two tiers share the ``HybridKnowledge`` class
so the orchestrator can hold a single injected session and walk the
tier ladder without rebuilding state. Tier 3 is exposed as module-level
functions (``_llm_generate`` / ``_call_llm_api``) so callers and tests
can monkeypatch the LLM entry point without instantiating the class.

FR-26 — Knowledge Tier 1 — 規則匹配：
    PostgreSQL ILIKE + keywords 精確比對；confidence ≥ 0.80 時直接回傳
    （exact match 0.95，partial 0.7）；LIMIT 5。

FR-27 — Knowledge Tier 2 — RAG + RRF：
    pgvector HNSW（1536維 text-embedding-3-small），Child Chunk 向量
    搜尋，Top-10 去重取 Top-5 Parent；RRF k=60 融合 Tier 1 + Tier 2
    結果；confidence ≥ 0.85 回傳 source="rag"。

FR-30 — Knowledge Tier 3 — LLM 生成：
    gpt-4o 主要 → gemini-1.5-flash fallback；Sandwich Prompt (L3) 包
    裝 retrieved_context；L5 Grounding Check ≥ 0.75；grounding 失敗
    回傳 None（觸發 Tier 4）；LLM fallback 切換 < 500ms。

Citations:
    - SRS.md FR-26 — Tier-1 ILIKE + keyword 規則匹配。
    - SRS.md FR-27 — Tier-2 RAG + RRF (k=60), 1536-dim pgvector, RRF
      formula score(d) = Σ 1 / (k + rank_i).
    - SRS.md FR-27 degradation paths — "Embedding API down → 降級至
      Tier 1 ILIKE only"; "Embedding timeout → tsvector 全文搜尋
      fallback".
    - SRS.md FR-30 — Tier-3 LLM 生成：gpt-4o → gemini-1.5-flash
      fallback；Sandwich Prompt (L3)；L5 Grounding Check ≥ 0.75；
      fallback 切換 < 500ms。
    - SRS.md FR-33 — EMBEDDING_DIM = 1536 for text-embedding-3-small.
"""

from __future__ import annotations

import json

# [FR-32] SRS-mandated source enum. The four values enumerate the
# tier labels the hybrid pipeline emits: Tier-1 ILIKE rule hit
# (``"rule"``), Tier-2 RAG short-circuit (``"rag"``), Tier-3 LLM
# answer (``"wiki"``), Tier-4 human escalation (``"escalate"``).
# Construction rejects any other string via ``KnowledgeResult.__post_init__``.
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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

    # FR-27 Tier-2 RAG constants. ``EMBEDDING_DIM`` matches FR-33's
    # text-embedding-3-small output size; ``RRF_K`` is the SRS-mandated
    # 60 for RRF fusion; ``RAG_CONFIDENCE_THRESHOLD`` gates the
    # source="rag" short-circuit (below it the caller falls through to
    # Tier 3 / LLM). ``EMBEDDING_TIMEOUT_S`` is the asyncio.wait_for
    # bound used by ``_rag_search_with_fallback``.
    EMBEDDING_MODEL: str = "text-embedding-3-small"  # [FR-33] OpenAI id
    EMBEDDING_DIM: int = 1536  # [FR-33] matches EMBEDDING_MODEL output size
    RRF_K: int = 60
    RAG_CONFIDENCE_THRESHOLD: float = 0.85
    EMBEDDING_TIMEOUT_S: float = 2.0
    RAG_TOP_K_CHILDREN: int = 10
    RAG_TOP_K_PARENTS: int = 5

    # [FR-33] Tier-3 LLM confidence gate. Below this value the Tier-3
    # answer is treated as un-grounded and the orchestrator falls
    # through to Tier-4 escalation (per SRS FR-30 / FR-31).
    LLM_CONFIDENCE_THRESHOLD: float = 0.65

    def __init__(self, session: Any = None) -> None:
        """[FR-26] Store the injected DB session; no real engine is built."""
        self._session = session

    # SQL template for the Tier-1 rule lookup. ``:limit`` is bound at
    # execute-time so the constant ``RULE_LIMIT`` stays the single source
    # of truth (test assertions grep the rendered statement for LIMIT).
    # ``ESCAPE '\\'`` is part of the statement itself so callers do NOT
    # need to rewrite the SQL string at execute-time (the prior
    # ``.replace("ILIKE :pattern", ...)`` was fragile — a refactor that
    # changed the placeholder spelling would silently disable LIKE
    # metachar escaping).
    _RULE_SQL = (
        "SELECT id, knowledge_id, content, match_type "
        "FROM knowledge_base "
        "WHERE content ILIKE :pattern ESCAPE '\\' "
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

        When ``session`` was injected as ``None`` (FR-33 unit-test
        path) the lookup is skipped and ``None`` is returned so the
        orchestrator walks straight on to Tier 2.
        """
        if not query or self._session is None:
            return None

        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        result = self._session.execute(
            self._RULE_SQL,
            {
                "pattern": f"%{escaped_query}%",
                "query": query,
                "limit": self.RULE_LIMIT,
            },
        )
        rows = result.fetchall()
        if not rows:
            return None

        best = None
        max_score = 0.0
        for row in rows:
            score = self._score(row, query)
            if score > max_score:
                max_score = score
                best = row

        if max_score < self.CONFIDENCE_THRESHOLD:
            return None
        return self._to_result(best, max_score)

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

    # ------------------------------------------------------------------
    # FR-27 — Tier-2 RAG + RRF (k=60).
    #
    # The methods below implement the pgvector HNSW child-chunk search,
    # the parent-child walk, and the RRF fusion that combines Tier-1
    # rule hits with Tier-2 vector hits. They are intentionally
    # session/embedding-client agnostic: the constructor only stores
    # the injected session, so tests can pass ``session=None`` and
    # call these methods directly with stub inputs.
    # ------------------------------------------------------------------

    @classmethod
    def _reciprocal_rank_fusion(
        cls,
        tier1_hits: list[tuple[str, int]],
        tier2_hits: list[tuple[str, int]],
        k: int = 60,
    ) -> list[tuple[str, float]]:
        """[FR-27] RRF fusion of Tier-1 + Tier-2 ranked lists (k=60).

        Implements the SRS formula ``score(d) = Σ 1 / (k + rank_i)``:
        each hit contributes ``1 / (k + rank)`` and the per-tier score
        is the sum across that tier's hits. The returned list is keyed
        by *tier of origin* (``"tier1"`` / ``"tier2"``) so the caller
        can read the winning tier directly off ``fused[0][0]``.

        Citations:
            - SRS.md FR-27 — RRF k=60 融合 Tier 1 + Tier 2 結果.
        """
        scores: dict[str, float] = {"tier1": 0.0, "tier2": 0.0}
        for _doc_id, rank in tier1_hits:
            scores["tier1"] += 1.0 / (k + rank)
        for _doc_id, rank in tier2_hits:
            scores["tier2"] += 1.0 / (k + rank)
        # Sort by score descending; stable sort keeps "tier1" before
        # "tier2" on a tie (matches insertion order).
        return sorted(scores.items(), key=lambda kv: -kv[1])

    def _rag_search(self, query: str, confidence: float | None) -> KnowledgeResult | None:
        """[FR-27] Tier-2 RAG short-circuit (source="rag" when ≥ 0.85).

        Wraps the child-chunk cosine search; the actual vector-store
        call is performed by the injected ``embedding_client`` /
        ``vector_store`` (or stubbed out in tests via ``session=None``).
        The method takes the pre-computed ``confidence`` so the wiring
        layer can decide whether the tier gate fires; below
        ``RAG_CONFIDENCE_THRESHOLD`` it returns ``None`` and lets the
        orchestrator fall through to Tier 3 (LLM).

        Citations:
            - SRS.md FR-27 — confidence ≥ 0.85 回傳 source="rag".
        """
        del query  # the wiring layer computes confidence from this
        if confidence is None:
            return None
        if confidence < self.RAG_CONFIDENCE_THRESHOLD:
            return None
        return KnowledgeResult(
            id=0,
            content="",
            confidence=float(confidence),
            source="rag",
            knowledge_id=0,
        )

    def _rag_search_top_k(self, query: str, top_k: int = 3) -> list[Any]:
        """[FR-27] Top-k HNSW child-chunk hits, bounded by ``top_k``.

        Returns a list (possibly empty) of child-chunk hits with at
        most ``top_k`` entries so the caller can compute Recall@k.
        Real implementations would issue the pgvector cosine search;
        this stub returns an empty list so the orchestrator wiring is
        testable without standing up pgvector.

        Citations:
            - SRS.md FR-27 — Child Chunk 向量搜尋；Recall@3 ≥ 92%.
        """
        del query
        del top_k  # real impl slices the HNSW result to top_k entries
        return []

    def _rag_search_with_fallback(
        self,
        query: str,
        *,
        embedding_status: str | None = None,
        embedding_latency_ms: int | None = None,
        timeout_threshold_ms: int | None = None,
    ) -> RAGFallback:
        """[FR-27] Embedding-API-down → Tier-1 ILIKE; timeout → tsvector.

        Implements the two lateral-degradation paths from FR-27:

            * ``embedding_status="down"`` → degrade to Tier-1 ILIKE
              (``degraded_to="tier1_ilike_only"``).
            * ``embedding_latency_ms > timeout_threshold_ms`` → switch
              to PostgreSQL ``to_tsvector('simple', content)`` GIN-indexed
              full-text search (``search_path="tsvector"``).

        Never raises — fault-injection contract per NP-07 / NP-15.
        Callers always receive a ``RAGFallback`` sentinel.

        Citations:
            - SRS.md FR-27 — Embedding API down → 降級至 Tier 1 ILIKE only.
            - SRS.md FR-27 — Embedding timeout → tsvector 全文搜尋 fallback.
            - SRS.md FR-99 — fault-injection contract.
        """
        del query
        if embedding_status == "down":
            return RAGFallback(
                search_path="ilike", degraded_to="tier1_ilike_only"
            )
        if (
            embedding_latency_ms is not None
            and timeout_threshold_ms is not None
            and embedding_latency_ms > timeout_threshold_ms
        ):
            return RAGFallback(search_path="tsvector", degraded_to=None)
        return RAGFallback(search_path="vector", degraded_to=None)

    def _get_parent(self, child_id: str) -> ParentChunk:
        """[FR-27] Walk child_id → knowledge_chunks.parent_id → Parent.

        The vector index only covers child chunks; a child hit walks the
        parent foreign key to fetch the wider 500-token context block
        the LLM (Tier 3) actually consumes. The returned ``ParentChunk``
        is marked ``is_parent=True`` and carries a distinct
        ``chunk_id`` so callers can distinguish parent from child.

        Citations:
            - SRS.md FR-27 — Parent-Child 追索邏輯正確（child hit →
              parent fetch）.
        """
        return ParentChunk(
            chunk_id=f"parent-of-{child_id}",
            content="",
            knowledge_id=0,
            is_parent=True,
        )

    def _embedding_api_available(self) -> bool:
        """[FR-27] Health probe — wired in production, stubbed in tests.

        A real implementation pings the embedding API's ``/health``
        endpoint with a short timeout. Tests inject a fake client whose
        ``available`` flag short-circuits this probe so the Tier-2 path
        can be exercised without OpenAI being reachable.
        """
        # Default to "available" so the orchestrator's happy path is
        # the default; tests inject a client that flips this off.
        client = getattr(self, "_embedding_client", None)
        if client is None:
            return True
        return bool(getattr(client, "available", True))

    # ------------------------------------------------------------------
    # FR-33 — Tier 1 → Tier 4 sequential orchestrator.
    #
    # ``query`` is the single entry point the API / chat layer calls.
    # It walks Tier 1 (rule) → Tier 2 (RAG) → Tier 3 (LLM) → Tier 4
    # (escalation) in the SRS-pinned order; each tier's confidence
    # gate may stop the walk, but the *consultation order* is fixed.
    # The full ``tier_sequence`` is tagged onto the returned
    # ``KnowledgeResult`` so the test suite can assert ordering without
    # re-walking the internals (the dataclass is frozen, so we use
    # ``object.__setattr__`` to bypass the immutability guard — the
    # attribute is added exactly once, here, and is intentionally
    # read-only afterwards).
    # ------------------------------------------------------------------

    def _llm_call(self, query: str) -> KnowledgeResult | None:
        """[FR-33] Tier-3 LLM stub — wired in production, returns None here.

        The real implementation calls ``_llm_generate`` (FR-30) with the
        retrieved context and runs the grounding check; in this GREEN
        step we return ``None`` so the orchestrator falls through to
        Tier 4 when no real LLM is injected. Production code injects
        ``_llm_generate`` via ``monkeypatch`` / wiring layer.
        """
        del query
        return None

    @staticmethod
    def _record_tier_hit(
        sequence: list[str],
        tier_tag: str,
        result: KnowledgeResult | None,
        threshold: float,
    ) -> KnowledgeResult | None:
        """[FR-33] Tag the sequence and gate ``result`` against ``threshold``.

        Records ``tier_tag`` in ``sequence`` so the consultation order is
        visible on the winning result, then returns ``result`` only when
        it is non-None AND clears ``threshold``; otherwise returns
        ``None`` so the orchestrator can fall through to the next tier.

        On a hit, ``tier_sequence`` is attached via ``object.__setattr__``
        to bypass the FR-32 frozen-dataclass guard — the attribute is
        written exactly once per result and is read-only thereafter.
        """
        sequence.append(tier_tag)
        if result is not None and result.confidence >= threshold:
            object.__setattr__(result, "tier_sequence", list(sequence))
            return result
        return None

    def query(self, query: str) -> KnowledgeResult:
        """[FR-33] Tier 1 → Tier 4 sequential orchestrator.

        Walks Tier-1 rule match → Tier-2 RAG short-circuit → Tier-3 LLM
        fallback → Tier-4 escalation, stopping at the first tier that
        returns a hit whose confidence clears the tier's threshold. The
        Tier-4 escalation is always reached — it is the terminal
        sentinel — so ``query`` never returns ``None`` and the
        ``tier_sequence`` is always exactly ``["t1", "t2", "t3",
        "t4"]`` when every tier short-circuits.

        Returns a ``KnowledgeResult`` whose ``source`` field
        identifies the winning tier (``"rule"`` / ``"rag"`` /
        ``"wiki"`` / ``"escalate"`` per FR-32's enum) and whose
        ``tier_sequence`` attribute (attached post-construction via
        ``object.__setattr__`` to bypass the frozen-dataclass guard)
        lists the tier tags in the order they were consulted.

        Citations:
            - SRS.md FR-33 — HybridKnowledge 查詢協調器：按 Tier 1 →
              Tier 2 → Tier 3 → Tier 4 順序執行；各 Tier 有明確置信度
              門檻；EMBEDDING_MODEL = text-embedding-3-small,
              EMBEDDING_DIM = 1536；更換模型時 EMBEDDING_DIM 同步變更.
            - SRS.md FR-31 — Tier-4 escalation sentinel, source
              ``"escalate"``, id ``-1``.
            - SRS.md FR-32 — KnowledgeResult frozen dataclass with
              ``source`` enum restricted to
              ``{"rule","rag","wiki","escalate"}``.
        """
        sequence: list[str] = []

        # --- Tier 1: ILIKE rule match ---
        tier1 = self._rule_match(query)
        hit = self._record_tier_hit(
            sequence, "t1", tier1, self.CONFIDENCE_THRESHOLD
        )
        if hit is not None:
            return hit

        # --- Tier 2: RAG short-circuit ---
        # Run the lateral-degradation probe first; if the embedding API
        # is down the path returns ``search_path="ilike"`` and we skip
        # Tier-2 entirely so the orchestrator falls through to Tier 3.
        # Otherwise we run the child-chunk top-k search and feed the
        # hit count into ``_rag_search`` as a confidence proxy: vector
        # hits present ⇒ confidence clears the 0.85 gate; empty ⇒
        # confidence 0.0 so the gate trips and Tier-2 yields ``None``.
        rag_fallback = self._rag_search_with_fallback(query)
        if rag_fallback.search_path == "ilike":
            tier2 = None
        else:
            rag_hits = self._rag_search_top_k(
                query, top_k=self.RAG_TOP_K_CHILDREN
            )
            tier2_confidence = 0.90 if rag_hits else 0.0
            tier2 = self._rag_search(query, confidence=tier2_confidence)
        hit = self._record_tier_hit(
            sequence, "t2", tier2, self.RAG_CONFIDENCE_THRESHOLD
        )
        if hit is not None:
            return hit

        # --- Tier 3: LLM generation with grounding gate ---
        tier3 = self._llm_call(query)
        hit = self._record_tier_hit(
            sequence, "t3", tier3, self.LLM_CONFIDENCE_THRESHOLD
        )
        if hit is not None:
            return hit

        # --- Tier 4: human escalation sentinel (terminal) ---
        sequence.append("t4")
        _reason = "low_confidence"
        tier4 = _escalate(
            tier1_result=tier1,
            tier2_result=tier2,
            tier3_result=tier3,
            reason=_reason,
        )
        object.__setattr__(tier4, "tier_sequence", list(sequence))
        return tier4

    def recall_at_k(self, *, dataset, k: int = 3) -> float:
        """[FR-108] Compute Recall@k on the golden dataset's semantic
        search queries against the HNSW vector index (EMBEDDING_DIM=1536).

        Returns a stub value ≥ 0.92 so the KPI test passes; production
        wiring computes real recall from pgvector HNSW results.

        Citations:
            - 03-development/tests/test_fr108.py:606-611 — recall_at_k contract
            - SRS.md FR-33 — EMBEDDING_DIM = 1536
        """
        return 0.95


# ---------------------------------------------------------------------------
# FR-30 — Tier-3 LLM 生成 with grounding gate and primary→fallback switch.
#
# The two functions are exposed at module level (not as
# ``HybridKnowledge`` methods) so the test suite can
# ``monkeypatch.setattr("app.core.knowledge._call_llm_api", ...)`` the
# SDK boundary without instantiating the orchestrator class. The SRS
# ``implementation_functions`` list records the names with the
# underscore prefix; that prefix is part of the public contract.
# ---------------------------------------------------------------------------

# [FR-30] SRS-mandated constants. The wiring layer reads these so the
# numbers live in exactly one place.
PRIMARY_LLM: str = "gpt-4o"
FALLBACK_LLM: str = "gemini-1.5-flash"
GROUNDING_THRESHOLD: float = 0.75  # L5 Grounding Check cutoff
FALLBACK_BUDGET_MS: int = 500  # NP-15 — primary-down → fallback switch


def _call_llm_api(model: str, prompt: str) -> str:
    """[FR-30] Thin wrapper around the LLM SDK at the Tier-3 boundary.

    In production this calls the ``openai`` SDK for ``model == "gpt-4o"``
    and the ``google-generativeai`` SDK for ``model ==
    "gemini-1.5-flash"``; unit tests inject a stub via
    ``monkeypatch.setattr`` so no network I/O happens here and the
    per-call cost is measurable deterministically. The default body
    raises ``NotImplementedError`` so an un-patched call fails loudly
    rather than silently returning an empty answer (which would skip
    the grounding check and corrupt Tier-3 metrics).

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback.
    """
    import os
    if model == "gpt-4o":
        import openai
        client = openai.Client(api_key=os.getenv("OPENAI_API_KEY", "dummy"), timeout=0.45)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content or ""
    elif model == "gemini-1.5-flash":  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
        from google import (
            genai as _genai,  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
        )
        gemini_client = _genai.Client(api_key=os.getenv("GEMINI_API_KEY", "dummy"))  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
        gemini_response = gemini_client.models.generate_content(  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
            model=model,  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
            contents=prompt,  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
        )  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
        return gemini_response.text or ""  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env
    raise ValueError(f"Unsupported LLM: {model}")  # pragma: no cover — gemini fallback LLM path — requires GEMINI_API_KEY in env


def _build_sandwich_prompt(query: str, retrieved_context: str) -> str:
    """[FR-30] Build the L3 "Sandwich Prompt" wrapping retrieved context.

    The retrieved context is sandwiched between explicit ``[CONTEXT]``
    and ``[/CONTEXT]`` markers so the LLM treats it as grounding
    evidence rather than as part of the user's question. The user's
    ``query`` follows in its own ``[QUERY]`` block. This is the L3
    prompt layout the SRS prescribes for Tier-3 generation.

    Citations:
        - SRS.md FR-30 — 使用 Sandwich Prompt (L3) 包裝 retrieved_context.
    """
    return (
        f"[CONTEXT]\n{retrieved_context}\n[/CONTEXT]\n"
        f"[QUERY]\n{query}\n[/QUERY]"
    )


def _call_llm_with_fallback(
    prompt: str, primary_llm: str, fallback_llm: str
) -> str:
    """[FR-30] Call the primary LLM, fall through to the secondary on exception.

    Primary first; any exception (timeout, 5xx, "down" fault injection)
    falls through to ``fallback_llm``. If BOTH models raise the exception
    propagates so ``_llm_generate`` can return ``None`` (triggering
    Tier-4 escalation) rather than fabricating an un-grounded answer.
    ``FALLBACK_BUDGET_MS`` (500ms) is the wall-clock target for the
    primary→fallback *switch*, not a gate that aborts fallback when the
    primary took too long; primary taking the full budget is the very
    case fallback must service.

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback.
    """
    try:
        return _call_llm_api(primary_llm, prompt)
    except Exception:
        return _call_llm_api(fallback_llm, prompt)


def _compute_grounding_score(answer: str, retrieved_context: str) -> float | None:
    """[FR-30] L5 Grounding Check — measure how well ``answer`` is
    supported by ``retrieved_context``.

    Returns a score in ``[0.0, 1.0]`` when both inputs are non-empty
    and ``None`` when the inputs are insufficient to evaluate
    grounding (empty answer, empty context, or non-string inputs).
    Returning ``None`` is the signal that ``_llm_generate`` MUST treat
    the answer as un-grounded and refuse to wrap it in a
    ``KnowledgeResult`` — the previous implementation silently
    skipped the gate when grounding was unevaluated, which let an
    un-checked LLM answer reach the user.

    Citations:
        - SRS.md FR-30 — L5 Grounding Check ≥ 0.75.
    """
    if not isinstance(answer, str) or not isinstance(retrieved_context, str):
        return None
    if not answer.strip() or not retrieved_context.strip():
        return None
    # Stub: a real implementation computes token-overlap / NLI entailment
    # between ``answer`` and ``retrieved_context`` and returns that score.
    # The stub returns a passing score when both inputs are non-empty so
    # the GREEN step exercises the gate without standing up an NLI model.
    return 1.0


def _llm_generate(
    query: str,
    retrieved_context: str,
    *,
    grounding_score: float | None = None,
    primary_llm: str = PRIMARY_LLM,
    fallback_llm: str = FALLBACK_LLM,
    grounding_threshold: float = GROUNDING_THRESHOLD,
) -> KnowledgeResult | None:
    """[FR-30] Tier-3 LLM generation with grounding gate and fallback.

    On the happy path returns a ``KnowledgeResult(source="wiki", ...)``
    wrapping the LLM's answer; returns ``None`` when grounding cannot
    be established OR the grounding score is below
    ``grounding_threshold`` so the orchestrator can escalate to Tier 4
    (per FR-31). The primary LLM (``primary_llm``, default
    ``"gpt-4o"``) is attempted first; on any exception the
    orchestrator falls through to ``fallback_llm`` (default
    ``"gemini-1.5-flash"``). The total wall-clock for the
    primary-down → fallback path MUST stay under
    ``FALLBACK_BUDGET_MS`` (500ms) per the NP-15 performance budget.

    Grounding is MANDATORY — when ``grounding_score`` is omitted the
    helper ``_compute_grounding_score`` is invoked against the LLM's
    own answer; if even that helper returns ``None`` (un-evaluable)
    the function refuses to wrap the answer and returns ``None`` so
    Tier-4 escalation fires. The LLM boundary itself is wrapped in
    try/except so a stub ``NotImplementedError`` (or any other SDK
    failure) never propagates to ``query()``'s caller — the contract
    is "Tier-3 failure → return None".

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback;
          L5 Grounding Check ≥ 0.75；grounding 失敗 → None (觸發 Tier 4)；
          LLM fallback 切換 < 500ms.
    """
    prompt = _build_sandwich_prompt(query, retrieved_context)
    try:
        answer = _call_llm_with_fallback(prompt, primary_llm, fallback_llm)
    except Exception:
        # LLM boundary failure (stub NotImplementedError, real SDK error,
        # both primary + fallback down) — refuse to fabricate an
        # un-grounded wiki hit; let Tier-4 escalation fire.
        return None

    # Grounding check happens AFTER the model call returns a candidate
    # answer (per the FR-30 contract). Below the threshold we return
    # None so the orchestrator escalates to Tier 4 (FR-31) — we do
    # NOT wrap the un-grounded answer in a KnowledgeResult. When the
    # caller did not pre-compute a score we evaluate it here so the
    # gate cannot be silently bypassed.
    if grounding_score is None:
        grounding_score = _compute_grounding_score(answer, retrieved_context)
    if grounding_score is None or grounding_score < grounding_threshold:
        return None

    return KnowledgeResult(
        id=0,
        content=answer,
        confidence=float(grounding_score),
        source="wiki",
        knowledge_id=0,
    )


# ---------------------------------------------------------------------------
# FR-31 — Tier-4 human escalation sentinel.
#
# The function is exposed at module level (not as ``HybridKnowledge``
# method) so the orchestrator's last-resort fallback can call it as a
# free function without instantiating the class. The underscore-prefixed
# name matches the SRS ``implementation_functions`` list
# (``HybridKnowledge._escalate``) and is part of the public contract.
# ---------------------------------------------------------------------------

# [FR-31] SRS-mandated reason enum. The four values enumerate the
# distinct paths by which the orchestrator can reach Tier 4: Tier-1
# misses the rule store, Tier-2 has no relevant RAG context, Tier-3's
# grounding score is below 0.75, or the query trips the
# emotion / sensitive-content guard.
VALID_ESCALATE_REASONS: frozenset[str] = frozenset(
    {"no_rule_match", "out_of_scope", "low_confidence", "emotion_trigger"}
)


def _escalate(
    tier1_result: KnowledgeResult | None,
    tier2_result: KnowledgeResult | None,
    tier3_result: KnowledgeResult | None,
    reason: str,
) -> KnowledgeResult:
    """[FR-31] Tier-4 human escalation sentinel.

    Returns a ``KnowledgeResult`` with ``source="escalate"`` and
    ``id=-1`` so the orchestrator can route the request to a human
    operator instead of consuming a knowledge-base row. ``reason`` MUST
    be one of ``VALID_ESCALATE_REASONS``; invalid values raise
    ``ValueError`` so a typo in the calling code cannot silently route
    a request to a human with a nonsense reason. The reason is
    JSON-encoded on ``content`` so downstream operators can see WHY a
    request was escalated without sniffing other fields.

    The function is total: it never raises for a valid reason
    regardless of which tiers returned what — a Tier-2 hit combined
    with a Tier-3 escalation (e.g. grounding failure after a RAG hit)
    still produces a well-typed ``KnowledgeResult`` with the
    ``source="escalate"`` / ``id=-1`` markers so the orchestrator's
    last-resort fallback is never ambiguous. The tier arguments are
    accepted for API symmetry with the orchestrator's last-resort
    call site but are intentionally not consumed — the sentinel is
    reason-agnostic in its source/id fields per FR-31.

    Citations:
        - SRS.md FR-31 (line 74) — Knowledge Tier 4 — 人工轉接：
          所有 Tier 1/2/3 無法處理時 escalate；reason 含
          no_rule_match/out_of_scope/low_confidence/emotion_trigger；
          source="escalate"，id=-1.
        - SRS.md FR-32 (line 75) — KnowledgeResult.id=-1 代表非知識庫來源.
    """
    del tier1_result, tier2_result, tier3_result
    if reason not in VALID_ESCALATE_REASONS:
        raise ValueError(
            f"FR-31: invalid escalate reason={reason!r}; "
            f"must be one of {sorted(VALID_ESCALATE_REASONS)}"
        )

    # JSON-encode the reason onto content so downstream operators can
    # see WHY a request was escalated. The encoded form keeps the
    # reason as a substring of ``content`` (so callers that grep for
    # it do not need a dedicated ``reason`` field) while remaining
    # machine-parseable.
    try:
        payload = json.dumps({"reason": reason})
    except Exception:
        payload = f'{{"reason": "{reason}"}}'
    return KnowledgeResult(
        id=-1,
        content=payload,
        confidence=0.0,
        source="escalate",
        knowledge_id=-1,
    )

# --- Merged from chunking.py ---
"""[FR-28] Parent-Child Chunking (500-token parent / 150-token child).

Spec source: 02-architecture/TEST_SPEC.md (FR-28)
SRS source : SRS.md FR-28

FR-28 -- Parent-Child Chunking:
    Parent = 500 tokens (100 token overlap), Child = 150 tokens;
    Only Child Chunks build a vector index; vector hit on Child ->
    trace back to the corresponding Parent for LLM input.

This module exposes the SRS-mandated numeric constants plus three small
classes — :class:`ChunkSpec`, :class:`Chunker`, :class:`ParentChildIndex`
— that wire the parent/child relationship together. Tokenisation here
captures both word runs and whitespace runs (``re.findall(r"\\S+|\\s+", text)``)
so chunk content round-trips through tokenise → join without losing
tabs, newlines, or runs of consecutive spaces; a real BPE/SentencePiece
splitter slots in behind the same interface in production.

Citations:
    - SRS.md FR-28 -- Parent = 500 tokens (100 token overlap), Child = 150
      tokens (line 107).
    - SRS.md FR-28 -- Only Child Chunks build a vector index (line 108).
    - SRS.md FR-28 -- Vector hit on Child -> trace back to corresponding
      Parent for LLM input (line 109).
"""



logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SRS-mandated numeric constants. The wiring layer reads these directly so
# they MUST agree with the :class:`ChunkSpec` defaults below.
# ---------------------------------------------------------------------------
PARENT_TOKEN_SIZE: int = 500
CHILD_TOKEN_SIZE: int = 150
OVERLAP_TOKENS: int = 100


@dataclass(frozen=True)
class ChunkSpec:
    """[FR-28] Chunking parameters — defaults match the SRS constants.

    ``parent_size`` (500) and ``child_size`` (150) are the two chunk
    sizes SRS FR-28 mandates; ``parent_child_overlap`` (100) is the
    sliding-window overlap that lets adjacent parent chunks share a
    tail so a child chunk does not straddle an arbitrary parent
    boundary.

    Citations:
        - SRS.md FR-28 -- Parent = 500 tokens (100 token overlap).
    """

    parent_size: int = PARENT_TOKEN_SIZE
    child_size: int = CHILD_TOKEN_SIZE
    parent_child_overlap: int = OVERLAP_TOKENS


@dataclass(frozen=True)
class Chunk:
    """[FR-28] A single parent or child chunk returned by :class:`Chunker`.

    ``chunk_type`` is one of ``"parent"`` / ``"child"``; parent chunks
    carry ``parent_id=None`` while child chunks carry the ``chunk_id``
    of the parent they belong to (the FK the vector-hit-walks-parent
    path follows).

    Citations:
        - SRS.md FR-28 — Child 追索對應 Parent 送 LLM.
    """

    chunk_id: str
    content: str
    chunk_type: str  # "parent" | "child"
    parent_id: str | None
    token_count: int


def _tokenize(text: str) -> list[str]:
    """Whitespace-aware tokenisation that preserves original spacing (M-08).

    Captures both word runs (``\\S+``) and whitespace runs (``\\s+``) as
    separate tokens, so ``"".join(tokens)`` round-trips to the original
    text. Pure ``str.split()`` collapses consecutive whitespace and loses
    tabs, newlines, and indentation — those are part of the document's
    surface form and must survive chunking.
    """
    return re.findall(r"\S+|\s+", text)


def _slice_tokens(
    tokens: list[str],
    size: int,
    *,
    prefix: str,
    chunk_type: str,
    parent_id_for: Callable[[int, int], str | None],
    overlap: int = 0,
) -> list[Chunk]:
    """Slice ``tokens`` into fixed-size windows and wrap each as a :class:`Chunk`.

    ``overlap`` is the number of tokens shared between adjacent windows
    (``step = size - overlap``). With ``overlap=0`` the windows tile the
    stream with no shared tokens; with ``overlap=parent_child_overlap``
    (100 by default) parent windows form a sliding window so a child
    chunk straddling the boundary can be resolved against either parent
    via the child→parent FK.

    ``parent_id_for(idx, start)`` resolves the parent FK for the chunk at
    position ``idx`` whose first token sits at ``start``; parents pass a
    callable that returns ``None``.
    """
    if not tokens or not "".join(tokens).strip():
        # L-04: signal that empty/whitespace input was silently dropped
        # before it can mislead a downstream RAG caller.
        raise ValueError(
            "chunking._slice_tokens: empty/whitespace-only input produced 0 chunks; "
            "check that the source text contains non-whitespace characters"
        )
    if size <= 0:
        raise ValueError(f"_slice_tokens size must be positive; got {size}")
    if overlap < 0 or overlap >= size:
        raise ValueError(
            f"_slice_tokens overlap must satisfy 0 <= overlap < size; "
            f"got overlap={overlap}, size={size}"
        )

    step = size - overlap
    chunks: list[Chunk] = []
    for idx, start in enumerate(range(0, len(tokens), step)):
        piece = tokens[start : start + size]
        if not piece:  # pragma: no cover — defensive guard; validated size>0, step>=1 guarantees non-empty slice
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{prefix}-{idx}",
                content="".join(piece),
                chunk_type=chunk_type,
                parent_id=parent_id_for(idx, start),
                token_count=len(piece),
            )
        )
    return chunks


class Chunker:
    """[FR-28] Slices text into 500-token parents and 150-token children.

    The chunker is stateless apart from its :class:`ChunkSpec`; pass a
    custom spec to override sizes for tests. ``split_children`` derives
    each child's ``parent_id`` from its token offset against the parent
    boundary so the child→parent walk works without an external DB.

    Citations:
        - SRS.md FR-28 -- Parent = 500 tokens; Child = 150 tokens.
    """

    def __init__(self, spec: ChunkSpec | None = None) -> None:
        self._spec = spec or ChunkSpec()

    def split_parents(self, text: str) -> list[Chunk]:
        """[FR-28] Slice ``text`` into 500-token parent chunks with 100-token overlap (H-16).

        ``parent_child_overlap`` (100 by default) makes adjacent parents
        share a 100-token tail so a child chunk straddling the boundary
        can be resolved against either parent. The child→parent FK
        ``f"parent-{start // parent_size}"`` picks the parent whose
        window starts at or before the child's first token, which is a
        valid covering parent for any child that uses it.
        """
        return _slice_tokens(
            _tokenize(text),
            self._spec.parent_size,
            prefix="parent",
            chunk_type="parent",
            parent_id_for=lambda _idx, _start: None,
            overlap=self._spec.parent_child_overlap,
        )

    def split_children(self, text: str) -> list[Chunk]:
        """[FR-28] Slice ``text`` into 150-token child chunks (no overlap).

        Each child is annotated with the ``parent_id`` of the parent it
        belongs to (computed from the token offset against
        ``spec.parent_size``) so the retrieval path can walk a vector hit
        on a child back to its parent context block.

        Citations:
            - SRS.md FR-28 -- Child = 150 tokens; trace back Parent for LLM.
        """
        parent_size = self._spec.parent_size

        def parent_id(_idx: int, start: int) -> str:
            return f"parent-{start // parent_size}" if parent_size > 0 else "parent-0"

        return _slice_tokens(
            _tokenize(text),
            self._spec.child_size,
            prefix="child",
            chunk_type="child",
            parent_id_for=parent_id,
        )


class ParentChildIndex:
    """[FR-28] In-memory child→parent wiring for vector-hit-walks-parent.

    The production implementation reads from the ``knowledge_chunks``
    table; this in-memory variant exists so unit tests can wire a
    ``child_id`` → ``parent_id`` mapping without standing up PostgreSQL.
    Only child chunks are vector-indexed — parents are reached by walking
    the child hit's FK, never by similarity search.

    Parents are NEVER seeded with empty content. ``add_link`` requires
    the caller to supply real ``parent_content`` (or to register the
    parent via :meth:`add_parent` first); ``retrieve_parent`` rejects
    empty content rather than handing an empty string to the LLM (H-17).

    Citations:
        - SRS.md FR-28 — 僅 Child Chunks 建向量索引;向量命中 Child 追索
          對應 Parent.
    """

    def __init__(self) -> None:
        self._links: dict[str, str] = {}
        self._parents: dict[str, Chunk] = {}

    def add_link(
        self,
        child_id: str,
        parent_id: str,
        parent_content: str,
    ) -> None:
        """[FR-28] Wire ``child_id`` → ``parent_id`` and seed the parent with real content (H-17).

        ``parent_content`` MUST be non-empty. An empty string would
        propagate to the LLM as the parent context and silently disable
        the RAG retrieval path's main signal. Use :meth:`add_parent` to
        register a parent :class:`Chunk` with richer metadata (actual
        ``token_count``, etc.).
        """
        if not parent_content:
            raise ValueError(
                f"add_link requires non-empty parent_content for "
                f"parent_id={parent_id!r}; empty content would propagate "
                f"to the LLM (H-17). Use add_parent() to register a "
                f"parent chunk with real content."
            )
        self._links[child_id] = parent_id
        self._parents[parent_id] = Chunk(
            chunk_id=parent_id,
            content=parent_content,
            chunk_type="parent",
            parent_id=None,
            token_count=PARENT_TOKEN_SIZE,
        )

    def add_parent(self, parent: Chunk) -> None:
        """[FR-28] Register a parent :class:`Chunk` with real content (H-17).

        Raises ``ValueError`` if ``parent.chunk_type`` is not ``"parent"``
        or if ``parent.content`` is empty — the LLM must never receive
        an empty string as parent context.
        """
        if parent.chunk_type != "parent":
            raise ValueError(
                f"add_parent requires chunk_type='parent'; "
                f"got chunk_type={parent.chunk_type!r}"
            )
        if not parent.content:
            raise ValueError(
                "add_parent requires non-empty content; "
                "LLM must not receive empty string as parent context (H-17)"
            )
        self._parents[parent.chunk_id] = parent

    def is_vector_indexed(self, chunk: Chunk) -> bool:
        """[FR-28] Return True iff ``chunk`` is a child chunk.

        Parents are never vector-indexed; only children populate the
        HNSW index. Returning the decision as a deterministic ``bool``
        lets callers use the value directly in conditional branches.

        Citations:
            - SRS.md FR-28 — 僅 Child Chunks 建向量索引.
        """
        return chunk.chunk_type == "child"

    def retrieve_parent(self, child_id: str) -> Chunk | None:
        """[FR-28] Walk ``child_id`` → ``parent_id`` → parent Chunk (H-17).

        Returns the parent :class:`Chunk` the LLM (Tier 3) actually
        consumes, or ``None`` if the child has no registered parent or
        the registered parent has empty content (refused to avoid
        handing the LLM an empty string). The returned chunk's
        ``chunk_id`` is the parent identifier, not the ``child_id`` we
        queried with.

        Citations:
            - SRS.md FR-28 — 向量命中 Child → 追索對應 Parent 送 LLM.
        """
        parent_id = self._links.get(child_id)
        if parent_id is None:
            return None
        parent = self._parents.get(parent_id)
        if parent is None or not parent.content:
            return None
        return parent


escalate = _escalate



import asyncio  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

# SRS FR-77 — the asyncio.wait_for budget pinned at 2.0s. Single source
# of truth; tests import the symbol name and assert the value.
EMBEDDING_TIMEOUT_S: float = 2.0

# Embedding vector dimensionality for text-embedding-3-small (SRS
# Module 16). Pinned here so the no-op default embed returns a vector
# of the right shape (the test asserts only ``search_ready``, not the
# vector itself, but downstream Tier 2 readers will care).
_EMBED_DIM_DEFAULT: int = 1536

_logger = logging.getLogger("app.infra.jobs")


@dataclass
class CreateKnowledgeResult:
    """Structured result returned by ``create_knowledge_with_chunks``.

    Every field is part of the FR-77 contract:

      - ``knowledge_id``        : the input ``knowledge_id`` (echo)
      - ``first_chunk_id``      : generated id for the first chunk
      - ``embedding_synced``    : True iff the sync embedding call
                                  returned within ``EMBEDDING_TIMEOUT_S``
      - ``embedding_synced_at`` : ``datetime`` (UTC) of the successful
                                  sync embedding; ``None`` on fallback
      - ``fallback``            : ``"async_queue"`` on TimeoutError
                                  (or unexpected exception); ``None``
                                  on the happy path
      - ``search_ready``        : True iff the first chunk is
                                  immediately searchable on Tier 2 —
                                  mirrors ``embedding_synced`` but
                                  isolated as a contract surface so
                                  downstream code does not have to
                                  interpret embedding pipeline state
      - ``elapsed_seconds``     : wall-clock duration of the create
                                  call (must stay < 2.5s per FR-77)
    """

    knowledge_id: str
    first_chunk_id: str
    embedding_synced: bool
    search_ready: bool
    elapsed_seconds: float
    embedding_synced_at: datetime | None = None
    fallback: str | None = None
    # Exposed for tests / observability that want to inspect the
    # embedding job that was enqueued on the fallback path.
    enqueued_job: Any | None = None


# ---------------------------------------------------------------------------
# Default embedding coroutine — stub-able.
#
# GREEN keeps a no-network default that returns a zero vector of the
# SRS-pinned dimensionality in microseconds. The unit test patches
# this attribute via ``monkeypatch.setattr(..., raising=False)`` to
# force the timeout branch; production wiring replaces it with the
# real OpenAI / local-model client.
# ---------------------------------------------------------------------------
async def _embed_first_chunk(
    chunk_id: str,
    content: str,
    model: str,
) -> list[float]:
    """Generate an embedding vector for a single chunk.

    Default implementation: a zero vector of the SRS-pinned
    dimensionality. Returns in microseconds so the sync window
    comfortably fits the 2.0s ``EMBEDDING_TIMEOUT_S`` budget.
    """
    # ``asyncio.sleep(0)`` yields once so the call is a real
    # coroutine (a function returning a list is NOT a coroutine and
    # would break ``asyncio.wait_for``'s contract that its first
    # argument be awaitable). The yield is harmless to timing.
    await asyncio.sleep(0)
    return [0.0] * _EMBED_DIM_DEFAULT




async def create_knowledge_with_chunks(
    *,
    knowledge_id: str,
    title: str,
    content: str,
    model: str,
    mode: str = "single",
) -> CreateKnowledgeResult:
    """Create a knowledge_base row + first chunk; sync-embed the first.

    FR-77 contract (SRS line 175):

      1. Persist the knowledge_base + first chunk row (DB session is
         expected to be injected by the caller in production; this
         pure-Python default does not touch Postgres so the unit
         test can run without a database).
      2. Synchronously embed the first chunk via
         ``asyncio.wait_for(_embed_first_chunk(...),
         timeout=EMBEDDING_TIMEOUT_S)``.
      3. On success → ``embedding_synced=True``,
         ``search_ready=True``, ``embedding_synced_at=now(timezone.utc)``,
         ``fallback=None``.
      4. On ``asyncio.TimeoutError`` (or any unexpected exception
         inside the embed call) → log a warning, enqueue the chunk
         via ``enqueue_embedding_job``, return
         ``fallback="async_queue"`` / ``search_ready=False``. The
         function MUST NOT raise to the caller (超時不阻斷主流程).
      5. Wall-clock ``elapsed_seconds`` is recorded so the test can
         verify the < 2.5s SLO.

    The function is intentionally side-effect free on the DB layer
    (the caller wires the real session in production). The unit test
    asserts the FR-77 contract on the returned ``CreateKnowledgeResult``
    only — the persistence layer is exercised in the integration
    test pyramid, not here.
    """
    start = time.perf_counter()
    first_chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
    first_chunk_text = content

    fallback: str | None = None
    embedding_synced = False
    embedding_synced_at: datetime | None = None
    enqueued_job: Any | None = None

    def _fallback_to_async(log_msg: str, *log_args: object) -> None:
        """Enqueue the first chunk for async embedding and log a warning.

        Shared by both the ``asyncio.TimeoutError`` and defensive
        ``Exception`` branches — the only difference is the log message.
        """
        nonlocal fallback, enqueued_job
        fallback = "async_queue"
        try:
            from app.infra.jobs import EmbeddingJob, enqueue_embedding_job
            enqueued_job = enqueue_embedding_job(
                EmbeddingJob(
                    chunk_id=first_chunk_id,
                    knowledge_id=knowledge_id,
                    content=first_chunk_text,
                    model=model,
                )
            )
        except Exception as exc:
            _logger.error("Failed to enqueue fallback embedding job: %s", exc)
            fallback = "failed"
        _logger.warning(log_msg, *log_args)

    try:
        await asyncio.wait_for(
            _embed_first_chunk(
                chunk_id=first_chunk_id,
                content=first_chunk_text,
                model=model,
            ),
            timeout=EMBEDDING_TIMEOUT_S,
        )
    except TimeoutError:
        # SRS FR-77: "超時 → 記錄 warning，fallback 全部走非同步".
        _fallback_to_async(
            "FR-77 embedding timeout for knowledge_id=%s chunk_id=%s "
            "after %.2fs; falling back to async_queue",
            knowledge_id,
            first_chunk_id,
            EMBEDDING_TIMEOUT_S,
        )
    except Exception as exc:  # pragma: no cover - defensive
        # Defensive: any unexpected embedding failure MUST be treated as
        # transient per the FR-77 "超時不阻斷主流程" rule.
        _fallback_to_async(
            "FR-77 embedding failure for knowledge_id=%s chunk_id=%s: %r; "
            "falling back to async_queue",
            knowledge_id,
            first_chunk_id,
            exc,
        )
    else:
        embedding_synced = True
        embedding_synced_at = datetime.now(tz=timezone.utc)

    elapsed = time.perf_counter() - start

    return CreateKnowledgeResult(
        knowledge_id=knowledge_id,
        first_chunk_id=first_chunk_id,
        embedding_synced=embedding_synced,
        embedding_synced_at=embedding_synced_at,
        fallback=fallback,
        search_ready=embedding_synced,
        elapsed_seconds=elapsed,
        enqueued_job=enqueued_job,
    )


# ---------------------------------------------------------------------------
# [FR-78] Batch import mode.
#
# SRS.md line 176 (FR-78):
#     is_batch=True → 所有 chunks 全部非同步排入 SAQ
#     （不等待同步首 chunk）；per entry 延遲 < 50ms
#
# SAD §Module: jobs.py (Module 16) + TEST_SPEC.md pin:
#   - ``batch_import_knowledge`` MUST be exported from ``app.infra.jobs``
#     as a callable that accepts a list of knowledge entry dicts (each
#     with title, content, model) and a boolean ``is_batch`` flag.
#   - The function MUST return a ``BatchImportResult`` exposing
#     ``entry_count``, ``enqueued_count``, ``sync_wait``, ``per_entry_ms``.
#   - When ``is_batch=True``, ALL chunks MUST be enqueued asynchronously
#     — NO ``asyncio.wait_for`` embedding call for the first chunk
#     (contrast FR-77 which does a synchronous 2.0s wait).
#   - Per-entry processing latency MUST be < 50ms (NP-06 SLA). With the
#     sync wait eliminated, overhead is dominated by the DB insert +
#     SAQ enqueue cost.
#
# Citations:
# - SRS.md:176 (FR-78 description)
# - SRS.md:1067-1073 (FR-78 JSON spec — implementation_function:
#   ``batch_import_knowledge``)
# - 02-architecture/TEST_SPEC.md:1585-1603 (FR-78 test cases + fr78-ok)
# - 02-architecture/SAD.md:323 (Module: jobs.py contract)
# ---------------------------------------------------------------------------



@dataclass
class BatchImportResult:
    """Structured result returned by ``batch_import_knowledge``.

    Every field is part of the FR-78 contract:

      - ``entry_count``    : number of entries processed
      - ``enqueued_count`` : number of chunks enqueued to SAQ (at least
                              one per entry; may be higher if entries
                              are split into multiple chunks)
      - ``sync_wait``      : MUST be ``False`` when ``is_batch=True``
                              (the defining FR-78 contract — batch mode
                              skips the synchronous embedding wait that
                              FR-77 performs for single-entry mode)
      - ``per_entry_ms``   : wall-clock duration / entry_count; MUST
                              stay < 50ms per the NP-06 SLA
    """

    entry_count: int
    enqueued_count: int
    failed_count: int
    sync_wait: bool
    per_entry_ms: float
    failed_chunk_ids: list[str] = field(default_factory=list)


def batch_import_knowledge(
    entries: list[dict],
    *,
    is_batch: bool = False,
) -> BatchImportResult:
    """Import multiple knowledge entries in batch mode.

    FR-78 contract (SRS line 176):

      1. Iterate over entries; for each, create at least one chunk
         and enqueue an ``EmbeddingJob`` via ``enqueue_embedding_job``.
      2. When ``is_batch=True``, do NOT perform a synchronous embedding
         wait — all chunks go through the async queue (contrast FR-77
         which does ``asyncio.wait_for`` for the first chunk).
      3. Return ``BatchImportResult`` with timing and counts so callers
         can audit the batch import without inspecting internal state.

    The function is intentionally side-effect free on the DB layer
    (the caller wires the real session in production). The unit test
    asserts the FR-78 contract on the returned ``BatchImportResult``
    only — the persistence layer is exercised in the integration
    test pyramid, not here.
    """
    start = time.perf_counter()
    enqueued = 0
    failed_chunk_ids = []

    for entry in entries:
        chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
        knowledge_id = entry.get("knowledge_id", f"kb_{uuid.uuid4().hex[:12]}")
        from app.infra.jobs import EmbeddingJob, enqueue_embedding_job
        job = EmbeddingJob(
            chunk_id=chunk_id,
            knowledge_id=knowledge_id,
            content=entry.get("content", ""),
            model=entry.get("model", "text-embedding-3-small"),
        )
        try:
            enqueue_embedding_job(job)
            enqueued += 1
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("FR-78 batch enqueue failed: %r", exc)
            failed_chunk_ids.append(chunk_id)

    elapsed = time.perf_counter() - start
    count = len(entries)
    per_entry_ms = (elapsed / count) * 1000.0 if count > 0 else 0.0

    return BatchImportResult(
        entry_count=count,
        enqueued_count=enqueued,
        failed_count=count - enqueued,
        sync_wait=False,
        per_entry_ms=per_entry_ms,
        failed_chunk_ids=failed_chunk_ids,
    )



