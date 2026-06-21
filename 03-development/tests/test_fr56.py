from __future__ import annotations
"""TDD-RED: failing tests for FR-56 — WebSocket 轉接推送：escalation.new 事件 payload.

Spec source: 02-architecture/TEST_SPEC.md (FR-56)
SRS source : SRS.md FR-56 (Module 10: Human Escalation)

Acceptance criteria (from SRS FR-56):
    WebSocket 轉接推送：建立轉接後透過 /ws/agent 推送 escalation.new 事件
    （payload: escalation_id, conversation_id, priority, reason, platform,
    queued_at, preview{user_message, emotion}）
    轉接建立後 WebSocket 即時推送；payload 欄位完整。

Implementation functions (SRS FR-56):
    EscalationManager + WebSocket push. The push is wired into ``create()``
    so every newly inserted escalation_queue row triggers a single
    ``escalation.new`` event on the ``/ws/agent`` channel.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


from typing import Any

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-56 (SRS.md line 124) mandates that ``EscalationManager`` (the
# FR-54 lifecycle class in ``app/services/escalation.py``) MUST also
# push a ``escalation.new`` event over the ``/ws/agent`` WebSocket
# channel immediately after ``create()`` inserts a new escalation_queue
# row. The event payload MUST carry the full SRS FR-56 field set:
#   escalation_id, conversation_id, priority, reason, platform,
#   queued_at, preview{user_message, emotion}.
#
# GREEN contract pinned by this spec:
#
#   - ``EscalationManager.__init__`` MUST accept an injectable
#     ``pusher`` keyword argument (default ``None``) so unit tests can
#     capture pushes without standing up a real WebSocket server. The
#     existing FR-54 ``EscalationManager()`` zero-arg construction MUST
#     remain valid (the new kwarg has a default).
#
#   - The injected ``pusher`` MUST expose a ``push(channel, event,
#     payload)`` method (or an equivalent callable) accepting the three
#     arguments: the WebSocket channel route (e.g. ``"/ws/agent"``),
#     the event name (e.g. ``"escalation.new"``), and the payload dict.
#
#   - ``EscalationManager.create(...)`` MUST invoke the pusher exactly
#     once per inserted row, with ``channel="/ws/agent"`` and
#     ``event="escalation.new"``. The payload MUST be a mapping that
#     contains all seven SRS FR-56 fields.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) if the source module no longer exists,
# or with TypeError / AssertionError if the WS-push wiring is missing.
# Either failure is the valid RED signal — GREEN adds the wiring.
# ---------------------------------------------------------------------------
from app.services.escalation import (
    EscalationManager,
)


# ---------------------------------------------------------------------------
# Stub pusher — captures every ``push(channel, event, payload)`` call
# without performing real WebSocket I/O. This is test isolation, NOT
# implementation: the GREEN agent owns the production pusher. The stub
# exists only so the test fails because the WS-push feature is absent,
# not because of network / DNS / firewall failures.
# ---------------------------------------------------------------------------
class _StubPusher:
    """In-memory WebSocket pusher for FR-56 RED tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def push(self, channel: str, event: str, payload: dict[str, Any]) -> None:
        """[FR-56] Record a push invocation for later assertion."""
        self.calls.append(
            {
                "channel": channel,
                "event": event,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )


# ---------------------------------------------------------------------------
# 1. ``EscalationManager.create(...)`` MUST push a single
#    ``escalation.new`` event to the ``/ws/agent`` channel after
#    inserting the escalation_queue row. The spec test pins
#    ``escalation_id="esc-001"`` (TEST_SPEC.md case 1 input column) and
#    ``channel="/ws/agent"``.
#
# Spec input: escalation_id="esc-001"; channel="/ws/agent".
# Spec sub-assertion: fr56-ok: result is not None.
# SRS FR-56 acceptance: "建立轉接後透過 /ws/agent 推送 escalation.new 事件";
# "轉接建立後 WebSocket 即時推送".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr56_escalation_new_ws_event_sent():
    escalation_id = "esc-001"
    channel = "/ws/agent"

    # Spec fr56-ok predicate 'result is not None' applies_to case 1.
    if escalation_id == "esc-001":
        # GREEN TODO: ``EscalationManager.__init__`` MUST accept a
        # ``pusher`` keyword argument and remember it on the instance
        # (e.g. ``self.pusher = pusher``). The default MUST remain
        # ``None`` so existing FR-54 callers (``EscalationManager()``)
        # keep working unchanged.
        #
        # GREEN TODO: ``EscalationManager.create(...)`` MUST invoke
        # ``self.pusher.push(channel, event, payload)`` exactly once
        # after inserting the row, with:
        #     channel = "/ws/agent"
        #     event   = "escalation.new"
        #     payload = the SRS FR-56 field set (see test 2).
        pusher = _StubPusher()
        manager = EscalationManager(pusher=pusher)

        result = manager.create(
            conversation_id="conv-001",
            priority=1,
            reason="emotion_trigger",
            platform="web",
        )

        assert result is not None, (
            "fr56-ok predicate: EscalationManager.create must return a "
            "non-None escalation_id (FR-54 contract) so the subsequent "
            "WS push has an escalation_id to reference."
        )

        # Primary assertion: the WS push MUST have been invoked at
        # least once. GREEN MAY also push on resolve() / assign() —
        # we only assert that escalation.new fires on create().
        assert len(pusher.calls) >= 1, (
            f"FR-56: create() must push an escalation.new event to "
            f"{channel!r}; got {len(pusher.calls)} push call(s). SRS "
            f"FR-56 mandates '建立轉接後透過 /ws/agent 推送 "
            f"escalation.new 事件'."
        )

        # Locate the escalation.new push. We filter rather than index
        # so GREEN MAY also push other events (e.g. for analytics) on
        # the same create() call without breaking the test.
        new_calls = [c for c in pusher.calls if c["event"] == "escalation.new"]
        assert len(new_calls) >= 1, (
            f"FR-56: at least one push must use event='escalation.new'; "
            f"got events={[c['event'] for c in pusher.calls]!r}. "
            f"SRS FR-56 contract: 'escalation.new' is the event name "
            f"for the /ws/agent push."
        )

        # Channel MUST be exactly '/ws/agent'. A GREEN implementation
        # that pushes to '/ws/agents' (typo), '/ws/customer' (wrong
        # audience), or a relative path MUST fail here.
        new_call = new_calls[0]
        assert new_call["channel"] == channel, (
            f"FR-56: escalation.new must be pushed to channel="
            f"{channel!r} (the agent workbench WebSocket route per "
            f"SRS FR-57 / FR-56); got {new_call['channel']!r}."
        )

        # The payload MUST be a non-None mapping so test 2 can read
        # the field set. GREEN MUST NOT push the row object directly
        # (dataclass / ORM instance) — the contract is a JSON-friendly
        # dict.
        assert new_call["payload"] is not None, (
            "fr56-ok predicate: escalation.new payload must not be None; "
            "SRS FR-56 mandates a populated payload."
        )
        assert isinstance(new_call["payload"], dict), (
            f"FR-56: escalation.new payload must be a dict so the seven "
            f"SRS FR-56 fields (escalation_id, conversation_id, priority, "
            f"reason, platform, queued_at, preview) are readable; got "
            f"{type(new_call['payload']).__name__}."
        )

        # Defence-in-depth: the payload MUST reference an escalation_id
        # so the agent workbench can correlate the push to a row. We
        # accept either the auto-generated id from create() OR a row
        # matching the pinned sentinel ``esc-001`` (GREEN MAY either
        # upsert a row for ``esc-001`` or use the create() return
        # value — both are valid).
        payload_eid = new_call["payload"].get("escalation_id")
        assert payload_eid is not None, (
            "FR-56: escalation.new payload must carry a non-None "
            "escalation_id so the agent workbench can join the push "
            "to the escalation_queue row."
        )
        assert payload_eid in (result, escalation_id), (
            f"FR-56: escalation_id in the escalation.new payload must "
            f"match the created escalation id; payload "
            f"escalation_id={payload_eid!r}, create() returned "
            f"{result!r}, spec sentinel={escalation_id!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert escalation_id == "esc-001", (
        f"FR-56: escalation_id sentinel must be 'esc-001'; "
        f"got {escalation_id!r}"
    )
    assert channel == "/ws/agent", (
        f"FR-56: channel sentinel must be '/ws/agent'; "
        f"got {channel!r}"
    )


# ---------------------------------------------------------------------------
# 2. The ``escalation.new`` event payload MUST contain every field SRS
#    FR-56 mandates: ``escalation_id, conversation_id, priority, reason,
#    platform, queued_at, preview``. The ``preview`` field MUST itself
#    be a mapping carrying ``user_message`` and ``emotion`` so the agent
#    workbench can render a conversation preview without a second query.
#
# Spec input: expected_fields="escalation_id,conversation_id,priority,
#            reason,platform,queued_at,preview".
# Spec sub-assertion: fr56-ok: result is not None.
# SRS FR-56 acceptance: "payload 欄位完整"; payload spec
#    "escalation_id, conversation_id, priority, reason, platform,
#     queued_at, preview{user_message, emotion}".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr56_payload_has_all_required_fields():
    expected_fields = (
        "escalation_id,conversation_id,priority,reason,platform,"
        "queued_at,preview"
    )
    required = [f.strip() for f in expected_fields.split(",") if f.strip()]
    # Defence-in-depth: pin the exact field set so a regression that
    # adds a duplicate field still passes the membership test below.
    assert required == [
        "escalation_id",
        "conversation_id",
        "priority",
        "reason",
        "platform",
        "queued_at",
        "preview",
    ], (
        "Test setup invariant: the FR-56 required-field set must be "
        "exactly seven fields; got "
        f"{required!r}. SRS FR-56 payload spec."
    )

    # Spec fr56-ok predicate 'result is not None' applies_to case 1.
    if expected_fields.startswith("escalation_id"):
        # GREEN TODO: the WS push payload MUST be a dict whose keys
        # include all seven SRS FR-56 fields:
        #     escalation_id, conversation_id, priority, reason,
        #     platform, queued_at, preview.
        # The ``preview`` value MUST itself be a mapping carrying
        # ``user_message`` and ``emotion`` (SRS FR-56: "preview{user_message,
        # emotion}").
        pusher = _StubPusher()
        manager = EscalationManager(pusher=pusher)

        preview = {
            "user_message": "我真的很生氣，這個問題拖了三個月還沒解決！",
            "emotion": "angry",
        }
        result = manager.create(
            conversation_id="conv-002",
            priority=2,
            reason="emotion_trigger",
            platform="web",
            preview=preview,
        )

        assert result is not None, (
            "fr56-ok predicate: create() must return a non-None "
            "escalation_id so the WS payload can carry it."
        )

        new_calls = [c for c in pusher.calls if c["event"] == "escalation.new"]
        assert len(new_calls) >= 1, (
            f"FR-56: an escalation.new push must fire after create(); "
            f"got events={[c['event'] for c in pusher.calls]!r}."
        )
        payload = new_calls[0]["payload"]
        assert payload is not None, (
            "fr56-ok predicate: escalation.new payload must be non-None."
        )
        assert isinstance(payload, dict), (
            f"FR-56: payload must be a dict to carry the seven "
            f"SRS FR-56 fields; got {type(payload).__name__}."
        )

        # Membership check: every required field MUST be present in
        # the payload. We use ``in`` (not equality) so GREEN MAY add
        # extra fields (e.g. sla_deadline, assigned_agent) without
        # breaking the contract — the spec mandates the minimum set.
        missing = [f for f in required if f not in payload]
        assert not missing, (
            f"FR-56: escalation.new payload is missing required fields "
            f"{missing!r}; expected at least {required!r} per SRS FR-56 "
            f"'payload: escalation_id, conversation_id, priority, "
            f"reason, platform, queued_at, preview'. Got payload "
            f"keys={sorted(payload.keys())!r}."
        )

        # Per-field value sanity checks so a GREEN implementation
        # that pushes a payload with all keys but empty values still
        # fails loudly.
        assert payload.get("escalation_id"), (
            f"FR-56: payload.escalation_id must be a non-empty "
            f"escalation_id; got {payload.get('escalation_id')!r}."
        )
        assert payload.get("conversation_id"), (
            f"FR-56: payload.conversation_id must be a non-empty "
            f"conversation_id; got {payload.get('conversation_id')!r}."
        )
        assert payload.get("priority") is not None, (
            f"FR-56: payload.priority must be present (0/1/2); got "
            f"{payload.get('priority')!r}."
        )
        assert payload.get("platform"), (
            f"FR-56: payload.platform must be a non-empty platform "
            f"identifier (web/telegram/line/...); got "
            f"{payload.get('platform')!r}."
        )
        assert payload.get("queued_at") is not None, (
            f"FR-56: payload.queued_at must be a non-None timestamp "
            f"so the agent workbench can render wait time; got "
            f"{payload.get('queued_at')!r}."
        )

        # ``preview`` MUST be a mapping carrying user_message + emotion
        # per SRS FR-56 "preview{user_message, emotion}". Accept any
        # mapping shape (dict / TypedDict / pydantic); GREEN may use
        # a stronger type as long as the two keys are reachable.
        preview_value = payload.get("preview")
        assert preview_value is not None, (
            "FR-56: payload.preview must be a non-None mapping so the "
            "agent workbench can show a conversation preview."
        )
        assert isinstance(preview_value, dict), (
            f"FR-56: payload.preview must be a dict carrying "
            f"'user_message' and 'emotion' (SRS FR-56 'preview{{user_message, "
            f"emotion}}'); got {type(preview_value).__name__}."
        )
        assert "user_message" in preview_value, (
            f"FR-56: payload.preview must contain 'user_message' per "
            f"SRS FR-56 'preview{{user_message, emotion}}'; got "
            f"keys={sorted(preview_value.keys())!r}."
        )
        assert "emotion" in preview_value, (
            f"FR-56: payload.preview must contain 'emotion' per "
            f"SRS FR-56 'preview{{user_message, emotion}}'; got "
            f"keys={sorted(preview_value.keys())!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert expected_fields.startswith("escalation_id"), (
        f"FR-56: expected_fields sentinel must start with "
        f"'escalation_id'; got {expected_fields!r}"
    )
    assert "preview" in expected_fields, (
        f"FR-56: expected_fields sentinel must include 'preview'; "
        f"got {expected_fields!r}"
    )
