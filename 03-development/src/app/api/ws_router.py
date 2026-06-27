"""[FR-56, FR-57, FR-58, FR-59] /ws/agent + /ws/user WebSocket router.

Wires the ``app.api.websocket`` library to FastAPI WebSocket routes:

    /ws/agent   JWT-gated agent workbench channel
    /ws/user    JWT-gated webchat user channel

Lifecycle per connection:

    accept() → verify_jwt(token) → register_connection(id) →
        start ping task (every PING_INTERVAL_SECONDS) →
        concurrently:  receive loop (handle_subscribe /
            agent.takeover / agent.typing) + send loop (drains the
            outbound queue) →
        on disconnect / pong timeout → unregister_connection(id)

The outbound queue is the contract with ``_AgentPusher``:
``pusher.push(channel, event, payload)`` resolves the channel's
subscribers via ``get_subscribers`` and enqueues the frame on each
subscriber's queue. The send loop drains queue → websocket. This
keeps the WS read loop and the publisher path independent — there is
no shared mutable state between the read coroutine and the publish
coroutine.

JWT is passed as a query param ``?token=<jwt>`` because browsers
cannot set custom headers on ``new WebSocket(url)``. Validation is
the same ``verify_jwt`` library function used by the REST auth path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.admin.portal import AgentPortal
from app.api.websocket import (
    PING_INTERVAL_SECONDS,
    PONG_TIMEOUT_SECONDS,
    build_ping_message,
    get_subscribers,
    handle_agent_takeover,
    handle_message_reply,
    handle_subscribe,
    pong_timeout_action,
    register_connection,
    unregister_connection,
    verify_jwt,
)
from app.services.escalation import EscalationManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Outbound queue per connection — publisher pushes here, send loop drains.
# Locked because the pusher may run on a different coroutine than the
# connection's send loop (publisher is sync from EscalationManager.create).
_outbound_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_outbound_lock = asyncio.Lock()


class _AgentPusher:
    """[FR-56] Injectable pusher wired into ``EscalationManager(pusher=...)``.

    ``push(channel, event, payload)`` schedules a coroutine on the
    running event loop to fan out to all subscribers. The push
    itself is fire-and-forget — the caller (EscalationManager.create)
    does not await the broadcast.
    """

    def push(self, channel: str, event: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (unit-test seam); skip silently
        loop.create_task(_publish(channel, event, payload))


# Wire EscalationManager → _AgentPusher at module import. ``build_app``
# imports this module; once the loop is running the pusher will pick
# up subscribers.
_escalation_manager = EscalationManager(pusher=_AgentPusher())
_portal = AgentPortal()


async def _publish(channel: str, event: str, payload: dict[str, Any]) -> None:
    """Fan out an event to every live subscriber of ``channel``.

    For ``escalation.new`` we ALSO call ``AgentPortal.on_escalation_new``
    so the REST inbox endpoint (``/portal/inbox/Unassigned``) reflects
    the new case — otherwise the portal page would only update via the
    live WS push and a page reload would show an empty inbox.

    The full envelope ``{event, payload, timestamp}`` is what
    ``handle_subscribe`` / ``handle_message_reply`` already shape; we
    just wrap it in a top-level ``type`` so the client can dispatch.
    """
    if event == "escalation.new":
        _portal.on_escalation_new(payload)
    subscribers = get_subscribers(channel)
    if not subscribers:
        return
    frame = {"type": "event", "event": event, "payload": payload}
    async with _outbound_lock:
        queues = [_outbound_queues.get(sid) for sid in subscribers]
    for q in queues:
        if q is not None:
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:  # pragma: no cover
                logger.warning("outbound queue full, dropping frame for subscriber")


async def _send_loop(ws: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Drain the outbound queue and write JSON frames to ``ws``."""
    while True:
        frame = await queue.get()
        try:
            await ws.send_text(json.dumps(frame, default=str))
        except Exception:
            return


async def _ping_loop(ws: WebSocket, last_pong: dict[str, float]) -> None:
    """Emit ``ping`` every PING_INTERVAL_SECONDS; disconnect on pong timeout."""
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        try:
            await ws.send_text(json.dumps(build_ping_message()))
        except Exception:
            return
        # pong-window check — last_pong["t"] is updated by the read loop.
        import time

        if time.time() - last_pong["t"] > PING_INTERVAL_SECONDS + PONG_TIMEOUT_SECONDS:
            try:
                await ws.send_text(json.dumps(pong_timeout_action()))
                await ws.close()
            except Exception:
                pass
            return


async def _accept_and_run(
    ws: WebSocket,
    token: str,
    channel: str,
    conn_id: str,
) -> None:
    """Common WS handler — accept, verify, register, run loops."""
    if not verify_jwt(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    register_connection(conn_id)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
    async with _outbound_lock:
        _outbound_queues[conn_id] = queue

    # Auto-subscribe to the channel that matches this endpoint.
    handle_subscribe({"channel": channel}, connection_id=conn_id)
    try:
        await ws.send_text(json.dumps(handle_subscribe({"channel": channel})))
    except Exception:
        pass

    last_pong: dict[str, float] = {"t": __import__("time").time()}
    sender = asyncio.create_task(_send_loop(ws, queue))
    pinger = asyncio.create_task(_ping_loop(ws, last_pong))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            # Heartbeat reply.
            if msg.get("type") == "pong":
                last_pong["t"] = __import__("time").time()
                continue
            action = msg.get("action") or msg.get("event")
            if action == "subscribe":
                resp = handle_subscribe(msg, connection_id=conn_id)
                queue.put_nowait(resp)
            elif action in ("agent.takeover", "escalation.new"):
                resp = handle_agent_takeover(msg)
                queue.put_nowait(resp)
            elif action == "agent.typing":
                # typing indicator — no echo required.
                continue
            elif action == "message.reply":
                resp = handle_message_reply(msg)
                queue.put_nowait(resp)
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        pinger.cancel()
        unregister_connection(conn_id)
        async with _outbound_lock:
            _outbound_queues.pop(conn_id, None)
        try:
            await ws.close()
        except Exception:
            pass


@router.websocket("/ws/agent")
async def ws_agent(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """[FR-57] /ws/agent — agent workbench channel."""
    conn_id = f"agent-{uuid.uuid4().hex[:8]}"
    await _accept_and_run(websocket, token, channel="/ws/agent", conn_id=conn_id)


@router.websocket("/ws/user")
async def ws_user(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """[FR-58] /ws/user — web chat user channel."""
    conn_id = f"user-{uuid.uuid4().hex[:8]}"
    await _accept_and_run(websocket, token, channel="/ws/user", conn_id=conn_id)


# Expose the singleton so other modules can drive escalations in tests.
escalation_manager = _escalation_manager


def get_escalation_manager() -> EscalationManager:
    """Return the module-level ``EscalationManager`` wired with the pusher."""
    return _escalation_manager


@router.get("/admin/test/fire-escalation")
async def fire_test_escalation() -> dict:
    """[P3 E2E] Trigger an ``escalation.new`` for manual verification.

    ONLY available when ``OMNIBOT_TESTING=1`` so production never
    exposes this. Returns the created ``escalation_id`` so the
    verification script can correlate the WS frame to the row.
    """
    import os

    if os.environ.get("OMNIBOT_TESTING") != "1":
        raise HTTPException(status_code=404, detail="not found")
    eid = _escalation_manager.create(
        conversation_id="conv-test",
        priority=2,
        reason="E2E test escalation",
        platform="web",
        preview={"user_message": "I need help", "emotion": "urgent"},
    )
    return {"escalation_id": eid}