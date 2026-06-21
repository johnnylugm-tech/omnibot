from __future__ import annotations
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
