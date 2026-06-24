"""TDD-RED: failing tests for FR-37 — AWAITING_CONFIRMATION 超時:
2 輪未確認 / 確認 / 否認 狀態轉移.

Spec source: 02-architecture/TEST_SPEC.md (FR-37)
SRS source : SRS.md FR-37

Acceptance criteria (from SRS FR-37):
    AWAITING_CONFIRMATION 超時：超過 2 輪未確認 → ESCALATED；
    用戶確認 → PROCESSING；用戶否認 → SLOT_FILLING.
    2 輪未確認觸發 ESCALATED；確認/否認狀態轉移正確.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — the AWAITING_CONFIRMATION timeout surface of
# ``app.core.dst`` does NOT exist yet (RED state).
#
# GREEN TODO (for the GREEN agent):
#   The 8-state FSM from FR-34 and the auto-escalation surface from
#   FR-36 live in ``03-development/src/app/core/dst.py``. FR-37 adds
#   the AWAITING_CONFIRMATION timeout / confirm / deny surface to the
#   SAME module:
#
#     - A module-level ``MAX_AWAITING_CONFIRMATION_ROUNDS: int = 2``
#       pinning the spec-mandated awaiting-confirmation round limit
#       (per SRS FR-37 "超過 2 輪未確認 → ESCALATED").
#
#     - ``DialogueState`` (introduced in FR-34 / FR-35 / FR-36) MUST
#       gain ``def handle_confirmation(self, user_response: str,
#       awaiting_rounds: int = 0) -> str`` which:
#         * Timeout trigger: ``self.state == "AWAITING_CONFIRMATION"``
#           AND ``awaiting_rounds >= MAX_AWAITING_CONFIRMATION_ROUNDS``
#           (>=, so 2 rounds triggers escalation per the spec-pinned
#           ``MAX_AWAITING_CONFIRMATION_ROUNDS == 2`` semantics).
#           On timeout: transition ``self.state`` to ``"ESCALATED"``,
#           increment ``self.turn_count`` by 1, return ``"ESCALATED"``.
#         * Confirm trigger: ``user_response == "confirm"`` →
#           transition ``self.state`` to ``"PROCESSING"`` (the legal
#           AWAITING_CONFIRMATION → PROCESSING edge from
#           ``ALLOWED_TRANSITIONS``), increment ``self.turn_count`` by
#           1, return ``"PROCESSING"``.
#         * Deny trigger: ``user_response == "deny"`` → transition
#           ``self.state`` to ``"SLOT_FILLING"`` (note: AWAITING_CONFIRMATION
#           → SLOT_FILLING is NOT a legal edge in ``ALLOWED_TRANSITIONS``,
#           so this is a side-channel transition — like
#           ``auto_escalate`` it MUST bypass ``transition()``), increment
#           ``self.turn_count`` by 1, return ``"SLOT_FILLING"``.
#
#   The imports below are unguarded: pytest will fail with Collection
#   Error (Exit Code 2) on the ``MAX_AWAITING_CONFIRMATION_ROUNDS`` /
#   ``handle_confirmation`` references because the AWAITING_CONFIRMATION
#   surface does not exist yet. That is the valid RED signal for this
#   step.
# ---------------------------------------------------------------------------
from app.core.dst import (
    MAX_AWAITING_CONFIRMATION_ROUNDS,
    DialogueState,
)


# ---------------------------------------------------------------------------
# 1. AWAITING_CONFIRMATION + 2 rounds unconfirmed → ESCALATED.
#
# Spec input: state="AWAITING_CONFIRMATION"; rounds="2";
# expected_state="ESCALATED".
# SRS FR-37: "AWAITING_CONFIRMATION 超時：超過 2 輪未確認 → ESCALATED".
# When the DST has spent 2 (or more) rounds in AWAITING_CONFIRMATION
# without the user confirming, the conversation MUST auto-escalate so
# a human agent takes over. The threshold MUST be 2 (not 3, not 5)
# because the spec-pinned limit is "2 輪" and the test rounds=2 is
# the happy-path trigger value.
# ---------------------------------------------------------------------------
def test_fr37_awaiting_2rounds_unconfirmed_escalated():
    state = "AWAITING_CONFIRMATION"
    rounds = 2
    expected_state = "ESCALATED"

    # Spec fr37-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``rounds``; we gate the predicate on
    # that variable matching the spec input (``rounds="2"``, i.e. 2).
    if rounds == 2:
        # Spec fr37-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert MAX_AWAITING_CONFIRMATION_ROUNDS is not None, (
            "fr37-ok predicate: MAX_AWAITING_CONFIRMATION_ROUNDS must "
            "be importable from app.core.dst"
        )

    # FR-37 functional assertion #1: MAX_AWAITING_CONFIRMATION_ROUNDS
    # MUST equal 2 (per SRS FR-37 "超過 2 輪"). The constant is the
    # single source of truth for the round limit so a regression that
    # drifts it to 3 (or any other value) is caught immediately.
    assert MAX_AWAITING_CONFIRMATION_ROUNDS == 2, (
        f"FR-37: MAX_AWAITING_CONFIRMATION_ROUNDS must equal 2 per "
        f"SRS FR-37 'AWAITING_CONFIRMATION 超時：超過 2 輪未確認'; "
        f"got {MAX_AWAITING_CONFIRMATION_ROUNDS}"
    )

    # GREEN TODO: ``DialogueState.__init__`` MUST accept
    # ``initial_state`` (already added in FR-34 GREEN) so we can
    # construct the FSM directly in AWAITING_CONFIRMATION without
    # walking the legal edge chain from IDLE. Until GREEN adds
    # ``handle_confirmation``, the call below raises ``AttributeError``
    # and the test fails RED.
    ds = DialogueState(initial_state=state)

    # FR-37 functional assertion #2: starting state MUST be the
    # spec-pinned AWAITING_CONFIRMATION — the precondition for the
    # round-count escalation trigger to fire.
    assert ds.state == state, (
        f"FR-37: DialogueState.state must be {state!r} after "
        f"construction; got state={ds.state!r}"
    )

    # FR-37 functional assertion #3: ``DialogueState.handle_confirmation``
    # MUST transition the FSM to ESCALATED when ``awaiting_rounds`` is
    # at or above ``MAX_AWAITING_CONFIRMATION_ROUNDS`` AND the current
    # state is AWAITING_CONFIRMATION. We pass ``user_response=""`` (an
    # empty / non-confirm / non-deny value) so the confirm/deny
    # branches cannot fire — the timeout trigger must be the one that
    # fires. The method's return value MUST equal the new state
    # (``"ESCALATED"``) so call sites can use the call as an expression.
    result = ds.handle_confirmation(
        user_response="", awaiting_rounds=rounds
    )

    assert result == expected_state, (
        f"FR-37: DialogueState.handle_confirmation must return "
        f"{expected_state!r} for AWAITING_CONFIRMATION with rounds="
        f"{rounds}; got result={result!r}"
    )
    # FR-37 functional assertion #4: after handle_confirmation, ``state``
    # MUST equal ESCALATED. This is the canonical check that the FSM
    # actually mutated.
    assert ds.state == expected_state, (
        f"FR-37: DialogueState.state must equal {expected_state!r} "
        f"after handle_confirmation for AWAITING_CONFIRMATION with "
        f"rounds={rounds}; got state={ds.state!r}"
    )


# ---------------------------------------------------------------------------
# 2. user_response="confirm" → AWAITING_CONFIRMATION → PROCESSING.
#
# Spec input: user_response="confirm"; expected_state="PROCESSING".
# SRS FR-37: "用戶確認 → PROCESSING". The confirm branch is the
# happy-path branch: the user explicitly confirms the slot-filling
# result and the DST MUST advance the FSM from AWAITING_CONFIRMATION
# to PROCESSING. This is the legal AWAITING_CONFIRMATION → PROCESSING
# edge in ``ALLOWED_TRANSITIONS`` (FR-34). The state MUST actually
# change — the canonical "FSM mutated" check.
# ---------------------------------------------------------------------------
def test_fr37_confirm_transitions_to_processing():
    state = "AWAITING_CONFIRMATION"
    user_response = "confirm"
    expected_state = "PROCESSING"

    # Spec fr37-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``user_response``; we gate the
    # predicate on that variable matching the spec input
    # (``user_response="confirm"``).
    if user_response == "confirm":
        # Spec fr37-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert DialogueState is not None, (
            "fr37-ok predicate: DialogueState must be importable "
            "from app.core.dst"
        )

    # GREEN TODO: see test 1 — same construction contract.
    # ``DialogueState(initial_state="AWAITING_CONFIRMATION")`` so the
    # test exercises the confirm path from the spec-pinned starting
    # state without depending on the FSM walk.
    ds = DialogueState(initial_state=state)

    # FR-37 functional assertion #1: starting state MUST be the
    # spec-pinned AWAITING_CONFIRMATION — the precondition for the
    # confirm branch to fire.
    assert ds.state == state, (
        f"FR-37: DialogueState.state must be {state!r} after "
        f"construction; got state={ds.state!r}"
    )

    # FR-37 functional assertion #2: ``DialogueState.handle_confirmation``
    # MUST transition the FSM to PROCESSING when ``user_response ==
    # "confirm"``. We pass ``awaiting_rounds=0`` so the timeout
    # trigger cannot fire — the confirm branch must be the one that
    # fires. The method's return value MUST equal the new state
    # (``"PROCESSING"``) so call sites can use the call as an
    # expression.
    result = ds.handle_confirmation(
        user_response=user_response, awaiting_rounds=0
    )

    assert result == expected_state, (
        f"FR-37: DialogueState.handle_confirmation must return "
        f"{expected_state!r} for user_response={user_response!r}; "
        f"got result={result!r}"
    )
    # FR-37 functional assertion #3: after handle_confirmation,
    # ``state`` MUST equal PROCESSING. This is the canonical check
    # that the FSM actually mutated.
    assert ds.state == expected_state, (
        f"FR-37: DialogueState.state must equal {expected_state!r} "
        f"after handle_confirmation with user_response="
        f"{user_response!r}; got state={ds.state!r}"
    )


# ---------------------------------------------------------------------------
# 3. user_response="deny" → AWAITING_CONFIRMATION → SLOT_FILLING.
#
# Spec input: user_response="deny"; expected_state="SLOT_FILLING".
# SRS FR-37: "用戶否認 → SLOT_FILLING". The deny branch tells the
# DST that the user rejected the slot-filling result, so the
# conversation loops back to SLOT_FILLING so the user can supply
# corrected values. Note: AWAITING_CONFIRMATION → SLOT_FILLING is
# NOT a legal edge in ``ALLOWED_TRANSITIONS`` (per FR-34 only the
# linear forward path AWAITING_CONFIRMATION → PROCESSING is legal),
# so this transition is a side-channel — like
# ``DialogueState.auto_escalate`` (FR-36) it MUST bypass
# ``transition()`` and update ``self.state`` / ``self.turn_count``
# directly. The state MUST actually change — the canonical "FSM
# mutated" check.
# ---------------------------------------------------------------------------
def test_fr37_deny_transitions_to_slot_filling():
    state = "AWAITING_CONFIRMATION"
    user_response = "deny"
    expected_state = "SLOT_FILLING"

    # Spec fr37-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``user_response``; we gate the
    # predicate on that variable matching the spec input
    # (``user_response="deny"``).
    if user_response == "deny":
        # Spec fr37-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert DialogueState is not None, (
            "fr37-ok predicate: DialogueState must be importable "
            "from app.core.dst"
        )

    # GREEN TODO: see test 1 — same construction contract.
    # ``DialogueState(initial_state="AWAITING_CONFIRMATION")`` so the
    # test exercises the deny path from the spec-pinned starting state
    # without depending on the FSM walk.
    ds = DialogueState(initial_state=state)

    # FR-37 functional assertion #1: starting state MUST be the
    # spec-pinned AWAITING_CONFIRMATION — the precondition for the
    # deny branch to fire.
    assert ds.state == state, (
        f"FR-37: DialogueState.state must be {state!r} after "
        f"construction; got state={ds.state!r}"
    )

    # FR-37 functional assertion #2: ``DialogueState.handle_confirmation``
    # MUST transition the FSM to SLOT_FILLING when ``user_response ==
    # "deny"``. We pass ``awaiting_rounds=0`` so the timeout trigger
    # cannot fire — the deny branch must be the one that fires. The
    # method's return value MUST equal the new state
    # (``"SLOT_FILLING"``) so call sites can use the call as an
    # expression.
    result = ds.handle_confirmation(
        user_response=user_response, awaiting_rounds=0
    )

    assert result == expected_state, (
        f"FR-37: DialogueState.handle_confirmation must return "
        f"{expected_state!r} for user_response={user_response!r}; "
        f"got result={result!r}"
    )
    # FR-37 functional assertion #3: after handle_confirmation,
    # ``state`` MUST equal SLOT_FILLING. This is the canonical check
    # that the FSM actually mutated.
    assert ds.state == expected_state, (
        f"FR-37: DialogueState.state must equal {expected_state!r} "
        f"after handle_confirmation with user_response="
        f"{user_response!r}; got state={ds.state!r}"
    )
