from __future__ import annotations
"""TDD-RED: failing tests for FR-67 — Accuracy 聚合 (min(primary, secondary)).

Spec source: 02-architecture/TEST_SPEC.md (FR-67)
SRS source : SRS.md FR-67 (Module 14: LLM Judge — Accuracy aggregation)
SAD mapping: app.services.llm_judge — "LLM-as-a-Judge ensemble (FR-65–69)"

Acceptance criteria (from SRS FR-67 / TEST_SPEC.md):
    The accuracy score in the aggregated JudgeResult MUST equal
    ``min(primary_score, secondary_score)``.

    Rationale (SRS FR-67 verbatim, 保守評分): "幻覺不可接受" — when
    judging accuracy, we take the STRICTER of the two judges (the min),
    so a single lenient judge cannot mask a hallucination. This is the
    opposite of FR-66 (politeness = max, 寬鬆評分 — emotional-support
    scoring is generous).

    Each judge independently scores accuracy on a 1–5 scale:
        1 = False
        2 = Incomplete
        3 = Partially Correct
        4 = Correct
        5 = Excellent

    The aggregation function is the same ``LLMJudge.evaluate()``
    established by FR-65; FR-67 pins the accuracy-aggregation RULE
    only (min), not the underlying LLM plumbing.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


import asyncio
import inspect
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-67 mandates that ``LLMJudge.evaluate()`` in ``app.services.llm_judge``
# (SAD.md §2.4 / line 267, FR-65–69) aggregate accuracy as the MIN of
# the two judges' accuracy scores (SRS FR-67: "Accuracy 聚合：min(
# primary_score, secondary_score)（保守評分，幻覺不可接受）"; line 155).
#
# The GREEN contract pinned by this spec:
#
#   - ``LLMJudge.evaluate`` MUST aggregate accuracy as
#     ``min(primary.accuracy, secondary.accuracy)`` — the stricter
#     of the two scores. This is FR-67's "保守評分" rule.
#   - The aggregation MUST be observable on the JudgeResult's
#     ``accuracy`` attribute regardless of how GREEN represents
#     JudgeResult (pydantic / dataclass / SimpleNamespace / dict).
#   - Politeness aggregation is FR-66 scope and out of scope for FR-67 —
#     FR-67 only pins the accuracy axis.
#   - The 1-5 accuracy scale is the union of both judges' raw scores.
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because the
# aggregation logic does not yet exist — that is the valid RED signal.
# ---------------------------------------------------------------------------
from app.services.llm_judge import (
    LLMJudge,
)


# ---------------------------------------------------------------------------
# Helpers — built on top of the FR-65/FR-67 contract, not on GREEN's
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
    result = judge.evaluate(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def _extract_accuracy(result: object) -> object:
    """Read ``accuracy`` from any JudgeResult shape (object attr / dict /
    tuple). Used so GREEN can pick whichever representation makes sense."""
    if hasattr(result, "accuracy"):
        return result.accuracy
    if isinstance(result, dict):
        return result.get("accuracy")
    if isinstance(result, tuple) and len(result) >= 2:
        return result[1]
    raise AssertionError(
        f"FR-67: cannot extract 'accuracy' from JudgeResult {result!r}"
    )


# ---------------------------------------------------------------------------
# 1. Accuracy equals min of both judges (happy_path): when the two judges
#    return accuracy scores where one is lower than the other, the
#    aggregated JudgeResult.accuracy MUST equal min(primary, secondary).
#
# Spec input: primary_score="4"; secondary_score="3"; expected_accuracy="3".
# Spec sub-assertion: fr67-ok: result is not None.
# SRS FR-67 acceptance: "accuracy = min(two scores)" (SRS line 155).
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr67_accuracy_equals_min_of_both_judges():
    primary_score = "4"
    secondary_score = "3"
    expected_accuracy = "3"

    if primary_score == "4" and secondary_score == "3":
        # GREEN TODO: ``LLMJudge.evaluate`` MUST aggregate the accuracy
        # dimension as ``min(primary.accuracy, secondary.accuracy)``.
        # In this case primary=4 and secondary=3, so the aggregated
        # accuracy MUST be 3 (the stricter of the two). This is
        # FR-67's "保守評分" (conservative scoring) rule — accuracy
        # is judged by the harsher judge so a hallucination cannot be
        # masked by a lenient judge.
        #
        # Test isolation: stub the judge callables so they each return a
        # fixed accuracy score. The test never invokes a real LLM.
        primary_val = int(primary_score)
        secondary_val = int(secondary_score)

        async def _primary_acc4(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=primary_val,
                judge_name="primary",
            )

        async def _secondary_acc3(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=secondary_val,
                judge_name="secondary",
            )

        judge = LLMJudge(
            primary_judge=_primary_acc4,
            secondary_judge=_secondary_acc3,
        )

        async def _drive() -> object:
            return await _call_evaluate(
                judge, message="hi", response="hello"
            )

        result = asyncio.new_event_loop().run_until_complete(_drive())

        # fr67-ok predicate: result is not None.
        assert result is not None, (
            "fr67-ok predicate: LLMJudge.evaluate must return a non-None "
            "JudgeResult when both judges succeed (accuracy=min test)."
        )

        # FR-67 core assertion: accuracy MUST equal min(4, 3) = 3.
        accuracy = _extract_accuracy(result)
        assert accuracy == int(expected_accuracy), (
            f"FR-67: aggregated accuracy must equal "
            f"min(primary_score, secondary_score) = "
            f"min({primary_val}, {secondary_val}) = {expected_accuracy}; "
            f"got {accuracy!r}. SRS FR-67 mandates 'accuracy = min("
            f"two scores)' (line 155, 保守評分 rule)."
        )

    # Sentinels MUST be preserved per spec.
    assert primary_score == "4", (
        f"FR-67: primary_score sentinel must be '4'; got {primary_score!r}"
    )
    assert secondary_score == "3", (
        f"FR-67: secondary_score sentinel must be '3'; got {secondary_score!r}"
    )
    assert expected_accuracy == "3", (
        f"FR-67: expected_accuracy sentinel must be '3'; "
        f"got {expected_accuracy!r}"
    )


# ---------------------------------------------------------------------------
# 2. Primary higher, secondary lower → use secondary (validation): when the
#    secondary judge is the stricter one, the aggregated accuracy MUST take
#    the secondary's lower score (NOT the primary's higher score). This pins
#    the "min" rule from the secondary-wins direction so GREEN cannot
#    accidentally implement "max" or "average".
#
# Spec input: primary_score="5"; secondary_score="2"; expected_accuracy="2".
# Spec sub-assertion: fr67-ok: result is not None.
# SRS FR-67 acceptance: "accuracy = min(two scores)"; accuracy is the
#   "stricter" of the two judges (2 = Incomplete).
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr67_primary_higher_secondary_lower_uses_secondary():
    primary_score = "5"
    secondary_score = "2"
    expected_accuracy = "2"

    if primary_score == "5" and secondary_score == "2":
        # GREEN TODO: ``LLMJudge.evaluate`` MUST aggregate accuracy as
        # ``min(primary.accuracy, secondary.accuracy)``. In this case
        # primary=5 (Excellent) and secondary=2 (Incomplete), so the
        # aggregated accuracy MUST be 2 — i.e. the secondary's lower
        # score wins. This is FR-67's "保守評分" rule applied in the
        # secondary-wins direction: GREEN must NOT silently drop the
        # secondary's lower score in favour of the primary's higher one.
        #
        # Test isolation: stub the judge callables so they each return a
        # fixed accuracy score. The test never invokes a real LLM.
        primary_val = int(primary_score)
        secondary_val = int(secondary_score)

        async def _primary_acc5(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=primary_val,
                judge_name="primary",
            )

        async def _secondary_acc2(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=secondary_val,
                judge_name="secondary",
            )

        judge = LLMJudge(
            primary_judge=_primary_acc5,
            secondary_judge=_secondary_acc2,
        )

        async def _drive() -> object:
            return await _call_evaluate(
                judge, message="hi", response="hello"
            )

        result = asyncio.new_event_loop().run_until_complete(_drive())

        # fr67-ok predicate: result is not None.
        assert result is not None, (
            "fr67-ok predicate: LLMJudge.evaluate must return a non-None "
            "JudgeResult when both judges succeed (secondary-lower test)."
        )

        # FR-67 core assertion: accuracy MUST equal min(5, 2) = 2.
        # Specifically the SECONDARY's lower score wins, not the
        # primary's higher score.
        accuracy = _extract_accuracy(result)
        assert accuracy == int(expected_accuracy), (
            f"FR-67: aggregated accuracy must equal "
            f"min(primary_score, secondary_score) = "
            f"min({primary_val}, {secondary_val}) = {expected_accuracy}; "
            f"got {accuracy!r}. SRS FR-67 mandates 'accuracy = min("
            f"two scores)' (line 155, 保守評分 rule). The secondary's "
            f"lower score ({secondary_val}) must win over the primary's "
            f"higher score ({primary_val}); got {accuracy!r}."
        )

        # Explicit anti-regression: accuracy MUST NOT collapse to the
        # primary's higher score. This pins that GREEN did not implement
        # "first judge wins" or "primary wins" by mistake.
        assert accuracy != primary_val, (
            f"FR-67: aggregated accuracy must NOT be the primary's "
            f"higher score ({primary_val}); got {accuracy!r}. SRS FR-67 "
            f"mandates 'accuracy = min(two scores)' — when secondary "
            f"is lower, the secondary wins."
        )

        # And the result MUST stay on the 1-5 accuracy scale (2 = Incomplete).
        assert isinstance(accuracy, (int, float)) and 1 <= accuracy <= 5, (
            f"FR-67: aggregated accuracy must lie on the 1-5 scale; "
            f"got {accuracy!r} from result={result!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert primary_score == "5", (
        f"FR-67: primary_score sentinel must be '5'; got {primary_score!r}"
    )
    assert secondary_score == "2", (
        f"FR-67: secondary_score sentinel must be '2'; got {secondary_score!r}"
    )
    assert expected_accuracy == "2", (
        f"FR-67: expected_accuracy sentinel must be '2'; "
        f"got {expected_accuracy!r}"
    )


# ---------------------------------------------------------------------------
# 3. Must NOT use max for accuracy aggregation (negative_constraint):
#    FR-67 explicitly forbids max-aggregation for accuracy. If a judge
#    gives a perfect 5 and another gives 1, the aggregated accuracy MUST
#    be 1 (the stricter score), NOT 5 (max would mask a hallucination).
#
# Spec input: primary_score="5"; secondary_score="1"; expected_accuracy="1";
#            forbidden_result="5".
# Spec sub-assertion: fr67-ok: result is not None.
# SRS FR-67 rationale: "幻覺不可接受" — hallucination is not acceptable;
#   the stricter score wins, never the more lenient one.
# Test type: negative_constraint (Q8 derivation).
# ---------------------------------------------------------------------------
def test_fr67_must_not_use_max_for_accuracy_aggregation():
    primary_score = "5"
    secondary_score = "1"
    expected_accuracy = "1"
    forbidden_result = "5"

    if (
        primary_score == "5"
        and secondary_score == "1"
        and forbidden_result == "5"
    ):
        # GREEN TODO: ``LLMJudge.evaluate`` MUST NOT use ``max`` for
        # accuracy aggregation. The anti-pattern (max) would mask a
        # hallucination: if primary says 5 (Excellent) and secondary
        # says 1 (False), the strict min rule MUST yield 1 — the
        # stricter of the two. FR-67's "幻覺不可接受" rule forbids
        # using max for accuracy.
        #
        # Test isolation: stub the judge callables so they each return a
        # fixed accuracy score. The test never invokes a real LLM.
        primary_val = int(primary_score)
        secondary_val = int(secondary_score)
        forbidden_val = int(forbidden_result)

        async def _primary_acc5(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=primary_val,
                judge_name="primary",
            )

        async def _secondary_acc1(*_args: object, **_kwargs: object) -> object:
            return _make_judge_result(
                politeness=4,
                accuracy=secondary_val,
                judge_name="secondary",
            )

        judge = LLMJudge(
            primary_judge=_primary_acc5,
            secondary_judge=_secondary_acc1,
        )

        async def _drive() -> object:
            return await _call_evaluate(
                judge, message="hi", response="hello"
            )

        result = asyncio.new_event_loop().run_until_complete(_drive())

        # fr67-ok predicate: result is not None.
        assert result is not None, (
            "fr67-ok predicate: LLMJudge.evaluate must return a non-None "
            "JudgeResult when both judges succeed (no-max constraint test)."
        )

        # FR-67 core assertion: accuracy MUST equal min(5, 1) = 1.
        accuracy = _extract_accuracy(result)
        assert accuracy == int(expected_accuracy), (
            f"FR-67: aggregated accuracy must equal "
            f"min(primary_score, secondary_score) = "
            f"min({primary_val}, {secondary_val}) = {expected_accuracy}; "
            f"got {accuracy!r}. SRS FR-67 forbids max-aggregation for "
            f"accuracy (幻覺不可接受 rule)."
        )

        # Negative_constraint: accuracy MUST NOT be the max value.
        # If GREEN accidentally implements max instead of min, the
        # aggregated accuracy would be 5 (the more lenient primary
        # score), which would mask the secondary's detection of a
        # hallucination (1 = False). FR-67 explicitly forbids this.
        assert accuracy != forbidden_val, (
            f"FR-67: aggregated accuracy must NOT be the max of the "
            f"two scores ({forbidden_val}); got {accuracy!r}. FR-67 "
            f"forbids max-aggregation for accuracy (幻覺不可接受: "
            f"hallucination is not acceptable). The stricter score "
            f"({secondary_val}) must win over the lenient score "
            f"({primary_val})."
        )

        # And the result MUST stay on the 1-5 accuracy scale (1 = False).
        assert isinstance(accuracy, (int, float)) and 1 <= accuracy <= 5, (
            f"FR-67: aggregated accuracy must lie on the 1-5 scale; "
            f"got {accuracy!r} from result={result!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert primary_score == "5", (
        f"FR-67: primary_score sentinel must be '5'; got {primary_score!r}"
    )
    assert secondary_score == "1", (
        f"FR-67: secondary_score sentinel must be '1'; got {secondary_score!r}"
    )
    assert expected_accuracy == "1", (
        f"FR-67: expected_accuracy sentinel must be '1'; "
        f"got {expected_accuracy!r}"
    )
    assert forbidden_result == "5", (
        f"FR-67: forbidden_result sentinel must be '5'; "
        f"got {forbidden_result!r}"
    )


# ---------------------------------------------------------------------------
# Suppress "imported but unused" warnings for the imports that exist purely
# to force collection-time failures during the RED step. These stay in
# scope so a future refactor cannot silently drop the FR-67 contract.
# ---------------------------------------------------------------------------
_ = MagicMock
                # GREEN will see once it implements the aggregation.
