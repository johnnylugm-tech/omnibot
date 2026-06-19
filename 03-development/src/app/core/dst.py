"""Dialogue State Tracker (DST) — 8-state FSM + slot filling.

[FR-34] 8-state FSM with strict ALLOWED_TRANSITIONS enforcement.
[FR-35] Slot-filling surface: DialogueSlot enum, INTENT_TO_SLOTS
        mapping, and DialogueState.missing_slots().

Citations:
- SRS.md FR-34 (8-state FSM + ALLOWED_TRANSITIONS contract)
- SRS.md FR-35 (slot filling: order_status needs order_id;
  return_request needs order_id + reason; missing_slots() returns
  the list of unfilled required slots; once filled the DST may
  advance to AWAITING_CONFIRMATION)
- 02-architecture/TEST_SPEC.md FR-34 (test cases 1-5)
- 02-architecture/TEST_SPEC.md FR-35 (test cases 1-4)
- 02-architecture/SAD.md Module: dst.py (NP-13 atomicity under
  concurrent async sessions → ``threading.Lock``)

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

import enum
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


# ---------------------------------------------------------------------------
# DialogueSlot — enumerated slot names understood by the DST.
#
# SRS FR-35: every slot the system can ask the user to fill MUST be
# named here so intent → required-slot lookups are exhaustive. The
# spec-pinned minimum set is ``order_id`` and ``reason`` (per
# "order_status 需要 order_id" and "return_request 需要 order_id +
# reason"). Members are string-valued so ``str(slot)`` and
# ``slot.value`` both round-trip to the spec-pinned literal names.
# ---------------------------------------------------------------------------
class DialogueSlot(enum.Enum):
    """Enumerated slot names for the slot-filling surface.

    [FR-35] SRS FR-35 acceptance criteria:
    - Every slot the DST can collect appears as a member.
    - The string form (``str(slot) == slot.value``) is the canonical
      name used by ``INTENT_TO_SLOTS`` and by callers comparing
      ``missing_slots()`` output against spec-pinned literals
      (``"order_id"``, ``"reason"``).
    """

    ORDER_ID = "order_id"
    REASON = "reason"


# ---------------------------------------------------------------------------
# INTENT_TO_SLOTS — frozen mapping from intent name to the required
# slot tuple.
#
# SRS FR-35: order_status 需要 order_id；return_request 需要
# order_id + reason. The keys MUST be the literal intent names from
# FR-32 (intent detection) so the DST can look up the required slots
# after intent detection. Values are tuples to preserve ordering
# (missing_slots() returns slots in this order).
# ---------------------------------------------------------------------------
INTENT_TO_SLOTS: dict[str, tuple[str, ...]] = {
    "order_status": ("order_id",),
    "return_request": ("order_id", "reason"),
}


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

    [FR-35] SRS FR-35 acceptance criteria:
    - Optionally carries the current intent and a slot-fill dict.
    - ``missing_slots()`` returns the names of required slots that
      have not yet been filled (in ``INTENT_TO_SLOTS`` order).
    - Once every required slot is filled, ``missing_slots()``
      returns ``[]`` — the precondition for the DST to advance
      from ``SLOT_FILLING`` to ``AWAITING_CONFIRMATION``.
    """

    __slots__ = ("state", "turn_count", "_lock", "intent", "slots")

    def __init__(
        self,
        initial_state: str = "IDLE",
        intent: str = "",
        slots: dict[str, str] | None = None,
    ) -> None:
        # FR-34: every conversation starts at IDLE per SRS FR-34.
        self.state: str = initial_state
        self.turn_count: int = 0
        # NP-13 — atomicity under concurrent async sessions.
        self._lock: threading.Lock = threading.Lock()
        # FR-35: current intent (set after intent detection) and the
        # collected slot dict. ``intent == ""`` means no intent has
        # been detected yet — ``missing_slots()`` then returns ``[]``
        # (no requirements known). ``slots`` defaults to an empty
        # dict so callers can read ``self.slots["order_id"]`` without
        # first checking for ``None``.
        self.intent: str = intent
        self.slots: dict[str, str] = slots if slots is not None else {}

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

    def missing_slots(self) -> list[str]:
        """Return the names of required slots that are still empty.

        [FR-35] SRS FR-35 acceptance criteria:
        - Reads the current ``intent`` and looks up the required slot
          tuple in ``INTENT_TO_SLOTS``.
        - Returns, in ``INTENT_TO_SLOTS`` order, every required slot
          whose value is missing or empty (whitespace-only counts as
          empty — the user has not yet provided a real answer).
        - When no intent is set, or the intent is not registered,
          returns ``[]`` (no requirements known → cannot be missing).
        - When every required slot is filled, returns ``[]`` — the
          DST may then advance to ``AWAITING_CONFIRMATION`` per
          SRS FR-35 "slot 填完後進入 AWAITING_CONFIRMATION".
        """
        required = INTENT_TO_SLOTS.get(self.intent)
        if not required:
            # No intent / unknown intent → no known required slots.
            return []
        missing: list[str] = []
        for slot_name in required:
            value = self.slots.get(slot_name)
            # An empty string (or whitespace-only) counts as "not yet
            # filled" — the user has not provided a real answer.
            if not value or not str(value).strip():
                missing.append(slot_name)
        return missing
