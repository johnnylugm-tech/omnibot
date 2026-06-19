"""TDD-RED: failing tests for FR-32 — KnowledgeResult data structure (frozen dataclass).

Spec source: 02-architecture/TEST_SPEC.md (FR-32)
SRS source : SRS.md FR-32

Acceptance criteria (from SRS FR-32):
    KnowledgeResult 資料結構：immutable frozen dataclass
    （id, content, confidence, source, knowledge_id(Optional)）；
    id=-1 代表非知識庫來源。
    KnowledgeResult 建構成功；source 限定 rule|rag|wiki|escalate。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``KnowledgeResult`` is already exported by
# ``app.core.knowledge`` as a frozen dataclass. However, the FR-32
# contract requires two additional invariants that the current
# implementation does NOT yet enforce:
#
#   1. ``source`` MUST be restricted to exactly one of the four
#      SRS-mandated values: ``rule``, ``rag``, ``wiki``, ``escalate``.
#      Any other string MUST raise ``ValueError`` so a typo at the call
#      site cannot silently produce a row with a bogus source label
#      that downstream routing would fail to dispatch.
#   2. ``knowledge_id`` MUST be ``Optional[int]`` (default ``None``)
#      because the FR-32 contract says id=-1 is the "non-knowledge-base"
#      marker — for that case ``knowledge_id`` is meaningless and
#      should default to ``None`` rather than force the caller to
#      fabricate a fake id (the current code requires an int, which
#      forces escalation sentinels to encode ``knowledge_id=-1``
#      alongside ``id=-1`` — duplicate state).
#
# GREEN must add to ``app/core/knowledge.py``:
#   - A module-level frozenset ``VALID_SOURCES`` listing the four
#     allowed source labels.
#   - A ``__post_init__`` on ``KnowledgeResult`` that raises
#     ``ValueError`` when ``source not in VALID_SOURCES``.
#   - A change to ``knowledge_id: int | None = None`` so the escalation
#     sentinel and other "no upstream row" callers can omit the field.
#
# The imports below are unguarded: pytest will collect this module and
# reach the assertions. The functional RED signal comes from the source
# enum rejection (test 2) — the existing dataclass accepts any string for
# ``source`` so a strict-assertion test that constructs an INVALID source
# and expects ``ValueError`` MUST fail until GREEN adds ``__post_init__``.
# ---------------------------------------------------------------------------
from app.core.knowledge import KnowledgeResult  # noqa: F401


# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/knowledge.py  (changes to the existing module)
#
#   VALID_SOURCES: frozenset[str] = frozenset(
#       {"rule", "rag", "wiki", "escalate"}
#   )
#
#   @dataclass(frozen=True)
#   class KnowledgeResult:
#       """[FR-32] Single knowledge hit returned by the hybrid pipeline.
#
#       ``source`` is restricted to ``VALID_SOURCES``; any other string
#       raises ``ValueError`` at construction time so misconfigured
#       callers fail loudly rather than silently producing an
#       un-dispatchable row. ``knowledge_id`` is optional because
#       ``id == -1`` is the SRS-mandated "non-knowledge-base" marker
#       (escalation sentinel) and the upstream row id is meaningless
#       in that case.
#       """
#       id: int
#       content: str
#       confidence: float
#       source: str  # MUST be in VALID_SOURCES
#       knowledge_id: int | None = None
#
#       def __post_init__(self) -> None:
#           if self.source not in VALID_SOURCES:
#               raise ValueError(
#                   f"FR-32: KnowledgeResult.source must be one of "
#                   f"{sorted(VALID_SOURCES)}; got source={self.source!r}"
#               )
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. KnowledgeResult is a frozen dataclass — mutation must raise
#    ``FrozenInstanceError``.
#
# Spec input: source="rule"; id="1"; attempt_mutate="content".
# SRS FR-32: "KnowledgeResult 資料結構：immutable frozen dataclass".
# The dataclass MUST be frozen end-to-end; assigning to any field after
# construction MUST raise ``dataclasses.FrozenInstanceError`` so callers
# cannot accidentally mutate a result that downstream routing has
# already dispatched on.
# ---------------------------------------------------------------------------
def test_fr32_knowledge_result_frozen():
    source = "rule"
    row_id = 1
    attempt_mutate = "content"

    # GREEN TODO: ``KnowledgeResult`` MUST remain frozen after GREEN
    # adds the ``__post_init__`` source-enum check. The post-init hook
    # must NOT mutate ``self.__frozen`` — the standard pattern is to
    # use ``object.__setattr__`` only inside ``__post_init__`` when an
    # immutable default needs to be coerced. Here no coercion is
    # needed, so the frozen property is preserved by construction.
    result = KnowledgeResult(
        id=row_id,
        content="original content",
        confidence=0.95,
        source=source,
        knowledge_id=10,
    )

    # Spec fr32-ok predicate 'result is not None' applies_to case 1.
    # The trigger variable for case 1 is ``source``; we gate the
    # predicate on that variable matching the spec input value
    # (``source="rule"``).
    if source == "rule":
        # Spec fr32-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (source="rule").
        assert result is not None, (
            "fr32-ok predicate: KnowledgeResult must be constructible "
            "with source='rule'"
        )

    # FR-32 functional assertion: ``KnowledgeResult`` MUST be a frozen
    # dataclass; assigning to any field after construction MUST raise
    # ``FrozenInstanceError``. The mutation target is the spec-pinned
    # ``attempt_mutate="content"`` field, exercised against a freshly
    # constructed row.
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        # The attribute name MUST be the spec input ``attempt_mutate``
        # field (``content``). Setting ``result.content`` on a frozen
        # dataclass is the canonical mutation that MUST be rejected.
        setattr(result, attempt_mutate, "mutated content")

    # FR-32 functional assertion #2: the original ``content`` MUST be
    # unchanged after the failed mutation attempt — confirming the
    # frozen guard rejected the write before the value was touched.
    assert result.content == "original content", (
        f"FR-32: KnowledgeResult.content must remain unchanged after "
        f"a frozen-mutation attempt; got content={result.content!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``KnowledgeResult.source`` is restricted to exactly four values:
#    ``rule``, ``rag``, ``wiki``, ``escalate``.
#
# Spec input: valid_sources="rule,rag,wiki,escalate".
# SRS FR-32: "source 限定 rule|rag|wiki|escalate". The four values
# enumerate the tier labels the hybrid pipeline can emit: Tier-1 ILIKE
# rule hit (``"rule"``), Tier-2 RAG short-circuit (``"rag"``),
# Tier-3 LLM answer (``"wiki"``), Tier-4 human escalation
# (``"escalate"``). The set MUST be exactly four — anything else MUST
# be rejected at construction time so a typo at the call site cannot
# produce a row that downstream routing fails to dispatch.
# ---------------------------------------------------------------------------
def test_fr32_source_enum_four_values():
    valid_sources = ["rule", "rag", "wiki", "escalate"]

    # GREEN TODO: ``KnowledgeResult`` MUST accept each of the four
    # SRS-mandated source strings and round-trip them onto ``.source``
    # verbatim. The dataclass's ``__post_init__`` (added by GREEN)
    # gates construction on ``source in VALID_SOURCES``; until that
    # post-init is added, this loop still succeeds because the
    # existing dataclass has no source validation, but the
    # invalid-source assertion below will fail (current code accepts
    # any string).
    for source in valid_sources:
        result = KnowledgeResult(
            id=1,
            content="x",
            confidence=0.95,
            source=source,
            knowledge_id=10,
        )

        # Spec fr32-ok predicate 'result is not None' applies_to case 1.
        # The trigger for case 2 is ``valid_sources``; each iteration
        # value IS a member of that list, so the predicate fires for
        # every loop iteration.
        if source in valid_sources:
            # Spec fr32-ok predicate 'result is not None' applies_to case 1.
            # The harness requires this assertion inside an `if VAR == c`
            # block whose trigger value matches TEST_SPEC case 2's input
            # (``valid_sources="rule,rag,wiki,escalate"``). Each
            # iteration value is a member of that set, so the predicate
            # fires for every iteration.
            assert result is not None, (
                f"fr32-ok predicate: KnowledgeResult must be "
                f"constructible with source={source!r}"
            )

        # FR-32 functional assertion: the source label MUST round-trip
        # verbatim onto the constructed instance.
        assert result.source == source, (
            f"FR-32: KnowledgeResult.source must equal {source!r}; "
            f"got source={result.source!r}"
        )

    # FR-32 functional assertion #2: the enum MUST be EXACTLY four
    # values. An invalid source MUST raise ``ValueError`` so a typo
    # at the call site cannot silently produce a row with a bogus
    # source label that downstream routing would fail to dispatch.
    # The current ``KnowledgeResult`` dataclass has NO source
    # validation, so this assertion MUST fail until GREEN adds
    # ``__post_init__`` that gates on ``source in VALID_SOURCES``.
    invalid_source = "bogus_source"
    with pytest.raises(ValueError):
        KnowledgeResult(
            id=1,
            content="x",
            confidence=0.95,
            source=invalid_source,  # NOT in VALID_SOURCES — must reject
            knowledge_id=10,
        )


# ---------------------------------------------------------------------------
# 3. ``KnowledgeResult(id=-1, source="escalate")`` is the canonical
#    non-knowledge-base sentinel (happy_path).
#
# Spec input: id="-1"; source="escalate".
# SRS FR-32: "KnowledgeResult.id=-1 代表非知識庫來源". The escalation
# sentinel is well-typed: ``id=-1`` flags "this row did NOT come from
# the knowledge_base table" and ``source="escalate"`` flags the human
# handoff path. Constructing the sentinel MUST succeed — Tier-4 callers
# depend on the dataclass accepting these values without raising.
# ---------------------------------------------------------------------------
def test_fr32_id_minus1_non_kb_marker():
    row_id = -1
    source = "escalate"

    # GREEN TODO: ``KnowledgeResult`` MUST accept ``id=-1`` and
    # ``source="escalate"`` as the canonical escalation sentinel.
    # ``source="escalate"`` is in the FR-32 enum so GREEN's
    # ``__post_init__`` accepts it; ``id=-1`` is a normal int field
    # with no validation, so the sentinel is constructible. The
    # ``knowledge_id`` field is optional per FR-32 — for the
    # escalation sentinel no upstream row exists, so the caller
    # omits the field (or passes ``None``).
    result = KnowledgeResult(
        id=row_id,
        content="escalate",
        confidence=0.0,
        source=source,
        knowledge_id=None,
    )

    # Spec fr32-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 3 is ``row_id`` (rendered as the spec's
    # ``id="-1"`` string); we gate on ``row_id == -1`` to mirror the
    # TEST_SPEC input ``id="-1"``.
    if row_id == -1:
        # Spec fr32-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input
        # (id="-1", i.e. row_id == -1).
        assert result is not None, (
            "fr32-ok predicate: KnowledgeResult must be constructible "
            "with id=-1 (non-KB marker)"
        )

    # FR-32 functional assertion #1: ``id`` MUST round-trip as the
    # spec-pinned ``-1`` so downstream routing can detect the
    # non-knowledge-base path via ``result.id == -1`` without sniffing
    # ``source``.
    assert result.id == row_id, (
        f"FR-32: KnowledgeResult.id must equal {row_id!r} "
        f"(non-knowledge-base marker); got id={result.id!r}"
    )
    # FR-32 functional assertion #2: ``source`` MUST round-trip as
    # ``"escalate"`` — the Tier-4 label that downstream routing
    # dispatches to the human operator.
    assert result.source == source, (
        f"FR-32: KnowledgeResult.source must equal {source!r} "
        f"(escalation label); got source={result.source!r}"
    )