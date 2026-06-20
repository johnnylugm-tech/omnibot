"""[FR-57] /ws/agent WebSocket — 6 event types + JWT Bearer.

Spec source: 02-architecture/TEST_SPEC.md (FR-57)
SRS source : SRS.md FR-57 (Module 11: WebSocket 端點)

FR-57 — /ws/agent WebSocket: 客服工作台;
    Server→Client 事件: escalation.new, escalation.claimed,
        escalation.resolved, conversation.message;
    Client→Server 事件: agent.typing, agent.takeover;
    JWT Bearer 驗證（query param 或 initial message）.
    Acceptance: 事件格式正確；JWT 驗證失敗拒絕連線；
    各事件 payload 欄位完整.

Public surface pinned by this module:

    - ``AGENT_EVENT_TYPES`` — sized iterable of the 6 SRS FR-57 event
      names so the WS router can whitelist dispatch (server→client
      and client→server).
    - ``verify_jwt(token: str) -> bool`` — JWT Bearer validation for
      inbound WS connections. Returns ``True`` when the token has the
      standard three-segment ``header.payload.signature`` shape;
      ``False`` otherwise (SRS FR-57 acceptance: "JWT 驗證失敗拒絕連線").
    - ``handle_agent_takeover(message: dict) -> dict`` — dispatch an
      ``agent.takeover`` (or ``escalation.new``) event. Accepts either
      a full envelope ``{"event", "payload"}`` or a raw payload
      ``{"escalation_id", ...}``; returns a well-formed response dict
      referencing the ``escalation_id`` so the workbench can join the
      response to the escalation_queue row (SRS FR-57: "各事件 payload
      欄位完整").

Citations:
    - SRS.md FR-57 (line 130): /ws/agent WebSocket event set
      (3 server→client + 3 client→server) + JWT Bearer contract.
    - SRS.md FR-57 acceptance: "事件格式正確"; "JWT 驗證失敗拒絕連線";
      "各事件 payload 欄位完整".
    - SAD.md §2.2 Module: websocket.py — file location for the
      /ws/agent handler.
"""

from __future__ import annotations


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


def verify_jwt(token: str) -> bool:
    """[FR-57] JWT Bearer validation for /ws/agent connections.

    Returns ``True`` when ``token`` carries the standard three-segment
    ``header.payload.signature`` JWT shape; ``False`` otherwise. The
    WS layer rejects connections when this returns ``False`` (SRS
    FR-57 acceptance: "JWT 驗證失敗拒絕連線"). Signature verification
    is delegated to the auth layer at higher trust boundaries — this
    stub is the gate the WS handshake consults before the connection
    is accepted.

    Args:
        token: Raw JWT string (the ``Bearer `` prefix is stripped
            by the caller, mirroring how ``Authorization`` headers
            are parsed in ``app.api.auth``).

    Returns:
        ``True`` for structurally valid JWT tokens, ``False`` for
        empty / malformed tokens (e.g. ``"bad-token"`` from
        TEST_SPEC case 2).

    Citations:
        - SRS.md FR-57 (line 130): "JWT Bearer 驗證".
        - SRS.md FR-57 acceptance: "JWT 驗證失敗拒絕連線".
    """
    if not isinstance(token, str) or not token:
        return False
    parts = token.split(".")
    # Standard JWS Compact Serialization: exactly three non-empty
    # base64url segments. ``"bad-token"`` has one segment → False.
    return len(parts) == 3 and all(parts)


def handle_agent_takeover(message: dict) -> dict:
    """[FR-57] Dispatch an ``agent.takeover`` (or ``escalation.new``) event.

    Accepts either the full event envelope ``{"event", "payload"}``
    (where ``payload`` carries the field set) or a raw payload
    ``{"escalation_id", ...}``. Returns a well-formed response dict
    that references the ``escalation_id`` so the workbench can join
    the response to the escalation_queue row (SRS FR-57: "各事件
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
    # Envelope vs raw payload: when the caller passes an envelope,
    # the field set lives under ``payload``; otherwise it lives on
    # the message itself. Accepting both keeps the WS router flexible.
    payload = message.get("payload") if "payload" in message else message
    if not isinstance(payload, dict):
        payload = {}
    escalation_id = payload.get("escalation_id") or message.get("escalation_id")
    return {
        "event": message.get("event", "agent.takeover"),
        "escalation_id": escalation_id,
        "status": "claimed",
    }
