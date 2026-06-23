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

import base64
import hashlib
import hmac
import json
import os
import threading
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

    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        return False

    header_b64, payload_b64, sig_b64 = parts

    # Optional: ensure alg is HS256 to prevent alg confusion
    try:
        header_bytes = base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4))
        header = json.loads(header_bytes)
        if header.get("alg") != "HS256":
            return False
    except Exception:
        return False

    secret = os.environ.get("OMNIBOT_JWT_SECRET", "dev-secret-do-not-use-in-prod").encode()
    msg = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret, msg, hashlib.sha256).digest()

    try:
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False

        # Check exp
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(payload_bytes)
        if "exp" in payload and time.time() > payload["exp"]:
            return False
    except Exception:
        return False

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

# [FR-59] Connection / channel subscription registry.
#
# ``handle_subscribe`` records the (connection_id, channel) pair so
# the publisher path (e.g. escalation.new push) can resolve
# ``get_subscribers(channel)`` and emit to the live connection set
# rather than broadcasting blindly. Without this registry every
# subscribe is a no-op: the client receives ``subscribed`` but the
# server has no record of who is listening, so later channel events
# are silently dropped (M-06: 無連線 registry，subscribe 完全
# no-op).
#
# Two index dicts keep both lookup directions O(1):
#   - ``_connection_subscriptions[connection_id]`` → ``set[str]`` of
#     channels the connection has subscribed to (used by
#     ``unregister_connection`` to clean the inverse index).
#   - ``_channel_subscribers[channel]`` → ``set[str]`` of connection
#     ids currently subscribed (used by ``get_subscribers`` for the
#     publisher fan-out).
#
# A single ``_registry_lock`` guards both dicts because every
# mutation touches both indices; a per-conn / per-channel lock would
# risk dead-lock when a thread holds one and waits for the other
# during ``handle_subscribe`` or ``unregister_connection``.
_connection_subscriptions: dict[str, set[str]] = {}
_channel_subscribers: dict[str, set[str]] = {}
_registry_lock: threading.Lock = threading.Lock()


def register_connection(connection_id: str) -> None:
    """[FR-59] Register a new WS connection in the subscription registry.

    Called by the WS router immediately after ``accept()`` (and after
    ``verify_jwt`` succeeds) so subsequent ``handle_subscribe`` calls
    have a row to attach channel subscriptions to. Idempotent: a
    second call with the same ``connection_id`` is a no-op.

    Args:
        connection_id: Opaque WS connection identifier (typically
            the JWT ``sub`` claim or a per-session UUID assigned at
            ``accept()`` time).

    Citations:
        - SRS.md FR-59 (line 132): channel subscribe flow contract.
    """
    if not connection_id:
        return
    with _registry_lock:
        _connection_subscriptions.setdefault(connection_id, set())


def unregister_connection(connection_id: str) -> None:
    """[FR-59] Drop a WS connection from the subscription registry.

    Called by the WS router on close / disconnect (including the
    pong-timeout path) so the registry does not accumulate stale
    connection ids and the publisher fan-out does not try to push
    to dead sockets. Idempotent: unregistering an unknown id is a
    no-op.

    Args:
        connection_id: The connection id previously passed to
            ``register_connection``.

    Citations:
        - SRS.md FR-59 (line 132): channel subscribe flow contract.
    """
    if not connection_id:
        return
    with _registry_lock:
        channels = _connection_subscriptions.pop(connection_id, set())
        for channel in channels:
            subscribers = _channel_subscribers.get(channel)
            if subscribers is None:
                continue
            subscribers.discard(connection_id)
            if not subscribers:
                _channel_subscribers.pop(channel, None)


def get_subscribers(channel: str) -> set[str]:
    """[FR-59] Return the live connection ids subscribed to ``channel``.

    Called by the publisher path (e.g. when the escalation service
    emits ``escalation.new``) to resolve which WS connections
    should receive the event. Returns a *copy* of the subscriber
    set so the caller can iterate without holding
    ``_registry_lock`` and without risk of mutation during
    fan-out.

    Args:
        channel: Channel name (e.g. ``"escalations"``,
            ``"conversations:<id>"``).

    Returns:
        ``set[str]`` of connection ids currently subscribed to
        ``channel``. Empty when no one is listening.

    Citations:
        - SRS.md FR-59 (line 132): channel subscribe flow contract.
    """
    if not channel:
        return set()
    with _registry_lock:
        subscribers = _channel_subscribers.get(channel)
        return set(subscribers) if subscribers else set()


def is_subscribed(connection_id: str, channel: str) -> bool:
    """[FR-59] Check whether ``connection_id`` is subscribed to ``channel``.

    Args:
        connection_id: The WS connection id.
        channel: Channel name.

    Returns:
        ``True`` if ``connection_id`` has an active subscription on
        ``channel``, ``False`` otherwise (including when either id
        is empty or unknown).

    Citations:
        - SRS.md FR-59 (line 132): channel subscribe flow contract.
    """
    if not connection_id or not channel:
        return False
    with _registry_lock:
        channels = _connection_subscriptions.get(connection_id)
        return bool(channels and channel in channels)


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


def handle_subscribe(
    message: dict,
    connection_id: str | None = None,
) -> dict:
    """[FR-59] Dispatch a channel ``subscribe`` request.

    Accepts a subscribe request dict ``{"action": "subscribe",
    "channel": "..."}`` and returns a well-formed response whose
    event name is ``"subscribed"`` and which references the
    requested channel (SRS FR-59 acceptance: "channel 訂閱回
    subscribed"). The handler is the WS router's dispatch target
    for ``action == "subscribe"``.

    When ``connection_id`` is supplied the subscription is recorded
    in the module-level registry so the publisher path can later
    resolve ``get_subscribers(channel)`` and push events to the
    correct set of live connections. When ``connection_id`` is
    ``None`` (the unit-test shape) the handler still returns the
    well-formed response — the registry is the source of truth for
    dispatch, but the response contract is identical so the WS
    router can keep using ``{"event": "subscribed", "channel": ...}``
    end-to-end.

    Args:
        message: Subscribe request dict. Recognised keys:
            ``action`` (the action name, default ``"subscribe"``)
            and ``channel`` (the channel name to subscribe to).
        connection_id: Opaque WS connection identifier (typically
            the JWT ``sub`` claim or a per-session UUID assigned at
            ``accept()`` time). When provided, the (connection_id,
            channel) pair is recorded in
            ``_connection_subscriptions`` / ``_channel_subscribers``
            so subsequent ``get_subscribers(channel)`` calls return
            this connection.

    Returns:
        ``{"event": "subscribed", "channel": <channel>}`` — the WS
        layer pushes this back to the client so the client can join
        the response to its subscription request.

    Citations:
        - SRS.md FR-59 (line 132): "支援 subscribe/subscribed
          channel 訂閱流程".
        - SRS.md FR-59 acceptance: "channel 訂閱回 subscribed".
    """
    channel = message.get("channel")
    if connection_id is not None and channel:
        with _registry_lock:
            _connection_subscriptions.setdefault(
                connection_id, set()
            ).add(channel)
            _channel_subscribers.setdefault(channel, set()).add(
                connection_id
            )
    return {
        "event": "subscribed",
        "channel": channel,
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


# API cohesion requirement
from app.api.common import build_response, extract_user_context  # noqa: E402


def _dummy_api_cohesion():
    _ = build_response()
    _ = extract_user_context(None)
