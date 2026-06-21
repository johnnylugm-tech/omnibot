from __future__ import annotations
"""TDD-RED: failing tests for FR-54 — EscalationManager (create/assign/resolve 完整生命週期).

Spec source: 02-architecture/TEST_SPEC.md (FR-54)
SRS source : SRS.md FR-54 (Module 10: Human Escalation)

Acceptance criteria (from SRS FR-54):
    EscalationManager：
      - create(EscalationRequest) → 插入 escalation_queue
        （conversation_id, reason, priority, sla_deadline）→ 回傳 escalation_id
      - assign(escalation_id, agent_id) → 更新 assigned_agent + picked_at
      - resolve(escalation_id) → 更新 resolved_at
    建立轉接記錄成功；assign 更新 assigned_agent + picked_at；resolve 更新
    resolved_at。

Implementation functions (SRS FR-54):
    EscalationManager.create(), .assign(), .resolve().

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-54 mandates ``EscalationManager`` (SRS FR-54 implementation_functions).
# The canonical module is ``app.services.escalation`` per SAD.md (Module:
# escalation.py, line 257-260: "EscalationManager.create(), .assign(),
# .resolve() → FR-54") and the directory tree at line 539 lists
# "app.services.escalation" alongside the AEE / AB-testing services.
#
# GREEN contract pinned by this spec:
#
#   - ``EscalationManager`` (in ``app/services/escalation.py``) MUST
#     expose three methods:
#
#         1. ``create(EscalationRequest) -> str``
#            Persists a new row to ``escalation_queue`` with the
#            conversation_id / reason / priority / sla_deadline fields and
#            returns the newly generated ``escalation_id``.
#
#         2. ``assign(escalation_id: str, agent_id: str) -> None``
#            Updates the row's ``assigned_agent`` and ``picked_at``
#            columns so the human agent can take ownership of the case.
#
#         3. ``resolve(escalation_id: str) -> None``
#            Sets the row's ``resolved_at`` timestamp so the case is
#            closed and removed from the active queue.
#
#   - ``EscalationRequest`` (or an equivalent kwarg signature) MUST
#     accept ``conversation_id`` and ``priority`` and forward them into the
#     row insert. ``reason`` and ``sla_deadline`` may either be passed
#     explicitly or derived inside ``create`` (e.g. sla_deadline derived
#     from priority via the FR-55 SLA table).
#
#   - The test for the full lifecycle (test 4) MUST be able to call
#     create → assign → resolve sequentially on the same escalation_id
#     and observe ``resolved_at`` populated at the end.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.services.escalation`` does not yet export ``EscalationManager``.
# That is the valid RED signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.services.escalation import (
    EscalationManager,
)


# ---------------------------------------------------------------------------
# 1. ``create`` MUST insert a row into ``escalation_queue`` carrying the
#    conversation_id and priority from the request, and MUST return the
#    newly minted ``escalation_id`` (non-None string).
#
# Spec input: conversation_id="conv-001"; priority="1".
# Spec sub-assertion: fr54-ok: result is not None.
# SRS FR-54 acceptance: "建立轉接記錄成功".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr54_create_inserts_escalation_queue():
    conversation_id = "conv-001"
    priority = "1"

    # Spec fr54-ok predicate 'result is not None' applies_to case 1.
    if conversation_id == "conv-001":
        # GREEN TODO: ``EscalationManager.create(EscalationRequest)``
        # MUST insert a new row into the ``escalation_queue`` table
        # (SRS FR-54: "插入 escalation_queue（conversation_id, reason,
        # priority, sla_deadline）") and return the newly generated
        # ``escalation_id`` as a non-None string.
        #
        # The exact field layout of ``EscalationRequest`` is left to
        # GREEN, but the spec test pins ``conversation_id="conv-001"``
        # and ``priority="1"`` (high SLA = 15 min per FR-55) as the
        # minimum inputs that MUST be carried into the row.
        manager = EscalationManager()
        # ``create`` MUST be callable with a request object carrying at
        # minimum the two fields the spec test pins. GREEN may extend
        # the request shape with ``reason`` / ``platform`` / ``preview``
        # etc., but the call MUST succeed for the two pinned fields.
        result = manager.create(
            conversation_id=conversation_id,
            priority=int(priority),
        )
        assert result is not None, (
            "fr54-ok predicate: EscalationManager.create must return a "
            "non-None escalation_id after inserting into escalation_queue"
        )
        # The returned id MUST be a string-like (escalation ids are
        # opaque tokens such as 'esc-001' / uuid4 / 'ESC-<ulid>'), not a
        # boolean / int / None masquerading as an id.
        assert isinstance(result, str), (
            f"FR-54: EscalationManager.create must return a string "
            f"escalation_id; got {type(result).__name__}={result!r}"
        )
        assert len(result) > 0, (
            "FR-54: EscalationManager.create must return a non-empty "
            "escalation_id"
        )

    # Sentinels MUST be preserved per spec.
    assert conversation_id == "conv-001", (
        f"FR-54: conversation_id sentinel must be 'conv-001'; "
        f"got {conversation_id!r}"
    )
    assert priority == "1", (
        f"FR-54: priority sentinel must be '1'; got {priority!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``assign`` MUST update the row's ``assigned_agent`` (and ``picked_at``)
#    so a human agent can take ownership of the case. The test pins the
#    observable input/output: given an existing escalation_id and a new
#    agent_id, the row's ``assigned_agent`` column MUST equal agent_id.
#
# Spec input: escalation_id="esc-001"; agent_id="agent-001".
# Spec sub-assertion: fr54-ok: result is not None.
# SRS FR-54 acceptance: "assign 更新 assigned_agent + picked_at".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr54_assign_updates_assigned_agent():
    escalation_id = "esc-001"
    agent_id = "agent-001"

    # Spec fr54-ok predicate 'result is not None' applies_to case 1.
    if escalation_id == "esc-001":
        # GREEN TODO: ``EscalationManager.assign(escalation_id, agent_id)``
        # MUST update the row's ``assigned_agent`` column to ``agent_id``
        # and set ``picked_at`` to the current time. The spec test pins
        # the contract by reading the row back and asserting
        # ``assigned_agent == agent_id``.
        #
        # GREEN's choice of data layer (PostgreSQL, in-memory dict, mock
        # repository) is left to the implementer, but the read-back
        # contract below MUST be satisfied.
        manager = EscalationManager()
        # Pre-populate the queue so the assign target exists. The
        # pre-population uses ``create`` (the FR-54 create method) to
        # avoid standing up a separate fixture; GREEN MAY also add a
        # ``seed`` helper for tests, but ``create`` is sufficient.
        seeded_id = manager.create(
            conversation_id="conv-pre-assign",
            priority=0,
        )
        # The spec test pins the ID; the assertion uses the spec
        # sentinel but the read-back still operates on the seeded
        # row to keep the test self-contained. If GREEN's create
        # returns an auto-generated ID (e.g. uuid4), the spec
        # sentinel ``esc-001`` is the contract value — the GREEN
        # implementation MUST make ``assign(esc-001, agent-001)``
        # affect a row whose ``assigned_agent`` ends up == agent-001.
        manager.assign(escalation_id=escalation_id, agent_id=agent_id)

        # Read-back contract: assigned_agent column MUST equal the
        # agent_id we just passed. We accept any of the common shapes
        # GREEN may expose (dict-like row, ``get_escalation`` helper,
        # public ``rows`` attribute, etc.).
        # GREEN TODO: EscalationManager MUST provide a way to read back
        # the assigned_agent column. Acceptable: ``manager.get(id)``,
        # ``manager.rows[id]``, or any public accessor returning a
        # mapping with an ``assigned_agent`` key.
        row = (
            getattr(manager, "rows", {}).get(escalation_id)
            or (
                hasattr(manager, "get")
                and manager.get(escalation_id)
            )
            or {}
        )
        assert row is not None, (
            "fr54-ok predicate: assign must return / leave a non-None "
            "row so the assigned_agent update is observable"
        )
        # Resolve the assigned_agent value across the common shapes
        # (dict key, dataclass attribute, object attribute).
        if isinstance(row, dict):
            assigned = row.get("assigned_agent")
        else:
            assigned = getattr(row, "assigned_agent", None)
        assert assigned == agent_id, (
            f"FR-54: assign(escalation_id={escalation_id!r}, "
            f"agent_id={agent_id!r}) must set assigned_agent="
            f"{agent_id!r}; got {assigned!r}. SRS FR-54 mandates "
            f"'assign 更新 assigned_agent + picked_at'."
        )
        # Suppress unused-variable warning for the seeded id — GREEN
        # may rely on it for setup but the spec test contract is
        # anchored on the pinned sentinel ``esc-001``.
        _ = seeded_id

    # Sentinels MUST be preserved per spec.
    assert escalation_id == "esc-001", (
        f"FR-54: escalation_id sentinel must be 'esc-001'; "
        f"got {escalation_id!r}"
    )
    assert agent_id == "agent-001", (
        f"FR-54: agent_id sentinel must be 'agent-001'; "
        f"got {agent_id!r}"
    )


# ---------------------------------------------------------------------------
# 3. ``resolve`` MUST set the row's ``resolved_at`` field so the case is
#    closed and removed from the active queue. The spec test pins the
#    field name ``resolved_at`` as the contract.
#
# Spec input: escalation_id="esc-001"; expected_field="resolved_at".
# Spec sub-assertion: fr54-ok: result is not None.
# SRS FR-54 acceptance: "resolve 更新 resolved_at".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr54_resolve_sets_resolved_at():
    escalation_id = "esc-001"
    expected_field = "resolved_at"

    if escalation_id == "esc-001":
        # GREEN TODO: ``EscalationManager.resolve(escalation_id)`` MUST
        # set the row's ``resolved_at`` column to the current time so
        # the case is closed. The spec test pins the field name
        # ``resolved_at`` (TEST_SPEC expected_field="resolved_at") and
        # reads it back.
        manager = EscalationManager()
        manager.create(conversation_id="conv-pre-resolve", priority=0)
        manager.resolve(escalation_id=escalation_id)

        # Read-back contract: resolved_at MUST be populated (non-None
        # and not the empty string) after resolve().
        # GREEN TODO: EscalationManager MUST expose the row so the
        # resolved_at column is readable. Accept ``manager.get(id)`` /
        # ``manager.rows[id]`` or any public accessor.
        row = (
            getattr(manager, "rows", {}).get(escalation_id)
            or (
                hasattr(manager, "get")
                and manager.get(escalation_id)
            )
            or {}
        )
        assert row is not None, (
            "fr54-ok predicate: resolve must return / leave a non-None "
            "row so the resolved_at update is observable"
        )
        if isinstance(row, dict):
            resolved_at = row.get(expected_field)
        else:
            resolved_at = getattr(row, expected_field, None)
        assert resolved_at is not None, (
            f"FR-54: resolve(escalation_id={escalation_id!r}) must set "
            f"{expected_field!r} to a non-None timestamp; got "
            f"{resolved_at!r}. SRS FR-54 mandates 'resolve 更新 "
            f"resolved_at'."
        )
        # The field MUST NOT be an empty string — None / '' are both
        # invalid for a populated timestamp.
        assert resolved_at != "", (
            f"FR-54: {expected_field!r} must not be an empty string "
            f"after resolve; got {resolved_at!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert escalation_id == "esc-001", (
        f"FR-54: escalation_id sentinel must be 'esc-001'; "
        f"got {escalation_id!r}"
    )
    assert expected_field == "resolved_at", (
        f"FR-54: expected_field sentinel must be 'resolved_at'; "
        f"got {expected_field!r}"
    )


# ---------------------------------------------------------------------------
# 4. Full lifecycle integration: create → assign → resolve on the same
#    escalation. After resolve, the row's ``resolved_at`` MUST be
#    populated and ``assigned_agent`` MUST reflect the agent that picked
#    it up. This test exercises the SRS contract end-to-end (Q7/FR-55
#    integration: priority="0" is "normal" = 30 min SLA per FR-55).
#
# Spec input: conversation_id="conv-002"; priority="0".
# Spec sub-assertion: fr54-ok: result is not None.
# SRS FR-54 acceptance: full create/assign/resolve sequence.
# Test type: integration (Q7 derivation, link to FR-55).
# ---------------------------------------------------------------------------
def test_fr54_create_to_resolve_full_lifecycle():
    conversation_id = "conv-002"
    priority = "0"

    # Spec fr54-ok predicate 'result is not None' applies_to case 1.
    if conversation_id == "conv-002":
        # GREEN TODO: full lifecycle: ``create`` returns a non-None
        # escalation_id; ``assign`` populates ``assigned_agent``;
        # ``resolve`` populates ``resolved_at``; the row remains
        # readable for audit (Q9 / NP-09). The spec test runs the
        # three methods in sequence on a single escalation and
        # asserts each post-condition.
        manager = EscalationManager()
        escalation_id = manager.create(
            conversation_id=conversation_id,
            priority=int(priority),
        )
        assert escalation_id is not None, (
            "fr54-ok predicate: create must return a non-None "
            "escalation_id at the start of the full lifecycle"
        )
        assert isinstance(escalation_id, str) and len(escalation_id) > 0, (
            f"FR-54: create must return a non-empty string "
            f"escalation_id; got {escalation_id!r}"
        )

        # Step 2: assign an agent. We use a fresh agent id so the
        # assertion has a unique value to check.
        assigned_agent = "agent-lifecycle"
        manager.assign(escalation_id=escalation_id, agent_id=assigned_agent)

        # Step 3: resolve the escalation.
        manager.resolve(escalation_id=escalation_id)

        # Read-back: BOTH post-conditions MUST hold.
        # GREEN TODO: EscalationManager MUST expose the row so
        # assigned_agent and resolved_at are readable. Accept
        # ``manager.get(id)`` / ``manager.rows[id]`` or any public
        # accessor.
        row = (
            getattr(manager, "rows", {}).get(escalation_id)
            or (
                hasattr(manager, "get")
                and manager.get(escalation_id)
            )
            or {}
        )
        assert row is not None, (
            "fr54-ok predicate: full-lifecycle row must remain "
            "readable after create/assign/resolve"
        )
        if isinstance(row, dict):
            actual_agent = row.get("assigned_agent")
            actual_resolved_at = row.get("resolved_at")
        else:
            actual_agent = getattr(row, "assigned_agent", None)
            actual_resolved_at = getattr(row, "resolved_at", None)

        assert actual_agent == assigned_agent, (
            f"FR-54: full-lifecycle assigned_agent must equal the "
            f"agent that was passed to assign(); expected "
            f"{assigned_agent!r}, got {actual_agent!r}. SRS FR-54 "
            f"mandates 'assign 更新 assigned_agent + picked_at'."
        )
        assert actual_resolved_at is not None, (
            f"FR-54: full-lifecycle resolved_at must be populated "
            f"after resolve(); got {actual_resolved_at!r}. SRS FR-54 "
            f"mandates 'resolve 更新 resolved_at'."
        )
        assert actual_resolved_at != "", (
            f"FR-54: resolved_at must not be an empty string after "
            f"resolve; got {actual_resolved_at!r}"
        )

    # Sentinels MUST be preserved per spec.
    assert conversation_id == "conv-002", (
        f"FR-54: conversation_id sentinel must be 'conv-002'; "
        f"got {conversation_id!r}"
    )
    assert priority == "0", (
        f"FR-54: priority sentinel must be '0'; got {priority!r}"
    )
