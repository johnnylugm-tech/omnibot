"""TDD-RED: failing tests for FR-46 — EmotionAnalyzer (positive/neutral/negative + intensity 0.0-1.0).

Spec source: 02-architecture/TEST_SPEC.md (FR-46)
SRS source : SRS.md FR-46 (Module: emotion.py, FR registry id=FR-46)

Acceptance criteria (from SRS FR-46):
    EmotionAnalyzer：分類情緒為 positive/neutral/negative，強度 intensity
    範圍 0.0–1.0，每次分析建立 EmotionScore 記錄。
    情緒分類結果限定三個合法值；intensity 範圍 [0.0, 1.0]。

Active NFR patterns: NP-06 (latency SLA — classification must be cheap).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# The canonical module is ``app.core.emotion`` per SAD.md (Module:
# emotion.py) and SRS.md FR-46's ``implementation_functions`` list:
#
#   - ``EmotionScore`` — dataclass / record type capturing a single
#     classification outcome (the SRS requires "每次分析建立
#     EmotionScore 記錄" — i.e. each analysis produces an
#     ``EmotionScore`` instance).
#   - ``emotion_classify`` — the classification entry point that
#     returns an ``EmotionScore`` (category + intensity).
#
# The exact attribute / parameter names below are pinned by the
# spec sub-assertion ``fr46-ok: result is not None`` plus the
# spec inputs ``text="很棒"`` and ``text="非常生氣"``. GREEN MUST
# implement:
#
#   - ``EmotionScore`` dataclass / pydantic model with at least the
#     fields ``category: str`` and ``intensity: float``.
#   - ``emotion_classify(text: str) -> EmotionScore`` (or a class
#     method ``EmotionAnalyzer.classify`` that returns the same
#     shape). The result's ``category`` MUST be one of
#     ``{"positive", "neutral", "negative"}`` and ``intensity``
#     MUST satisfy ``0.0 <= intensity <= 1.0``.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.core.emotion`` does not exist yet. That is the valid RED
# signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.core.emotion import (  # noqa: F401  -- RED: GREEN adds this module
    EmotionAnalyzer,
    EmotionScore,
    emotion_classify,
)


# ---------------------------------------------------------------------------
# 1. EmotionAnalyzer.classify() result category MUST be one of
#    {"positive", "neutral", "negative"} — the three legal values
#    for emotion classification.
#
# Spec input: text="很棒"; expected_valid_values="positive,neutral,negative".
# Spec sub-assertion: fr46-ok: result is not None.
# SRS FR-46 acceptance: "情緒分類結果限定三個合法值".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr46_classify_positive_neutral_negative_enum():
    text = "很棒"
    expected_valid_values = "positive,neutral,negative"

    if text == "很棒":
        # Spec fr46-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        # GREEN TODO: ``EmotionAnalyzer.classify(text)`` (or
        # ``emotion_classify(text)``) MUST return a non-None
        # ``EmotionScore`` instance for any non-empty input.
        result = EmotionAnalyzer().classify(text)
        assert result is not None, (
            "fr46-ok predicate: EmotionAnalyzer.classify must return "
            "a non-None EmotionScore for text='很棒'"
        )

    # GREEN TODO: ``EmotionScore.category`` MUST be one of the
    # three legal values {"positive", "neutral", "negative"}.
    valid_values = {v.strip() for v in expected_valid_values.split(",")}
    assert valid_values == {"positive", "neutral", "negative"}, (
        f"FR-46: expected_valid_values sentinel must be the three "
        f"legal emotion categories; got {valid_values!r}"
    )

    # ``EmotionScore`` must expose the category as ``.category`` (or
    # ``.label`` / ``.sentiment``) — the canonical name from the
    # spec is "category" (matching the SRS phrasing "分類情緒為
    # positive/neutral/negative"). GREEN must publish a ``category``
    # attribute on ``EmotionScore``.
    category = getattr(result, "category", None)
    assert category in valid_values, (
        f"FR-46: EmotionScore.category must be one of "
        f"{sorted(valid_values)} (text={text!r}, "
        f"expected_valid_values={expected_valid_values!r}); "
        f"got category={category!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert text == "很棒", (
        f"FR-46: text sentinel must be '很棒'; got {text!r}"
    )
    assert expected_valid_values == "positive,neutral,negative", (
        f"FR-46: expected_valid_values sentinel must be "
        f"'positive,neutral,negative'; got {expected_valid_values!r}"
    )


# ---------------------------------------------------------------------------
# 2. EmotionAnalyzer.classify() result intensity MUST lie in
#    [0.0, 1.0] — closed interval, both endpoints inclusive.
#
# Spec input: text="非常生氣"; expected_min="0.0"; expected_max="1.0".
# Spec sub-assertion: fr46-ok: result is not None.
# SRS FR-46 acceptance: "intensity 範圍 [0.0, 1.0]".
# Test type: boundary (Q3 derivation).
#
# A 24hr half-life / temporal-decay signal would have its own FR (FR-47)
# — FR-46 is purely about the (category, intensity) tuple emitted by
# a SINGLE classification. This test pins only the per-call range.
# ---------------------------------------------------------------------------
def test_fr46_intensity_in_0_to_1_range():
    text = "非常生氣"
    expected_min = "0.0"
    expected_max = "1.0"

    if text == "非常生氣":
        # Spec fr46-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        # GREEN TODO: ``EmotionAnalyzer.classify(text)`` MUST return a
        # non-None ``EmotionScore`` whose ``.intensity`` attribute is
        # a float in [0.0, 1.0].
        result = EmotionAnalyzer().classify(text)
        assert result is not None, (
            "fr46-ok predicate: EmotionAnalyzer.classify must return "
            "a non-None EmotionScore for text='非常生氣'"
        )

    # GREEN TODO: ``EmotionScore`` must expose intensity as
    # ``.intensity`` (float) — a real numeric value bounded by the
    # closed interval [0.0, 1.0].
    intensity = getattr(result, "intensity", None)
    assert intensity is not None, (
        f"FR-46: EmotionScore must expose an 'intensity' attribute; "
        f"got intensity={intensity!r}"
    )

    # Boundary: 0.0 (inclusive) and 1.0 (inclusive). intensity MUST
    # be numerically comparable (int / float) — not a string. Use
    # explicit type coercion to reject str-encoded numbers.
    lower = float(expected_min)
    upper = float(expected_max)
    assert lower == 0.0 and upper == 1.0, (
        f"FR-46: expected_min/expected_max sentinels must be 0.0/1.0; "
        f"got lower={lower!r}, upper={upper!r}"
    )
    assert isinstance(intensity, (int, float)), (
        f"FR-46: EmotionScore.intensity must be numeric (int|float); "
        f"got type={type(intensity).__name__}, value={intensity!r}"
    )
    # bool is a subclass of int — reject it explicitly to keep the
    # numeric range meaningful.
    assert not isinstance(intensity, bool), (
        f"FR-46: EmotionScore.intensity must not be a bool; "
        f"got {intensity!r}"
    )
    intensity_value = float(intensity)
    assert lower <= intensity_value <= upper, (
        f"FR-46: EmotionScore.intensity must be in [0.0, 1.0] "
        f"(text={text!r}, expected_min={expected_min!r}, "
        f"expected_max={expected_max!r}); got intensity={intensity_value!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert text == "非常生氣", (
        f"FR-46: text sentinel must be '非常生氣'; got {text!r}"
    )
    assert expected_min == "0.0", (
        f"FR-46: expected_min sentinel must be '0.0'; got {expected_min!r}"
    )
    assert expected_max == "1.0", (
        f"FR-46: expected_max sentinel must be '1.0'; got {expected_max!r}"
    )
