"""TDD-RED: failing tests for FR-66 — Politeness 聚合 (max(primary, secondary)).

Spec source: 02-architecture/TEST_SPEC.md (FR-66)
SRS source : SRS.md FR-66 (Module 14: LLM Judge — Politeness aggregation)
SAD mapping: app.services.llm_judge — "LLM-as-a-Judge ensemble (FR-65–69)"

Acceptance criteria (from SRS FR-66 / TEST_SPEC.md):
    The politeness score in the aggregated JudgeResult MUST equal
    ``max(primary_score, secondary_score)``.

    Rationale (SRS FR-66 verbatim, 寬鬆評分): "情感支持寧可寬容" — when
    judging politeness for emotional-support conversations, we take the
    MORE generous of the two judges (the max), so a single stricter
    judge cannot drag a kind response down. This is the opposite of
    FR-67 (accuracy = min, 保守評分 — hallucination不可接受).

    Each judge independently scores politeness on a 1–5 scale:
        1 = Rude
        2 = Cold
        3 = Professional
        4 = Warm
        5 = Exceptional

    The aggregation function is the same ``LLMJudge.evaluate()``
    established by FR-65; FR-66 pins the politeness-aggregation RULE
    only (max), not the underlying LLM plumbing.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import asyncio
import inspect
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-66 mandates that ``LLMJudge.evaluate()`` in ``app.services.llm_judge``
# (SAD.md §2.4 / line 267, FR-65–69) aggregate politeness as the MAX of
# the two judges' politeness scores (SRS FR-66: "Politeness 聚合：max(
# primary_score, secondary_score)（寬鬆評分，情感支持寧可寬容）"; line 154).
#
# The GREEN contract pinned by this spec:
#
#   - ``LLMJudge.evaluate`` MUST aggregate politeness as
#     ``max(primary.politeness, secondary.politeness)`` — the more
#     generous of the two scores. This is FR-66's "寬鬆評分" rule.
#   - The aggregation MUST be observable on the JudgeResult's
#     ``politeness`` attribute regardless of how GREEN represents
#     JudgeResult (pydantic / dataclass / SimpleNamespace / dict).
#   - Accuracy aggregation is FR-67 scope and out of scope for FR-66 —
#     FR-66 only pins the politeness axis.
#   - The 1-5 politeness scale is the union of both judges' raw scores.
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because the
# aggregation logic does not yet exist — that is the valid RED signal.
# ---------------------------------------------------------------------------
from app.services.llm_judge import (
    LLMJudge,
)


# ---------------------------------------------------------------------------
# Helpers — built on top of the FR-65/FR-66 contract, not on GREEN's
# eventual implementation. They let the tests assert behaviour without
# depending on whether JudgeResult is implemented as a pydantic model,
# dataclass, plain object, or dict.
# ---------------------------------------------------------------------------
def _make_judge_result(
    politeness: int,
    accuracy: int,
    judge_name: str = "",
) -> object:
    """Build a JudgeResult stand-in. GREEN's JudgeResult may be a pydantic
    BaseModel, dataclass, NamedTuple, SimpleNamespace, or dict — the tests
    only ever read ``.politeness`` / ``.accuracy`` so any of those work."""
    return types.SimpleNamespace(
        politeness=politeness,
        accuracy=accuracy,
        judge_name=judge_name,
    )


async def _call_evaluate(judge: LLMJudge, *args: object, **kwargs: object) -> object:
    """Call ``judge.evaluate(...)`` handling both sync and async implementations.

    The SAD marks LLMJudge as a parallel-network-call module, so GREEN will
    almost certainly make ``evaluate`` async. But we accept sync too in case
    GREEN chooses a ThreadPoolExecutor design — the behavioural contract is
    the same either way.
    """
    result = judge.evaluate(*args, **kwargs)  # type: ignore[arg-type]
    if inspect.isawaitable(result):
        result = await result  # type: ignore[assignment]
    return result


def _extract_politeness(result: object) -> object:
    """Read ``politeness`` from any JudgeResult shape (object attr / dict /
    tuple). Used so GREEN can pick whichever representation makes sense."""
    if hasattr(result, "politeness"):
        return result.politeness
    if isinstance(result, dict):
        return result.get("politeness")
    if isinstance(result, tuple) and len(result) >= 1:
        return result[0]
    raise AssertionError(
        f"FR-66: cannot extract 'politeness' from JudgeResult {result!r}"
    )


# ---------------------------------------------------------------------------
# 1. Politeness equals max of both judges (happy_path): when the two judges
#    return politeness scores where one is higher than the other, the
#    aggregated JudgeResult.politeness MUST equal max(primary, secondary).
#
# Spec input: primary_score="3"; secondary_score="4"; expected_politeness="4".
# Spec sub-assertion: fr66-ok: result is not None.
# SRS FR-66 acceptance: "politeness = max(two scores)" (SRS line 154).
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr66_politeness_equals_max_of_both_judges():
    primary_score = "3"
    secondary_score = "4"
    expected_politeness = "4"

    if primary_score == "3" and secondary_score == "4":
        # GREEN TODO: ``LLMJudge.evaluate`` MUST aggregate the politeness
        # dimension as ``max(primary.politeness, secondary.politeness)``.
        # In this case primary=3 and secondary=4, so the aggregated
        # politeness MUST be 4 (the more generous of the two). This is
        # FR-66's "寬鬆評分" (lenient scoring) rule — emotional-support
        # conversations are scored by the kinder judge.
        #
        # Test isolation: stub the judge callables so they each return a
        # fixed politeness score. The test never invokes a real LLM.
        primary_val = int(primary_score)
        secondary_val = int(secondary_score)

        async def _primary_pol3(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=primary_val,
                accuracy=4,
                judge_name="primary",
            )

        async def _secondary_pol4(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=secondary_val,
                accuracy=4,
                judge_name="secondary",
            )

        judge = LLMJudge(
            primary_judge=_primary_pol3,
            secondary_judge=_secondary_pol4,
        )

        async def _drive() -> object:
            return await _call_evaluate(
                judge, message="hi", response="hello"
            )

        result = asyncio.new_event_loop().run_until_complete(_drive())

        # fr66-ok predicate: result is not None.
        assert result is not None, (
            "fr66-ok predicate: LLMJudge.evaluate must return a non-None "
            "JudgeResult when both judges succeed (politeness=max test)."
        )

        # FR-66 core assertion: politeness MUST equal max(3, 4) = 4.
        politeness = _extract_politeness(result)
        assert politeness == int(expected_politeness), (
            f"FR-66: aggregated politeness must equal "
            f"max(primary_score, secondary_score) = "
            f"max({primary_val}, {secondary_val}) = {expected_politeness}; "
            f"got {politeness!r}. SRS FR-66 mandates 'politeness = max("
            f"two scores)' (line 154, 寬鬆評分 rule)."
        )

    # Sentinels MUST be preserved per spec.
    assert primary_score == "3", (
        f"FR-66: primary_score sentinel must be '3'; got {primary_score!r}"
    )
    assert secondary_score == "4", (
        f"FR-66: secondary_score sentinel must be '4'; got {secondary_score!r}"
    )
    assert expected_politeness == "4", (
        f"FR-66: expected_politeness sentinel must be '4'; "
        f"got {expected_politeness!r}"
    )


# ---------------------------------------------------------------------------
# 2. Primary lower, secondary higher → use secondary (validation): when the
#    secondary judge is the more generous one, the aggregated politeness
#    MUST take the secondary's higher score (NOT the primary's lower
#    score). This pins the "max" rule from the secondary-wins direction
#    so GREEN cannot accidentally implement "min" or "average".
#
# Spec input: primary_score="2"; secondary_score="5"; expected_politeness="5".
# Spec sub-assertion: fr66-ok: result is not None.
# SRS FR-66 acceptance: "politeness = max(two scores)"; politeness is the
#   "kinder" of the two judges (5 = Exceptional).
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr66_primary_lower_secondary_higher_uses_secondary():
    primary_score = "2"
    secondary_score = "5"
    expected_politeness = "5"

    if primary_score == "2" and secondary_score == "5":
        # GREEN TODO: ``LLMJudge.evaluate`` MUST aggregate politeness as
        # ``max(primary.politeness, secondary.politeness)``. In this case
        # primary=2 (Cold) and secondary=5 (Exceptional), so the
        # aggregated politeness MUST be 5 — i.e. the secondary's higher
        # score wins. This is FR-66's "寬鬆評分" rule applied in the
        # secondary-wins direction: GREEN must NOT silently drop the
        # secondary's higher score in favour of the primary's lower one.
        #
        # Test isolation: stub the judge callables so they each return a
        # fixed politeness score. The test never invokes a real LLM.
        primary_val = int(primary_score)
        secondary_val = int(secondary_score)

        async def _primary_pol2(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=primary_val,
                accuracy=4,
                judge_name="primary",
            )

        async def _secondary_pol5(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=secondary_val,
                accuracy=4,
                judge_name="secondary",
            )

        judge = LLMJudge(
            primary_judge=_primary_pol2,
            secondary_judge=_secondary_pol5,
        )

        async def _drive() -> object:
            return await _call_evaluate(
                judge, message="hi", response="hello"
            )

        result = asyncio.new_event_loop().run_until_complete(_drive())

        # fr66-ok predicate: result is not None.
        assert result is not None, (
            "fr66-ok predicate: LLMJudge.evaluate must return a non-None "
            "JudgeResult when both judges succeed (secondary-higher test)."
        )

        # FR-66 core assertion: politeness MUST equal max(2, 5) = 5.
        # Specifically the SECONDARY's higher score wins, not the
        # primary's lower score.
        politeness = _extract_politeness(result)
        assert politeness == int(expected_politeness), (
            f"FR-66: aggregated politeness must equal "
            f"max(primary_score, secondary_score) = "
            f"max({primary_val}, {secondary_val}) = {expected_politeness}; "
            f"got {politeness!r}. SRS FR-66 mandates 'politeness = max("
            f"two scores)' (line 154, 寬鬆評分 rule). The secondary's "
            f"higher score ({secondary_val}) must win over the primary's "
            f"lower score ({primary_val}); got {politeness!r}."
        )

        # Explicit anti-regression: politeness MUST NOT collapse to the
        # primary's lower score. This pins that GREEN did not implement
        # "first judge wins" or "primary wins" by mistake.
        assert politeness != primary_val, (
            f"FR-66: aggregated politeness must NOT be the primary's "
            f"lower score ({primary_val}); got {politeness!r}. SRS FR-66 "
            f"mandates 'politeness = max(two scores)' — when secondary "
            f"is higher, the secondary wins."
        )

        # And the result MUST stay on the 1-5 politeness scale (5 = Exceptional).
        assert isinstance(politeness, (int, float)) and 1 <= politeness <= 5, (
            f"FR-66: aggregated politeness must lie on the 1-5 scale; "
            f"got {politeness!r} from result={result!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert primary_score == "2", (
        f"FR-66: primary_score sentinel must be '2'; got {primary_score!r}"
    )
    assert secondary_score == "5", (
        f"FR-66: secondary_score sentinel must be '5'; got {secondary_score!r}"
    )
    assert expected_politeness == "5", (
        f"FR-66: expected_politeness sentinel must be '5'; "
        f"got {expected_politeness!r}"
    )


# ---------------------------------------------------------------------------
# Suppress "imported but unused" warnings for the imports that exist purely
# to force collection-time failures during the RED step. These stay in
# scope so a future refactor cannot silently drop the FR-66 contract.
# ---------------------------------------------------------------------------
_ = MagicMock
                # GREEN will see once it implements the aggregation.
