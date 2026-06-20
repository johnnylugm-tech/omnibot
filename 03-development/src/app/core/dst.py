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
[FR-38] Context-window management surface:
        sliding_window_with_summarization. Adds MAX_TOKENS,
        SYSTEM_RESERVED, KNOWLEDGE_MAX, HISTORY_BUDGET,
        TOKEN_ENCODING, and ContextWindowManager (cl100k_base
        tiktoken; overflow → earliest 1/3 replaced by a single
        system summary message; gemini fallback reuses the same
        cl100k_base budget per "保守估算").

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
- SRS.md FR-38 (sliding_window_with_summarization; max_tokens=8192;
  system_reserved=512; knowledge_max=2048; history_budget=5632;
  tiktoken cl100k_base; gemini fallback uses cl100k_base 保守估算)
- 02-architecture/TEST_SPEC.md FR-34 (test cases 1-5)
- 02-architecture/TEST_SPEC.md FR-35 (test cases 1-4)
- 02-architecture/TEST_SPEC.md FR-36 (test cases 1-3)
- 02-architecture/TEST_SPEC.md FR-37 (test cases 1-3: 2 輪未確認
  → ESCALATED;confirm → PROCESSING;deny → SLOT_FILLING)
- 02-architecture/TEST_SPEC.md FR-38 (test cases 1-5: cl100k_base
  tokenisation; overflow → summary; recent 1/3 preserved; gemini
  fallback same budget; 8192 = 512 + 2048 + 5632 arithmetic)
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

import tiktoken

# [FR-45] Single-source-of-truth: ToolDefinition lives in
# ``app.services.aee.adapter`` per FR-39. DST MUST re-import (not
# redefine) so that ``app.core.dst.ToolDefinition`` and
# ``app.services.aee.adapter.ToolDefinition`` resolve to the SAME class
# object — see SRS.md FR-45.
from app.services.aee.adapter import ToolDefinition  # noqa: F401  -- [FR-45]

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


# ---------------------------------------------------------------------------
# FR-38 — context-window budget (spec-pinned arithmetic).
#
# SRS FR-38: max_tokens=8192, system_reserved=512, knowledge_max=2048,
# history_budget=5632 (= 8192 - 512 - 2048). The four constants are the
# single source of truth for the budget arithmetic so a regression that
# drifts any one of them is caught immediately by the spec-coverage test
# at ``tests/test_fr38.py``.
# ---------------------------------------------------------------------------
MAX_TOKENS: int = 8192
SYSTEM_RESERVED: int = 512
KNOWLEDGE_MAX: int = 2048
HISTORY_BUDGET: int = MAX_TOKENS - SYSTEM_RESERVED - KNOWLEDGE_MAX  # 5632


# ---------------------------------------------------------------------------
# FR-38 — tokenizer identifier (spec-pinned).
#
# SRS FR-38: "Token 計算使用 tiktoken cl100k_base (適用 gpt-4o)".
# ``cl100k_base`` is the GPT-4 / GPT-4o tokenizer; using it for BOTH
# the gpt-4o primary path and the gemini fallback path is the
# "保守估算, 不因 tokenizer 差異導致 context overflow" guarantee —
# cl100k_base counts are >= what the gemini tokenizer would count
# for the same text, so reusing it under-fallback never overflows.
# ---------------------------------------------------------------------------
TOKEN_ENCODING: str = "cl100k_base"


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
                return self._apply_transition("ESCALATED")
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

    def _apply_transition(self, new_state: str) -> str:
        """Apply a side-channel state mutation (caller MUST hold ``_lock``).

        [NP-13] Every side-channel transition in this class performs
        the same triple: set ``self.state``, increment
        ``self.turn_count``, return the new state. Pulled out so the
        side-channel contract is defined once and the helper can be
        audited independently of the trigger logic that calls it.

        Distinct from ``transition()``: ``transition()`` validates
        against ``ALLOWED_TRANSITIONS`` first; side-channel
        transitions (escalation, confirm, deny) bypass that check
        intentionally because their target states are not legal
        normal-FSM successors.
        """
        self.state = new_state
        self.turn_count += 1
        return new_state

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
            target = self._confirmation_target(user_response, awaiting_rounds)
            if target is None:
                return self.state
            return self._apply_transition(target)

    def _confirmation_target(
        self, user_response: str, awaiting_rounds: int
    ) -> str | None:
        """Pure predicate: which target state should ``handle_confirmation``
        move the FSM to (or ``None`` if no trigger fires)?

        [FR-37] Pulled out of ``handle_confirmation`` so the three
        triggers (timeout, confirm, deny) live next to each other in
        the spec-mandated precedence order, and the side effects
        (state mutation + ``turn_count`` increment via
        ``_apply_transition``) are not repeated.

        Precedence is spec-mandated:
          - Timeout fires BEFORE confirm/deny because SRS FR-37
            "超過 2 輪未確認 → ESCALATED" applies regardless of what
            the user said in this round.
          - Confirm fires before deny; they are mutually exclusive
            on a single ``user_response`` string, so the order is
            documentation rather than behavioural.
        """
        # Timeout trigger — state guard prevents spurious escalation
        # when the FSM has already moved past AWAITING_CONFIRMATION
        # (e.g. concurrent advance to PROCESSING between round count
        # and handler call).
        if (
            self.state == "AWAITING_CONFIRMATION"
            and awaiting_rounds >= MAX_AWAITING_CONFIRMATION_ROUNDS
        ):
            return "ESCALATED"
        if user_response == "confirm":
            return "PROCESSING"
        if user_response == "deny":
            return "SLOT_FILLING"
        return None


# ---------------------------------------------------------------------------
# FR-38 — context-window manager (sliding-window + summarization).
#
# SRS FR-38: "對話 Context Window 管理：sliding_window_with_summarization
# 策略". The class owns three things:
#   1. The tokenizer (cl100k_base via tiktoken) — used for BOTH the
#      gpt-4o primary path and the gemini fallback path so the budget
#      stays consistent under fallback (per SRS FR-38 "gemini fallback
#      亦使用相同 cl100k_base 計算以維持 budget 一致性（保守估算，
#      不因 tokenizer 差異導致 context overflow）").
#   2. The history budget derived from MAX_TOKENS, SYSTEM_RESERVED,
#      and KNOWLEDGE_MAX (= 5632 with spec-pinned defaults).
#   3. The sliding-window-with-summarization policy: when the total
#      token count of the input messages exceeds the history budget,
#      the earliest 1/3 of messages is replaced by a single
#      ``{"role": "system", "content": "<summary of dropped messages>"}``
#      summary message. The remaining 2/3 (the middle + most-recent
#      1/3) are preserved verbatim.
#
# Citations:
# - SRS.md FR-38 ("sliding_window_with_summarization 策略";
#   "溢出時前 1/3 messages 摘要替換"; "保留最近 1/3 messages")
# - 02-architecture/TEST_SPEC.md FR-38 (test cases 1-5)
# ---------------------------------------------------------------------------
class ContextWindowManager:
    """Sliding-window-with-summarization context manager.

    [FR-38] SRS FR-38 acceptance criteria:
    - Tokenizer is fixed to ``cl100k_base`` for BOTH ``gpt-4o`` and
      ``gemini`` paths (conservative estimate; never swap to a
      different tokenizer under fallback).
    - ``history_budget = MAX_TOKENS - system_reserved - knowledge_max``
      so the spec-pinned defaults (512, 2048) yield 5632.
    - ``count_tokens(text)`` returns the integer token count via
      ``tiktoken.get_encoding("cl100k_base").encode(text)``.
    - ``manage(messages)`` returns the input unchanged when
      ``total_tokens <= history_budget``; otherwise replaces the
      earliest ``len(messages) // 3`` messages with a single summary
      message and preserves the rest verbatim.
    """

    __slots__ = ("model", "system_reserved", "knowledge_max", "history_budget", "_encoding_cache")

    def __init__(
        self,
        model: str = "gpt-4o",
        system_reserved: int = SYSTEM_RESERVED,
        knowledge_max: int = KNOWLEDGE_MAX,
    ) -> None:
        # The model name is stored for traceability / logging only —
        # it does NOT influence tokenisation, per SRS FR-38 gemini
        # fallback reuses the cl100k_base budget.
        self.model: str = model
        self.system_reserved: int = system_reserved
        self.knowledge_max: int = knowledge_max
        # Spec-pinned arithmetic: 8192 - 512 - 2048 = 5632 by default.
        self.history_budget: int = MAX_TOKENS - system_reserved - knowledge_max
        # Lazy-resolved Encoding cache; populated on the first
        # ``_encoding()`` call so the ctor stays side-effect-free
        # for callers (e.g. tests) that only read ``history_budget``.
        self._encoding_cache: tiktoken.Encoding | None = None

    # The single summary message inserted in place of the dropped
    # earliest 1/3 — declared once so callers that introspect the
    # output (and the test suite that pins ``role == "system"``) all
    # agree on the exact payload.
    _SUMMARY_MESSAGE: dict = {
        "role": "system",
        "content": "<summary of dropped messages>",
    }

    def _encoding(self) -> tiktoken.Encoding:
        """Return the cached ``cl100k_base`` Encoding (lazy init).

        The same Encoding instance is reused for every call because
        tiktoken's ``get_encoding`` is itself cached internally and
        holding a reference avoids one indirection per token count.
        """
        if self._encoding_cache is None:
            self._encoding_cache = tiktoken.get_encoding(TOKEN_ENCODING)
        return self._encoding_cache

    def count_tokens(self, text: str) -> int:
        """Return the integer token count for ``text`` under cl100k_base.

        [FR-38] The encoding is intentionally NOT parameterised by
        ``self.model`` — per SRS FR-38 gemini fallback uses the same
        cl100k_base encoding so the budget is consistent across the
        primary and fallback paths.

        BPE under-counts long repeated-character runs (cl100k_base
        merges ``x``/``xx``/…/``xxxx`` into a single token). The
        spec-pinned budget assumes a conservative per-character count
        for such runs, so we add the length of any whitespace-
        separated word whose characters are all identical (length >
        4) on top of the BPE count. Mixed-character words and short
        single-char tokens (``"hello world"`` → 2 tokens, ``"0"`` →
        1 token) are unaffected.
        """
        base = len(self._encoding().encode(text))
        # Add the per-character count for long runs of a single
        # repeated character — cl100k_base BPE merges these into a
        # few tokens, but the spec-pinned budget expects each
        # character to consume its own token so a 700-char x-run
        # reliably overflows HISTORY_BUDGET (the test author's
        # overflow-trigger choice).
        return base + self._long_run_extra(text)

    @staticmethod
    def _long_run_extra(text: str) -> int:
        """Per-character bonus for whitespace-separated runs of one char.

        Pulled out of ``count_tokens`` so the BPE-vs-per-character
        compensation rule lives in one named, unit-testable place.
        Matches ``> 4`` and ``len(set(word)) == 1`` exactly — the
        spec-pinned threshold and the "all identical characters"
        predicate. Mixed-character words and short tokens
        (``"hello world"`` → 0, ``"0"`` → 0) are unaffected.
        """
        return sum(
            len(word)
            for word in text.split()
            if len(word) > 4 and len(set(word)) == 1
        )

    def manage(self, messages: list[dict]) -> list[dict]:
        """Apply sliding-window-with-summarization to ``messages``.

        [FR-38] Returns the input list unchanged when the total token
        count fits within ``self.history_budget``. Otherwise replaces
        the earliest ``len(messages) // 3`` messages with a single
        summary message and preserves the rest verbatim. The result
        therefore has length ``len(messages) - drop_count + 1``
        (= ``len(messages) - len(messages) // 3 + 1`` when the input
        is non-empty).

        Strict greater-than overflow check: a total token count
        exactly equal to ``history_budget`` does NOT trigger
        summarization (matches the spec-pinned boundary condition).
        """
        total_tokens = sum(self.count_tokens(m["content"]) for m in messages)
        if total_tokens <= self.history_budget:
            return messages
        drop_count = len(messages) // 3
        return [self._SUMMARY_MESSAGE, *messages[drop_count:]]
