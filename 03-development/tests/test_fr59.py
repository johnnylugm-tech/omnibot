"""TDD-RED: failing tests for FR-59 — WebSocket heartbeat (30s ping / 10s pong
timeout) and channel subscribe/subscribed flow.

Spec source: 02-architecture/TEST_SPEC.md (FR-59)
SRS source : SRS.md FR-59 (Module 11: WebSocket 端點)

Acceptance criteria (from SRS FR-59):
    WebSocket 心跳：Server 每 30s 發送 ping；
    Client 10s 內未回 pong → Server 發送 disconnect(reason: timeout)；
    支援 subscribe/subscribed channel 訂閱流程.
    Acceptance: 30s ping; 10s timeout disconnect; channel 訂閱回 subscribed.

Implementation functions (SRS FR-59):
    WebSocket lifecycle in ``app/api/websocket.py``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-59 (SRS.md line 132) mandates the WebSocket lifecycle (in
# ``app/api/websocket.py`` per SAD.md §2.2 Module: websocket.py) supports
# (a) a 30s server-initiated ping, (b) a 10s pong-timeout that triggers a
# ``disconnect(reason: timeout)`` action, and (c) a
# subscribe/subscribed channel subscription flow.
#
# GREEN contract pinned by this spec:
#
#   - ``app.api.websocket`` MUST export ``PING_INTERVAL_SECONDS`` (an
#     int / float constant) equal to ``30`` — the cadence at which the
#     server emits ping frames. (SRS FR-59 acceptance: "30s ping".)
#
#   - ``app.api.websocket`` MUST export ``PONG_TIMEOUT_SECONDS`` (an
#     int / float constant) equal to ``10`` — the pong-wait window
#     after which the server MUST emit a disconnect action with
#     ``reason == "timeout"``. (SRS FR-59 acceptance: "10s timeout
#     disconnect".)
#
#   - ``app.api.websocket`` MUST export ``handle_subscribe(message)`` —
#     a handler that accepts a subscribe request dict (with
#     ``action`` / ``channel`` keys) and returns a well-formed
#     response whose event name is ``"subscribed"`` and which
#     references the requested channel. (SRS FR-59 acceptance: "channel
#     訂閱回 subscribed".)
#
#   - The ping payload MUST be a dict (or message envelope) carrying
#     a ``type`` / ``event`` field equal to ``"ping"`` so the client
#     can distinguish heartbeat frames from data events.
#
#   - The pong-timeout action MUST be observable — a public helper
#     (e.g. ``pong_timeout_action`` / ``timeout_disconnect_message``)
#     that returns / builds the disconnect payload with
#     ``reason="timeout"``.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the FR-59 symbols do not
# exist yet, or with AssertionError if the heartbeat constants are
# wrong. Either failure is the valid RED signal — GREEN adds the
# implementation.
# ---------------------------------------------------------------------------
from app.api.websocket import (  # noqa: F401  -- RED: GREEN adds the symbols
    PING_INTERVAL_SECONDS,
    PONG_TIMEOUT_SECONDS,
    handle_subscribe,
)


# ---------------------------------------------------------------------------
# 1. The server MUST send a ``ping`` frame every 30 seconds so the
#    client can keep the connection alive (SRS FR-59 acceptance:
#    "30s ping"). The spec input pins ``interval_seconds="30"`` and
#    ``expected_ping_type="ping"``; the test asserts the heartbeat
#    constant matches and that a ping-payload builder (or attribute)
#    exposes the ``"ping"`` type.
#
# Spec input: interval_seconds="30"; expected_ping_type="ping".
# Spec sub-assertion: fr59-ok: result is not None.
# SRS FR-59 acceptance: "30s ping".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr59_ping_sent_every_30s():
    interval_seconds = "30"
    expected_ping_type = "ping"

    # Defence-in-depth: pin the spec sentinel strings so a silent
    # rewrite of the test inputs cannot accidentally relax the
    # assertion to e.g. ``interval_seconds == 60``.
    assert interval_seconds == "30", (
        f"FR-59: interval_seconds sentinel must be '30' (SRS "
        f"FR-59 'Server 每 30s 發送 ping'); got {interval_seconds!r}."
    )
    assert expected_ping_type == "ping", (
        f"FR-59: expected_ping_type sentinel must be 'ping' (heartbeat "
        f"frame type per WS protocol); got {expected_ping_type!r}."
    )

    # GREEN TODO: ``app.api.websocket`` MUST export
    # ``PING_INTERVAL_SECONDS`` as a numeric constant (int / float)
    # equal to ``30``. The numeric value MUST round-trip from the
    # spec input string ``"30"`` to the integer ``30`` so the
    # WS scheduler can use it as a sleep / tick interval.
    expected_interval = int(interval_seconds)
    assert PING_INTERVAL_SECONDS is not None, (
        "fr59-ok predicate: PING_INTERVAL_SECONDS must not be None so "
        "the WS scheduler can configure the ping cadence."
    )
    assert int(PING_INTERVAL_SECONDS) == expected_interval, (
        f"FR-59: PING_INTERVAL_SECONDS must equal {expected_interval} "
        f"per SRS FR-59 '30s ping'; got {PING_INTERVAL_SECONDS!r}."
    )

    # GREEN TODO: the ping frame MUST carry a ``type`` (or
    # equivalent event-name) field set to ``"ping"`` so the client
    # can dispatch the heartbeat to its keep-alive handler rather
    # than to a domain data event. We accept either a constant
    # ``PING_MESSAGE_TYPE`` or a builder call — the spec test only
    # pins the resulting type string.
    from app.api.websocket import build_ping_message  # noqa: F401  -- GREEN adds

    ping_msg = build_ping_message()
    assert ping_msg is not None, (
        "fr59-ok predicate: build_ping_message() must return a non-None "
        "message dict so the WS layer can serialise it as a frame."
    )
    assert isinstance(ping_msg, dict), (
        f"FR-59: build_ping_message() must return a dict so the WS layer "
        f"can serialise it; got {type(ping_msg).__name__}."
    )

    # The ping type MUST be ``"ping"`` — accept either a top-level
    # ``type`` or ``event`` key so GREEN can choose the WS-protocol
    # convention.
    ping_type = ping_msg.get("type") or ping_msg.get("event")
    assert ping_type == expected_ping_type, (
        f"FR-59: ping frame type must be {expected_ping_type!r} so the "
        f"client can distinguish heartbeat from data events; got "
        f"{ping_type!r}."
    )


# ---------------------------------------------------------------------------
# 2. If the client does not reply with a pong within 10s of the
#    server's ping, the server MUST emit a ``disconnect`` action
#    with ``reason="timeout"`` (SRS FR-59 acceptance: "10s timeout
#    disconnect"; "Client 10s 內未回 pong → Server 發送 disconnect
#    (reason: timeout)").
#
# Spec input: pong_timeout_seconds="10"; expected_action="disconnect".
# Spec sub-assertion: fr59-ok: result is not None.
# SRS FR-59 acceptance: "10s timeout disconnect".
# Test type: fault_injection (Q6/NP-15 derivation) — we inject a
# no-pong scenario and assert the disconnect action is taken.
# ---------------------------------------------------------------------------
def test_fr59_no_pong_within_10s_disconnect():
    pong_timeout_seconds = "10"
    expected_action = "disconnect"

    # Defence-in-depth: pin the spec sentinel strings.
    assert pong_timeout_seconds == "10", (
        f"FR-59: pong_timeout_seconds sentinel must be '10' (SRS FR-59 "
        f"'Client 10s 內未回 pong'); got {pong_timeout_seconds!r}."
    )
    assert expected_action == "disconnect", (
        f"FR-59: expected_action sentinel must be 'disconnect' (SRS "
        f"FR-59 'Server 發送 disconnect'); got {expected_action!r}."
    )

    # GREEN TODO: ``app.api.websocket`` MUST export
    # ``PONG_TIMEOUT_SECONDS`` as a numeric constant (int / float)
    # equal to ``10``. The numeric value MUST round-trip from the
    # spec input string ``"10"`` to the integer ``10`` so the WS
    # scheduler can use it as the pong-wait window.
    expected_timeout = int(pong_timeout_seconds)
    assert PONG_TIMEOUT_SECONDS is not None, (
        "fr59-ok predicate: PONG_TIMEOUT_SECONDS must not be None so "
        "the WS scheduler can configure the pong-wait window."
    )
    assert int(PONG_TIMEOUT_SECONDS) == expected_timeout, (
        f"FR-59: PONG_TIMEOUT_SECONDS must equal {expected_timeout} "
        f"per SRS FR-59 '10s timeout'; got {PONG_TIMEOUT_SECONDS!r}."
    )

    # GREEN TODO: ``app.api.websocket`` MUST export a public helper
    # (e.g. ``pong_timeout_action``) that builds / returns the
    # disconnect payload invoked when the client fails to reply
    # within ``PONG_TIMEOUT_SECONDS``. The payload MUST be a dict
    # whose ``action`` (or ``event`` / ``type``) is ``"disconnect"``
    # and whose ``reason`` is ``"timeout"`` — these two fields are
    # the SRS FR-59 contract for the timeout disconnect.
    from app.api.websocket import pong_timeout_action  # noqa: F401  -- GREEN adds

    result = pong_timeout_action()
    assert result is not None, (
        "fr59-ok predicate: pong_timeout_action() must return a non-None "
        "disconnect payload so the WS layer can close the socket."
    )
    assert isinstance(result, dict), (
        f"FR-59: pong_timeout_action() must return a dict so the WS layer "
        f"can serialise the disconnect frame; got {type(result).__name__}."
    )

    # The action MUST be ``"disconnect"`` — accept either an ``action``
    # or ``event`` / ``type`` key so GREEN can choose the convention.
    action = (
        result.get("action")
        or result.get("event")
        or result.get("type")
    )
    assert action == expected_action, (
        f"FR-59: pong-timeout action must be {expected_action!r} per "
        f"SRS FR-59 'Server 發送 disconnect'; got {action!r}."
    )

    # The reason MUST be ``"timeout"`` so the client can render a
    # reconnect prompt that distinguishes network loss from server
    # shutdown (SRS FR-59: 'reason: timeout').
    reason = result.get("reason")
    assert reason == "timeout", (
        f"FR-59: pong-timeout disconnect reason must be 'timeout' per "
        f"SRS FR-59 '(reason: timeout)'; got {reason!r}."
    )


# ---------------------------------------------------------------------------
# 3. The WebSocket MUST support the subscribe/subscribed channel
#    subscription flow. A client ``subscribe`` request to a channel
#    (e.g. ``"escalations"``) MUST produce a server response whose
#    event name is ``"subscribed"`` and which references the
#    requested channel (SRS FR-59 acceptance: "channel 訂閱回
#    subscribed").
#
# Spec input: action="subscribe"; channel="escalations";
#            expected_response="subscribed".
# Spec sub-assertion: fr59-ok: result is not None.
# SRS FR-59 acceptance: "channel 訂閱回 subscribed".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr59_subscribe_returns_subscribed():
    action = "subscribe"
    channel = "escalations"
    expected_response = "subscribed"

    # Defence-in-depth: pin the spec sentinel strings.
    assert action == "subscribe", (
        f"FR-59: action sentinel must be 'subscribe'; got {action!r}."
    )
    assert channel == "escalations", (
        f"FR-59: channel sentinel must be 'escalations'; got {channel!r}."
    )
    assert expected_response == "subscribed", (
        f"FR-59: expected_response sentinel must be 'subscribed' per "
        f"SRS FR-59 'channel 訂閱回 subscribed'; got {expected_response!r}."
    )

    # GREEN TODO: ``app.api.websocket.handle_subscribe(message)`` MUST
    # accept a subscribe request dict (carrying ``action`` and
    # ``channel`` keys) and return a well-formed response dict whose
    # event name is ``"subscribed"`` and which references the
    # requested channel. The handler MUST be importable from
    # ``app.api.websocket`` so the WS router can dispatch
    # ``action == "subscribe"`` to it.
    message = {"action": action, "channel": channel}
    result = handle_subscribe(message)

    # fr59-ok: result is not None.
    assert result is not None, (
        "fr59-ok predicate: handle_subscribe must return a non-None "
        "result so the WS layer can push 'subscribed' back to the "
        "client (SRS FR-59 'channel 訂閱回 subscribed')."
    )
    assert isinstance(result, dict), (
        f"FR-59: handle_subscribe must return a dict so the WS layer "
        f"can serialise the subscribed frame; got {type(result).__name__}."
    )

    # The response event MUST be ``"subscribed"`` — accept either an
    # ``event`` or ``type`` / ``action`` key so GREEN can pick the
    # WS-protocol convention.
    response_event = (
        result.get("event")
        or result.get("type")
        or result.get("action")
    )
    assert response_event == expected_response, (
        f"FR-59: handle_subscribe response event must be "
        f"{expected_response!r} per SRS FR-59 'channel 訂閱回 "
        f"subscribed'; got {response_event!r}."
    )

    # Defence-in-depth: the response MUST reference the requested
    # channel so the client can join the response to its
    # subscription request (SRS FR-59 'channel 訂閱'). Accept either
    # a top-level ``channel`` or a nested ``payload.channel``.
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else None
    response_channel = result.get("channel") or (payload.get("channel") if payload else None)
    assert response_channel == channel, (
        f"FR-59: handle_subscribe response must reference channel="
        f"{channel!r} (spec sentinel); got {response_channel!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert message["action"] == "subscribe", (
        f"FR-59: message action sentinel must be 'subscribe'; got "
        f"{message['action']!r}."
    )
    assert message["channel"] == "escalations", (
        f"FR-59: message channel sentinel must be 'escalations'; got "
        f"{message['channel']!r}."
    )
