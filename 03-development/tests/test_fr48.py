"""TDD-RED: failing tests for FR-48 — 連續負面觸發轉接 (consecutive_negative_count >= 3).

Spec source: 02-architecture/TEST_SPEC.md (FR-48)
SRS source : SRS.md FR-48 (Module 8: Emotion Analyzer)

Acceptance criteria (from SRS FR-48):
    consecutive_negative_count() ≥ 3 → should_escalate()=True；
    計算從最近往回的連續負面次數。
    連續 3 次負面觸發；中間有非負面打斷重計；should_escalate() 正確。

Active NFR patterns: none (pure counting rule over a category sequence).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# The canonical module is ``app.core.emotion`` per SAD.md (Module:
# emotion.py) and SRS.md FR-48's ``implementation_functions`` list:
#
#   - ``EmotionTracker.should_escalate`` — class method on the existing
#     EmotionTracker that examines a sequence of emotion categories
#     (in chronological order, oldest → newest) and returns True iff
#     the trailing run of consecutive ``"negative"`` entries is at
#     least three long.
#
# The contract pinned by the spec is:
#
#   - ``EmotionTracker.should_escalate(emotions)`` accepts an iterable of
#     category strings and returns ``True`` when the count of consecutive
#     ``"negative"`` entries at the END of the sequence is ``>= 3``;
#     any non-``"negative"`` category (``"positive"`` or ``"neutral"``)
#     in the trailing window MUST reset the count.
#   - Inputs shorter than the threshold (e.g. only 2 ``"negative"``
#     entries) MUST return ``False``.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.core.emotion`` does not yet expose ``EmotionTracker.should_escalate``.
# That is the valid RED signal — GREEN adds the method.
# ---------------------------------------------------------------------------
from app.core.emotion import (
    EmotionTracker,
)


# ---------------------------------------------------------------------------
# 1. A trailing run of exactly three consecutive "negative" entries MUST
#    trigger escalation (should_escalate() == True).
#
# Spec input: emotions="negative,negative,negative"; expected_escalate="true".
# Spec sub-assertion: fr48-ok: result is not None.
# SRS FR-48 acceptance: "連續 3 次負面觸發".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr48_3_consecutive_negative_triggers():
    emotions = "negative,negative,negative"
    expected_escalate = "true"

    if emotions == "negative,negative,negative":
        # Spec fr48-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        # GREEN TODO: ``EmotionTracker.should_escalate(emotions)`` MUST
        # return a non-None boolean when given a sequence whose trailing
        # run of "negative" entries is at least three long.
        tracker = EmotionTracker()
        result = tracker.should_escalate(["negative", "negative", "negative"])
        assert result is not None, (
            "fr48-ok predicate: EmotionTracker.should_escalate must "
            "return a non-None value for a 3-consecutive-negative input"
        )

    # GREEN TODO: with three trailing "negative" entries the count is
    # exactly 3, which meets the SRS FR-48 threshold — should_escalate
    # MUST therefore be True. No non-"negative" entry is present in
    # the trailing window so the count is NOT reset.
    expected = expected_escalate == "true"
    assert expected is True, (
        f"FR-48: expected_escalate sentinel must be 'true'; "
        f"got {expected_escalate!r}"
    )
    assert result is True, (
        f"FR-48: should_escalate must be True for three consecutive "
        f"negative emotions (emotions={emotions!r}, "
        f"expected_escalate={expected_escalate!r}); "
        f"got result={result!r}. SRS FR-48 mandates "
        f"'consecutive_negative_count() >= 3 → should_escalate()=True'."
    )

    # Sentinels MUST be preserved per spec.
    assert emotions == "negative,negative,negative", (
        f"FR-48: emotions sentinel must be 'negative,negative,negative'; "
        f"got {emotions!r}"
    )
    assert expected_escalate == "true", (
        f"FR-48: expected_escalate sentinel must be 'true'; "
        f"got {expected_escalate!r}"
    )


# ---------------------------------------------------------------------------
# 2. A non-"negative" entry between negative entries MUST reset the
#    consecutive count — even if more "negative" entries follow, the
#    trailing run length is what matters and is therefore only 1.
#
# Spec input: emotions="negative,negative,neutral,negative";
#            expected_escalate="false".
# Spec sub-assertion: fr48-ok: result is not None.
# SRS FR-48 acceptance: "中間有非負面打斷重計".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr48_non_negative_interrupts_count():
    emotions = "negative,negative,neutral,negative"
    expected_escalate = "false"

    if emotions == "negative,negative,neutral,negative":
        # Spec fr48-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        # GREEN TODO: ``EmotionTracker.should_escalate(emotions)`` MUST
        # return a non-None boolean for a sequence containing an
        # interrupting "neutral" entry between "negative" entries.
        tracker = EmotionTracker()
        result = tracker.should_escalate(
            ["negative", "negative", "neutral", "negative"]
        )
        assert result is not None, (
            "fr48-ok predicate: EmotionTracker.should_escalate must "
            "return a non-None value when a non-negative entry "
            "interrupts the negative run"
        )

    # GREEN TODO: the trailing run is only one "negative" entry
    # (the last one — the "neutral" between the last two "negative"
    # entries resets the count). SRS FR-48 mandates
    # "中間有非負面打斷重計" → should_escalate MUST be False.
    expected = expected_escalate == "true"
    assert expected is False, (
        f"FR-48: expected_escalate sentinel must be 'false'; "
        f"got {expected_escalate!r}"
    )
    assert result is False, (
        f"FR-48: should_escalate must be False when a non-negative "
        f"entry interrupts the negative run (emotions={emotions!r}, "
        f"expected_escalate={expected_escalate!r}); "
        f"got result={result!r}. SRS FR-48 mandates "
        f"'中間有非負面打斷重計' — the trailing run length is only 1, "
        f"below the 3-entry threshold."
    )

    # Sentinels MUST be preserved per spec.
    assert emotions == "negative,negative,neutral,negative", (
        f"FR-48: emotions sentinel must be "
        f"'negative,negative,neutral,negative'; got {emotions!r}"
    )
    assert expected_escalate == "false", (
        f"FR-48: expected_escalate sentinel must be 'false'; "
        f"got {expected_escalate!r}"
    )


# ---------------------------------------------------------------------------
# 3. A trailing run of only TWO consecutive "negative" entries MUST NOT
#    trigger escalation — the threshold is exactly three.
#
# Spec input: emotions="negative,negative"; expected_escalate="false".
# Spec sub-assertion: fr48-ok: result is not None.
# SRS FR-48 acceptance: "consecutive_negative_count() >= 3".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr48_2_consecutive_negative_not_trigger():
    emotions = "negative,negative"
    expected_escalate = "false"

    if emotions == "negative,negative":
        # Spec fr48-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        # GREEN TODO: ``EmotionTracker.should_escalate(emotions)`` MUST
        # return a non-None boolean for a short negative sequence that
        # does not yet meet the threshold.
        tracker = EmotionTracker()
        result = tracker.should_escalate(["negative", "negative"])
        assert result is not None, (
            "fr48-ok predicate: EmotionTracker.should_escalate must "
            "return a non-None value for a 2-consecutive-negative input"
        )

    # GREEN TODO: with only two trailing "negative" entries the count
    # is 2, which is BELOW the SRS FR-48 threshold of 3 → escalation
    # MUST NOT fire. This pins the boundary behaviour so a future
    # off-by-one (e.g. ``> 2`` vs ``>= 3``) cannot silently regress.
    expected = expected_escalate == "true"
    assert expected is False, (
        f"FR-48: expected_escalate sentinel must be 'false'; "
        f"got {expected_escalate!r}"
    )
    assert result is False, (
        f"FR-48: should_escalate must be False for only two consecutive "
        f"negative emotions (emotions={emotions!r}, "
        f"expected_escalate={expected_escalate!r}); "
        f"got result={result!r}. SRS FR-48 threshold is "
        f"consecutive_negative_count() >= 3 — two trailing entries is "
        f"strictly below that boundary."
    )

    # Sentinels MUST be preserved per spec.
    assert emotions == "negative,negative", (
        f"FR-48: emotions sentinel must be 'negative,negative'; "
        f"got {emotions!r}"
    )
    assert expected_escalate == "false", (
        f"FR-48: expected_escalate sentinel must be 'false'; "
        f"got {expected_escalate!r}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in core/emotion.py
# ---------------------------------------------------------------------------

def test_fr48_emotion_should_escalate_none_emotions_returns_false():
    """``emotion_should_escalate(None)`` MUST return ``False`` (NOT True).
    Kills mutant #113 which inverts ``return False`` → ``return True``
    for the ``is None`` short-circuit.
    """
    from app.core.emotion import emotion_should_escalate
    assert emotion_should_escalate(None) is False, (
        f"emotion_should_escalate(None) must return False (no escalation "
        f"triggered by no input); got True"
    )


def test_fr48_emotion_tracker_should_escalate_none_returns_false():
    """``EmotionTracker.should_escalate(None)`` MUST return ``False``.
    """
    from app.core.emotion import EmotionTracker
    tracker = EmotionTracker()
    assert tracker.should_escalate(None) is False, (
        f"EmotionTracker.should_escalate(None) must return False; got True"
    )
