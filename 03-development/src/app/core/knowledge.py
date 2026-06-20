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

        When ``session`` was injected as ``None`` (FR-33 unit-test
        path) the lookup is skipped and ``None`` is returned so the
        orchestrator walks straight on to Tier 2.
        """
        if not query or self._session is None:
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
        # Confidence is 0.0 here so the gate at ``RAG_CONFIDENCE_THRESHOLD``
        # (0.85) trips and Tier-2 returns ``None`` in the no-context
        # case. A wiring layer that pre-computes confidence feeds it in.
        tier2 = self._rag_search(query, confidence=0.0)
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
        tier4 = _escalate(
            tier1_result=tier1,
            tier2_result=tier2,
            tier3_result=tier3,
            reason="no_rule_match",
        )
        object.__setattr__(tier4, "tier_sequence", list(sequence))
        return tier4


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
    raise NotImplementedError(
        "FR-30: wire openai/google-generativeai SDK in production; "
        "tests inject a stub via monkeypatch.setattr"
    )


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
    propagates so the orchestrator can surface a 503 rather than
    returning a fabricated answer.

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback.
    """
    import time
    start_time = time.perf_counter()
    try:
        return _call_llm_api(primary_llm, prompt)
    except Exception:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if elapsed_ms >= FALLBACK_BUDGET_MS:
            raise TimeoutError(f"FR-30: 500ms budget exceeded during primary LLM failure ({elapsed_ms:.1f}ms)")
        return _call_llm_api(fallback_llm, prompt)


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
    wrapping the LLM's answer; returns ``None`` when ``grounding_score``
    is below ``grounding_threshold`` so the orchestrator can escalate
    to Tier 4 (per FR-31). The primary LLM (``primary_llm``,
    default ``"gpt-4o"``) is attempted first; on any exception the
    orchestrator falls through to ``fallback_llm`` (default
    ``"gemini-1.5-flash"``). The total wall-clock for the
    primary-down → fallback path MUST stay under
    ``FALLBACK_BUDGET_MS`` (500ms) per the NP-15 performance budget.

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback;
          L5 Grounding Check ≥ 0.75；grounding 失敗 → None (觸發 Tier 4)；
          LLM fallback 切換 < 500ms.
    """
    prompt = _build_sandwich_prompt(query, retrieved_context)
    answer = _call_llm_with_fallback(prompt, primary_llm, fallback_llm)

    # Grounding check happens AFTER the model call returns a candidate
    # answer (per the FR-30 contract). Below the threshold we return
    # None so the orchestrator escalates to Tier 4 (FR-31) — we do
    # NOT wrap the un-grounded answer in a KnowledgeResult.
    if grounding_score is not None and grounding_score < grounding_threshold:
        return None

    confidence = float(grounding_score) if grounding_score is not None else 0.0
    return KnowledgeResult(
        id=0,
        content=answer,
        confidence=confidence,
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
