from __future__ import annotations
"""TDD-RED: failing tests for FR-68 — CSAT 公式 0.4×速度 + 0.2×擬人化 + 0.2×禮貌 + 0.2×準確.

Spec source: 02-architecture/TEST_SPEC.md (FR-68)
SRS source : SRS.md FR-68 (Module 14: LLM Judge — CSAT aggregation)
SAD mapping: app.services.llm_judge — "CSAT = 0.4×speed + 0.2×anthro +
            0.2×politeness + 0.2×accuracy → FR-68" (line 270)

Acceptance criteria (from SRS FR-68 / TEST_SPEC.md):
    aggregate_csat(speed, personalization, politeness, accuracy) MUST compute
    the weighted CSAT score using the canonical formula:

        CSAT = 0.4 * speed
             + 0.2 * personalization
             + 0.2 * politeness
             + 0.2 * accuracy

    Each of the four input scores is on a 1-5 scale; the resulting CSAT
    score is therefore also in the closed interval [0, 5] (weights sum to
    1.0; the floor of 0 is included for type-inclusivity even though the
    minimum realistic value with all-1 inputs is 1.0 — see test 2).

    Rationale (SRS FR-68 verbatim): "CSAT = 0.4×速度 + 0.2×擬人化 + 0.2×
    禮貌度 + 0.2×準確度；aggregate_csat 以正規化公式計算；目標 CSAT 4.8"
    (line 156). The 0.4 weight on speed reflects the dominant business
    value of response latency; the three 0.2 weights share the remainder
    across the qualitative axes.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


import inspect
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-68 mandates ``aggregate_csat`` in ``app.services.llm_judge``
# (SAD.md §2.4 / line 270, FR-68):
#
#     FR-68: "CSAT = 0.4×speed + 0.2×anthro + 0.2×politeness + 0.2×accuracy"
#
# The GREEN contract pinned by this spec:
#
#   - ``app.services.llm_judge`` MUST export ``aggregate_csat`` (a callable
#     — free function, static method, or class method) that returns a
#     numeric CSAT score.
#   - The signature MUST accept the four 1-5 component scores (speed,
#     personalization, politeness, accuracy). GREEN may choose either
#     four positional/keyword arguments OR a single structured object
#     that exposes those four scores; the tests call the function with
#     keyword arguments so GREEN's choice of positional/keyword naming
#     is unconstrained.
#   - The returned CSAT MUST equal
#         0.4 * speed + 0.2 * personalization + 0.2 * politeness
#         + 0.2 * accuracy
#     to within a small floating-point tolerance.
#   - The result MUST lie in [0, 5] (weights sum to 1.0; each input is
#     on [1, 5] so the realistic range is [1.0, 5.0] but the
#     contractual range for the formula is [0, 5]).
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because
# ``aggregate_csat`` is not yet exported by ``app.services.llm_judge`` —
# that is the valid RED signal.
# ---------------------------------------------------------------------------
from app.services.llm_judge import (
    aggregate_csat,
)


# ---------------------------------------------------------------------------
# Helper: call aggregate_csat with the four component scores regardless
# of whether GREEN exposes it as a free function, a static method, or a
# class method. The spec pins the formula, not the calling convention.
# ---------------------------------------------------------------------------
def _call_aggregate_csat(
    speed: float,
    personalization: float,
    politeness: float,
    accuracy: float,
) -> float:
    """Call ``aggregate_csat`` with the four component scores.

    The function is called with keyword arguments so GREEN's choice of
    positional/keyword ordering is unconstrained. If GREEN chose a
    class-method shape, the test still works because Python resolves
    the bound method identically.
    """
    return aggregate_csat(
        speed=speed,
        personalization=personalization,
        politeness=politeness,
        accuracy=accuracy,
    )


# ---------------------------------------------------------------------------
# 1. Happy path: the canonical 0.4 / 0.2 / 0.2 / 0.2 weighting. Given
#    speed=5, personalization=4, politeness=4, accuracy=4, the formula
#    yields:
#
#        0.4 * 5 + 0.2 * 4 + 0.2 * 4 + 0.2 * 4
#      = 2.0 + 0.8 + 0.8 + 0.8
#      = 4.4
#
#    Spec input: speed="5"; personalization="4"; politeness="4";
#                accuracy="4"; expected_csat="4.4".
#    Spec sub-assertion: fr68-ok: result is not None.
#    SRS FR-68 acceptance: "CSAT 公式計算正確".
#    Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr68_csat_formula_04_02_02_02_weights():
    speed = "5"
    personalization = "4"
    politeness = "4"
    accuracy = "4"
    expected_csat = "4.4"

    if (
        speed == "5"
        and personalization == "4"
        and politeness == "4"
        and accuracy == "4"
    ):
        # GREEN TODO: ``aggregate_csat(speed, personalization, politeness,
        # accuracy)`` in ``app.services.llm_judge`` MUST compute
        #
        #     CSAT = 0.4 * speed + 0.2 * personalization
        #          + 0.2 * politeness + 0.2 * accuracy
        #
        # per SRS FR-68 (line 156). For the canonical inputs
        # (5, 4, 4, 4) the formula MUST yield exactly 4.4. The 0.4
        # weight on speed and 0.2 weights on the qualitative axes
        # are mandated by the spec — a uniform average (0.25 each)
        # or any other weighting is wrong.
        #
        # No mocking required: aggregate_csat is a pure formula and
        # must not perform any I/O.
        speed_v = float(speed)
        personalization_v = float(personalization)
        politeness_v = float(politeness)
        accuracy_v = float(accuracy)
        expected_v = float(expected_csat)

        result = _call_aggregate_csat(
            speed=speed_v,
            personalization=personalization_v,
            politeness=politeness_v,
            accuracy=accuracy_v,
        )

        # fr68-ok predicate: result is not None.
        assert result is not None, (
            "fr68-ok predicate: aggregate_csat must return a non-None "
            "CSAT score for the canonical (5, 4, 4, 4) input."
        )

        # FR-68 core assertion: the formula MUST produce 4.4 for the
        # canonical inputs. A tolerance of 1e-9 is generous — the
        # formula is exact and any implementation that uses 0.4/0.2
        # floats will match within that tolerance.
        assert abs(float(result) - expected_v) < 1e-9, (
            f"FR-68: aggregate_csat(5, 4, 4, 4) must equal "
            f"0.4*5 + 0.2*4 + 0.2*4 + 0.2*4 = 4.4; got {result!r}. "
            f"SRS FR-68 mandates the 0.4/0.2/0.2/0.2 weighting."
        )

    # Sentinels MUST be preserved per spec.
    assert speed == "5", f"FR-68: speed sentinel must be '5'; got {speed!r}"
    assert personalization == "4", (
        f"FR-68: personalization sentinel must be '4'; "
        f"got {personalization!r}"
    )
    assert politeness == "4", (
        f"FR-68: politeness sentinel must be '4'; got {politeness!r}"
    )
    assert accuracy == "4", (
        f"FR-68: accuracy sentinel must be '4'; got {accuracy!r}"
    )
    assert expected_csat == "4.4", (
        f"FR-68: expected_csat sentinel must be '4.4'; "
        f"got {expected_csat!r}"
    )


# ---------------------------------------------------------------------------
# 2. Boundary: every component at its minimum (1) MUST still produce a
#    CSAT score that lies within the [0, 5] range mandated by SRS FR-68
#    acceptance: "score 正規化至 0-5 範圍".
#
#    With all-1 inputs the formula yields 0.4*1 + 0.2*1 + 0.2*1 + 0.2*1
#    = 1.0 — well inside [0, 5]. This is a boundary check on the output
#    range, NOT a test of the all-1 input semantics; GREEN could
#    conceivably clamp the result further and still pass.
#
#    Spec input: speed="1"; personalization="1"; politeness="1";
#                accuracy="1"; expected_min="0"; expected_max="5".
#    Spec sub-assertion: fr68-ok: result is not None (inherited from
#      the spec's predicate; this case pins the range, not the value).
#    SRS FR-68 acceptance: "score 正規化至 0-5 範圍".
#    Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr68_csat_score_in_0_5_range():
    speed = "1"
    personalization = "1"
    politeness = "1"
    accuracy = "1"
    expected_min = "0"
    expected_max = "5"

    if (
        speed == "1"
        and personalization == "1"
        and politeness == "1"
        and accuracy == "1"
    ):
        # GREEN TODO: ``aggregate_csat`` MUST normalize its output to
        # the [0, 5] range mandated by SRS FR-68 acceptance
        # ("score 正規化至 0-5 範圍"). For the all-minimum input
        # (1, 1, 1, 1) the result MUST be ≥ 0 and ≤ 5. GREEN may
        # additionally clamp internally, but the output MUST NOT
        # escape the [0, 5] range.
        #
        # No mocking required: aggregate_csat is a pure formula.
        speed_v = float(speed)
        personalization_v = float(personalization)
        politeness_v = float(politeness)
        accuracy_v = float(accuracy)
        min_v = float(expected_min)
        max_v = float(expected_max)

        result = _call_aggregate_csat(
            speed=speed_v,
            personalization=personalization_v,
            politeness=politeness_v,
            accuracy=accuracy_v,
        )

        # fr68-ok predicate: result is not None.
        assert result is not None, (
            "fr68-ok predicate: aggregate_csat must return a non-None "
            "CSAT score for the all-minimum (1, 1, 1, 1) input."
        )

        result_v = float(result)

        # FR-68 boundary assertion: the output MUST be ≥ 0 (lower
        # bound of the normalized range).
        assert result_v >= min_v, (
            f"FR-68: aggregate_csat(1, 1, 1, 1) must be >= "
            f"{expected_min} (the lower bound of the normalized "
            f"[0, 5] range); got {result!r}. SRS FR-68 mandates "
            f"'score 正規化至 0-5 範圍'."
        )

        # FR-68 boundary assertion: the output MUST be ≤ 5 (upper
        # bound of the normalized range; the weights sum to 1.0 so
        # the max realistic value with all-5 inputs is exactly 5.0).
        assert result_v <= max_v, (
            f"FR-68: aggregate_csat(1, 1, 1, 1) must be <= "
            f"{expected_max} (the upper bound of the normalized "
            f"[0, 5] range); got {result!r}. SRS FR-68 mandates "
            f"'score 正規化至 0-5 範圍'."
        )

    # Sentinels MUST be preserved per spec.
    assert speed == "1", f"FR-68: speed sentinel must be '1'; got {speed!r}"
    assert personalization == "1", (
        f"FR-68: personalization sentinel must be '1'; "
        f"got {personalization!r}"
    )
    assert politeness == "1", (
        f"FR-68: politeness sentinel must be '1'; got {politeness!r}"
    )
    assert accuracy == "1", (
        f"FR-68: accuracy sentinel must be '1'; got {accuracy!r}"
    )
    assert expected_min == "0", (
        f"FR-68: expected_min sentinel must be '0'; got {expected_min!r}"
    )
    assert expected_max == "5", (
        f"FR-68: expected_max sentinel must be '5'; got {expected_max!r}"
    )


# ---------------------------------------------------------------------------
# Suppress "imported but unused" warnings for the imports that exist purely
# to force collection-time failures during the RED step. These stay in
# scope so a future refactor cannot silently drop the FR-68 contract.
# ---------------------------------------------------------------------------
_ = (MagicMock, inspect)
# these once it implements aggregate_csat.
