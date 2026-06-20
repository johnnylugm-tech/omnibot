"""TDD-RED: failing tests for FR-51 — Emotion Tone Modulation.

Spec source: 02-architecture/TEST_SPEC.md (FR-51)
SRS source : SRS.md FR-51 (Module 9: Response Generator)

Acceptance criteria (from SRS FR-51):
    Emotion Tone Modulation：
    - negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」
    - positive → 前綴「太好了！」
    - repeat_count > 0 且 negative → 抑制重複道歉
    Implementation function: ``ResponseGenerator._apply_emotion_tone``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-51 mandates ``ResponseGenerator._apply_emotion_tone`` (SRS FR-51
# implementation_functions). The canonical module is
# ``app.core.response_generator`` per SAD.md (Module: response_generator.py)
# and SRS.md FR-51's implementation_functions list.
#
# GREEN contract pinned by this spec:
#
#   - ``ResponseGenerator._apply_emotion_tone(emotion, intensity,
#     repeat_count, base_text="") -> str`` MUST be a method on
#     ``ResponseGenerator``. It receives the user's classified emotion
#     label, the numeric intensity in [0.0, 1.0], the historical repeat
#     count of negative-tense messages (int >= 0), and the base reply
#     body that the prefix will be prepended to.
#
#   - When ``emotion == "negative"`` AND ``intensity > 0.7`` AND
#     ``repeat_count == 0`` the returned string MUST start with the
#     apology prefix 「非常抱歉造成您的困擾。」 (the spec-derived
#     ``expected_prefix`` substring is "非常抱歉"). When
#     ``repeat_count > 0`` for a negative emotion, the apology prefix
#     MUST be suppressed — the returned string MUST NOT contain
#     "非常抱歉".
#
#   - When ``emotion == "positive"`` the returned string MUST start
#     with the prefix 「太好了！」 (TEST_SPEC expected_prefix="太好了！"),
#     regardless of intensity and regardless of repeat_count.
#
#   - When ``emotion == "neutral"`` (or any unrecognised label that is
#     neither "negative" nor "positive") the method MUST return the
#     base_text unchanged with no prefix injected (TEST_SPEC
#     expected_prefix="").
#
# These imports are unguarded on purpose. ``ResponseGenerator`` is
# already exported by FR-50's GREEN commit, but the
# ``_apply_emotion_tone`` method does not yet exist on it, so the
# four tests below will fail with AttributeError on the first call.
# That is the valid RED signal — GREEN adds the method body.
# ---------------------------------------------------------------------------
from app.core.response_generator import (  # noqa: F401  -- RED: GREEN adds this method
    ResponseGenerator,
)


# ---------------------------------------------------------------------------
# 1. ``negative`` emotion with intensity > 0.7 MUST prepend the apology
#    prefix 「非常抱歉造成您的困擾。」 so the user feels the bot has
#    acknowledged the gravity of the issue.
#
# Spec input: emotion="negative"; intensity="0.8"; expected_prefix="非常抱歉".
# Spec sub-assertion: fr51-ok: result is not None.
# SRS FR-51 acceptance: "negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr51_negative_intensity_above_07_apology_prefix():
    emotion = "negative"
    intensity = 0.8
    expected_prefix = "非常抱歉"

    # Spec fr51-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c`
    # block whose trigger value matches TEST_SPEC case 1's input.
    if emotion == "negative":
        # GREEN TODO: ``ResponseGenerator._apply_emotion_tone`` MUST
        # return a non-None string whose leading characters form the
        # apology prefix 「非常抱歉造成您的困擾。」 when called with
        # emotion="negative" and intensity > 0.7.
        result = ResponseGenerator._apply_emotion_tone(
            emotion=emotion,
            intensity=intensity,
            repeat_count=0,
            base_text="我來協助您處理這個問題。",
        )
        assert result is not None, (
            "fr51-ok predicate: ResponseGenerator._apply_emotion_tone "
            "must return a non-None string for emotion='negative'"
        )
        assert expected_prefix in result, (
            f"FR-51: _apply_emotion_tone must prepend the apology "
            f"prefix containing {expected_prefix!r} for emotion="
            f"{emotion!r} with intensity={intensity} (> 0.7); "
            f"got {result!r}. SRS FR-51 mandates "
            f"'negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」'."
        )

    # Sentinels MUST be preserved per spec.
    assert emotion == "negative", (
        f"FR-51: emotion sentinel must be 'negative'; got {emotion!r}"
    )
    assert intensity == 0.8, (
        f"FR-51: intensity sentinel must be 0.8; got {intensity!r}"
    )
    assert expected_prefix == "非常抱歉", (
        f"FR-51: expected_prefix sentinel must be '非常抱歉'; "
        f"got {expected_prefix!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``positive`` emotion MUST prepend the positive prefix 「太好了！」
#    regardless of intensity / repeat_count so celebratory replies
#    land on a warm tone.
#
# Spec input: emotion="positive"; expected_prefix="太好了！".
# SRS FR-51 acceptance: "positive → 前綴「太好了！」".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr51_positive_adds_positive_prefix():
    emotion = "positive"
    expected_prefix = "太好了！"

    result = ResponseGenerator._apply_emotion_tone(
        emotion=emotion,
        intensity=0.5,
        repeat_count=0,
        base_text="您的問題已順利解決。",
    )
    assert result is not None, (
        "FR-51: _apply_emotion_tone must return a non-None string "
        "for emotion='positive'"
    )
    assert result.startswith(expected_prefix), (
        f"FR-51: _apply_emotion_tone must prepend the positive "
        f"prefix {expected_prefix!r} for emotion={emotion!r}; "
        f"got {result!r}. SRS FR-51 mandates 'positive → 前綴「太好了！」'."
    )

    # Sentinels MUST be preserved per spec.
    assert emotion == "positive", (
        f"FR-51: emotion sentinel must be 'positive'; got {emotion!r}"
    )
    assert expected_prefix == "太好了！", (
        f"FR-51: expected_prefix sentinel must be '太好了！'; "
        f"got {expected_prefix!r}"
    )


# ---------------------------------------------------------------------------
# 3. Repeat suppression: when ``repeat_count > 0`` for a negative
#    emotion, the apology prefix MUST be suppressed so the user is not
#    battered by a second "非常抱歉" three messages in a row.
#
# Spec input: emotion="negative"; repeat_count="2"; expected_apology="false".
# SRS FR-51 acceptance: "repeat_count > 0 且 negative → 抑制重複道歉".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr51_repeat_negative_suppresses_apology():
    emotion = "negative"
    repeat_count = 2
    expected_apology = "false"

    # The TEST_SPEC pins expected_apology="false" — reify it so the
    # sentinel check is a clean boolean comparison rather than a
    # stringly-typed truthy/falsy comparison.
    if expected_apology == "false":
        # GREEN TODO: ``ResponseGenerator._apply_emotion_tone`` MUST
        # return a string that does NOT contain the apology prefix
        # 「非常抱歉」 when emotion="negative" and repeat_count > 0,
        # even though intensity > 0.7. The base_text is returned with
        # no apology prefix injected.
        result = ResponseGenerator._apply_emotion_tone(
            emotion=emotion,
            intensity=0.9,
            repeat_count=repeat_count,
            base_text="我來繼續協助您。",
        )
        assert result is not None, (
            "FR-51: _apply_emotion_tone must return a non-None string "
            "even when the apology is suppressed"
        )
        assert "非常抱歉" not in result, (
            f"FR-51: _apply_emotion_tone must suppress the apology "
            f"prefix for emotion={emotion!r} when repeat_count="
            f"{repeat_count} > 0; got {result!r}. SRS FR-51 mandates "
            f"'repeat_count > 0 且 negative → 抑制重複道歉'."
        )

    # Sentinels MUST be preserved per spec.
    assert emotion == "negative", (
        f"FR-51: emotion sentinel must be 'negative'; got {emotion!r}"
    )
    assert repeat_count == 2, (
        f"FR-51: repeat_count sentinel must be 2; got {repeat_count!r}"
    )
    assert expected_apology == "false", (
        f"FR-51: expected_apology sentinel must be 'false'; "
        f"got {expected_apology!r}"
    )


# ---------------------------------------------------------------------------
# 4. ``neutral`` emotion MUST NOT receive any tone adjustment — the
#    base_text is returned unchanged, with no prefix injected. This
#    keeps informational replies from feeling artificially cheerful or
#    apologetic.
#
# Spec input: emotion="neutral"; expected_prefix="".
# SRS FR-51 acceptance: implicit — only negative/positive paths adjust
#   tone; everything else is pass-through.
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr51_neutral_no_tone_adjustment():
    emotion = "neutral"
    expected_prefix = ""

    base_text = "我們的營業時間為週一至週五 9:00-18:00。"
    result = ResponseGenerator._apply_emotion_tone(
        emotion=emotion,
        intensity=0.3,
        repeat_count=0,
        base_text=base_text,
    )
    assert result is not None, (
        "FR-51: _apply_emotion_tone must return a non-None string "
        "for emotion='neutral'"
    )
    # The pass-through contract: the returned string equals the
    # base_text exactly, with no prefix prepended.
    assert result == base_text, (
        f"FR-51: _apply_emotion_tone must return the base_text "
        f"unchanged for emotion={emotion!r}; "
        f"expected {base_text!r}, got {result!r}. SRS FR-51 only "
        f"adjusts tone for emotion in ('negative', 'positive'); "
        f"neutral is a strict pass-through."
    )
    # And — per TEST_SPEC expected_prefix="" — the returned string
    # must not start with a tone prefix (i.e. must equal base_text).
    assert not result.startswith(expected_prefix) or expected_prefix == "", (
        f"FR-51: expected_prefix for emotion='neutral' must be "
        f"empty string; got result starting with {expected_prefix!r}. "
        f"TEST_SPEC FR-51 case 4 pins expected_prefix=''."
    )

    # Sentinels MUST be preserved per spec.
    assert emotion == "neutral", (
        f"FR-51: emotion sentinel must be 'neutral'; got {emotion!r}"
    )
    assert expected_prefix == "", (
        f"FR-51: expected_prefix sentinel must be ''; "
        f"got {expected_prefix!r}"
    )
