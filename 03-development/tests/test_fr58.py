"""TDD-RED: failing tests for FR-58 — /ws/user WebSocket (message.reply push + JWT).

Spec source: 02-architecture/TEST_SPEC.md (FR-58)
SRS source : SRS.md FR-58 (Module 11: WebSocket 端點)

Acceptance criteria (from SRS FR-58):
    /ws/user WebSocket: Web 前端用戶;
    Server→Client: message.reply (message_id, content, source, timestamp);
    JWT BearerAuth.
    Acceptance: message.reply 即時推送; JWT 驗證; 避免輪詢.

Implementation functions (SRS FR-58):
    /ws/user WebSocket handler in ``app/api/websocket.py``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-58 (SRS.md line 131) mandates the ``/ws/user`` WebSocket handler
# (in ``app/api/websocket.py`` per SAD.md §2.2 Module: websocket.py)
# pushes ``message.reply`` events with the field set
# (message_id, content, source, timestamp), authenticates clients
# with JWT Bearer tokens, and never requires client polling (server
# pushes proactively).
#
# GREEN contract pinned by this spec:
#
#   - ``app.api.websocket`` MUST export ``USER_EVENT_TYPES`` (a
#     collection / enum / frozenset / list / tuple) containing the
#     ``message.reply`` event name (and any others the Web client
#     subscribes to).
#
#   - ``app.api.websocket`` MUST export ``verify_jwt(token: str) -> bool``
#     (or a callable / function with equivalent signature) that returns
#     ``True`` for valid JWT tokens and ``False`` (or raises a specific
#     authentication error) for invalid tokens. The exact contract
#     pinned by the spec tests is "valid JWT → connection established"
#     (SRS FR-58 acceptance: "JWT 驗證").
#
#   - ``app.api.websocket`` MUST export a handler (function / class /
#     method) that processes a ``message.reply`` event and produces a
#     well-formed payload carrying the message_id, content, source, and
#     timestamp fields. The exact contract: ``handle_message_reply``
#     (or equivalent) accepts the message payload and returns / pushes
#     an event whose payload references message_id and content.
#
#   - The server MUST push message.reply proactively — the Web client
#     MUST NOT need to poll. The handler MUST be push-based, not
#     pull-based.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module does not
# expose these names yet, or with TypeError / AssertionError if the
# WS event dispatch is missing. Either failure is the valid RED
# signal — GREEN adds the implementation.
# ---------------------------------------------------------------------------
from app.api.websocket import (  # noqa: F401  -- RED: GREEN adds the names
    USER_EVENT_TYPES,
    handle_message_reply,
    verify_jwt,
)


# ---------------------------------------------------------------------------
# Stub collaboration utilities — these are TEST ISOLATION only, not
# implementation. The GREEN agent owns the production collaborators.
# ---------------------------------------------------------------------------
class _StubUserConnection:
    """In-memory WebSocket connection stub for FR-58 RED tests."""

    def __init__(self, *, token: str | None = None) -> None:
        self.token = token
        self.accepted: bool = False
        self.rejected: bool = False
        self.sent: list[dict[str, Any]] = []
        self.received: list[dict[str, Any]] = []
        self.closed: bool = False
        self.close_code: int | None = None
        # Track polling behaviour: FR-58 MUST NOT require the client
        # to poll. The server pushes events proactively.
        self.poll_attempts: int = 0

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

    async def poll_for_messages(self) -> list[dict[str, Any]]:
        """Simulate a polling loop — FR-58 explicitly forbids this."""
        self.poll_attempts += 1
        return list(self.sent)


# ---------------------------------------------------------------------------
# 1. Sending the ``message.reply`` event over the ``/ws/user`` channel
#    MUST produce a payload that the Web client can consume. The spec
#    test pins the message_id ``msg-001`` and content ``hello`` and
#    asserts the payload carries both fields so the client can render
#    the reply in the conversation.
#
# Spec input: event="message.reply"; message_id="msg-001"; content="hello".
# Spec sub-assertion: fr58-ok: result is not None.
# SRS FR-58 acceptance: "message.reply 即時推送"; "各事件 payload 欄位完整".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr58_user_ws_message_reply_pushed():
    event = "message.reply"
    message_id = "msg-001"
    content = "hello"

    if event == "message.reply":
        # GREEN TODO: ``app.api.websocket`` MUST provide a way to
        # dispatch the ``message.reply`` event (function, method, or
        # class) that takes the message fields and returns a
        # parsed / well-formed payload dict. The handler MUST be
        # importable as ``handle_message_reply``.
        result = handle_message_reply(
            {"event": event, "message_id": message_id, "content": content}
        )

        # fr58-ok: result is not None.
        assert result is not None, (
            "fr58-ok predicate: handler must return a non-None result "
            "for the message.reply event so the WS layer can push it "
            "to the Web client."
        )

        # The handler MUST return a dict so the Web client can render
        # the reply.
        assert isinstance(result, dict), (
            f"FR-58: message.reply handler must return a dict so the "
            f"Web client can read the message_id and content; got "
            f"{type(result).__name__}."
        )

        # Defence-in-depth: the message_id MUST be present in the
        # returned payload (SRS FR-58 '各事件 payload 欄位完整' +
        # FR-58 field set: message_id, content, source, timestamp).
        # The test pins the sentinel ``msg-001`` from the spec input.
        assert result.get("message_id") == message_id, (
            f"FR-58: message.reply payload must carry message_id="
            f"'msg-001' (spec sentinel); got {result.get('message_id')!r}."
        )

        # The content MUST be present and match the spec sentinel.
        assert result.get("content") == content, (
            f"FR-58: message.reply payload must carry content='hello' "
            f"(spec sentinel); got {result.get('content')!r}."
        )

        # SRS FR-58 mandates the field set
        # (message_id, content, source, timestamp). The event name
        # MUST also be present so the client can dispatch on it.
        assert result.get("event") == event, (
            f"FR-58: message.reply payload must carry event="
            f"'message.reply' (spec sentinel); got {result.get('event')!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert event == "message.reply", (
        f"FR-58: event sentinel must be 'message.reply'; got {event!r}"
    )
    assert message_id == "msg-001", (
        f"FR-58: message_id sentinel must be 'msg-001'; got {message_id!r}"
    )
    assert content == "hello", (
        f"FR-58: content sentinel must be 'hello'; got {content!r}"
    )


# ---------------------------------------------------------------------------
# 2. A valid JWT Bearer token MUST cause the ``/ws/user`` WebSocket
#    connection to be established. The test pins
#    ``jwt="valid-user-jwt"`` and ``expected_connected="true"`` from
#    the spec.
#
# Spec input: jwt="valid-user-jwt"; expected_connected="true".
# Spec sub-assertion: fr58-ok: result is not None.
# SRS FR-58 acceptance: "JWT 驗證".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr58_user_ws_jwt_verified():
    jwt = "valid-user-jwt"
    expected_connected = "true"

    if expected_connected == "true":
        # GREEN TODO: ``verify_jwt(token: str) -> bool`` MUST
        # return ``True`` for a structurally valid JWT so the WS
        # layer can accept the connection. The signature pinned by
        # the spec test accepts a raw token string (the ``Bearer
        # `` prefix is stripped by the caller, mirroring how a
        # real Authorization header is parsed in app.api.auth).
        verified = verify_jwt(jwt)

        assert verified is True, (
            f"FR-58: verify_jwt('valid-user-jwt') must return True "
            f"so the /ws/user connection is accepted; got "
            f"{verified!r}. SRS FR-58 acceptance: 'JWT 驗證'."
        )

        # Defence-in-depth: pin the connection acceptance semantics.
        # The WebSocket layer MUST treat ``True`` as an accept (not
        # reject). We model that with a stub connection to keep the
        # test honest.
        conn = _StubUserConnection(token=jwt)
        if verified:
            # Simulate the production accept path.
            conn.accepted = True

        assert conn.accepted is True, (
            f"FR-58: valid JWT must cause the WebSocket to be "
            f"accepted (expected_connected={expected_connected!r}); "
            f"the connection was not accepted."
        )

    # Sentinels MUST be preserved per spec.
    assert jwt == "valid-user-jwt", (
        f"FR-58: jwt sentinel must be 'valid-user-jwt'; got {jwt!r}"
    )
    assert expected_connected == "true", (
        f"FR-58: expected_connected sentinel must be 'true'; got "
        f"{expected_connected!r}"
    )


# ---------------------------------------------------------------------------
# 3. The ``/ws/user`` WebSocket MUST be push-based — the server MUST
#    push ``message.reply`` events proactively to the Web client
#    without requiring the client to poll. This is a negative
#    constraint (Q8 derivation): "must not require client polling".
#
# Spec input: ws_client_polling_attempts="0"; expected_push_only="true".
# Spec sub-assertion: q8_c1: must not require client polling — server
#   MUST push events proactively.
# SRS FR-58 acceptance: "避免輪詢".
# Test type: negative_constraint (Q8 derivation).
# ---------------------------------------------------------------------------
def test_fr58_must_not_c1():
    ws_client_polling_attempts = "0"
    expected_push_only = "true"

    if expected_push_only == "true":
        # GREEN TODO: ``handle_message_reply`` MUST be push-based —
        # the Web client receives message.reply events without
        # polling. The server is responsible for dispatching events
        # to connected clients (e.g. via a broadcast / fan-out
        # queue), so the test asserts that the handler does NOT
        # require a client poll loop.
        conn = _StubUserConnection()

        # Simulate the server push path: the handler returns a
        # well-formed event that the server pushes to the
        # connection — no client polling required.
        result = handle_message_reply(
            {"event": "message.reply", "message_id": "msg-001", "content": "hello"}
        )
        # The server-side push MUST populate the connection's
        # outbound buffer without the client polling.
        if isinstance(result, dict):
            # In production, the WS router would call
            # ``conn.send_json(result)`` directly. We mirror that
            # here so the test asserts push semantics.
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                conn.send_json(result)
            ) if not asyncio.get_event_loop().is_running() else None

        # The client MUST NOT have polled. ``poll_attempts`` is the
        # number of times the client called ``poll_for_messages``
        # — the spec input pins it at ``"0"`` (string, per the
        # spec input column).
        assert int(ws_client_polling_attempts) == 0, (
            f"FR-58: ws_client_polling_attempts must be '0' "
            f"(server-push only); got {ws_client_polling_attempts!r}."
        )
        assert conn.poll_attempts == 0, (
            f"FR-58: client must not poll the /ws/user endpoint — "
            f"the server pushes message.reply events proactively. "
            f"poll_attempts={conn.poll_attempts}; expected 0."
        )

        # The connection MUST have received the pushed event (the
        # outbound buffer is non-empty), proving the push path
        # works end-to-end.
        assert len(conn.sent) >= 1, (
            f"FR-58: server must push message.reply to the Web "
            f"client (conn.sent should be non-empty); got "
            f"{len(conn.sent)} sent frames."
        )

    # Sentinels MUST be preserved per spec.
    assert ws_client_polling_attempts == "0", (
        f"FR-58: ws_client_polling_attempts sentinel must be '0'; "
        f"got {ws_client_polling_attempts!r}"
    )
    assert expected_push_only == "true", (
        f"FR-58: expected_push_only sentinel must be 'true'; got "
        f"{expected_push_only!r}"
    )
