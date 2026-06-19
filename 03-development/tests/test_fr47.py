"""TDD-RED: failing tests for FR-47 — 時序衰減 (24hr half-life 指數衰減).

Spec source: 02-architecture/TEST_SPEC.md (FR-47)
SRS source : SRS.md FR-47 (Module 8: Emotion Analyzer)

Acceptance criteria (from SRS FR-47):
    EmotionTracker 以 24hr half-life 指數衰減
    （decay = exp(-0.693 * hours_ago / 24.0)）
    計算 current_weighted_score()；近期情緒權重更高。
    衰減計算公式正確；half_life=24hr；24hr 後權重降至 50%。

Active NFR patterns: none (pure decay algebra).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import math

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# The canonical module is ``app.core.emotion`` per SAD.md (Module:
# emotion.py) and SRS.md FR-47's ``implementation_functions`` list:
#
#   - ``EmotionTracker`` — class that owns the temporal-decay
#     arithmetic and exposes ``current_weighted_score(score, hours_ago)``
#     (SRS: "EmotionTracker 以 24hr half-life 指數衰減
#     （decay = exp(-0.693 * hours_ago / 24.0)）計算
#     current_weighted_score()").
#
# The contract pinned by the spec is:
#
#   - ``EmotionTracker.current_weighted_score(score, hours_ago)``
#     returns ``score * exp(-0.693 * hours_ago / 24.0)``.
#   - When ``hours_ago == 24`` the weight MUST equal ``0.5``
#     (one half-life elapsed — 24hr half-life).
#   - When ``hours_ago == 0`` the decay factor MUST equal ``1.0``
#     (no time elapsed → no decay).
#   - The decay is monotonically non-increasing in ``hours_ago``,
#     so a more recent score (smaller ``hours_ago``) MUST carry a
#     strictly higher weight than an older one with the same raw
#     score.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.core.emotion`` does not yet export ``EmotionTracker``.
# That is the valid RED signal — GREEN adds the class.
# ---------------------------------------------------------------------------
from app.core.emotion import (  # noqa: F401  -- RED: GREEN adds this class
    EmotionTracker,
)


# ---------------------------------------------------------------------------
# 1. current_weighted_score() with hours_ago=24 MUST produce a weight
#    equal to 0.5 (i.e. one half-life elapsed).
#
# Spec input: hours_ago="24"; expected_weight="0.5".
# Spec sub-assertion: fr47-ok: result is not None.
# SRS FR-47 acceptance: "24hr 後權重降至 50%".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr47_24hr_weight_50_percent_of_current():
    hours_ago = "24"
    expected_weight = "0.5"

    if hours_ago == "24":
        # Spec fr47-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        # GREEN TODO: ``EmotionTracker.current_weighted_score(score,
        # hours_ago)`` MUST return a non-None numeric weight whose
        # value, when the raw score is 1.0 and hours_ago == 24, is
        # exactly 0.5 (one 24hr half-life elapsed →
        # exp(-0.693 * 24 / 24) = exp(-0.693) ≈ 0.5).
        tracker = EmotionTracker()
        result = tracker.current_weighted_score(score=1.0, hours_ago=24)
        assert result is not None, (
            "fr47-ok predicate: EmotionTracker.current_weighted_score "
            "must return a non-None numeric weight for hours_ago=24"
        )

    # GREEN TODO: weight MUST equal 0.5 to within the standard
    # floating-point tolerance — half-life semantics pinned by the
    # SRS decay formula ``decay = exp(-0.693 * hours_ago / 24.0)``.
    expected = float(expected_weight)
    assert expected == 0.5, (
        f"FR-47: expected_weight sentinel must be 0.5; "
        f"got {expected!r}"
    )
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"FR-47: current_weighted_score must equal 0.5 after 24hr "
        f"(one half-life; hours_ago={hours_ago!r}, "
        f"expected_weight={expected_weight!r}); "
        f"got result={result!r}. SRS FR-47 mandates "
        f"decay = exp(-0.693 * hours_ago / 24.0) — at hours_ago=24 "
        f"this evaluates to exp(-0.693) ≈ 0.5."
    )

    # Sentinels MUST be preserved per spec.
    assert hours_ago == "24", (
        f"FR-47: hours_ago sentinel must be '24'; got {hours_ago!r}"
    )
    assert expected_weight == "0.5", (
        f"FR-47: expected_weight sentinel must be '0.5'; "
        f"got {expected_weight!r}"
    )


# ---------------------------------------------------------------------------
# 2. The decay factor itself MUST equal 1.0 when hours_ago == 0
#    (no time elapsed → no decay).
#
# Spec input: hours_ago="0"; expected_decay="1.0".
# Spec sub-assertion: fr47-ok: result is not None.
# SRS FR-47 acceptance: "衰減計算公式正確".
# Test type: validation (Q2 derivation).
#
# At hours_ago=0 the formula ``decay = exp(-0.693 * 0 / 24.0)``
# collapses to ``exp(0) == 1.0`` — i.e. a score recorded "now"
# contributes its full raw value to the weighted aggregate.
# ---------------------------------------------------------------------------
def test_fr47_decay_formula_correct():
    hours_ago = "0"
    expected_decay = "1.0"

    if hours_ago == "0":
        # Spec fr47-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        # GREEN TODO: ``EmotionTracker.current_weighted_score(score,
        # hours_ago)`` MUST return the full raw score when
        # hours_ago == 0 — i.e. decay(exp(0)) == 1.0.
        tracker = EmotionTracker()
        result = tracker.current_weighted_score(score=1.0, hours_ago=0)
        assert result is not None, (
            "fr47-ok predicate: EmotionTracker.current_weighted_score "
            "must return a non-None numeric decay for hours_ago=0"
        )

    # GREEN TODO: decay at hours_ago=0 MUST equal 1.0 (identity).
    expected = float(expected_decay)
    assert expected == 1.0, (
        f"FR-47: expected_decay sentinel must be 1.0; "
        f"got {expected!r}"
    )
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"FR-47: current_weighted_score must equal 1.0 at hours_ago=0 "
        f"(hours_ago={hours_ago!r}, expected_decay={expected_decay!r}); "
        f"got result={result!r}. SRS FR-47 mandates "
        f"decay = exp(-0.693 * hours_ago / 24.0) — at hours_ago=0 "
        f"this evaluates to exp(0) == 1.0."
    )

    # Sentinels MUST be preserved per spec.
    assert hours_ago == "0", (
        f"FR-47: hours_ago sentinel must be '0'; got {hours_ago!r}"
    )
    assert expected_decay == "1.0", (
        f"FR-47: expected_decay sentinel must be '1.0'; "
        f"got {expected_decay!r}"
    )


# ---------------------------------------------------------------------------
# 3. A more recent score MUST carry a strictly higher weight than an
#    older score with the same raw value — i.e. the decay function
#    is monotonically non-increasing in ``hours_ago``.
#
# Spec input: recent_hours="1"; old_hours="48".
# Spec sub-assertion: fr47-ok: result is not None.
# SRS FR-47 acceptance: "近期情緒權重更高".
# Test type: happy_path (Q1 derivation).
#
# 48hr ago is TWO half-lives (decay = 0.25); 1hr ago is barely
# decayed (decay ≈ 0.97). The recent score's weighted contribution
# MUST therefore be strictly greater than the old score's.
# ---------------------------------------------------------------------------
def test_fr47_recent_score_higher_weight():
    recent_hours = "1"
    old_hours = "48"

    if recent_hours == "1" and old_hours == "48":
        # Spec fr47-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        # GREEN TODO: ``EmotionTracker.current_weighted_score(score,
        # hours_ago)`` MUST return a non-None numeric weight for both
        # the recent (1hr ago) and old (48hr ago) probes.
        tracker = EmotionTracker()
        recent_weight = tracker.current_weighted_score(score=1.0, hours_ago=1)
        old_weight = tracker.current_weighted_score(score=1.0, hours_ago=48)
        assert recent_weight is not None, (
            "fr47-ok predicate: EmotionTracker.current_weighted_score "
            "must return a non-None numeric weight for hours_ago=1"
        )
        assert old_weight is not None, (
            "fr47-ok predicate: EmotionTracker.current_weighted_score "
            "must return a non-None numeric weight for hours_ago=48"
        )

    # GREEN TODO: the recent score's weight MUST be strictly greater
    # than the old score's weight — recent emotion carries more
    # weight. Concretely:
    #   recent_hours=1  → weight ≈ exp(-0.693 * 1/24)  ≈ 0.972
    #   old_hours=48    → weight ≈ exp(-0.693 * 48/24) ≈ 0.250
    assert isinstance(recent_weight, (int, float)), (
        f"FR-47: recent_weight must be numeric (int|float); "
        f"got type={type(recent_weight).__name__}, "
        f"value={recent_weight!r}"
    )
    assert isinstance(old_weight, (int, float)), (
        f"FR-47: old_weight must be numeric (int|float); "
        f"got type={type(old_weight).__name__}, value={old_weight!r}"
    )
    # bool is a subclass of int — reject explicitly.
    assert not isinstance(recent_weight, bool), (
        f"FR-47: recent_weight must not be a bool; "
        f"got {recent_weight!r}"
    )
    assert not isinstance(old_weight, bool), (
        f"FR-47: old_weight must not be a bool; "
        f"got {old_weight!r}"
    )
    assert recent_weight > old_weight, (
        f"FR-47: recent emotion weight MUST be strictly greater than "
        f"old emotion weight (recent_hours={recent_hours!r}, "
        f"old_hours={old_hours!r}); got recent_weight={recent_weight!r}, "
        f"old_weight={old_weight!r}. SRS FR-47 mandates "
        f"'近期情緒權重更高'."
    )

    # Sanity: both weights MUST be in (0.0, 1.0] — decay never produces
    # a negative weight and never amplifies beyond the raw score when
    # the raw score is 1.0.
    recent_value = float(recent_weight)
    old_value = float(old_weight)
    assert 0.0 < recent_value <= 1.0, (
        f"FR-47: recent_weight must lie in (0.0, 1.0] for hours_ago=1; "
        f"got recent_value={recent_value!r}"
    )
    assert 0.0 < old_value <= 1.0, (
        f"FR-47: old_weight must lie in (0.0, 1.0] for hours_ago=48; "
        f"got old_value={old_value!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert recent_hours == "1", (
        f"FR-47: recent_hours sentinel must be '1'; "
        f"got {recent_hours!r}"
    )
    assert old_hours == "48", (
        f"FR-47: old_hours sentinel must be '48'; got {old_hours!r}"
    )