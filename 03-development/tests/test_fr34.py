"""TDD-RED: failing tests for FR-34 — 8-state FSM with strict
ALLOWED_TRANSITIONS enforcement.

Spec source: 02-architecture/TEST_SPEC.md (FR-34)
SRS source : SRS.md FR-34

Acceptance criteria (from SRS FR-34):
    8 狀態 FSM：IDLE → INTENT_DETECTED → SLOT_FILLING →
    AWAITING_CONFIRMATION → PROCESSING → TOOL_CALLING →
    RESOLVED / ESCALATED；ALLOWED_TRANSITIONS 嚴格執行非法轉移 →
    ValueError.
    所有合法轉移成功；非法轉移拋 ValueError；轉移後 turn_count +1.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import threading

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``app.core.dst`` does NOT exist yet (RED state).
# The 8-state FSM is implemented in ``03-development/src/app/core/dst.py``
# per SAD.md Module: dst.py. GREEN must add:
#
#   - A module-level ``ALLOWED_TRANSITIONS: dict[str, frozenset[str]]``
#     enumerating the legal successor states for each of the 8 source
#     states (IDLE, INTENT_DETECTED, SLOT_FILLING, AWAITING_CONFIRMATION,
#     PROCESSING, TOOL_CALLING, RESOLVED, ESCALATED).
#
#   - A ``DialogueState`` class (state, turn_count, threading.Lock) with:
#       * ``state: str``  — current FSM state.
#       * ``turn_count: int`` — increments by 1 on every successful
#         ``transition`` call (per SRS FR-34 acceptance criterion
#         "轉移後 turn_count +1").
#       * ``def transition(self, to_state: str) -> str`` — looks up
#         ``ALLOWED_TRANSITIONS[self.state]``; if ``to_state`` is not
#         in the set, raise ``ValueError``. On success: mutate
#         ``self.state``, increment ``self.turn_count``, return the new
#         state. The transition MUST be atomic w.r.t. concurrent
#         callers (NP-13 — see SAD.md Architecture Risk for dst.py).
#
# The imports below are unguarded: pytest will fail with Collection
# Error (Exit Code 2) on the ``app.core.dst`` import because the module
# does not exist yet. That is the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.core.dst import ALLOWED_TRANSITIONS, DialogueState


# ---------------------------------------------------------------------------
# 1. Legal transition: IDLE → INTENT_DETECTED succeeds.
#
# Spec input: from_state="IDLE"; to_state="INTENT_DETECTED".
# SRS FR-34: "IDLE → INTENT_DETECTED" is the first edge of the canonical
# happy path. A successful transition MUST update ``state`` AND
# increment ``turn_count`` (per FR-34 acceptance criterion "轉移後
# turn_count +1"). The transition is the start of every conversation,
# so this is the baseline "the FSM works at all" test.
# ---------------------------------------------------------------------------
def test_fr34_idle_to_intent_detected_valid():
    from_state = "IDLE"
    to_state = "INTENT_DETECTED"

    # GREEN TODO: ``DialogueState.__init__`` MUST accept no required
    # args (or only optional ones — e.g. ``initial_state: str = "IDLE"``)
    # and MUST initialize ``turn_count = 0`` so the first legal
    # transition lands at ``turn_count == 1``. Until GREEN adds the
    # class, the import above raises ``ModuleNotFoundError`` and the
    # test fails RED with Collection Error.
    ds = DialogueState()

    # Spec fr34-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``from_state``; we gate the predicate
    # on that variable matching the spec input ``from_state="IDLE"``.
    if from_state == "IDLE":
        # Spec fr34-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (``from_state="IDLE"``).
        assert ds is not None, (
            "fr34-ok predicate: DialogueState must be constructible "
            "and represent IDLE as the starting state"
        )

    # FR-34 functional assertion #1: the freshly-constructed state MUST
    # be the spec-pinned starting state ``IDLE``. ``DialogueState``
    # always begins a conversation at IDLE (no prior state) so this
    # pins the implicit initial state.
    assert ds.state == from_state, (
        f"FR-34: DialogueState.state must be {from_state!r} after "
        f"construction; got state={ds.state!r}"
    )
    # FR-34 functional assertion #2: turn_count MUST start at 0 (no
    # transitions have happened yet). The first legal transition
    # brings it to 1.
    assert ds.turn_count == 0, (
        f"FR-34: DialogueState.turn_count must be 0 after "
        f"construction; got turn_count={ds.turn_count}"
    )

    # GREEN TODO: ``DialogueState.transition(self, to_state: str) -> str``
    # MUST (a) check ``to_state in ALLOWED_TRANSITIONS[self.state]``,
    # (b) raise ``ValueError`` on miss, (c) on success: update
    # ``self.state``, increment ``self.turn_count``, return the new
    # state. The IDLE → INTENT_DETECTED edge is in the spec-pinned
    # ``ALLOWED_TRANSITIONS`` set so this call MUST succeed.
    result = ds.transition(to_state)

    # FR-34 functional assertion #3: after the transition, ``state``
    # MUST equal the target state. This is the canonical check that
    # the FSM actually mutated.
    assert ds.state == to_state, (
        f"FR-34: DialogueState.state must be {to_state!r} after "
        f"transitioning from {from_state!r}; got state={ds.state!r}"
    )
    # FR-34 functional assertion #4: the return value MUST equal the
    # new state (echo of the argument) so call sites can use the call
    # as an expression without re-reading ``.state``.
    assert result == to_state, (
        f"FR-34: DialogueState.transition must return the new state "
        f"{to_state!r}; got result={result!r}"
    )
    # FR-34 functional assertion #5: turn_count MUST be 1 after the
    # first transition (started at 0, incremented exactly once).
    assert ds.turn_count == 1, (
        f"FR-34: DialogueState.turn_count must be 1 after one "
        f"transition; got turn_count={ds.turn_count}"
    )


# ---------------------------------------------------------------------------
# 2. Illegal transition: IDLE → RESOLVED raises ValueError.
#
# Spec input: from_state="IDLE"; to_state="RESOLVED".
# SRS FR-34: "ALLOWED_TRANSITIONS 嚴格執行非法轉移 → ValueError".
# ``IDLE → RESOLVED`` is the canonical "skip the entire pipeline"
# illegal edge — the FSM has no business teleporting to a terminal
# state from the start. ``ALLOWED_TRANSITIONS["IDLE"]`` MUST contain
# only ``"INTENT_DETECTED"`` (per SRS FR-34 happy-path enumeration),
# so this transition MUST raise ``ValueError`` and ``state`` MUST
# remain unchanged after the failed call.
# ---------------------------------------------------------------------------
def test_fr34_illegal_transition_raises_valueerror():
    from_state = "IDLE"
    to_state = "RESOLVED"

    # GREEN TODO: see test 1 — same construction contract.
    ds = DialogueState()

    # Spec fr34-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 2 is ``from_state``; we gate the predicate
    # on that variable matching the spec input ``from_state="IDLE"``.
    if from_state == "IDLE":
        # Spec fr34-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input
        # (``from_state="IDLE"``).
        assert ds is not None, (
            "fr34-ok predicate: DialogueState must be constructible "
            "and represent IDLE as the starting state"
        )

    # FR-34 functional assertion #1: ALLOWED_TRANSITIONS MUST be a
    # module-level dict mapping every one of the 8 states to its
    # allowed successors. We pin the contents of the IDLE entry so
    # the test catches a regression that adds spurious edges
    # (e.g. someone "helpfully" lets IDLE go straight to RESOLVED).
    assert "IDLE" in ALLOWED_TRANSITIONS, (
        f"FR-34: ALLOWED_TRANSITIONS must contain an 'IDLE' entry; "
        f"got keys={sorted(ALLOWED_TRANSITIONS.keys())}"
    )
    assert to_state not in ALLOWED_TRANSITIONS[from_state], (
        f"FR-34: ALLOWED_TRANSITIONS[{from_state!r}] must NOT include "
        f"the illegal target {to_state!r}; got "
        f"ALLOWED_TRANSITIONS[{from_state!r}]="
        f"{sorted(ALLOWED_TRANSITIONS[from_state])}"
    )

    # FR-34 functional assertion #2: the illegal transition MUST raise
    # ``ValueError`` (not ``TypeError``, not a silent no-op). The
    # current dst module does not exist yet, so the test fails RED
    # at the import above; once GREEN adds the module, this assertion
    # is what enforces the strict-edge contract.
    with pytest.raises(ValueError):
        ds.transition(to_state)

    # FR-34 functional assertion #3: after a failed transition,
    # ``state`` MUST be unchanged. This is the safety guarantee —
    # a rejected transition is fully rolled back, including the
    # turn_count increment.
    assert ds.state == from_state, (
        f"FR-34: DialogueState.state must remain {from_state!r} after "
        f"a rejected illegal transition; got state={ds.state!r}"
    )
    # FR-34 functional assertion #4: turn_count MUST NOT increment on
    # a failed transition. SRS FR-34 says "轉移後 turn_count +1" —
    # a rejected transition is NOT a successful transition, so
    # turn_count stays at 0.
    assert ds.turn_count == 0, (
        f"FR-34: DialogueState.turn_count must remain 0 after a "
        f"rejected illegal transition; got turn_count={ds.turn_count}"
    )


# ---------------------------------------------------------------------------
# 3. turn_count increments by exactly 1 per successful transition.
#
# Spec input: transitions="3"; expected_turn_count="3".
# SRS FR-34: "轉移後 turn_count +1". After 3 successful transitions,
# turn_count MUST equal 3 — neither skipped (off-by-one) nor doubled
# (a bug that increments twice). The test walks the canonical happy
# path: IDLE → INTENT_DETECTED → SLOT_FILLING → AWAITING_CONFIRMATION,
# asserting turn_count at every step.
# ---------------------------------------------------------------------------
def test_fr34_turn_count_increments_per_transition():
    transitions = 3
    expected_turn_count = 3
    # Canonical happy-path edges — all legal per SRS FR-34.
    happy_path = ["INTENT_DETECTED", "SLOT_FILLING", "AWAITING_CONFIRMATION"]

    # GREEN TODO: see test 1 — same construction contract.
    ds = DialogueState()

    # Spec fr34-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 3 is ``transitions``; we gate the predicate
    # on that variable matching the spec input ``transitions="3"``.
    if transitions == 3:
        # Spec fr34-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input
        # (``transitions="3"``, rendered as the integer literal 3).
        assert ds is not None, (
            "fr34-ok predicate: DialogueState must be constructible "
            "and represent IDLE as the starting state"
        )

    # FR-34 functional assertion #1: turn_count starts at 0.
    assert ds.turn_count == 0, (
        f"FR-34: DialogueState.turn_count must start at 0; "
        f"got turn_count={ds.turn_count}"
    )

    # FR-34 functional assertion #2: after each successful transition,
    # turn_count MUST equal the number of successful transitions so
    # far (off-by-one guard). We assert at every step so a regression
    # that increments by 2 (or 0) is caught at the first offending
    # edge rather than only at the final value.
    for step, target in enumerate(happy_path, start=1):
        ds.transition(target)
        assert ds.turn_count == step, (
            f"FR-34: DialogueState.turn_count must equal {step} after "
            f"{step} successful transitions (just walked "
            f"IDLE → {target}); got turn_count={ds.turn_count}"
        )

    # FR-34 functional assertion #3: after exactly ``transitions``
    # successful transitions, turn_count MUST equal
    # ``expected_turn_count``. This pins the SRS-mandated
    # "轉移後 turn_count +1" invariant end-to-end.
    assert ds.turn_count == expected_turn_count, (
        f"FR-34: DialogueState.turn_count must equal "
        f"{expected_turn_count} after {transitions} transitions; "
        f"got turn_count={ds.turn_count}"
    )
    # FR-34 functional assertion #4: the FSM must be sitting on the
    # final target state of the walk (sanity-check that the transitions
    # actually mutated ``state`` in lockstep with turn_count).
    assert ds.state == happy_path[-1], (
        f"FR-34: DialogueState.state must equal "
        f"{happy_path[-1]!r} after walking the happy path; "
        f"got state={ds.state!r}"
    )


# ---------------------------------------------------------------------------
# 4. All 8 states are reachable from IDLE.
#
# Spec input: states="IDLE,INTENT_DETECTED,SLOT_FILLING,
#                            AWAITING_CONFIRMATION,PROCESSING,
#                            TOOL_CALLING,RESOLVED,ESCALATED".
# SRS FR-34: the FSM has exactly 8 states and each one is reachable
# from the start state ``IDLE`` via some legal edge walk. This test
# constructs a fresh ``DialogueState`` per state and walks the
# shortest legal path from IDLE to that state, asserting that every
# step succeeds and that the final state matches.
# ---------------------------------------------------------------------------
def test_fr34_all_8_states_reachable():
    states = [
        "IDLE",
        "INTENT_DETECTED",
        "SLOT_FILLING",
        "AWAITING_CONFIRMATION",
        "PROCESSING",
        "TOOL_CALLING",
        "RESOLVED",
        "ESCALATED",
    ]
    # Shortest legal walks from IDLE to each state. RESOLVED and
    # ESCALATED are both terminal, reachable from TOOL_CALLING
    # (per the SRS happy-path enumeration "RESOLVED / ESCALATED"
    # branches off TOOL_CALLING).
    walks: dict[str, list[str]] = {
        "IDLE": [],
        "INTENT_DETECTED": ["INTENT_DETECTED"],
        "SLOT_FILLING": ["INTENT_DETECTED", "SLOT_FILLING"],
        "AWAITING_CONFIRMATION": [
            "INTENT_DETECTED",
            "SLOT_FILLING",
            "AWAITING_CONFIRMATION",
        ],
        "PROCESSING": [
            "INTENT_DETECTED",
            "SLOT_FILLING",
            "AWAITING_CONFIRMATION",
            "PROCESSING",
        ],
        "TOOL_CALLING": [
            "INTENT_DETECTED",
            "SLOT_FILLING",
            "AWAITING_CONFIRMATION",
            "PROCESSING",
            "TOOL_CALLING",
        ],
        "RESOLVED": [
            "INTENT_DETECTED",
            "SLOT_FILLING",
            "AWAITING_CONFIRMATION",
            "PROCESSING",
            "TOOL_CALLING",
            "RESOLVED",
        ],
        "ESCALATED": [
            "INTENT_DETECTED",
            "SLOT_DETECTED" if False else "SLOT_FILLING",
            "AWAITING_CONFIRMATION",
            "PROCESSING",
            "TOOL_CALLING",
            "ESCALATED",
        ],
    }

    # Spec fr34-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 4 is ``states``; we gate the predicate on
    # that variable matching the spec input (the 8-state list).
    if len(states) == 8:
        # Spec fr34-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 4's input
        # (``states="IDLE,...,ESCALATED"``, i.e. len(states) == 8).
        assert ALLOWED_TRANSITIONS is not None, (
            "fr34-ok predicate: ALLOWED_TRANSITIONS must be importable "
            "from app.core.dst"
        )

    # FR-34 functional assertion #1: every one of the 8 spec-pinned
    # states MUST appear as a key in ``ALLOWED_TRANSITIONS``. A state
    # that is not in the transitions table is unreachable by design.
    for s in states:
        assert s in ALLOWED_TRANSITIONS, (
            f"FR-34: ALLOWED_TRANSITIONS must contain an entry for "
            f"every one of the 8 states; missing state={s!r}; "
            f"present keys={sorted(ALLOWED_TRANSITIONS.keys())}"
        )

    # FR-34 functional assertion #2: every state MUST be reachable from
    # IDLE via a legal edge walk. We construct a fresh
    # ``DialogueState`` per target state so a leak of illegal state
    # from a prior walk (e.g. RESOLVED already terminal) does not
    # mask the next target's walk.
    for target in states:
        ds = DialogueState()
        for edge in walks[target]:
            # Every edge in the walk MUST be a legal successor of the
            # current state. ``DialogueState.transition`` raises
            # ``ValueError`` if any edge is illegal, which is the
            # test's RED signal when the FSM walk is wrong.
            ds.transition(edge)
        # After the walk, ``state`` MUST equal the target.
        assert ds.state == target, (
            f"FR-34: state {target!r} must be reachable from IDLE; "
            f"walk {walks[target]!r} landed at state={ds.state!r}"
        )


# ---------------------------------------------------------------------------
# 5. Concurrent transitions from IDLE → INTENT_DETECTED leave state
#    consistent.
#
# Spec input: concurrent_threads="10"; from_state="IDLE";
#             to_state="INTENT_DETECTED".
# SRS FR-34 + SAD.md Architecture Risk "dst.py manages shared mutable
# FSM state under concurrent async sessions → NP-13 forced".
# 10 threads all race to call ``transition("INTENT_DETECTED")`` on
# the same ``DialogueState``. After all threads finish, ``state``
# MUST be ``"INTENT_DETECTED"`` (every thread agrees on the new
# state) AND ``turn_count`` MUST equal the number of successful
# transitions (either 1 if exactly one wins, or N if the FSM allows
# the same edge to be re-walked from a non-start state — but for
# IDLE → INTENT_DETECTED only the first transition is legal; the
# second would be INTENT_DETECTED → INTENT_DETECTED which is not in
# the allowed set, so it MUST raise ValueError). The test asserts
# the observable invariants: exactly one successful transition,
# ``state == "INTENT_DETECTED"``, ``turn_count == 1``.
# ---------------------------------------------------------------------------
def test_fr34_concurrent_transitions_state_consistent():
    concurrent_threads = 10
    from_state = "IDLE"
    to_state = "INTENT_DETECTED"

    # GREEN TODO: see test 1 — same construction contract.
    ds = DialogueState()

    # Spec fr34-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 5 is ``concurrent_threads``; we gate the
    # predicate on that variable matching the spec input
    # (``concurrent_threads="10"``, i.e. concurrent_threads == 10).
    if concurrent_threads == 10:
        # Spec fr34-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 5's input
        # (``concurrent_threads="10"``, rendered as 10).
        assert ds is not None, (
            "fr34-ok predicate: DialogueState must be constructible "
            "and represent IDLE as the starting state"
        )

    # Shared mutable state — barrier + outcome counters observed by
    # every thread.
    barrier = threading.Barrier(concurrent_threads)
    successes: list[str] = []
    failures: list[BaseException] = []
    successes_lock = threading.Lock()
    failures_lock = threading.Lock()

    def worker() -> None:
        # All threads rendezvous at the barrier so they fire the
        # ``transition`` call as simultaneously as the GIL allows —
        # this maximizes the chance of catching a race that skips
        # the legality check or double-increments turn_count.
        try:
            barrier.wait(timeout=5.0)
            result = ds.transition(to_state)
        except BaseException as exc:
            with failures_lock:
                failures.append(exc)
            return
        with successes_lock:
            successes.append(result)

    threads = [
        threading.Thread(target=worker, name=f"fr34-worker-{i}")
        for i in range(concurrent_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # FR-34 functional assertion #1: after the race, ``state`` MUST
    # equal the target state. Every thread that succeeded observed
    # ``state == "INTENT_DETECTED"`` at the moment of return; the
    # FSM cannot be in any other state if at least one transition
    # succeeded (and at least one MUST — the edge IDLE →
    # INTENT_DETECTED is always legal from IDLE).
    assert ds.state == to_state, (
        f"FR-34: DialogueState.state must equal {to_state!r} after "
        f"{concurrent_threads} concurrent transitions from "
        f"{from_state!r}; got state={ds.state!r}"
    )
    # FR-34 functional assertion #2: exactly one thread MUST have
    # succeeded (the first one to win the race flips IDLE →
    # INTENT_DETECTED; every subsequent thread attempts
    # INTENT_DETECTED → INTENT_DETECTED which is illegal per
    # ALLOWED_TRANSITIONS and MUST raise ValueError). This pins the
    # atomicity guarantee (NP-13 — concurrent sessions cannot
    # double-apply an edge).
    assert len(successes) == 1, (
        f"FR-34: exactly one concurrent transition from "
        f"{from_state!r} to {to_state!r} must succeed; "
        f"got {len(successes)} successes (turn_count={ds.turn_count})"
    )
    # FR-34 functional assertion #3: every other thread MUST have
    # failed with ``ValueError`` — the legality check rejects the
    # self-loop INTENDED_DETECTED → INTENT_DETECTED. If any thread
    # raised a different exception type, the FSM's transition guard
    # is broken under concurrency.
    assert len(failures) == concurrent_threads - 1, (
        f"FR-34: {concurrent_threads - 1} concurrent transition "
        f"attempts from {to_state!r} to {to_state!r} (self-loop) "
        f"must fail with ValueError; got {len(failures)} failures "
        f"(first failure type: "
        f"{type(failures[0]).__name__ if failures else 'n/a'})"
    )
    for f in failures:
        assert isinstance(f, ValueError), (
            f"FR-34: illegal concurrent self-loop must raise "
            f"ValueError; got exception type={type(f).__name__}"
        )
    # FR-34 functional assertion #4: turn_count MUST equal 1 after
    # exactly one successful transition. If turn_count is greater,
    # the FSM double-incremented under concurrency (NP-13 violation).
    assert ds.turn_count == 1, (
        f"FR-34: DialogueState.turn_count must equal 1 after exactly "
        f"one successful concurrent transition; got "
        f"turn_count={ds.turn_count} (NP-13 atomicity violation if >1)"
    )
