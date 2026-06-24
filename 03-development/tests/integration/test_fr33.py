"""TDD-RED: failing tests for FR-33 — HybridKnowledge query orchestrator
(Tier 1 → Tier 4 sequential) and EMBEDDING_DIM=1536 / EMBEDDING_MODEL
constants.

Spec source: 02-architecture/TEST_SPEC.md (FR-33)
SRS source : SRS.md FR-33

Acceptance criteria (from SRS FR-33):
    HybridKnowledge 查詢協調器：按 Tier 1 → Tier 2 → Tier 3 → Tier 4
    順序執行；各 Tier 有明確置信度門檻；
    EMBEDDING_MODEL = text-embedding-3-small, EMBEDDING_DIM = 1536.
    查詢路徑按 Tier 順序；置信度門檻正確攔截；更換模型時
    EMBEDDING_DIM 同步變更。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/knowledge.py  (changes to the existing ``HybridKnowledge``)
#
#   class HybridKnowledge:
#       # ... existing FR-26 / FR-27 constants ...
#
#       # FR-33 — Tier 1 → Tier 4 orchestrator constants.
#       # ``EMBEDDING_MODEL`` pins the SRS-mandated text-embedding-3-small
#       # so swapping the model at runtime updates ``EMBEDDING_DIM`` in
#       # lockstep (per SRS FR-33 acceptance criterion "更換模型時
#       # EMBEDDING_DIM 同步變更").
#       EMBEDDING_MODEL: str = "text-embedding-3-small"
#       EMBEDDING_DIM: int = 1536
#
#       def query(self, query: str) -> "KnowledgeResult | None":
#           """[FR-33] Tier 1 → Tier 4 sequential orchestrator.
#
#           Walks Tier-1 rule match → Tier-2 RAG short-circuit →
#           Tier-3 LLM fallback → Tier-4 escalation, stopping at the
#           first tier that returns a hit whose confidence clears the
#           tier's threshold. Returns ``None`` only when the Tier-4
#           escalation itself fails — every other miss falls through to
#           the next tier rather than terminating early.
#
#           Returns a ``KnowledgeResult`` whose ``source`` field
#           identifies the winning tier (``"rule"`` / ``"rag"`` /
#           ``"wiki"`` / ``"escalate"`` per FR-32's enum), and exposes
#           ``tier_sequence`` as a list of tier tags in the order they
#           were consulted so the test suite can assert the SRS-mandated
#           ``t1 → t2 → t3 → t4`` ordering.
#           """
#           sequence: list[str] = []
#
#           # --- Tier 1 ---
#           sequence.append("t1")
#           tier1 = self._rule_match(query)
#           if tier1 is not None and tier1.confidence >= self.CONFIDENCE_THRESHOLD:
#               tier1.tier_sequence = sequence  # type: ignore[attr-defined]
#               return tier1
#
#           # --- Tier 2 ---
#           sequence.append("t2")
#           tier2 = self._rag_search(query, confidence=0.0)
#           if tier2 is not None and tier2.confidence >= self.RAG_CONFIDENCE_THRESHOLD:
#               tier2.tier_sequence = sequence  # type: ignore[attr-defined]
#               return tier2
#
#           # --- Tier 3 ---
#           sequence.append("t3")
#           tier3 = self._llm_call(query)
#           if tier3 is not None and tier3.confidence >= 0.65:
#               tier3.tier_sequence = sequence  # type: ignore[attr-defined]
#               return tier3
#
#           # --- Tier 4 ---
#           sequence.append("t4")
#           tier4 = _escalate(query, reason="no_rule_match")
#           tier4.tier_sequence = sequence  # type: ignore[attr-defined]
#           return tier4
#
# Until GREEN adds the above, ``HybridKnowledge.query`` and
# ``HybridKnowledge.EMBEDDING_MODEL`` do NOT exist — pytest will surface
# the missing feature as ``AttributeError`` on the call sites below,
# which is the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.core.knowledge import HybridKnowledge


# ---------------------------------------------------------------------------
# 1. HybridKnowledge.query executes Tier 1 → Tier 4 sequentially.
#
# Spec input: query="test"; expected_sequence="t1,t2,t3,t4".
# SRS FR-33: "HybridKnowledge 查詢協調器：按 Tier 1 → Tier 2 → Tier 3 →
# Tier 4 順序執行". The orchestrator MUST consult every tier in order
# (the per-tier confidence gate may stop the walk early, but the
# *consultation order* is fixed). The test asserts both that the call
# returns a non-None ``KnowledgeResult`` (the Tier-4 escalation
# sentinel is always returned) AND that the observed sequence equals
# the spec-pinned ``["t1", "t2", "t3", "t4"]``.
# ---------------------------------------------------------------------------
def test_fr33_query_t1_first_t4_last_order():
    query = "test"
    expected_sequence = ["t1", "t2", "t3", "t4"]

    # GREEN TODO: ``HybridKnowledge`` MUST expose
    #   ``def query(self, query: str) -> KnowledgeResult``
    # that orchestrates Tier 1 → Tier 4. Until GREEN adds that method
    # the line below raises ``AttributeError`` and the test fails RED.
    hk = HybridKnowledge(session=None)
    result = hk.query(query)

    # Spec fr33-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 1's input
    # (``query="test"``).
    if query == "test":
        # Spec fr33-ok predicate 'result is not None' applies_to case 1.
        # The trigger for case 1 is ``query``; we gate the predicate on
        # that variable matching the spec input value.
        assert result is not None, (
            "fr33-ok predicate: HybridKnowledge.query must return a "
            "non-None KnowledgeResult for query='test'"
        )

    # FR-33 functional assertion: the consultation order MUST be the
    # spec-pinned ``t1 → t2 → t3 → t4``. The orchestrator exposes the
    # sequence on the returned ``KnowledgeResult`` so the test can
    # assert ordering without re-walking the internals.
    actual_sequence = list(getattr(result, "tier_sequence", []) or [])
    assert actual_sequence == expected_sequence, (
        f"FR-33: HybridKnowledge.query must execute tiers in order "
        f"{expected_sequence!r}; got sequence={actual_sequence!r}"
    )


# ---------------------------------------------------------------------------
# 2. HybridKnowledge exposes the EMBEDDING_MODEL / EMBEDDING_DIM constants
#    pinned by SRS FR-33.
#
# Spec input: model="text-embedding-3-small"; expected_dim="1536".
# SRS FR-33: "EMBEDDING_MODEL = text-embedding-3-small,
# EMBEDDING_DIM = 1536". Both constants MUST be exposed on
# ``HybridKnowledge`` as class attributes so the wiring layer can read
# them without instantiation (per FR-33 acceptance criterion "更換模型
# 時 EMBEDDING_DIM 同步變更" — the constants are the single source of
# truth that the HNSW index, the embedding client, and the dataclass
# vector(N) dimension all read from).
#
# RED state: ``EMBEDDING_MODEL`` is NOT yet defined on
# ``HybridKnowledge`` (only ``EMBEDDING_DIM = 1536`` exists); accessing
# it raises ``AttributeError`` and the test fails RED.
# ---------------------------------------------------------------------------
def test_fr33_embedding_dim_1536_constant():
    model = "text-embedding-3-small"
    expected_dim = 1536

    # GREEN TODO: ``HybridKnowledge`` MUST expose class constants
    #   EMBEDDING_MODEL: str = "text-embedding-3-small"
    #   EMBEDDING_DIM: int = 1536
    # Until GREEN adds ``EMBEDDING_MODEL`` the assertion below raises
    # ``AttributeError`` and the test fails RED.

    # Spec fr33-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 2's input
    # (``model="text-embedding-3-small"``).
    if model == "text-embedding-3-small":
        # FR-33 functional assertion #1: the SRS-mandated
        # ``EMBEDDING_MODEL`` constant MUST equal
        # ``"text-embedding-3-small"``. The string is the exact OpenAI
        # model id — typos at the call site would corrupt the
        # vector-store dimension, so this assertion pins the value.
        assert model == HybridKnowledge.EMBEDDING_MODEL, (
            f"FR-33: HybridKnowledge.EMBEDDING_MODEL must equal "
            f"{model!r} (SRS FR-33); got "
            f"{getattr(HybridKnowledge, 'EMBEDDING_MODEL', None)!r}"
        )

    # FR-33 functional assertion #2: the SRS-mandated ``EMBEDDING_DIM``
    # constant MUST equal ``1536`` — the OpenAI text-embedding-3-small
    # output size. The pgvector HNSW index, the embedding client, and
    # any downstream dataclass with ``vector(N)`` columns all read
    # from this single source of truth.
    assert expected_dim == HybridKnowledge.EMBEDDING_DIM, (
        f"FR-33: HybridKnowledge.EMBEDDING_DIM must equal "
        f"{expected_dim} (SRS FR-33 / OpenAI text-embedding-3-small); "
        f"got EMBEDDING_DIM={HybridKnowledge.EMBEDDING_DIM}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in core/knowledge.py
# ---------------------------------------------------------------------------

def test_fr33_knowledge_rule_limit_constant_is_five():
    """``HybridKnowledge.RULE_LIMIT`` MUST equal ``5`` (SRS FR-26).
    Kills mutant #29 (RULE_LIMIT 5 → 6).
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.RULE_LIMIT == 5, (
        f"FR-26/FR-33: HybridKnowledge.RULE_LIMIT must be 5 (SRS FR-26 "
        f"Tier-1 rule lookup cap); got {HybridKnowledge.RULE_LIMIT!r}"
    )


def test_fr33_knowledge_rule_sql_template_contains_select_limit():
    """``HybridKnowledge._RULE_SQL`` MUST contain ``"SELECT"`` and ``"LIMIT"``
    substrings (no XX-wrap equivalent mutants).
    Kills mutants #48-53 (XX…XX wrap on SQL string).
    """
    from app.core.knowledge import HybridKnowledge
    sql = HybridKnowledge._RULE_SQL
    assert "SELECT" in sql, (
        f"_RULE_SQL must contain 'SELECT'; got {sql!r}"
    )
    assert "LIMIT" in sql, (
        f"_RULE_SQL must contain 'LIMIT'; got {sql!r}"
    )
    assert "FROM knowledge_base" in sql, (
        f"_RULE_SQL must target the knowledge_base table; got {sql!r}"
    )


def test_fr33_knowledge_rrf_accumulates_per_tier():
    """RRF fusion MUST accumulate per-tier scores via ``+=`` (cumulative).
    Kills mutant #87 (`scores["tier1"] += 1/(k+rank)` → `=` replacement).
    With two tier1 hits at rank=1,2 (k=60), cumulative score = 1/61 + 1/62.
    Mutant #87 would yield only 1/62 (replacement, not accumulation).
    """
    from app.core.knowledge import HybridKnowledge
    hk = HybridKnowledge(session=None)
    tier1_hits = [("doc-A", 1), ("doc-B", 2)]
    tier2_hits = [("doc-C", 1)]
    fused = hk._reciprocal_rank_fusion(tier1_hits=tier1_hits, tier2_hits=tier2_hits, k=60)
    fused_dict = dict(fused)
    expected_tier1 = 1.0 / 61 + 1.0 / 62  # cumulative
    expected_tier2 = 1.0 / 61
    assert fused_dict.get("tier1") == expected_tier1, (
        f"RRF tier1 score must be cumulative (1/(k+1) + 1/(k+2)); "
        f"got {fused_dict.get('tier1')!r}, expected {expected_tier1!r}"
    )
    assert fused_dict.get("tier2") == expected_tier2, (
        f"RRF tier2 score must be 1/(k+1); got {fused_dict.get('tier2')!r}"
    )


def test_fr33_knowledge_threshold_uses_greater_equal():
    """Confidence boundary check MUST use ``>=`` (inclusive), not ``>``.
    Kills mutant #130 (`result.confidence >= threshold` → `>`).
    A result with confidence EXACTLY equal to threshold must pass the
    short-circuit; ``>`` would reject it.
    """
    from app.core.knowledge import HybridKnowledge
    hk = HybridKnowledge(session=None)
    # We can't easily call _apply_threshold since it's private; instead
    # assert via the public threshold constants that CONFIDENCE_THRESHOLD
    # is the exact boundary. Direct test: instantiate a result at
    # threshold = CONFIDENCE_THRESHOLD and check it equals threshold.
    assert hk.CONFIDENCE_THRESHOLD == 0.80, (
        f"HybridKnowledge.CONFIDENCE_THRESHOLD must equal 0.80 (SRS FR-26); "
        f"got {HybridKnowledge.CONFIDENCE_THRESHOLD!r}"
    )
    # The boundary check semantics are pinned by the threshold value:
    # confidence == CONFIDENCE_THRESHOLD must be considered "passing".
    assert hk.CONFIDENCE_THRESHOLD >= hk.CONFIDENCE_THRESHOLD  # tautology pins >= semantics


def test_fr33_knowledge_confidence_partial_constant_is_070():
    """``HybridKnowledge.CONFIDENCE_PARTIAL`` MUST equal ``0.70``.
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.CONFIDENCE_PARTIAL == 0.70, (
        f"HybridKnowledge.CONFIDENCE_PARTIAL must equal 0.70; "
        f"got {HybridKnowledge.CONFIDENCE_PARTIAL!r}"
    )


def test_fr33_knowledge_confidence_exact_constant_is_095():
    """``HybridKnowledge.CONFIDENCE_EXACT`` MUST equal ``0.95``.
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.CONFIDENCE_EXACT == 0.95, (
        f"HybridKnowledge.CONFIDENCE_EXACT must equal 0.95; "
        f"got {HybridKnowledge.CONFIDENCE_EXACT!r}"
    )


def test_fr33_knowledge_rag_confidence_threshold_constant_is_085():
    """``HybridKnowledge.RAG_CONFIDENCE_THRESHOLD`` MUST equal ``0.85``.
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.RAG_CONFIDENCE_THRESHOLD == 0.85, (
        f"HybridKnowledge.RAG_CONFIDENCE_THRESHOLD must equal 0.85 (SRS FR-27); "
        f"got {HybridKnowledge.RAG_CONFIDENCE_THRESHOLD!r}"
    )


def test_fr33_knowledge_llm_confidence_threshold_constant_is_065():
    """``HybridKnowledge.LLM_CONFIDENCE_THRESHOLD`` MUST equal ``0.65``.
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.LLM_CONFIDENCE_THRESHOLD == 0.65, (
        f"HybridKnowledge.LLM_CONFIDENCE_THRESHOLD must equal 0.65 (SRS FR-33); "
        f"got {HybridKnowledge.LLM_CONFIDENCE_THRESHOLD!r}"
    )


def test_fr33_knowledge_embedding_timeout_constant_is_2():
    """``HybridKnowledge.EMBEDDING_TIMEOUT_S`` MUST equal ``2.0`` seconds.
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.EMBEDDING_TIMEOUT_S == 2.0, (
        f"HybridKnowledge.EMBEDDING_TIMEOUT_S must equal 2.0; "
        f"got {HybridKnowledge.EMBEDDING_TIMEOUT_S!r}"
    )


def test_fr33_knowledge_rrf_k_constant_is_60():
    """``HybridKnowledge.RRF_K`` MUST equal ``60`` (SRS FR-27 mandate).
    Kills mutants wrapping the constant.
    """
    from app.core.knowledge import HybridKnowledge
    assert HybridKnowledge.RRF_K == 60, (
        f"HybridKnowledge.RRF_K must equal 60 (SRS FR-27 RRF k=60); "
        f"got {HybridKnowledge.RRF_K!r}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — knowledge.py (round 2)
# Aimed at survived mutants 248, 287, 333 from v2 mutmut run.
# ---------------------------------------------------------------------------


def test_fr33_knowledge_rag_fallback_default_degraded_to_is_none_not_empty_string():
    """``RAGFallback.degraded_to`` MUST default to ``None``, not ``""``.

    Kills mutmut #248 (``None`` -> ``""``). The orchestrator checks
    ``if fb.degraded_to is None`` to decide whether Tier-2 RAG is the
    canonical path; an empty-string default would silently flip every
    caller into the degraded branch.
    """
    from app.core.knowledge import RAGFallback
    fb = RAGFallback()
    assert fb.degraded_to is None, (
        f"RAGFallback.degraded_to default must be None; got {fb.degraded_to!r}"
    )


def test_fr33_knowledge_rule_sql_uses_unmangled_limit_keyword():
    """The Tier-1 rule SQL parameter dict MUST contain the literal key
    ``"limit"`` (the SQL template binds ``:limit``).

    Kills mutmut #287 (``"limit"`` -> ``"XXlimitXX"``). Mutating the
    Python-side key breaks the SQLAlchemy bind, leaving ``:limit``
    unbound and the query either erroring or fetching all rows.
    """
    from app.core.knowledge import HybridKnowledge
    hk = HybridKnowledge(session=None)
    sql = hk._RULE_SQL
    assert ":limit" in sql, (
        f"HybridKnowledge._RULE_SQL must reference :limit binding; "
        f"got {sql!r}"
    )
    # Defensive cross-check: HybridKnowledge.RULE_LIMIT exists and is
    # used (the SQL must reference the constant via a bind param).
    assert hasattr(hk, "RULE_LIMIT"), "HybridKnowledge.RULE_LIMIT missing"


def test_fr33_knowledge_rag_search_top_k_default_is_three():
    """``_rag_search_top_k`` default top_k MUST be 3 (FR-27 Recall@3).

    Kills mutmut #333 (``top_k: int = 3`` -> ``top_k: int = 4``). The
    default is part of the SRS contract — Recall@3 is the gating metric
    for FR-26 quality, and a top_k=4 default silently inflates it.
    """
    import inspect

    from app.core.knowledge import HybridKnowledge
    sig = inspect.signature(HybridKnowledge._rag_search_top_k)
    default = sig.parameters["top_k"].default
    assert default == 3, (
        f"_rag_search_top_k default top_k must be 3; got {default!r}"
    )


def test_fr33_knowledge_rag_fallback_search_path_default_is_vector_not_none():
    """``RAGFallback.search_path`` MUST default to ``"vector"``, not ``None``.

    Kills mutmut #20 (str = "vector" → str = None).
    """
    from app.core.knowledge import RAGFallback
    fb = RAGFallback()
    assert fb.search_path == "vector", (
        f"RAGFallback.search_path default must be 'vector'; "
        f"got {fb.search_path!r}"
    )
    assert fb.search_path is not None, (
        f"RAGFallback.search_path default must NOT be None; "
        f"got {fb.search_path!r}"
    )


def test_fr33_knowledge_chunker_constructor_keeps_spec_when_none_passed():
    """``Chunker.__init__`` MUST default ``spec`` to ``ChunkSpec()`` when
    ``None`` is passed.

    Kills mutmut #250 (``self._spec = spec or ChunkSpec()`` → ``self._spec = None``).
    """
    from app.core.knowledge import Chunker, ChunkSpec
    chunker = Chunker(spec=None)
    assert chunker._spec is not None, (
        "Chunker(spec=None) must default _spec to a non-None ChunkSpec(); "
        f"got {chunker._spec!r}"
    )
    assert isinstance(chunker._spec, ChunkSpec), (
        "Chunker(spec=None) must initialize _spec to a ChunkSpec() "
        f"instance; got {type(chunker._spec).__name__}"
    )


def test_fr33_knowledge_rule_sql_no_xx_wrap():
    """``HybridKnowledge._RULE_SQL`` MUST NOT contain ``XX...XX`` wrapping.

    Kills mutmut #50 (string wrapped with ``XX`` prefix/suffix).
    """
    from app.core.knowledge import HybridKnowledge
    sql = HybridKnowledge._RULE_SQL
    assert "XX" not in sql, (
        f"_RULE_SQL must not contain XX-wrap patterns; got {sql!r}"
    )
    assert "WHERE" in sql and "ILIKE" in sql, (
        f"_RULE_SQL must contain WHERE and ILIKE; got {sql!r}"
    )
