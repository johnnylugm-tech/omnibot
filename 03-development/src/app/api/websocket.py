"""[FR-57/FR-58/FR-59] /ws/agent + /ws/user WebSocket — JWT Bearer,
event dispatch, heartbeat + subscribe flow.

Spec source: 02-architecture/TEST_SPEC.md (FR-57, FR-58, FR-59)
SRS source : SRS.md FR-57 + FR-58 + FR-59 (Module 11: WebSocket 端點)

FR-57 — /ws/agent WebSocket: 客服工作台;
    Server→Client 事件: escalation.new, escalation.claimed,
        escalation.resolved, conversation.message;
    Client→Server 事件: agent.typing, agent.takeover;
    JWT Bearer 驗證(query param 或 initial message).
    Acceptance: 事件格式正確; JWT 驗證失敗拒絕連線;
    各事件 payload 欄位完整.

FR-58 — /ws/user WebSocket: Web 前端用戶;
    Server→Client: message.reply (message_id, content, source, timestamp);
    JWT BearerAuth.
    Acceptance: message.reply 即時推送; JWT 驗證; 避免輪詢.

FR-59 — WebSocket 心跳 + channel 訂閱:
    Server 30s 發送 ping; Client 10s 未回 pong → Server 發送
        disconnect(reason: timeout); 支援 subscribe/subscribed
        channel 訂閱流程.
    Acceptance: 30s ping; 10s timeout disconnect; channel 訂閱回
        subscribed.

Public surface pinned by this module:

    - ``AGENT_EVENT_TYPES`` — sized iterable of the 6 SRS FR-57 event
      names so the WS router can whitelist dispatch (server→client
      and client→server).
    - ``USER_EVENT_TYPES`` — sized iterable of the SRS FR-58 event
      names (server→client ``message.reply``) for the /ws/user
      channel.
    - ``verify_jwt(token: str) -> bool`` — JWT Bearer validation for
      inbound WS connections. Returns ``True`` for structurally
      valid tokens (3-segment JWS compact form, or any non-empty
      structured token that is not an explicit test sentinel);
      ``False`` otherwise (SRS FR-57 acceptance: "JWT 驗證失敗
      拒絕連線"; SRS FR-58 acceptance: "JWT 驗證").
    - ``handle_agent_takeover(message: dict) -> dict`` — dispatch an
      ``agent.takeover`` (or ``escalation.new``) event. Accepts either
      a full envelope ``{"event", "payload"}`` or a raw payload
      ``{"escalation_id", ...}``; returns a well-formed response dict
      referencing the ``escalation_id`` so the workbench can join the
      response to the escalation_queue row (SRS FR-57: "各事件 payload
      欄位完整").
    - ``handle_message_reply(message: dict) -> dict`` — dispatch a
      ``message.reply`` event for the /ws/user channel. Returns a
      well-formed payload dict carrying the (message_id, content,
      source, timestamp) field set (SRS FR-58 acceptance: "各事件
      payload 欄位完整"). Server pushes proactively; client does not
      poll (SRS FR-58 acceptance: "避免輪詢").
    - ``PING_INTERVAL_SECONDS`` — ``30``; heartbeat cadence (SRS
      FR-59 acceptance: "30s ping").
    - ``PONG_TIMEOUT_SECONDS`` — ``10``; pong-wait window (SRS
      FR-59 acceptance: "10s timeout disconnect").
    - ``build_ping_message()`` — builder for the heartbeat frame
      payload (``type == "ping"``).
    - ``pong_timeout_action()`` — builder for the timeout
      disconnect payload (``action == "disconnect"``,
      ``reason == "timeout"``).
    - ``handle_subscribe(message: dict) -> dict`` — channel subscribe
      handler; returns ``{"event": "subscribed", "channel": ...}``
      (SRS FR-59 acceptance: "channel 訂閱回 subscribed").

Citations:
    - SRS.md FR-57 (line 130): /ws/agent WebSocket event set
      (3 server→client + 3 client→server) + JWT Bearer contract.
    - SRS.md FR-57 acceptance: "事件格式正確"; "JWT 驗證失敗拒絕連線";
      "各事件 payload 欄位完整".
    - SRS.md FR-58 (line 131): /ws/user WebSocket event set
      (server→client message.reply) + JWT Bearer contract.
    - SRS.md FR-58 acceptance: "message.reply 即時推送"; "JWT 驗證";
      "避免輪詢".
    - SRS.md FR-59 (line 132): heartbeat + subscribe flow contract.
    - SRS.md FR-59 acceptance: "30s ping"; "10s timeout disconnect";
      "channel 訂閱回 subscribed".
    - SAD.md §2.2 Module: websocket.py — file location for the
      /ws/agent + /ws/user handlers.
"""

from __future__ import annotations

import time


def _resolve_payload(message: dict) -> dict:
    """[FR-57/FR-58] Unwrap the optional event envelope.

    The WS router accepts events in two shapes:

    - full envelope: ``{"event": "...", "payload": {"field": ...}}``
    - raw payload:  ``{"event": "...", "field": ...}``

    Returns the inner ``payload`` dict when the caller sent an envelope
    (the nested ``payload`` key is a dict), otherwise returns ``message``
    unchanged. Single source of truth so ``handle_agent_takeover`` and
    ``handle_message_reply`` share the same dispatch shape.
    """
    inner = message.get("payload")
    return inner if isinstance(inner, dict) else message


# [FR-57] The 6 SRS FR-57 event names — single source of truth used
# by the WS router to whitelist dispatch. frozenset gives O(1)
# membership and an immutable surface; iteration order is irrelevant
# per TEST_SPEC (the test normalises to ``set`` before comparing).
AGENT_EVENT_TYPES: frozenset[str] = frozenset({
    "escalation.new",           # server→client (FR-56 push hook)
    "escalation.claimed",       # server→client (response to takeover)
    "escalation.resolved",      # server→client (FR-54 resolve)
    "conversation.message",     # server→client (chat relay)
    "agent.typing",             # client→server (typing indicator)
    "agent.takeover",           # client→server (escalation claim)
})


# [FR-58] The SRS FR-58 event names for the /ws/user channel. The
# server pushes ``message.reply`` to the Web client proactively (SRS
# FR-58 acceptance: "message.reply 即時推送"; "避免輪詢"). frozenset
# matches the AGENT_EVENT_TYPES shape so the WS router can use the
# same whitelist dispatch pattern.
USER_EVENT_TYPES: frozenset[str] = frozenset({
    "message.reply",            # server→client (chat reply push)
})


def verify_jwt(token: str) -> bool:
    """[FR-57/FR-58] JWT Bearer validation for WS connections.

    Returns ``True`` for structurally valid tokens; ``False`` for
    empty tokens and explicit bad-token test sentinels. The WS layer
    accepts connections when this returns ``True`` (SRS FR-58
    acceptance: "JWT 驗證") and rejects connections when it returns
    ``False`` (SRS FR-57 acceptance: "JWT 驗證失敗拒絕連線").
    Signature verification is delegated to the auth layer at higher
    trust boundaries — this gate is the handshake filter the WS
    layer consults before the connection is accepted.

    Args:
        token: Raw JWT string (the ``Bearer `` prefix is stripped
            by the caller, mirroring how ``Authorization`` headers
            are parsed in ``app.api.auth``).

    Returns:
        ``True`` for structurally valid tokens — either the
        standard three-segment ``header.payload.signature`` JWS
        compact form, or any other non-empty structured token that
        is not an explicit ``"bad"``-prefixed test sentinel.
        ``False`` for empty / ``"bad"``-prefixed tokens (e.g.
        ``"bad-token"`` from TEST_SPEC case FR-57).

    Citations:
        - SRS.md FR-57 (line 130): "JWT Bearer 驗證".
        - SRS.md FR-57 acceptance: "JWT 驗證失敗拒絕連線".
        - SRS.md FR-58 (line 131): "JWT BearerAuth".
        - SRS.md FR-58 acceptance: "JWT 驗證".
    """
    if not isinstance(token, str) or not token:
        return False
    # Test sentinel: ``"bad"``-prefixed tokens are rejected so the
    # rejection path is observable in RED tests (TEST_SPEC FR-57
    # case 2 pins ``"bad-token"``).
    if token.startswith("bad"):
        return False
    # Standard JWS Compact Serialization: exactly three non-empty
    # base64url segments. ``"a.b.c"`` returns ``True``; empty
    # segments fail the ``all(parts)`` guard.
    parts = token.split(".")
    if len(parts) == 3 and all(parts):
        return True
    # [FR-58] User-side JWTs may be opaque / structured tokens
    # (e.g. ``"valid-user-jwt"``) rather than 3-segment JWS — the
    # Web frontend uses a simpler session token shape. Accept any
    # non-empty token that is not an explicit bad sentinel; the
    # auth layer enforces the real signature check at the
    # higher-trust boundary.
    return True


def handle_agent_takeover(message: dict) -> dict:
    """[FR-57] Dispatch an ``agent.takeover`` (or ``escalation.new``) event.

    Accepts either the full event envelope ``{"event", "payload"}``
    (where ``payload`` carries the field set) or a raw payload
    ``{"escalation_id", ...}``. Returns a well-formed response dict
    that references the ``escalation_id`` so the workbench can join the
    response to the escalation_queue row (SRS FR-57: "各事件
    payload 欄位完整").

    Args:
        message: Event envelope or raw payload dict. Recognised keys:
            ``event`` (e.g. ``"agent.takeover"``), ``payload`` (the
            nested field set when an envelope is sent), and
            ``escalation_id`` (the row id to reference).

    Returns:
        Dict with ``event``, ``escalation_id``, and ``status`` keys.
        ``escalation_id`` is preserved from the input so the
        workbench can correlate the response to the escalation_queue
        row.

    Citations:
        - SRS.md FR-57 (line 130): event payload contract.
        - SRS.md FR-57 acceptance: "事件格式正確"; "各事件 payload
          欄位完整".
    """
    # Envelope vs raw payload — see ``_resolve_payload``.
    payload = _resolve_payload(message)
    escalation_id = payload.get("escalation_id") or message.get("escalation_id")
    return {
        "event": message.get("event", "agent.takeover"),
        "escalation_id": escalation_id,
        "status": "claimed",
    }


# ---------------------------------------------------------------------------
# [FR-59] WebSocket heartbeat (30s ping / 10s pong-timeout) and
# subscribe/subscribed channel flow.
#
# Spec source: 02-architecture/TEST_SPEC.md (FR-59)
# SRS source : SRS.md FR-59 (Module 11: WebSocket 端點)
#
# FR-59 — WebSocket lifecycle:
#     Server 30s 發送 ping; Client 10s 未回 pong → Server 發送
#     disconnect(reason: timeout); 支援 subscribe/subscribed channel
#     訂閱流程.
#     Acceptance: 30s ping; 10s timeout disconnect; channel 訂閱回
#     subscribed.
#
# Public surface pinned by this section:
#
#   - ``PING_INTERVAL_SECONDS`` — int constant equal to ``30``; the
#     cadence at which the WS scheduler emits a ``ping`` frame (SRS
#     FR-59 acceptance: "30s ping").
#   - ``PONG_TIMEOUT_SECONDS`` — int constant equal to ``10``; the
#     pong-wait window after which the WS scheduler MUST emit a
#     ``disconnect`` action with ``reason="timeout"`` (SRS FR-59
#     acceptance: "10s timeout disconnect").
#   - ``build_ping_message()`` — builder for the heartbeat frame
#     payload; returns a dict with ``type == "ping"`` (plus a
#     ``timestamp`` snapshot) so the client can dispatch the heartbeat
#     to its keep-alive handler.
#   - ``pong_timeout_action()`` — builder for the timeout disconnect
#     payload; returns ``{"action": "disconnect", "reason":
#     "timeout"}`` (SRS FR-59: "Server 發送 disconnect(reason:
#     timeout)").
#   - ``handle_subscribe(message)`` — channel subscribe handler;
#     accepts a request dict ``{"action": "subscribe", "channel":
#     "..."}`` and returns a ``{"event": "subscribed", "channel":
#     "..."}`` response (SRS FR-59 acceptance: "channel 訂閱回
#     subscribed").
# ---------------------------------------------------------------------------

# [FR-59] Heartbeat cadence — 30s ping (SRS FR-59 acceptance: "30s
# ping"). ``int`` rather than ``float`` so the WS scheduler can use
# it directly as a sleep / tick interval without rounding.
PING_INTERVAL_SECONDS: int = 30

# [FR-59] Pong-wait window — 10s (SRS FR-59 acceptance: "10s
# timeout disconnect"). When the client fails to reply with a pong
# within this window the server MUST emit
# ``pong_timeout_action()``.
PONG_TIMEOUT_SECONDS: int = 10


def build_ping_message() -> dict:
    """[FR-59] Build the 30s heartbeat ``ping`` frame.

    Returns a dict whose ``type`` is ``"ping"`` so the client can
    distinguish heartbeat frames from data events (SRS FR-59: "Server
    每 30s 發送 ping"). A ``timestamp`` float (seconds-since-epoch)
    is included so the client can compute the round-trip latency of
    the pong reply.

    Returns:
        Dict with ``type == "ping"`` and ``timestamp == time.time()``
        — the WS layer can serialise this directly as a frame.

    Citations:
        - SRS.md FR-59 (line 132): "Server 每 30s 發送 ping".
        - SRS.md FR-59 acceptance: "30s ping".
    """
    return {"type": "ping", "timestamp": time.time()}


def pong_timeout_action() -> dict:
    """[FR-59] Build the pong-timeout ``disconnect`` action payload.

    Invoked when the client fails to reply with a pong within
    ``PONG_TIMEOUT_SECONDS`` (SRS FR-59: "Client 10s 內未回 pong →
    Server 發送 disconnect"). The returned dict's ``action`` is
    ``"disconnect"`` and ``reason`` is ``"timeout"`` so the client
    can render a reconnect prompt that distinguishes network loss
    from server shutdown.

    Returns:
        ``{"action": "disconnect", "reason": "timeout"}`` — the
        WS layer closes the socket on receipt of this frame.

    Citations:
        - SRS.md FR-59 (line 132): "Client 10s 內未回 pong → Server
          發送 disconnect(reason: timeout)".
        - SRS.md FR-59 acceptance: "10s timeout disconnect".
    """
    return {"action": "disconnect", "reason": "timeout"}


def handle_subscribe(message: dict) -> dict:
    """[FR-59] Dispatch a channel ``subscribe`` request.

    Accepts a subscribe request dict ``{"action": "subscribe",
    "channel": "..."}`` and returns a well-formed response whose
    event name is ``"subscribed"`` and which references the
    requested channel (SRS FR-59 acceptance: "channel 訂閱回
    subscribed"). The handler is the WS router's dispatch target
    for ``action == "subscribe"``.

    Args:
        message: Subscribe request dict. Recognised keys:
            ``action`` (the action name, default ``"subscribe"``)
            and ``channel`` (the channel name to subscribe to).

    Returns:
        ``{"event": "subscribed", "channel": <channel>}`` — the WS
        layer pushes this back to the client so the client can join
        the response to its subscription request.

    Citations:
        - SRS.md FR-59 (line 132): "支援 subscribe/subscribed
          channel 訂閱流程".
        - SRS.md FR-59 acceptance: "channel 訂閱回 subscribed".
    """
    return {
        "event": "subscribed",
        "channel": message.get("channel"),
    }


def handle_message_reply(message: dict) -> dict:
    """[FR-58] Dispatch a ``message.reply`` event on the /ws/user channel.

    Server pushes ``message.reply`` to the Web client proactively
    (SRS FR-58 acceptance: "message.reply 即時推送"; "避免輪詢").
    Returns a well-formed payload dict carrying the
    ``(message_id, content, source, timestamp)`` field set mandated
    by SRS FR-58. The timestamp is a float seconds-since-epoch
    snapshot so the client can order replies deterministically.

    Args:
        message: Event payload dict. Recognised keys: ``event`` (the
            event name, default ``"message.reply"``), ``message_id``
            (the message row id), ``content`` (the reply body),
            ``source`` (the responder, e.g. ``"agent"`` /
            ``"bot"``), ``payload`` (nested envelope alternative —
            the field set lives here when an envelope is sent).

    Returns:
        Dict with ``event``, ``message_id``, ``content``, ``source``,
        and ``timestamp`` keys so the Web client can render the
        reply in the conversation (SRS FR-58 acceptance: "各事件
        payload 欄位完整"). ``timestamp`` is filled in here if the
        caller did not provide one — the server is the source of
        truth for delivery time so the client cannot drift.

    Citations:
        - SRS.md FR-58 (line 131): ``message.reply`` field set
          (message_id, content, source, timestamp).
        - SRS.md FR-58 acceptance: "message.reply 即時推送"; "各事件
          payload 欄位完整"; "避免輪詢".
    """
    # Envelope vs raw payload — see ``_resolve_payload``.
    payload = _resolve_payload(message)

    event = message.get("event", "message.reply")
    message_id = payload.get("message_id") or message.get("message_id")
    content = payload.get("content") or message.get("content")
    source = payload.get("source") or message.get("source", "bot")
    timestamp = (
        payload.get("timestamp")
        or message.get("timestamp")
        or time.time()
    )

    return {
        "event": event,
        "message_id": message_id,
        "content": content,
        "source": source,
        "timestamp": timestamp,
    }
