"""Dialogue State Tracker (DST) — 8-state FSM + slot filling.

[FR-34] 8-state FSM with strict ALLOWED_TRANSITIONS enforcement.
[FR-35] Slot-filling surface: DialogueSlot enum, INTENT_TO_SLOTS
        mapping, and DialogueState.missing_slots().
[FR-36] Auto-escalation triggers: 3-round slot filling /
        confidence < 0.65. Adds INTENT_CONFIDENCE_THRESHOLD,
        MAX_SLOT_FILLING_ROUNDS, and DialogueState.auto_escalate().
[FR-37] AWAITING_CONFIRMATION timeout surface: 2-round unconfirmed
        → ESCALATED; user confirm → PROCESSING; user deny →
        SLOT_FILLING. Adds MAX_AWAITING_CONFIRMATION_ROUNDS and
        DialogueState.handle_confirmation().

Citations:
- SRS.md FR-34 (8-state FSM + ALLOWED_TRANSITIONS contract)
- SRS.md FR-35 (slot filling: order_status needs order_id;
  return_request needs order_id + reason; missing_slots() returns
  the list of unfilled required slots; once filled the DST may
  advance to AWAITING_CONFIRMATION)
- SRS.md FR-36 (auto-escalation: SLOT_FILLING > 3 rounds →
  ESCALATED; intent confidence < INTENT_CONFIDENCE_THRESHOLD (0.65)
  → ESCALATED; PROCESSING confidence < 0.65 → ESCALATED)
- SRS.md FR-37 (AWAITING_CONFIRMATION 超時:超過 2 輪未確認 →
  ESCALATED;用戶確認 → PROCESSING;用戶否認 → SLOT_FILLING;
  2 輪未確認觸發 ESCALATED;確認/否認狀態轉移正確)
- 02-architecture/TEST_SPEC.md FR-34 (test cases 1-5)
- 02-architecture/TEST_SPEC.md FR-35 (test cases 1-4)
- 02-architecture/TEST_SPEC.md FR-36 (test cases 1-3)
- 02-architecture/TEST_SPEC.md FR-37 (test cases 1-3: 2 輪未確認
  → ESCALATED;confirm → PROCESSING;deny → SLOT_FILLING)
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
# SRS FR-35: order_status 需要 order_id; return_request 需要
# order_id + reason. The keys MUST be the literal intent names from
# FR-32 (intent detection) so the DST can look up the required slots
# after intent detection. Values are tuples to preserve ordering
# (missing_slots() returns slots in this order).
# ---------------------------------------------------------------------------
INTENT_TO_SLOTS: dict[str, tuple[str, ...]] = {
    "order_status": ("order_id",),
    "return_request": ("order_id", "reason"),
}


# ---------------------------------------------------------------------------
# FR-36 — auto-escalation thresholds (spec-pinned).
#
# SRS FR-36: "意圖置信度 < INTENT_CONFIDENCE_THRESHOLD (0.65) →
# ESCALATED" and "SLOT_FILLING 超過 3 輪未完成 → ESCALATED". These
# two constants are the single source of truth for the threshold
# values; the spec-coverage tests pin them at exactly 0.65 and 3.
# ---------------------------------------------------------------------------
INTENT_CONFIDENCE_THRESHOLD: float = 0.65
MAX_SLOT_FILLING_ROUNDS: int = 3


# ---------------------------------------------------------------------------
# FR-37 — AWAITING_CONFIRMATION round limit (spec-pinned).
#
# SRS FR-37: "AWAITING_CONFIRMATION 超時:超過 2 輪未確認 → ESCALATED".
# The constant is the single source of truth for the round limit so
# a regression that drifts it to 3 (or any other value) is caught
# immediately by the spec-coverage test at ``tests/test_fr37.py``.
# ---------------------------------------------------------------------------
MAX_AWAITING_CONFIRMATION_ROUNDS: int = 2


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

    [FR-36] SRS FR-36 acceptance criteria:
    - ``auto_escalate(slot_filling_rounds, confidence)`` evaluates
      the two spec-pinned triggers (round limit, confidence
      threshold) and either transitions to ``"ESCALATED"`` (with a
      ``turn_count`` increment) or leaves the FSM untouched.

    [FR-37] SRS FR-37 acceptance criteria:
    - ``handle_confirmation(user_response, awaiting_rounds)`` evaluates
      three spec-pinned triggers (timeout, confirm, deny) from
      ``AWAITING_CONFIRMATION`` and either transitions to
      ``"ESCALATED"`` / ``"PROCESSING"`` / ``"SLOT_FILLING"`` (with
      a ``turn_count`` increment) or leaves the FSM untouched.
    """

    __slots__ = ("_lock", "intent", "slots", "state", "turn_count")

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
        # No intent / unknown intent → no known required slots → nothing
        # can be missing. ``()`` as the default lets the loop below
        # bail out via the empty-tuple iteration.
        required = INTENT_TO_SLOTS.get(self.intent, ())
        missing: list[str] = []
        for slot_name in required:
            # An empty string (or whitespace-only) counts as "not yet
            # filled" — the user has not provided a real answer.
            value = self.slots.get(slot_name, "")
            if not str(value).strip():
                missing.append(slot_name)
        return missing

    def auto_escalate(
        self, slot_filling_rounds: int = 0, confidence: float = 1.0
    ) -> str:
        """Auto-escalate to ``ESCALATED`` when a trigger fires.

        [FR-36] SRS FR-36 acceptance criteria:
        - Confidence trigger: ``confidence < INTENT_CONFIDENCE_THRESHOLD``
          (0.65) fires regardless of the current FSM state — covers
          both the "意圖置信度" (INTENT_DETECTED) leg and the
          "PROCESSING 置信度" leg.
        - Round trigger: ``state == "SLOT_FILLING"`` AND
          ``slot_filling_rounds >= MAX_SLOT_FILLING_ROUNDS`` (3) fires
          the round-limit escalation.
        - On trigger: ``self.state`` transitions to ``"ESCALATED"``,
          ``self.turn_count`` increments by 1, and the method returns
          ``"ESCALATED"``.
        - On no trigger: ``self.state`` / ``self.turn_count`` are
          unchanged and the method returns ``self.state``.
        - Atomic w.r.t. concurrent callers (NP-13) — mirrors the
          ``transition`` lock discipline.
        - Auto-escalation bypasses ``ALLOWED_TRANSITIONS``: a
          SLOT_FILLING / PROCESSING / IDLE → ESCALATED edge is NOT a
          legal normal-FSM transition (only TOOL_CALLING may go to
          ESCALATED per FR-34). Escalation is a side-channel out of
          the FSM, not a legal transition, so it MUST NOT reuse
          ``transition()``.
        """
        with self._lock:
            if self._escalation_triggered(slot_filling_rounds, confidence):
                self.state = "ESCALATED"
                self.turn_count += 1
                return "ESCALATED"
            return self.state

    def _escalation_triggered(
        self, slot_filling_rounds: int, confidence: float
    ) -> bool:
        """Pure predicate: should this FSM auto-escalate now?

        [FR-36] Pulled out of ``auto_escalate`` so the two triggers
        (confidence, round limit) live next to each other and the
        side effects (state mutation + ``turn_count`` increment) are
        not repeated. A value exactly equal to the confidence
        threshold is NOT a trigger (strict less-than per SRS FR-36
        "< 0.65"); a value exactly equal to
        ``MAX_SLOT_FILLING_ROUNDS`` IS a trigger (>=, so 3 rounds
        fires per the spec-pinned limit).
        """
        # Confidence trigger — fires regardless of FSM state.
        if confidence < INTENT_CONFIDENCE_THRESHOLD:
            return True
        # Round trigger — only applies while the FSM is in
        # SLOT_FILLING (other states do not consume slot-filling
        # rounds).
        return (
            self.state == "SLOT_FILLING"
            and slot_filling_rounds >= MAX_SLOT_FILLING_ROUNDS
        )

    def handle_confirmation(
        self, user_response: str, awaiting_rounds: int = 0
    ) -> str:
        """Handle an AWAITING_CONFIRMATION response or timeout.

        [FR-37] SRS FR-37 acceptance criteria:
        - Timeout trigger: ``self.state == "AWAITING_CONFIRMATION"``
          AND ``awaiting_rounds >= MAX_AWAITING_CONFIRMATION_ROUNDS``
          (>=, so 2 rounds triggers escalation per the spec-pinned
          ``MAX_AWAITING_CONFIRMATION_ROUNDS == 2`` semantics).
          On timeout: ``self.state`` → ``"ESCALATED"``, increment
          ``self.turn_count`` by 1, return ``"ESCALATED"``.
        - Confirm trigger: ``user_response == "confirm"`` →
          ``self.state`` → ``"PROCESSING"`` (the legal
          AWAITING_CONFIRMATION → PROCESSING edge from
          ``ALLOWED_TRANSITIONS``), increment ``self.turn_count``
          by 1, return ``"PROCESSING"``.
        - Deny trigger: ``user_response == "deny"`` →
          ``self.state`` → ``"SLOT_FILLING"`` (AWAITING_CONFIRMATION
          → SLOT_FILLING is NOT a legal edge in
          ``ALLOWED_TRANSITIONS``, so this is a side-channel
          transition — like ``auto_escalate`` it bypasses
          ``transition()``), increment ``self.turn_count`` by 1,
          return ``"SLOT_FILLING"``.
        - No trigger: ``self.state`` / ``self.turn_count`` are
          unchanged and the method returns ``self.state``.
        - Atomic w.r.t. concurrent callers (NP-13) — mirrors the
          ``transition`` / ``auto_escalate`` lock discipline.
        """
        with self._lock:
            # Timeout trigger — state guard prevents spurious
            # escalation when the FSM has already moved past
            # AWAITING_CONFIRMATION (e.g. concurrent advance to
            # PROCESSING between round count and handler call).
            if (
                self.state == "AWAITING_CONFIRMATION"
                and awaiting_rounds >= MAX_AWAITING_CONFIRMATION_ROUNDS
            ):
                self.state = "ESCALATED"
                self.turn_count += 1
                return "ESCALATED"
            # Confirm trigger — bypasses ``transition()`` to keep all
            # three branches in one atomic block; PROCESSING is a
            # legal successor so this is purely a style choice (the
            # legal-edge semantics are unchanged).
            if user_response == "confirm":
                self.state = "PROCESSING"
                self.turn_count += 1
                return "PROCESSING"
            # Deny trigger — MUST bypass ``transition()`` because
            # AWAITING_CONFIRMATION → SLOT_FILLING is NOT in
            # ``ALLOWED_TRANSITIONS`` (only AWAITING_CONFIRMATION →
            # PROCESSING is). Same side-channel pattern as
            # ``auto_escalate``.
            if user_response == "deny":
                self.state = "SLOT_FILLING"
                self.turn_count += 1
                return "SLOT_FILLING"
            return self.state
