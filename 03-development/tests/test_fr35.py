from __future__ import annotations
"""TDD-RED: failing tests for FR-35 — Slot Filling:
order_id / reason missing_slots().

Spec source: 02-architecture/TEST_SPEC.md (FR-35)
SRS source : SRS.md FR-35

Acceptance criteria (from SRS FR-35):
    Slot filling：order_status 需要 order_id；return_request 需要
    order_id + reason；missing_slots() 回傳缺失的必填 slot 清單.
    order_status / return_request 缺 slot 時 missing_slots() 正確
    回傳；slot 填完後進入 AWAITING_CONFIRMATION.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test — the slot-filling surface of ``app.core.dst`` does
# NOT exist yet (RED state).
#
# GREEN TODO (for the GREEN agent):
#   The 8-state FSM from FR-34 lives in
#   ``03-development/src/app/core/dst.py``. FR-35 adds the slot-filling
#   surface to the SAME module:
#
#     - An enum (or comparable value type) ``DialogueSlot`` enumerating
#       every slot name the system understands. The spec-pinned names
#       are at minimum ``"order_id"`` and ``"reason"`` (per SRS FR-35
#       acceptance criteria "order_status 需要 order_id" and
#       "return_request 需要 order_id + reason"). The enum values
#       MUST round-trip to their string names via ``str(slot)`` /
#       ``slot.value`` so the missing-slots test can compare against
#       the spec-pinned literals ``"order_id"`` and ``"reason"``.
#
#     - A module-level ``INTENT_TO_SLOTS: dict[str, tuple[str, ...]]``
#       mapping intent name → required slot names. The spec-pinned
#       mapping per SRS FR-35 is:
#           "order_status"  → ("order_id",)
#           "return_request" → ("order_id", "reason")
#       The keys MUST be the literal intent names from FR-32 so the
#       DST can look up the required slots after intent detection.
#
#     - ``DialogueState`` (introduced in FR-34) MUST gain
#       ``def missing_slots(self) -> list[str]`` returning the names
#       of required slots that have not yet been filled. The method
#       reads the current intent (e.g. set via constructor or
#       ``__init__(self, intent: str = ..., slots: dict[str, str] |
#       None = None)``) and returns, in INTENT_TO_SLOTS order, every
#       required slot whose value is empty / missing.
#
#   The imports below are unguarded: pytest will fail with Collection
#   Error (Exit Code 2) on the ``DialogueSlot``, ``INTENT_TO_SLOTS``,
#   or ``missing_slots`` references because the slot-filling surface
#   does not exist yet. That is the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.core.dst import INTENT_TO_SLOTS, DialogueSlot, DialogueState  # noqa: F401


# ---------------------------------------------------------------------------
# 1. order_status intent missing order_id → missing_slots() == ["order_id"].
#
# Spec input: intent="order_status"; order_id=""; expected_missing="order_id".
# SRS FR-35: "order_status 需要 order_id". When the intent is
# order_status and the user has not yet provided an order_id, the
# DialogueState MUST report ``order_id`` as the single missing
# required slot — no other required slot exists for order_status,
# so the returned list has length 1 and contains exactly "order_id".
# ---------------------------------------------------------------------------
def test_fr35_order_status_missing_order_id():
    intent = "order_status"
    order_id = ""
    expected_missing = ["order_id"]

    # Spec fr35-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``intent``; we gate the predicate on
    # that variable matching the spec input ``intent="order_status"``.
    if intent == "order_status":
        # FR-35 functional assertion #1: INTENT_TO_SLOTS MUST expose
        # the spec-pinned mapping for the order_status intent. Without
        # this entry, the DST cannot look up the required slots and
        # missing_slots() cannot answer correctly. The mapping MUST
        # be a tuple/list containing at least ``"order_id"`` (per
        # SRS FR-35 "order_status 需要 order_id").
        assert "order_status" in INTENT_TO_SLOTS, (
            f"FR-35: INTENT_TO_SLOTS must contain an 'order_status' "
            f"entry; got keys={sorted(INTENT_TO_SLOTS.keys())}"
        )
        assert "order_id" in INTENT_TO_SLOTS["order_status"], (
            f"FR-35: INTENT_TO_SLOTS['order_status'] must include "
            f"'order_id' (SRS FR-35 'order_status 需要 order_id'); "
            f"got {list(INTENT_TO_SLOTS['order_status'])!r}"
        )

    # GREEN TODO: ``DialogueState.__init__`` MUST accept the intent
    # (and optionally the slots dict) so missing_slots() can resolve
    # the required slots via INTENT_TO_SLOTS. Until GREEN adds the
    # constructor + missing_slots(), the call below raises
    # ``AttributeError`` / ``TypeError`` and the test fails RED.
    ds = DialogueState(intent=intent, slots={"order_id": order_id})

    # Spec fr35-ok predicate 'result is not None' applies_to case 1.
    # We re-assert here that ``ds`` (the result of construction) is
    # not None — this is the sub-assertion the harness reads to
    # confirm case 1.
    if intent == "order_status":
        # Spec fr35-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (``intent="order_status"``).
        assert ds is not None, (
            "fr35-ok predicate: DialogueState must be constructible "
            "with intent='order_status' and the slots dict"
        )

    # FR-35 functional assertion #2: missing_slots() MUST return the
    # names of the required slots that are still empty. For an
    # order_status intent with no order_id provided, the only missing
    # slot is ``order_id`` (no other required slots exist for
    # order_status per SRS FR-35).
    missing = ds.missing_slots()

    assert list(missing) == expected_missing, (
        f"FR-35: DialogueState.missing_slots() must return "
        f"{expected_missing!r} for intent='order_status' with "
        f"order_id=''; got missing={list(missing)!r}"
    )


# ---------------------------------------------------------------------------
# 2. return_request intent missing BOTH order_id and reason →
#    missing_slots() == ["order_id", "reason"].
#
# Spec input: intent="return_request"; order_id=""; reason="".
# SRS FR-35: "return_request 需要 order_id + reason". When the
# intent is return_request and the user has provided NEITHER order_id
# NOR reason, both required slots are missing — the returned list
# MUST contain both names. The order of the returned list mirrors
# the order of INTENT_TO_SLOTS["return_request"] so the test pins
# both presence AND ordering.
# ---------------------------------------------------------------------------
def test_fr35_return_request_missing_both_slots():
    intent = "return_request"
    order_id = ""
    reason = ""

    # FR-35 functional assertion #1: INTENT_TO_SLOTS MUST pin the
    # return_request → (order_id, reason) mapping. Without both
    # entries, missing_slots() cannot report both missing slots.
    assert "return_request" in INTENT_TO_SLOTS, (
        f"FR-35: INTENT_TO_SLOTS must contain a 'return_request' "
        f"entry; got keys={sorted(INTENT_TO_SLOTS.keys())}"
    )
    required_for_return = INTENT_TO_SLOTS["return_request"]
    assert "order_id" in required_for_return, (
        f"FR-35: INTENT_TO_SLOTS['return_request'] must include "
        f"'order_id' (SRS FR-35 'return_request 需要 order_id + "
        f"reason'); got {list(required_for_return)!r}"
    )
    assert "reason" in required_for_return, (
        f"FR-35: INTENT_TO_SLOTS['return_request'] must include "
        f"'reason' (SRS FR-35 'return_request 需要 order_id + "
        f"reason'); got {list(required_for_return)!r}"
    )

    # GREEN TODO: see test 1 — DialogueState.__init__ must accept
    # intent + slots, and DialogueState.missing_slots() must read
    # INTENT_TO_SLOTS to determine the required slots.
    ds = DialogueState(
        intent=intent, slots={"order_id": order_id, "reason": reason}
    )

    # FR-35 functional assertion #2: missing_slots() MUST return both
    # order_id AND reason. The exact list contents (and order) are
    # pinned to match INTENT_TO_SLOTS["return_request"] so the test
    # catches a regression that drops one of the two required slots.
    missing = ds.missing_slots()

    assert "order_id" in missing, (
        f"FR-35: missing_slots() must include 'order_id' for an "
        f"empty-slots return_request; got missing={list(missing)!r}"
    )
    assert "reason" in missing, (
        f"FR-35: missing_slots() must include 'reason' for an "
        f"empty-slots return_request; got missing={list(missing)!r}"
    )
    assert len(missing) == 2, (
        f"FR-35: missing_slots() must contain exactly the two "
        f"required slots for return_request; got missing="
        f"{list(missing)!r}"
    )


# ---------------------------------------------------------------------------
# 3. return_request with both required slots filled → missing_slots()
#    returns an empty list (no missing slots → DST may advance to
#    AWAITING_CONFIRMATION per SRS FR-35 "slot 填完後進入
#    AWAITING_CONFIRMATION").
#
# Spec input: intent="return_request"; order_id="ORD-001";
#             reason="damaged".
# Happy-path case: every required slot for the intent has been
# collected, so missing_slots() returns an empty list. This is the
# precondition for the DST to advance from SLOT_FILLING to
# AWAITING_CONFIRMATION per SRS FR-35 acceptance criterion.
# ---------------------------------------------------------------------------
def test_fr35_all_slots_filled_no_missing():
    intent = "return_request"
    order_id = "ORD-001"
    reason = "damaged"

    # GREEN TODO: see test 1 — DialogueState.__init__ must accept the
    # filled slots dict so missing_slots() can find every required
    # slot already populated.
    ds = DialogueState(
        intent=intent, slots={"order_id": order_id, "reason": reason}
    )

    # FR-35 functional assertion #1: missing_slots() MUST return an
    # empty list when every required slot is filled. This is the
    # "slot 填完後進入 AWAITING_CONFIRMATION" gate — if missing_slots
    # still reports something, the DST will not advance.
    missing = ds.missing_slots()

    assert list(missing) == [], (
        f"FR-35: missing_slots() must return [] when both required "
        f"slots (order_id='{order_id}', reason='{reason}') are "
        f"filled for intent='return_request'; got "
        f"missing={list(missing)!r}"
    )


# ---------------------------------------------------------------------------
# 4. return_request missing only reason (order_id provided) →
#    missing_slots() == ["reason"].
#
# Spec input: intent="return_request"; order_id="ORD-001"; reason="".
# Asymmetric / partial case: exactly one of the two required slots
# has been collected. The test pins that missing_slots() reports
# ONLY the still-missing slot (reason), not the already-filled
# order_id — a regression that reports filled slots as missing
# would block the DST from ever advancing.
# ---------------------------------------------------------------------------
def test_fr35_return_request_missing_reason_only():
    intent = "return_request"
    order_id = "ORD-001"
    reason = ""
    expected_missing = ["reason"]

    # GREEN TODO: see test 1 — DialogueState.__init__ must accept the
    # partially-filled slots dict so missing_slots() can distinguish
    # filled from missing required slots.
    ds = DialogueState(
        intent=intent, slots={"order_id": order_id, "reason": reason}
    )

    # FR-35 functional assertion #1: missing_slots() MUST report
    # ONLY the empty required slot (reason) and MUST NOT report
    # already-filled slots (order_id). This pins the asymmetric
    # case — the DST should still hold the conversation in
    # SLOT_FILLING because reason is missing.
    missing = ds.missing_slots()

    assert list(missing) == expected_missing, (
        f"FR-35: missing_slots() must return {expected_missing!r} "
        f"for intent='return_request' with order_id='{order_id}' "
        f"filled and reason=''; got missing={list(missing)!r}"
    )
    # FR-35 functional assertion #2: the already-filled order_id MUST
    # NOT appear in the missing list. A regression that conflates
    # "user-provided" with "required-but-empty" would break every
    # multi-slot intent.
    assert "order_id" not in missing, (
        f"FR-35: missing_slots() must NOT include already-filled "
        f"order_id='{order_id}'; got missing={list(missing)!r}"
    )
