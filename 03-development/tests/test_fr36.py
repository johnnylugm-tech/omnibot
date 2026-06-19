"""TDD-RED: failing tests for FR-36 — Auto-escalation triggers:
3-round slot filling / confidence < 0.65.

Spec source: 02-architecture/TEST_SPEC.md (FR-36)
SRS source : SRS.md FR-36

Acceptance criteria (from SRS FR-36):
    自動轉接觸發條件：SLOT_FILLING 超過 3 輪未完成 → ESCALATED；
    意圖置信度 < INTENT_CONFIDENCE_THRESHOLD (0.65) → ESCALATED；
    PROCESSING 置信度 < 0.65 → ESCALATED.
    超過 3 輪 slot filling 觸發轉接；confidence < 0.65 觸發轉接.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — the auto-escalation surface of ``app.core.dst`` does
# NOT exist yet (RED state).
#
# GREEN TODO (for the GREEN agent):
#   The 8-state FSM from FR-34 and the slot-filling surface from FR-35
#   live in ``03-development/src/app/core/dst.py``. FR-36 adds the
#   auto-escalation surface to the SAME module:
#
#     - A module-level ``INTENT_CONFIDENCE_THRESHOLD: float = 0.65``
#       pinning the spec-mandated intent-confidence threshold (per
#       SRS FR-36 "意圖置信度 < INTENT_CONFIDENCE_THRESHOLD (0.65)
#       → ESCALATED").
#
#     - A module-level ``MAX_SLOT_FILLING_ROUNDS: int = 3`` pinning the
#       spec-mandated slot-filling round limit (per SRS FR-36
#       "SLOT_FILLING 超過 3 輪未完成 → ESCALATED").
#
#     - ``DialogueState`` (introduced in FR-34 / FR-35) MUST gain
#       ``def auto_escalate(self, slot_filling_rounds: int = 0,
#       confidence: float = 1.0) -> str`` which:
#         * Checks escalation triggers based on ``self.state`` and the
#           supplied arguments.
#         * SLOT_FILLING + ``slot_filling_rounds >= MAX_SLOT_FILLING_ROUNDS``
#           (>=, not strict >, so 3 rounds triggers escalation per the
#           spec-pinned ``MAX_SLOT_FILLING_ROUNDS == 3`` semantics).
#         * ``confidence < INTENT_CONFIDENCE_THRESHOLD`` triggers
#           escalation regardless of ``self.state`` (covers both the
#           INTENT_DETECTED case "意圖置信度 < 0.65 → ESCALATED" and the
#           PROCESSING case "PROCESSING 置信度 < 0.65 → ESCALATED").
#         * On trigger: transition ``self.state`` to ``"ESCALATED"``,
#           increment ``self.turn_count`` by 1, return ``"ESCALATED"``.
#         * On no-trigger: return ``self.state`` unchanged.
#
#   The imports below are unguarded: pytest will fail with Collection
#   Error (Exit Code 2) on the ``INTENT_CONFIDENCE_THRESHOLD`` /
#   ``MAX_SLOT_FILLING_ROUNDS`` / ``auto_escalate`` references because
#   the auto-escalation surface does not exist yet. That is the valid
#   RED signal for this step.
# ---------------------------------------------------------------------------
from app.core.dst import (  # noqa: F401
    DialogueState,
    INTENT_CONFIDENCE_THRESHOLD,
    MAX_SLOT_FILLING_ROUNDS,
)


# ---------------------------------------------------------------------------
# 1. SLOT_FILLING + 3 rounds → ESCALATED.
#
# Spec input: rounds="3"; state="SLOT_FILLING"; expected_state="ESCALATED".
# SRS FR-36: "SLOT_FILLING 超過 3 輪未完成 → ESCALATED" — when the DST
# has spent 3 (or more) rounds in SLOT_FILLING without the user filling
# the required slots, the conversation MUST auto-escalate to ESCALATED
# so a human agent takes over. The threshold MUST be 3 (not 4, not 5)
# because the spec-pinned limit is "3 輪" and the test rounds=3 is the
# happy-path trigger value.
# ---------------------------------------------------------------------------
def test_fr36_slot_filling_3rounds_escalated():
    rounds = 3
    state = "SLOT_FILLING"
    expected_state = "ESCALATED"

    # Spec fr36-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``rounds``; we gate the predicate on
    # that variable matching the spec input (``rounds="3"``, i.e. 3).
    if rounds == 3:
        # Spec fr36-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert MAX_SLOT_FILLING_ROUNDS is not None, (
            "fr36-ok predicate: MAX_SLOT_FILLING_ROUNDS must be "
            "importable from app.core.dst"
        )

    # FR-36 functional assertion #1: MAX_SLOT_FILLING_ROUNDS MUST equal
    # 3 (per SRS FR-36 "超過 3 輪"). The constant is the single source
    # of truth for the round limit so a regression that drifts it to 5
    # (or any other value) is caught immediately.
    assert MAX_SLOT_FILLING_ROUNDS == 3, (
        f"FR-36: MAX_SLOT_FILLING_ROUNDS must equal 3 per SRS FR-36 "
        f"'SLOT_FILLING 超過 3 輪未完成'; got {MAX_SLOT_FILLING_ROUNDS}"
    )

    # GREEN TODO: ``DialogueState.__init__`` MUST accept
    # ``initial_state`` (already added in FR-34 GREEN) so we can
    # construct the FSM directly in SLOT_FILLING without walking the
    # legal edge chain from IDLE. Until GREEN adds ``auto_escalate``,
    # the call below raises ``AttributeError`` and the test fails RED.
    ds = DialogueState(initial_state=state)

    # FR-36 functional assertion #2: starting state MUST be the
    # spec-pinned SLOT_FILLING — the precondition for the round-count
    # escalation trigger to fire.
    assert ds.state == state, (
        f"FR-36: DialogueState.state must be {state!r} after "
        f"construction; got state={ds.state!r}"
    )

    # FR-36 functional assertion #3: ``DialogueState.auto_escalate`` MUST
    # transition the FSM to ESCALATED when ``slot_filling_rounds`` is
    # at or above ``MAX_SLOT_FILLING_ROUNDS`` AND the current state is
    # SLOT_FILLING. We pass a high confidence (1.0) so the confidence
    # trigger cannot fire — the round-count trigger must be the one
    # that fires. The method's return value MUST equal the new state
    # (``"ESCALATED"``) so call sites can use the call as an expression.
    result = ds.auto_escalate(slot_filling_rounds=rounds, confidence=1.0)

    assert result == expected_state, (
        f"FR-36: DialogueState.auto_escalate must return "
        f"{expected_state!r} for SLOT_FILLING with rounds={rounds}; "
        f"got result={result!r}"
    )
    # FR-36 functional assertion #4: after auto_escalate, ``state`` MUST
    # equal ESCALATED. This is the canonical check that the FSM
    # actually mutated.
    assert ds.state == expected_state, (
        f"FR-36: DialogueState.state must equal {expected_state!r} "
        f"after auto_escalate for SLOT_FILLING with rounds={rounds}; "
        f"got state={ds.state!r}"
    )


# ---------------------------------------------------------------------------
# 2. confidence 0.60 < INTENT_CONFIDENCE_THRESHOLD (0.65) → ESCALATED.
#
# Spec input: confidence="0.60"; threshold="0.65"; expected_state="ESCALATED".
# SRS FR-36: "意圖置信度 < INTENT_CONFIDENCE_THRESHOLD (0.65) → ESCALATED".
# When the intent classifier returns a confidence below the threshold,
# the DST MUST auto-escalate regardless of which state it is in. The
# threshold itself is a module-level constant pinned at 0.65 — the test
# pins both the constant AND the resulting state transition.
# ---------------------------------------------------------------------------
def test_fr36_confidence_below_065_escalated():
    confidence = 0.60
    threshold = 0.65
    expected_state = "ESCALATED"

    # Spec fr36-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``confidence``; we gate the predicate
    # on that variable matching the spec input
    # (``confidence="0.60"``, i.e. 0.60).
    if confidence == 0.60:
        # Spec fr36-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert INTENT_CONFIDENCE_THRESHOLD is not None, (
            "fr36-ok predicate: INTENT_CONFIDENCE_THRESHOLD must be "
            "importable from app.core.dst"
        )

    # FR-36 functional assertion #1: INTENT_CONFIDENCE_THRESHOLD MUST
    # equal 0.65 (per SRS FR-36 "INTENT_CONFIDENCE_THRESHOLD (0.65)").
    # The constant is the single source of truth for the confidence
    # boundary so a regression that drifts it (e.g. to 0.5 or 0.8) is
    # caught immediately.
    assert INTENT_CONFIDENCE_THRESHOLD == threshold, (
        f"FR-36: INTENT_CONFIDENCE_THRESHOLD must equal {threshold} "
        f"per SRS FR-36 'INTENT_CONFIDENCE_THRESHOLD (0.65)'; got "
        f"{INTENT_CONFIDENCE_THRESHOLD}"
    )
    # FR-36 functional assertion #2: the spec-pinned confidence (0.60)
    # MUST be strictly less than the threshold (0.65). This is the
    # boundary condition the escalation trigger fires on — a value
    # equal to the threshold must NOT fire (strict less-than, not
    # less-than-or-equal).
    assert confidence < INTENT_CONFIDENCE_THRESHOLD, (
        f"FR-36: confidence={confidence} must be strictly less than "
        f"INTENT_CONFIDENCE_THRESHOLD={INTENT_CONFIDENCE_THRESHOLD} "
        f"for the escalation trigger to fire"
    )

    # GREEN TODO: see test 1 — same construction contract.
    # Starting from IDLE (the default initial state) so the test
    # exercises the "意圖置信度" path: intent detected, classifier
    # returns low confidence, DST escalates before doing any work.
    ds = DialogueState()

    # FR-36 functional assertion #3: ``DialogueState.auto_escalate``
    # MUST transition the FSM to ESCALATED when ``confidence`` is
    # strictly below ``INTENT_CONFIDENCE_THRESHOLD``, regardless of
    # the current FSM state. We pass ``slot_filling_rounds=0`` so the
    # round-count trigger cannot fire — the confidence trigger must
    # be the one that fires.
    result = ds.auto_escalate(slot_filling_rounds=0, confidence=confidence)

    assert result == expected_state, (
        f"FR-36: DialogueState.auto_escalate must return "
        f"{expected_state!r} when confidence={confidence} < "
        f"threshold={INTENT_CONFIDENCE_THRESHOLD}; got result={result!r}"
    )
    # FR-36 functional assertion #4: after auto_escalate, ``state``
    # MUST equal ESCALATED.
    assert ds.state == expected_state, (
        f"FR-36: DialogueState.state must equal {expected_state!r} "
        f"after auto_escalate with low confidence={confidence}; "
        f"got state={ds.state!r}"
    )


# ---------------------------------------------------------------------------
# 3. PROCESSING state + confidence 0.60 → ESCALATED.
#
# Spec input: state="PROCESSING"; confidence="0.60".
# SRS FR-36: "PROCESSING 置信度 < 0.65 → ESCALATED". The PROCESSING
# state is the second place the DST evaluates confidence — even after
# the conversation has begun executing the user's request, if the
# processing pipeline (e.g. knowledge lookup) returns a low-confidence
# result, the DST MUST still escalate to ESCALATED. This is the
# third-leg coverage so the confidence trigger is not accidentally
# scoped to INTENT_DETECTED only.
# ---------------------------------------------------------------------------
def test_fr36_processing_confidence_below_065_escalated():
    state = "PROCESSING"
    confidence = 0.60
    expected_state = "ESCALATED"

    # Spec fr36-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is the pair ``(state, confidence)``; we
    # gate the predicate on that variable matching the spec input
    # (``state="PROCESSING"`` and ``confidence="0.60"``).
    if confidence == 0.60 and state == "PROCESSING":
        # Spec fr36-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert INTENT_CONFIDENCE_THRESHOLD is not None, (
            "fr36-ok predicate: INTENT_CONFIDENCE_THRESHOLD must be "
            "importable from app.core.dst"
        )

    # FR-36 functional assertion #1: the spec-pinned confidence (0.60)
    # MUST be strictly less than INTENT_CONFIDENCE_THRESHOLD (0.65).
    # This is the boundary condition the escalation trigger fires on.
    assert INTENT_CONFIDENCE_THRESHOLD == 0.65, (
        f"FR-36: INTENT_CONFIDENCE_THRESHOLD must equal 0.65 per "
        f"SRS FR-36; got {INTENT_CONFIDENCE_THRESHOLD}"
    )
    assert confidence < INTENT_CONFIDENCE_THRESHOLD, (
        f"FR-36: confidence={confidence} must be strictly less than "
        f"INTENT_CONFIDENCE_THRESHOLD={INTENT_CONFIDENCE_THRESHOLD} "
        f"for the PROCESSING-state escalation trigger to fire"
    )

    # GREEN TODO: see test 1 — same construction contract.
    # ``DialogueState(initial_state="PROCESSING")`` so the test
    # exercises the PROCESSING-state escalation path independently of
    # the FSM walk (avoids depending on whether GREEN exposes
    # ``auto_escalate`` as state-aware or as a pure trigger).
    ds = DialogueState(initial_state=state)

    # FR-36 functional assertion #2: starting state MUST be the
    # spec-pinned PROCESSING.
    assert ds.state == state, (
        f"FR-36: DialogueState.state must be {state!r} after "
        f"construction; got state={ds.state!r}"
    )

    # FR-36 functional assertion #3: ``DialogueState.auto_escalate``
    # MUST transition the FSM to ESCALATED when invoked from the
    # PROCESSING state with a low confidence. This proves the
    # confidence trigger is not scoped to INTENT_DETECTED only —
    # PROCESSING is its own explicit leg in SRS FR-36.
    result = ds.auto_escalate(slot_filling_rounds=0, confidence=confidence)

    assert result == expected_state, (
        f"FR-36: DialogueState.auto_escalate must return "
        f"{expected_state!r} for PROCESSING state with "
        f"confidence={confidence} < threshold="
        f"{INTENT_CONFIDENCE_THRESHOLD}; got result={result!r}"
    )
    # FR-36 functional assertion #4: after auto_escalate, ``state``
    # MUST equal ESCALATED.
    assert ds.state == expected_state, (
        f"FR-36: DialogueState.state must equal {expected_state!r} "
        f"after auto_escalate for PROCESSING with confidence="
        f"{confidence}; got state={ds.state!r}"
    )
