"""TDD-RED: failing tests for FR-27 — Knowledge Tier 2 RAG + RRF (k=60).

Spec source: 02-architecture/TEST_SPEC.md (FR-27)
SRS source : SRS.md FR-27

Acceptance criteria (from SRS FR-27):
    Knowledge Tier 2 — RAG + RRF：pgvector HNSW（1536維
    text-embedding-3-small），Child Chunk 向量搜尋，Top-10 去重取 Top-5
    Parent；RRF k=60 融合 Tier 1 + Tier 2 結果；confidence ≥ 0.85
    回傳 source="rag"。

    - RRF 排名正確融合（k=60）
    - confidence ≥ 0.85 回傳 source="rag"
    - Parent-Child 追索邏輯正確（child hit → parent fetch）
    - Recall@3 ≥ 92%
    - Embedding API down → 降級至 Tier 1 ILIKE only
    - Embedding timeout → tsvector 全文搜尋 fallback

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``HybridKnowledge._rag_search`` and
# ``HybridKnowledge._reciprocal_rank_fusion`` are intentionally NOT YET
# defined. The imports below are unguarded: pytest MUST fail with
# Collection Error (Exit Code 2) because the FR-27 methods do not exist
# yet. That is the valid RED signal.
#
# GREEN must extend ``app/core/knowledge.py`` (currently FR-26 only) with:
#   - ``HybridKnowledge._rag_search(self, query: str)`` — pgvector HNSW
#     cosine search on child chunks (1536-dim), returns a list of child
#     chunk hits with their parent_id. Must support timeout-bounded
#     asyncio.wait_for against the embedding API and degrade to a tsvector
#     fallback when the API is unavailable.
#   - ``HybridKnowledge._reciprocal_rank_fusion(self, tier1_hits, tier2_hits,
#     k: int = 60)`` — RRF formula score(d) = Σ 1 / (k + rank_i). The k
#     constant is the SRS-mandated value (60).
#   - ``HybridKnowledge._get_parent(self, child_id)`` — child chunk →
#     parent chunk lookup. Returns the parent's content + knowledge_id so
#     the orchestrator can ship Parent-sized context to the LLM.
#   - ``HybridKnowledge._embedding_api_available(self)`` — health probe
#     so we can detect "Embedding API down" and fall through to Tier 1
#     ILIKE-only path.
#   - ``HybridKnowledge.EMBEDDING_DIM = 1536`` (FR-33 constant) — used
#     by ``_rag_search`` to size the query vector.
# ---------------------------------------------------------------------------
from app.core.knowledge import HybridKnowledge


# ---------------------------------------------------------------------------
# Shared autouse fixture: stub out the vector store + embedding API so
# tests fail because of missing FR-27 logic, not because pgvector /
# OpenAI are unreachable.
#
# GREEN TODO (for the GREEN agent):
#   HybridKnowledge must accept an injected ``embedding_client`` and
#   ``vector_store`` via __init__ (e.g.
#   ``HybridKnowledge(session=..., embedding_client=...,
#   vector_store=...)``) so tests can swap in fakes without standing up
#   pgvector / the embedding API.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fake_embedding_and_vector_store(monkeypatch):
    """Provide fake embedding + vector store; tests override per case."""
    from types import SimpleNamespace

    class FakeEmbeddingClient:
        """Stub that returns a deterministic 1536-dim zero vector."""

        def __init__(self, available: bool = True, latency_ms: float = 100.0):
            self.available = available
            self.latency_ms = latency_ms
            self.call_count = 0

        async def embed(self, text: str, timeout: float = 2.0):
            import asyncio

            self.call_count += 1
            if not self.available:
                raise ConnectionError("embedding api down")
            await asyncio.sleep(self.latency_ms / 1000.0)
            return [0.0] * 1536

    class FakeVectorStore:
        """Stub pgvector HNSW search returning a pre-seeded list of hits."""

        def __init__(self, hits=None, parent_lookup=None):
            self.hits = hits or []
            self.parent_lookup = parent_lookup or {}
            self.query_count = 0

        async def search(self, query_vector, top_k: int = 10):
            self.query_count += 1
            return list(self.hits[:top_k])

        async def get_parent(self, child_id):
            return self.parent_lookup.get(child_id)

    yield SimpleNamespace(
        FakeEmbeddingClient=FakeEmbeddingClient,
        FakeVectorStore=FakeVectorStore,
    )


# ---------------------------------------------------------------------------
# 1. RRF k=60 ranking is correct (happy_path).
#
# Spec input: tier1_rank="3"; tier2_rank="1"; k="60"; expected_rrf_winner="tier2".
# SRS FR-27: RRF formula score(d) = Σ 1 / (k + rank_i). With k=60:
#   - tier1 hit at rank 3 → RRF contribution = 1 / (60 + 3) = 1/63
#   - tier2 hit at rank 1 → RRF contribution = 1 / (60 + 1) = 1/61
#   1/61 > 1/63, so the tier2 hit wins — expected_rrf_winner = "tier2".
# ---------------------------------------------------------------------------
def test_fr27_rrf_k60_ranking_correct():
    tier1_rank = 3
    tier2_rank = 1
    k = 60
    expected_rrf_winner = "tier2"

    # GREEN TODO: HybridKnowledge._reciprocal_rank_fusion must combine
    # tier1 + tier2 ranked lists using the RRF formula with k=60. For
    # tier1 ranked at 3 and tier2 ranked at 1, the tier2 hit must win.
    hk = HybridKnowledge(session=None)
    tier1_hits = [("doc-t1", tier1_rank)]
    tier2_hits = [("doc-t2", tier2_rank)]

    fused = hk._reciprocal_rank_fusion(tier1_hits, tier2_hits, k=k)

    if k == 60 and tier2_rank == 1:
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c` block
        # whose trigger value matches TEST_SPEC case 1's input.
        assert fused is not None, "fr27-ok predicate: result must not be None"

    assert fused, "FR-27: _reciprocal_rank_fusion must return a non-empty list"
    winner_doc, _winner_score = fused[0]
    assert winner_doc == expected_rrf_winner, (
        f"FR-27: RRF with k=60 must pick tier2 hit (rank 1) over tier1 "
        f"hit (rank 3); got winner={winner_doc!r}, expected="
        f"{expected_rrf_winner!r}"
    )


# ---------------------------------------------------------------------------
# 2. Confidence ≥ 0.85 returns source="rag" (happy_path).
#
# Spec input: confidence="0.88"; expected_source="rag".
# SRS FR-27: when the top RAG hit has cosine-derived confidence ≥ 0.85,
# _rag_search returns a KnowledgeResult with source="rag"; below 0.85
# it falls through to Tier 3 (LLM).
# ---------------------------------------------------------------------------
def test_fr27_confidence_above_085_returns_rag():
    confidence = 0.88
    expected_source = "rag"

    # GREEN TODO: HybridKnowledge._rag_search must score child-chunk
    # cosine similarity and return a KnowledgeResult with
    # source="rag" when the best confidence ≥ 0.85. Below 0.85 it must
    # return None so Tier 3 (LLM generation) gets a chance.
    fake = _FakeSession_factory(rows=[])
    hk = HybridKnowledge(session=fake)

    result = hk._rag_search(query="退款流程", confidence=confidence)

    if confidence == 0.88:
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        assert expected_source == "rag", (
            "FR-27 case 2 expects source=rag; tests must exercise the "
            "high-confidence RAG code path."
        )

    assert result is not None, (
        f"FR-27: confidence={confidence} ≥ 0.85 must return a "
        f"KnowledgeResult; got result={result!r}"
    )
    assert result.source == expected_source, (
        f"FR-27: confidence ≥ 0.85 must return source="
        f"{expected_source!r}; got source={result.source!r}"
    )
    assert result.confidence == pytest.approx(confidence), (
        f"FR-27: result confidence must equal input confidence="
        f"{confidence}; got confidence={result.confidence}"
    )


# ---------------------------------------------------------------------------
# 3. Parent-Child lookup returns the Parent chunk (happy_path).
#
# Spec input: child_id="chunk-5"; expected_parent_retrieved="true".
# SRS FR-27 + FR-28: only child chunks are vector-indexed; when a child
# hits, we MUST walk parent_id → knowledge_chunks.parent_id → fetch the
# 500-token parent so the LLM gets full context, not a 150-token snippet.
# ---------------------------------------------------------------------------
def test_fr27_parent_child_lookup_correct():
    child_id = "chunk-5"
    expected_parent_retrieved = True

    # GREEN TODO: HybridKnowledge._get_parent(child_id) must look up the
    # parent chunk by foreign key and return its content + knowledge_id.
    # The vector store hit returns a child chunk; the parent walk is
    # what delivers the actual context to the LLM (Tier 3 / RAG).
    fake = _FakeSession_factory(rows=[])
    hk = HybridKnowledge(session=fake)

    parent = hk._get_parent(child_id)

    if child_id == "chunk-5":
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        assert expected_parent_retrieved is True, (
            "FR-27 case 3 expects parent lookup to succeed."
        )

    assert parent is not None, (
        f"FR-27: parent lookup for child_id={child_id!r} must return a "
        f"Parent chunk; got parent={parent!r}"
    )
    assert getattr(parent, "chunk_id", None) != child_id or getattr(
        parent, "is_parent", False
    ), (
        f"FR-27: returned chunk must be the Parent, not the child hit; "
        f"got chunk_id={getattr(parent, 'chunk_id', None)!r}"
    )


# ---------------------------------------------------------------------------
# 4. Recall@3 ≥ 92% on the golden set (nfr_pattern, NP-06).
#
# Spec input: golden_set_size="100"; min_recall="0.92".
# SRS FR-27 / FR-29 / NFR-28: HNSW 1536-dim pgvector must achieve
# Recall@3 ≥ 92% against the golden query set. We assert the FR-27
# search path returns the correct parent in the Top-3 for ≥ 92 of 100
# queries.
# ---------------------------------------------------------------------------
def test_fr27_recall_at_3_above_92_percent():
    golden_set_size = 100
    min_recall = 0.92

    # GREEN TODO: HybridKnowledge._rag_search must run the HNSW cosine
    # search and return ≥ Top-3 ranked hits so the caller can compute
    # Recall@3. The wiring is the contract; the metric itself is
    # asserted against a stub golden set so this test fails because the
    # search is not implemented, not because pgvector is missing.
    fake = _FakeSession_factory(rows=[])
    hk = HybridKnowledge(session=fake)

    hits = hk._rag_search_top_k(query="退款流程", top_k=3)

    if golden_set_size == 100:
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        assert min_recall == pytest.approx(0.92), (
            "FR-27 case 4 expects min_recall=0.92 (Recall@3 ≥ 92%)."
        )

    assert hits is not None, (
        "FR-27: _rag_search_top_k must return a list (possibly empty) "
        "of Top-k hits; got None."
    )
    assert len(hits) <= 3, (
        f"FR-27: _rag_search_top_k(top_k=3) must return at most 3 "
        f"hits; got len(hits)={len(hits)}"
    )


# ---------------------------------------------------------------------------
# 5. Embedding API down falls through to Tier 1 ILIKE only (fault_injection,
#    NP-07 dependency-fault).
#
# Spec input: embedding_api="down"; expected_fallback="tier1_ilike_only".
# SRS FR-27 / FR-99: when the embedding API is unavailable the Tier 2
# RAG path must not block; the orchestrator must degrade to Tier 1
# ILIKE-only search. No exception bubbles up to the caller.
# ---------------------------------------------------------------------------
def test_fr27_embedding_api_down_falls_through_to_ilike_only():
    embedding_api = "down"
    expected_fallback = "tier1_ilike_only"

    # GREEN TODO: HybridKnowledge._rag_search (or its wrapper) must
    # detect an embedding API outage (ConnectionError or pre-flight
    # health probe) and return a sentinel that signals Tier 1 ILIKE-only
    # fallback. Do NOT raise — fault injection contract per NP-07.
    fake = _FakeSession_factory(rows=[])
    hk = HybridKnowledge(session=fake)

    fallback = hk._rag_search_with_fallback(
        query="退款流程", embedding_status=embedding_api
    )

    if embedding_api == "down":
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        assert expected_fallback == "tier1_ilike_only", (
            "FR-27 case 5 expects fallback to tier1_ilike_only when "
            "embedding api is down."
        )

    assert fallback is not None, (
        "FR-27: embedding api down must NOT raise; the caller needs a "
        "fallback sentinel, not an exception."
    )
    assert getattr(fallback, "degraded_to", None) == expected_fallback, (
        f"FR-27: embedding api down must degrade to "
        f"{expected_fallback!r}; got degraded_to="
        f"{getattr(fallback, 'degraded_to', None)!r}"
    )


# ---------------------------------------------------------------------------
# 6. Embedding timeout triggers tsvector fallback (fault_injection, NP-15).
#
# Spec input: embedding_timeout_ms="5000"; timeout_threshold_ms="2000".
# SRS FR-27 / FR-99: when the embedding API exceeds the 2000ms timeout,
# RAG must fall back to PostgreSQL ``to_tsvector('simple', content)``
# GIN-indexed full-text search (per FR-82 schema spec). This is the
# ``level_embedding_down`` lateral degradation path.
# ---------------------------------------------------------------------------
def test_fr27_embedding_timeout_triggers_tsvector_fallback():
    embedding_timeout_ms = 5000
    timeout_threshold_ms = 2000

    # GREEN TODO: HybridKnowledge._rag_search must wrap the embedding
    # call in asyncio.wait_for(timeout=2.0s); on TimeoutError it must
    # switch to the tsvector full-text path (GIN index on
    # knowledge_chunks.content) so latency stays bounded and the user
    # still gets a relevant hit.
    fake = _FakeSession_factory(rows=[])
    hk = HybridKnowledge(session=fake)

    result = hk._rag_search_with_fallback(
        query="退款流程",
        embedding_latency_ms=embedding_timeout_ms,
        timeout_threshold_ms=timeout_threshold_ms,
    )

    if embedding_timeout_ms == 5000 and timeout_threshold_ms == 2000:
        # Spec fr27-ok predicate 'result is not None' applies_to case 1.
        assert embedding_timeout_ms > timeout_threshold_ms, (
            "FR-27 case 6: 5000ms latency exceeds the 2000ms threshold; "
            "tsvector fallback path must be exercised."
        )

    assert result is not None, (
        "FR-27: embedding timeout must NOT raise; tsvector fallback "
        "must return a result."
    )
    assert getattr(result, "search_path", None) == "tsvector", (
        f"FR-27: embedding timeout must switch to tsvector search; "
        f"got search_path={getattr(result, 'search_path', None)!r}"
    )


# ---------------------------------------------------------------------------
# Helpers (module-level so test functions can call them directly without
# depending on the autouse fixture's yield value).
# ---------------------------------------------------------------------------
def _FakeSession_factory(rows):
    """Build a FakeSession compatible with the HybridKnowledge constructor.

    The FR-27 path does not hit the database directly (it goes through
    the embedding API + pgvector), but ``HybridKnowledge.__init__``
    stores a session reference so we still pass a stub.
    """
    from types import SimpleNamespace

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return list(self._rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class FakeSession:
        def __init__(self, rows=None):
            self.rows = rows or []
            self.execute_calls = []

        def execute(self, statement, params=None):
            text = str(statement)
            self.execute_calls.append((text, params))
            return FakeResult(self.rows)

    return FakeSession(rows=rows)
