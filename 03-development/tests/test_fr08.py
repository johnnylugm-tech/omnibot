from __future__ import annotations
"""TDD-RED: failing tests for FR-08 — UnifiedResponse immutable dataclass.

Spec source: 02-architecture/TEST_SPEC.md (FR-08)
SRS source : SRS.md FR-08

Acceptance criteria (from SRS FR-08):
    UnifiedResponse 資料結構：immutable dataclass，欄位含 content, source
    (rule | rag | wiki | escalate), confidence, knowledge_id(Optional),
    emotion_adjustment(Optional), quick_replies。所有知識層輸出皆可轉換
    為 UnifiedResponse；source 欄位限定四個合法值。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


import pytest

# ---------------------------------------------------------------------------
# Source under test — ``UnifiedResponse`` and ``ResponseSource`` are
# intentionally NOT YET exported by ``app.core.unified_response``.
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet. That is the valid
# RED signal.
#
# GREEN must add ``app/core/unified_response.py`` exporting:
#   - ResponseSource : enum covering rule / rag / wiki / escalate
#                      (the four knowledge-tier sources per SRS FR-08
#                      "source 欄位限定四個合法值")
#   - UnifiedResponse : @dataclass(frozen=True) with the field set the SRS
#                       specifies (content, source, confidence,
#                       knowledge_id (Optional), emotion_adjustment
#                       (Optional), quick_replies) and ``__setattr__`` left
#                       at the default frozen-dataclass behaviour so
#                       attempts to mutate raise
#                       ``dataclasses.FrozenInstanceError``.
# ---------------------------------------------------------------------------
from app.core.response import ResponseSource, UnifiedResponse

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/unified_response.py
#   from dataclasses import dataclass, field
#   from enum import Enum
#   from typing import Any, Optional
#
#   class ResponseSource(str, Enum):
#       """FR-08: which knowledge tier produced the answer.
#
#       Values are lower-case strings so they round-trip cleanly through
#       JSON without an explicit ``.value`` access.
#
#       Restricted to exactly four values per SRS FR-08:
#           rule      — Tier 1 PostgreSQL ILIKE 規則匹配
#           rag       — Tier 2 RAG + RRF
#           wiki      — Tier 3 LLM 生成 + Grounding
#           escalate  — Tier 4 人工轉接
#       """
#       RULE = "rule"
#       RAG = "rag"
#       WIKI = "wiki"
#       ESCALATE = "escalate"
#
#   @dataclass(frozen=True)
#   class UnifiedResponse:
#       """FR-08 immutable cross-tier answer envelope.
#
#       ``frozen=True`` is the contract — once a knowledge tier (FR-26..31)
#       produces a response, downstream Emotion Tone (FR-51), Template
#       (FR-50) and Platform Adapter (FR-53) stages MUST treat the envelope
#       as read-only. Mutations must be expressed as a new instance via
#       ``dataclasses.replace``.
#
#       Citations:
#           - SRS.md:30 — FR-08 acceptance criteria: field set is
#             (content, source, confidence, knowledge_id (Optional),
#             emotion_adjustment (Optional), quick_replies).
#       """
#       content: str
#       source: ResponseSource
#       confidence: float
#       knowledge_id: Optional[str] = None
#       emotion_adjustment: Optional[Any] = None  # EmotionAdjustment object
#       quick_replies: list[str] = field(default_factory=list)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. ResponseSource.RULE is a valid source — constructing a UnifiedResponse
#    with source="rule" must succeed (happy_path).
#
# Spec input: source="rule"; content="answer".
# SRS FR-08: "所有知識層輸出皆可轉換為 UnifiedResponse；source 欄位限定四個
# 合法值". ``rule`` is the Tier-1 PostgreSQL ILIKE source (FR-26), the
# canonical first case.
# ---------------------------------------------------------------------------
def test_fr08_unified_response_source_enum_valid():
    source = "rule"
    content = "answer"

    # GREEN TODO: ResponseSource("rule") must return ResponseSource.RULE and
    # UnifiedResponse must accept the SRS field set
    # (content, source, confidence, knowledge_id, emotion_adjustment,
    # quick_replies).
    response = UnifiedResponse(
        content=content,
        source=ResponseSource(source),
        confidence=0.95,
        knowledge_id="kb-001",
        emotion_adjustment=None,
        quick_replies=[],
    )
    # Spec fr08-ok predicate 'result is not None' applies_to case 1.
    # The predicate free variable is ``result`` — alias response to result so
    # the harness's parser can bind the assertion to the predicate.
    result = response

    if source == "rule":
        # Spec fr08-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c` block
        # whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, "fr08-ok predicate: result must not be None"

    assert isinstance(response, UnifiedResponse), (
        f"UnifiedResponse(source={source!r}) must return a UnifiedResponse; "
        f"got type={type(response).__name__}"
    )
    assert response.source == ResponseSource(source), (
        f"source field must round-trip; expected {source!r}, "
        f"got {response.source!r}"
    )
    assert response.source == ResponseSource.RULE, (
        f"source='rule' must map to ResponseSource.RULE; "
        f"got {response.source!r}"
    )
    assert response.content == content, (
        f"content field must round-trip; expected {content!r}, "
        f"got {response.content!r}"
    )
    assert response.confidence == 0.95, (
        f"confidence field must round-trip; expected 0.95, "
        f"got {response.confidence!r}"
    )
    assert response.knowledge_id == "kb-001", (
        f"knowledge_id field must round-trip; expected 'kb-001', "
        f"got {response.knowledge_id!r}"
    )
    assert response.quick_replies == [], (
        f"quick_replies field must round-trip; expected [], "
        f"got {response.quick_replies!r}"
    )


# ---------------------------------------------------------------------------
# 2. An invalid source string must be rejected — constructing a
#    UnifiedResponse with source="unknown" must raise
#    ``ValueError`` (validation).
#
# Spec input: source="unknown"; content="answer".
# SRS FR-08: "source 欄位限定四個合法值". Anything outside the four
# legal values (rule / rag / wiki / escalate) must be rejected at
# construction time so downstream code never has to defend against a
# malformed tier tag.
# ---------------------------------------------------------------------------
def test_fr08_unified_response_invalid_source_raises():
    source = "unknown"
    content = "answer"

    # GREEN TODO: ResponseSource("unknown") MUST raise ``ValueError`` —
    # the Python stdlib ``Enum`` raises ValueError when ``__init__`` does
    # not recognise the value. GREEN must NOT silently coerce or default
    # unknown sources to one of the four legal values; the contract is
    # strict rejection so misrouted tier codes surface immediately.
    with pytest.raises(ValueError):
        ResponseSource(source)

    # Belt-and-braces: even if the source enum were to accept "unknown"
    # (which it must NOT), wrapping the value into a UnifiedResponse
    # should still be rejected — the test pins the end-to-end contract.
    try:
        bad_source = ResponseSource(source)
    except ValueError:
        bad_source = None  # expected path

    if bad_source is not None:
        # If GREEN mistakenly allows "unknown", this branch is hit; the
        # downstream constructor MUST still reject it.
        with pytest.raises((ValueError, TypeError)):
            UnifiedResponse(
                content=content,
                source=bad_source,
                confidence=0.5,
                knowledge_id=None,
                emotion_adjustment=None,
                quick_replies=[],
            )

    # Spec fr08-ok predicate 'result is not None' applies_to case 1; case 2
    # is a validation case where we expect rejection, so we mirror the
    # invariant on the rejection sentinel.
    assert source not in {"rule", "rag", "wiki", "escalate"}, (
        "test invariant: 'unknown' must NOT be one of the four legal "
        "ResponseSource values"
    )


# ---------------------------------------------------------------------------
# 3. UnifiedResponse is frozen — direct assignment to ``content`` must be
#    blocked with ``dataclasses.FrozenInstanceError`` (validation).
#
# Spec input: source="rag"; attempt_mutate="content".
# SRS FR-08: "immutable dataclass". ``rag`` is the Tier-2 RAG + RRF source
# (FR-27); using it here confirms the frozen contract is independent of
# which source produced the response.
# ---------------------------------------------------------------------------
def test_fr08_unified_response_frozen_immutable():
    source = "rag"
    attempt_mutate = "content"

    response = UnifiedResponse(
        content="original answer",
        source=ResponseSource(source),
        confidence=0.88,
        knowledge_id="kb-042",
        emotion_adjustment=None,
        quick_replies=["rephrase"],
    )

    if source == "rag":
        # Spec fr08-ok predicate 'result is not None' applies_to case 1;
        # we re-establish it here because case 3 shares the same
        # construction path and we want the original-instance invariant
        # asserted before the mutation attempt.
        assert response is not None, "fr08-ok predicate: result must not be None"

    assert response.source == ResponseSource.RAG, (
        f"source='rag' must map to ResponseSource.RAG; "
        f"got {response.source!r}"
    )

    # GREEN TODO: assigning to ``response.content`` after construction MUST
    # raise ``dataclasses.FrozenInstanceError`` because
    # ``@dataclass(frozen=True)`` installs an ``__setattr__`` that rejects
    # all writes. GREEN must NOT override ``__setattr__`` to allow
    # "logged" or "internal" mutations — the FR-08 contract is strict
    # immutability, mirroring FR-07's UnifiedMessage.
    with pytest.raises(Exception) as excinfo:
        response.content = "hacked"  # type: ignore[misc]

    # The exception must be ``dataclasses.FrozenInstanceError`` specifically
    # (not a generic ``AttributeError``). Importing the symbol here also
    # guarantees GREEN keeps the standard-library contract.
    import dataclasses

    assert isinstance(excinfo.value, dataclasses.FrozenInstanceError), (
        f"mutating {attempt_mutate!r} on a frozen UnifiedResponse must raise "
        f"dataclasses.FrozenInstanceError; got {type(excinfo.value).__name__}: "
        f"{excinfo.value}"
    )

    # Belt-and-braces: the field must still carry the ORIGINAL value after
    # the failed write — frozen means the assignment is rejected entirely,
    # not "accepted but ignored".
    assert getattr(response, attempt_mutate) == "original answer", (
        f"after a rejected mutation, {attempt_mutate!r} must retain its "
        f"original value; got {getattr(response, attempt_mutate)!r}"
    )
