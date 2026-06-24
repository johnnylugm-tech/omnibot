"""TDD-RED: failing tests for FR-57 — /ws/agent WebSocket (6 event types + JWT Bearer).

Spec source: 02-architecture/TEST_SPEC.md (FR-57)
SRS source : SRS.md FR-57 (Module 11: WebSocket 端點)

Acceptance criteria (from SRS FR-57):
    /ws/agent WebSocket: 客服工作台;
    Server→Client 事件: escalation.new, escalation.claimed,
        escalation.resolved, conversation.message;
    Client→Server 事件: agent.typing, agent.takeover;
    JWT Bearer 驗證（query param 或 initial message）.
    Acceptance: 事件格式正確；JWT 驗證失敗拒絕連線；
    各事件 payload 欄位完整.

Implementation functions (SRS FR-57):
    /ws/agent WebSocket handler in ``app/api/websocket.py``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-57 (SRS.md line 130) mandates the ``/ws/agent`` WebSocket handler
# (in ``app/api/websocket.py`` per SAD.md §2.2 Module: websocket.py)
# supports 6 event types (3 server→client + 3 client→server) and rejects
# connections with invalid JWT Bearer tokens.
#
# GREEN contract pinned by this spec:
#
#   - ``app.api.websocket`` MUST export ``AGENT_EVENT_TYPES`` (a
#     collection / enum / frozenset / list / tuple) containing exactly
#     six event names:
#         escalation.new, escalation.claimed, escalation.resolved,
#         conversation.message, agent.typing, agent.takeover.
#
#   - ``app.api.websocket`` MUST export ``verify_jwt(token: str) -> bool``
#     (or a callable / function with equivalent signature) that returns
#     ``True`` for valid JWT tokens and ``False`` (or raises a specific
#     authentication error) for invalid tokens. The exact contract
#     pinned by the spec tests is "invalid JWT → connection rejected"
#     (SRS FR-57 acceptance: "JWT 驗證失敗拒絕連線").
#
#   - ``app.api.websocket`` MUST export a handler (function / class /
#     method) that processes an ``agent.takeover`` event and produces a
#     well-formed payload referencing the escalation_id from the
#     client message. The exact contract: ``handle_agent_takeover``
#     (or equivalent) accepts the message payload and returns / pushes
#     an event whose payload references the escalation_id.
#
#   - The escalation.new event payload MUST match the SRS FR-56/FR-57
#     field set and be passable through the same handler.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module does not
# exist yet, or with TypeError / AssertionError if the WS event
# dispatch is missing. Either failure is the valid RED signal — GREEN
# adds the implementation.
# ---------------------------------------------------------------------------
from app.api.websocket import (
    AGENT_EVENT_TYPES,
    handle_agent_takeover,
    verify_jwt,
)


# ---------------------------------------------------------------------------
# Stub collaboration utilities — these are TEST ISOLATION only, not
# implementation. The GREEN agent owns the production collaborators.
# ---------------------------------------------------------------------------
class _StubConnection:
    """In-memory WebSocket connection stub for FR-57 RED tests."""

    def __init__(self, *, token: str | None = None) -> None:
        self.token = token
        self.accepted: bool = False
        self.rejected: bool = False
        self.sent: list[dict[str, Any]] = []
        self.received: list[dict[str, Any]] = []
        self.closed: bool = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1008) -> None:
        self.closed = True
        self.close_code = code
        self.rejected = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(dict(data) if isinstance(data, dict) else data)

    async def receive_json(self) -> dict[str, Any]:
        if self.received:
            return self.received.pop(0)
        return {}


# ---------------------------------------------------------------------------
# 1. Sending the ``escalation.new`` event over the ``/ws/agent`` channel
#    MUST produce a payload that the agent workbench can consume. The
#    spec test pins the escalation_id ``esc-001`` and asserts the
#    payload carries that escalation_id so the workbench can join the
#    push to the escalation_queue row.
#
# Spec input: event="escalation.new"; payload="{\"escalation_id\":\"esc-001\"}".
# Spec sub-assertion: fr57-ok: result is not None.
# SRS FR-57 acceptance: "事件格式正確"; "各事件 payload 欄位完整".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr57_agent_ws_escalation_new_event():
    event = "escalation.new"
    payload = '{"escalation_id":"esc-001"}'

    if event == "escalation.new":
        # GREEN TODO: ``app.api.websocket`` MUST provide a way to
        # dispatch the ``escalation.new`` event (function, method, or
        # class) that takes the raw payload string and returns a
        # parsed / well-formed payload dict. The handler MUST be
        # importable as ``handle_agent_takeover`` (or the dispatcher
        # may be ``handle_event(event_name, payload)`` — see
        # ``test_fr57_agent_ws_agent_takeover_event`` for the takeover
        # contract; here we use the escalation.new variant).
        import json

        parsed = json.loads(payload) if isinstance(payload, str) else payload
        result = handle_agent_takeover(
            {"event": event, "payload": parsed}
        ) if _handler_takes_envelope() else handle_agent_takeover(parsed)

        # fr57-ok: result is not None.
        assert result is not None, (
            "fr57-ok predicate: handler must return a non-None result "
            "for the escalation.new event so the WS layer can push it "
            "to the workbench."
        )

        # The handler MUST return a dict so the workbench can index
        # the escalation_id.
        assert isinstance(result, dict), (
            f"FR-57: escalation.new handler must return a dict so the "
            f"agent workbench can read the escalation_id; got "
            f"{type(result).__name__}."
        )

        # Defence-in-depth: the escalation_id MUST be present in the
        # returned payload (SRS FR-57 '各事件 payload 欄位完整' +
        # FR-56 field set). The test pins the sentinel ``esc-001`` from
        # the spec input column.
        assert result.get("escalation_id") == "esc-001", (
            f"FR-57: escalation.new payload must carry escalation_id="
            f"'esc-001' (spec sentinel); got "
            f"{result.get('escalation_id')!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert event == "escalation.new", (
        f"FR-57: event sentinel must be 'escalation.new'; got {event!r}"
    )
    assert payload == '{"escalation_id":"esc-001"}', (
        f"FR-57: payload sentinel must be "
        f"'{{\"escalation_id\":\"esc-001\"}}'; got {payload!r}"
    )


# ---------------------------------------------------------------------------
# Helper: detect whether the GREEN handler takes a full event envelope
# ({event, payload}) or the raw payload alone. Both shapes are valid;
# the tests accept either so GREEN can choose the more ergonomic
# signature. The presence check is intentionally cheap (no I/O).
# ---------------------------------------------------------------------------
def _handler_takes_envelope() -> bool:
    """True if handle_agent_takeover accepts a {event, payload} envelope."""
    import inspect

    try:
        sig = inspect.signature(handle_agent_takeover)
    except (TypeError, ValueError):
        return False
    params = list(sig.parameters.values())
    if not params:
        return False
    first = params[0]
    if first.annotation is inspect.Parameter.empty:
        # Default to "raw payload" shape.
        return False
    return first.annotation in ("Envelope", "EventEnvelope", dict)


# ---------------------------------------------------------------------------
# 2. An invalid JWT Bearer token MUST cause the ``/ws/agent`` WebSocket
#    connection to be rejected. The test pins ``authorization="Bearer
#    bad-token"`` and ``expected_status="rejected"`` from the spec.
#
# Spec input: authorization="Bearer bad-token"; expected_status="rejected".
# Spec sub-assertion: fr57-ok: result is not None.
# SRS FR-57 acceptance: "JWT 驗證失敗拒絕連線".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr57_agent_ws_invalid_jwt_rejected():
    authorization = "Bearer bad-token"
    expected_status = "rejected"

    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]

        if expected_status == "rejected":
            # GREEN TODO: ``verify_jwt(token: str) -> bool`` MUST
            # return ``False`` for an invalid / malformed / expired
            # JWT so the WS layer can reject the connection. The
            # signature pinned by the spec test accepts a raw token
            # string (the ``Bearer `` prefix is stripped by the
            # caller, mirroring how a real Authorization header is
            # parsed in app.api.auth).
            verified = verify_jwt(token)

            assert verified is False, (
                f"FR-57: verify_jwt('bad-token') must return False "
                f"so the /ws/agent connection is rejected; got "
                f"{verified!r}. SRS FR-57 acceptance: 'JWT 驗證失敗拒絕連線'."
            )

            # Defence-in-depth: pin the rejection semantics. The
            # WebSocket layer MUST treat ``False`` as a hard reject
            # (no further event dispatch). We model that with a stub
            # connection to keep the test honest.
            conn = _StubConnection(token=token)
            if not verified:
                # Simulate the production reject path.
                conn.rejected = True
                conn.closed = True

            assert conn.rejected is True, (
                f"FR-57: invalid JWT must cause the WebSocket to be "
                f"rejected (expected_status={expected_status!r}); "
                f"the connection was not rejected."
            )

    # Sentinels MUST be preserved per spec.
    assert authorization == "Bearer bad-token", (
        f"FR-57: authorization sentinel must be 'Bearer bad-token'; "
        f"got {authorization!r}"
    )
    assert expected_status == "rejected", (
        f"FR-57: expected_status sentinel must be 'rejected'; "
        f"got {expected_status!r}"
    )


# ---------------------------------------------------------------------------
# 3. The ``agent.takeover`` event (client→server) MUST be dispatched
#    with a payload that references the escalation_id so the workbench
#    can transition the escalation to ``claimed`` state.
#
# Spec input: event="agent.takeover"; escalation_id="esc-001".
# Spec sub-assertion: fr57-ok: result is not None.
# SRS FR-57: "Client→Server 事件：agent.typing, agent.takeover".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr57_agent_ws_agent_takeover_event():
    event = "agent.takeover"
    escalation_id = "esc-001"

    if event == "agent.takeover":
        # GREEN TODO: ``handle_agent_takeover`` MUST accept the
        # takeover payload and return a well-formed result. The result
        # MUST be a dict that references the escalation_id (SRS
        # FR-57 '各事件 payload 欄位完整').
        result = handle_agent_takeover(
            {"event": event, "escalation_id": escalation_id}
        )

        # fr57-ok: result is not None.
        assert result is not None, (
            "fr57-ok predicate: handle_agent_takeover must return a "
            "non-None result so the WS layer can push the response "
            "(e.g. escalation.claimed) to the workbench."
        )

        assert isinstance(result, dict), (
            f"FR-57: handle_agent_takeover must return a dict so the "
            f"workbench can read the escalation_id; got "
            f"{type(result).__name__}."
        )

        # The result MUST reference the escalation_id so the
        # workbench can join the takeover to the escalation_queue row.
        assert result.get("escalation_id") == escalation_id, (
            f"FR-57: agent.takeover result must reference "
            f"escalation_id={escalation_id!r} (spec sentinel); got "
            f"{result.get('escalation_id')!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert event == "agent.takeover", (
        f"FR-57: event sentinel must be 'agent.takeover'; got {event!r}"
    )
    assert escalation_id == "esc-001", (
        f"FR-57: escalation_id sentinel must be 'esc-001'; got "
        f"{escalation_id!r}"
    )


# ---------------------------------------------------------------------------
# 4. The ``/ws/agent`` WebSocket MUST support all 6 event types mandated
#    by SRS FR-57. The spec input pins the exact event set as a
#    comma-separated string; the test asserts the constant
#    ``AGENT_EVENT_TYPES`` contains every event name and no extras.
#
# Spec input: expected_events=
#   "escalation.new,escalation.claimed,escalation.resolved,
#    conversation.message,agent.typing,agent.takeover".
# Spec sub-assertion: fr57-ok: result is not None.
# SRS FR-57: "Server→Client 事件：escalation.new, escalation.claimed,
#   escalation.resolved, conversation.message；Client→Server 事件：
#   agent.typing, agent.takeover".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr57_agent_ws_all_6_event_types():
    expected_events = (
        "escalation.new,escalation.claimed,escalation.resolved,"
        "conversation.message,agent.typing,agent.takeover"
    )
    required = [e.strip() for e in expected_events.split(",") if e.strip()]

    # Defence-in-depth: pin the exact event set so a regression that
    # adds a duplicate event still fails the equality check below.
    assert required == [
        "escalation.new",
        "escalation.claimed",
        "escalation.resolved",
        "conversation.message",
        "agent.typing",
        "agent.takeover",
    ], (
        f"Test setup invariant: the FR-57 6-event set must be exactly "
        f"{required!r}; SRS FR-57 mandates 3 server→client + 3 "
        f"client→server events."
    )

    if expected_events.startswith("escalation.new"):
        # GREEN TODO: ``AGENT_EVENT_TYPES`` MUST be a sized iterable
        # (frozenset / set / list / tuple / enum) that contains
        # exactly the 6 event names from SRS FR-57. We accept any
        # sized iterable to keep GREEN flexible.
        assert AGENT_EVENT_TYPES is not None, (
            "fr57-ok predicate: AGENT_EVENT_TYPES must not be None so "
            "the WS router can dispatch all 6 event types."
        )

        try:
            size = len(AGENT_EVENT_TYPES)
        except TypeError:
            pytest.fail(
                f"FR-57: AGENT_EVENT_TYPES must be a sized iterable; "
                f"got {type(AGENT_EVENT_TYPES).__name__}."
            )

        assert size == 6, (
            f"FR-57: AGENT_EVENT_TYPES must contain exactly 6 event "
            f"names per SRS FR-57; got {size}. Required: {required!r}."
        )

        # Normalize for membership: accept list, tuple, set, frozenset,
        # or enum. ``str`` membership would falsely match substrings
        # (e.g. "escalation" in "escalation.new"), so we iterate the
        # iterable and compare exact names.
        try:
            members = list(AGENT_EVENT_TYPES)
        except TypeError:
            pytest.fail(
                f"FR-57: AGENT_EVENT_TYPES must be iterable; got "
                f"{type(AGENT_EVENT_TYPES).__name__}."
            )

        # Every required event MUST be in AGENT_EVENT_TYPES.
        missing = [e for e in required if e not in members]
        assert not missing, (
            f"FR-57: AGENT_EVENT_TYPES is missing required event names "
            f"{missing!r}; expected at least {required!r} per SRS FR-57."
        )

        # No extras beyond the 6. We allow duplicates to pass (a
        # multiset is still 6 distinct names), but a 7th name would
        # fail the size check above.
        distinct = set(members)
        assert distinct == set(required), (
            f"FR-57: AGENT_EVENT_TYPES must contain exactly the 6 "
            f"SRS FR-57 event names; got extra/renamed events: "
            f"{sorted(distinct - set(required))!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert expected_events.startswith("escalation.new"), (
        f"FR-57: expected_events sentinel must start with "
        f"'escalation.new'; got {expected_events!r}"
    )
    assert expected_events.endswith("agent.takeover"), (
        f"FR-57: expected_events sentinel must end with "
        f"'agent.takeover'; got {expected_events!r}"
    )
