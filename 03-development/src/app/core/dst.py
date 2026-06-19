"""Dialogue State Tracker (DST) — 8-state FSM.

[FR-34] 8-state FSM with strict ALLOWED_TRANSITIONS enforcement.

Citations:
- SRS.md FR-34 (8-state FSM + ALLOWED_TRANSITIONS contract)
- 02-architecture/TEST_SPEC.md FR-34 (test cases 1-5)
- 02-architecture/SAD.md Module: dst.py (NP-13 atomicity under concurrent
  async sessions → ``threading.Lock``)

The FSM has 8 states:
    IDLE → INTENT_DETECTED → SLOT_FILLING → AWAITING_CONFIRMATION →
    PROCESSING → TOOL_CALLING → RESOLVED | ESCALATED

``ALLOWED_TRANSITIONS`` is a module-level constant mapping every state
to its legal successor set. Any ``transition`` call targeting a state
NOT in the set raises ``ValueError`` and leaves ``state`` /
``turn_count`` unchanged (failed transitions are fully rolled back —
SRS FR-34 acceptance criterion).

``DialogueState.transition`` is atomic w.r.t. concurrent callers
(NP-13): the GIL + ``threading.Lock`` together guarantee the legality
check, the ``state`` mutation and the ``turn_count`` increment happen
as a single indivisible step.
"""

from __future__ import annotations

import threading

# ---------------------------------------------------------------------------
# ALLOWED_TRANSITIONS — frozen edge table.
#
# SRS FR-34: "ALLOWED_TRANSITIONS 嚴格執行非法轉移 → ValueError". Every
# one of the 8 states MUST appear as a key. Terminal states
# (RESOLVED, ESCALATED) map to the empty frozenset — there is no edge
# out of a terminal state by design.
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "IDLE": frozenset({"INTENT_DETECTED"}),
    "INTENT_DETECTED": frozenset({"SLOT_FILLING"}),
    "SLOT_FILLING": frozenset({"AWAITING_CONFIRMATION"}),
    "AWAITING_CONFIRMATION": frozenset({"PROCESSING"}),
    "PROCESSING": frozenset({"TOOL_CALLING"}),
    "TOOL_CALLING": frozenset({"RESOLVED", "ESCALATED"}),
    "RESOLVED": frozenset(),
    "ESCALATED": frozenset(),
}


def _is_legal_transition(from_state: str, to_state: str) -> bool:
    """Pure predicate: is the edge ``from_state -> to_state`` legal?

    Pulled out of ``DialogueState.transition`` so the legality rule
    lives in one named, testable place — ``transition`` then only
    needs to wrap it in the NP-13 atomicity lock.
    """
    allowed = ALLOWED_TRANSITIONS.get(from_state)
    return allowed is not None and to_state in allowed


class DialogueState:
    """Mutable 8-state FSM tracker for a single conversation.

    [FR-34] SRS FR-34 acceptance criteria:
    - Starts at ``state = "IDLE"`` with ``turn_count = 0``.
    - ``transition(to_state)`` validates against
      ``ALLOWED_TRANSITIONS[self.state]``; raises ``ValueError`` on
      an illegal target.
    - On success: updates ``state``, increments ``turn_count`` by 1,
      returns the new state.
    - On failure: ``state`` and ``turn_count`` are unchanged
      (atomic roll-back).
    - Atomic w.r.t. concurrent callers (NP-13).
    """

    __slots__ = ("state", "turn_count", "_lock")

    def __init__(self, initial_state: str = "IDLE") -> None:
        # Construction contract: no required args. ``initial_state`` is
        # optional and defaults to "IDLE" — every conversation starts
        # at IDLE per SRS FR-34.
        self.state: str = initial_state
        self.turn_count: int = 0
        # NP-13 — atomicity under concurrent async sessions.
        self._lock: threading.Lock = threading.Lock()

    def transition(self, to_state: str) -> str:
        """Atomically move to ``to_state`` if the edge is legal.

        Raises ``ValueError`` if ``to_state`` is not in
        ``ALLOWED_TRANSITIONS[self.state]``.
        Returns the new state on success.
        """
        with self._lock:
            current = self.state
            if not _is_legal_transition(current, to_state):
                allowed = ALLOWED_TRANSITIONS.get(current)
                raise ValueError(
                    f"FR-34: illegal transition {current!r} -> "
                    f"{to_state!r}; allowed successors="
                    f"{sorted(allowed) if allowed is not None else 'n/a'}"
                )
            self.state = to_state
            self.turn_count += 1
            return to_state
