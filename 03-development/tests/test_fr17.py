"""TDD-RED: failing tests for FR-17 — Per-Platform L4 Retraction + fail-secure.

Spec source: 02-architecture/TEST_SPEC.md (FR-17)
SRS source : SRS.md FR-17

Acceptance criteria (from SRS FR-17):
    各平台 L4 事後撤回策略：
      Telegram — deleteMessage（48hr 內）.
      LINE     — 不支援刪除 → 補發道歉訊息.
      Messenger — DELETE（10 分鐘內）.
      WhatsApp — 受限 → 補發更正.
      Web      — WebSocket 直接替換.
      A2A      — 回傳 revoked: true.
    撤回失敗路徑（fail-secure）：
      Telegram 48hr 視窗過期或 API 拒絕 → 補發道歉 + 記錄
      retraction_failed 至 security_logs.
      Messenger 10min 視窗過期 → 同 Telegram 補發道歉.
      所有撤回失敗均 fail-secure（不重試，補發更正，記錄日誌）.

Acceptance Criteria:
    1. 各平台按策略執行撤回或補發.
    2. 撤回失敗時補發道歉並記錄 retraction_failed.
    3. Web 端 WebSocket 替換正確.
    4. A2A 回傳 revoked: true.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Source under test — ``app.core.retraction`` does NOT YET exist. The
# import below triggers a Collection Error (ModuleNotFoundError) on this
# RED step, which is the canonical RED signal for a fresh module.
#
# GREEN must add ``app/core/retraction.py`` with at least:
#
#   - ``RetractionResult`` frozen dataclass:
#         platform: str
#         success: bool
#         method: str                # one of:
#                                   #   "delete" | "apology" | "correction"
#                                   #   | "ws_replace" | "revoked"
#         message_id: Optional[str]
#         apology_sent: bool = False
#         correction_sent: bool = False
#         revoked: bool = False      # True on A2A path so callers can
#                                   # reflect the verdict back through
#                                   # JSON-RPC `revoked: true`.
#
#   - ``retract(platform, message_id, sent_at, *, telegram_client=None,
#               messenger_client=None, line_client=None, whatsapp_client=
#               None, web_ws_pusher=None, a2a_client=None,
#               security_log_writer=None) -> RetractionResult``
#       Per-platform routing (SRS FR-17):
#
#         * ``platform == "telegram"``:
#             - if ``now - sent_at <= 48h`` AND ``telegram_client`` is
#               injected → call ``telegram_client.delete_message(
#               message_id)`` and return ``RetractionResult(platform,
#               success=True, method="delete", message_id=...)`` on
#               success. The Telegram Bot API only allows deletion
#               within 48 hours; older messages are unsendable.
#             - if ``now - sent_at > 48h`` OR the client raises → fall
#               through to fail-secure: ``success=False``,
#               ``method="apology"``, ``apology_sent=True`` AND emit
#               ``security_log_writer(event="retraction_failed", ...)``
#               with platform / message_id / reason="window_expired"
#               (or reason="api_error" when an exception is raised).
#
#         * ``platform == "messenger"``:
#             - if ``now - sent_at <= 10m`` AND ``messenger_client`` is
#               injected → call ``messenger_client.delete_message(
#               message_id)`` and return ``success=True``,
#               ``method="delete"`` on success.
#             - else → fail-secure apology + ``retraction_failed`` log.
#
#         * ``platform == "line"``:
#             - LINE does not support message deletion via the Messaging
#               API; always return ``success=False``,
#               ``method="apology"``, ``apology_sent=True``. No
#               platform call is attempted.
#
#         * ``platform == "whatsapp"``:
#             - WhatsApp Business API does not expose a delete-message
#               endpoint; always return ``success=False``,
#               ``method="correction"``, ``correction_sent=True``.
#
#         * ``platform == "web"``:
#             - Push a replacement frame through ``web_ws_pusher.
#               replace_response(message_id, replacement=...)`` and
#               return ``success=True``, ``method="ws_replace"``.
#
#         * ``platform == "a2a"``:
#             - Call ``a2a_client.mark_revoked(message_id)`` and return
#               ``success=True``, ``method="revoked"``,
#               ``revoked=True`` so the JSON-RPC layer can echo
#               ``revoked: true`` to the caller.
#
#         * Unknown platform → ``ValueError`` (do not silently no-op).
#
#   The retraction window for telegram (48h) and messenger (10m) are
#   module constants GREEN may name ``TELEGRAM_RETRACTION_WINDOW``
#   / ``MESSENGER_RETRACTION_WINDOW``. Tests import the function only.
# ---------------------------------------------------------------------------
from app.core.retraction import retract


# ---------------------------------------------------------------------------
# Helper: a list-appending security_log_writer stub.
# Mirrors the FR-16 / FR-15 pattern — pipeline modules accept an
# injected callable ``(**payload) -> None`` so unit tests can introspect
# what was emitted without standing up a real audit sink.
# ---------------------------------------------------------------------------
class _ListSecurityLogWriter:
    """[FR-17] Test stub capturing ``security_log_writer(**payload)`` calls."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, **payload) -> None:
        self.events.append(payload)


# ---------------------------------------------------------------------------
# Helper: fake platform clients.
#
# Each fake records the methods called and (optionally) raises on
# demand. We intentionally keep the surface minimal — GREEN's real
# implementation will wrap the platform SDKs; the contract surface
# tests pin down here is what GREEN must honor.
# ---------------------------------------------------------------------------
@dataclass
class _FakeTelegramClient:
    delete_calls: list[str] = field(default_factory=list)
    delete_returns: bool = True
    delete_raises: Exception | None = None

    def delete_message(self, message_id: str) -> bool:
        self.delete_calls.append(message_id)
        if self.delete_raises is not None:
            raise self.delete_raises
        return self.delete_returns


@dataclass
class _FakeMessengerClient:
    delete_calls: list[str] = field(default_factory=list)
    delete_returns: bool = True
    delete_raises: Exception | None = None

    def delete_message(self, message_id: str) -> bool:
        self.delete_calls.append(message_id)
        if self.delete_raises is not None:
            raise self.delete_raises
        return self.delete_returns


@dataclass
class _FakeWebWsPusher:
    replace_calls: list[tuple[str, Any]] = field(default_factory=list)
    replace_returns: bool = True

    def replace_response(self, message_id: str, *, replacement: Any) -> bool:
        self.replace_calls.append((message_id, replacement))
        return self.replace_returns


@dataclass
class _FakeA2AClient:
    revoke_calls: list[str] = field(default_factory=list)
    revoke_returns: bool = True

    def mark_revoked(self, message_id: str) -> bool:
        self.revoke_calls.append(message_id)
        return self.revoke_returns


# ---------------------------------------------------------------------------
# 1. Telegram retraction within 48hr → deleteMessage is invoked and the
#    result carries method="delete" / success=True.
#
# Spec input: platform="telegram"; hours_since_send="24".
#   SRS FR-17: "Telegram deleteMessage（48hr 內）".
#
# A retraction that falls through to "apology" on a within-window send
# would let an injected response stay visible to the user — a direct
# violation of the FR-16 retrospective-block contract.
# ---------------------------------------------------------------------------
def test_fr17_telegram_retraction_within_48hr():
    platform = "telegram"
    hours_since_send = "24"
    message_id = "tg-msg-001"

    sent_at = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    # Freeze "now" 24h after sent_at so the test is deterministic
    # without depending on real wall-clock — GREEN's retract() reads
    # ``datetime.now(timezone.utc)`` internally and the 24h/49h
    # boundaries matter; we patch datetime via a small monkeypatch
    # helper below.
    fixed_now = sent_at + timedelta(hours=24)

    tg_client = _FakeTelegramClient(delete_returns=True)

    # GREEN TODO: ``retract`` MUST accept a ``telegram_client`` kwarg
    # whose object exposes ``.delete_message(message_id) -> bool``.
    # Within the 48-hour window the function MUST call this hook and
    # return RetractionResult(success=True, method="delete",
    # message_id=message_id, apology_sent=False).
    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        telegram_client=tg_client,
    )

    if platform == "telegram" and hours_since_send == "24":
        # Spec fr17-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr17-ok predicate: retract() must return a non-None "
            "RetractionResult on the within-window Telegram path"
        )

    # Telegram deleteMessage MUST have been called exactly once with
    # the message_id we are trying to retract.
    assert tg_client.delete_calls == [message_id], (
        f"Telegram within-window retraction MUST invoke "
        f"telegram_client.delete_message({message_id!r}) exactly "
        f"once (SRS FR-17: 'Telegram deleteMessage（48hr 內）'); "
        f"observed calls={tg_client.delete_calls!r}"
    )

    # The result MUST report the delete-method outcome.
    assert getattr(result, "success", None) is True, (
        f"within-window Telegram delete must succeed; got "
        f"success={getattr(result, 'success', None)!r}"
    )
    assert getattr(result, "method", None) == "delete", (
        f"within-window Telegram retraction MUST use method='delete'; "
        f"got method={getattr(result, 'method', None)!r}"
    )


# ---------------------------------------------------------------------------
# Tiny helper that patches ``datetime.now`` inside ``retraction`` for
# the duration of a single call so the test does not depend on
# wall-clock drift across the 48h boundary.
# ---------------------------------------------------------------------------
def _call_retract_with_frozen_now(
    *,
    platform: str,
    message_id: str,
    sent_at: datetime,
    fixed_now: datetime,
    telegram_client: _FakeTelegramClient | None = None,
    messenger_client: _FakeMessengerClient | None = None,
    line_client: Any = None,
    whatsapp_client: Any = None,
    web_ws_pusher: _FakeWebWsPusher | None = None,
    a2a_client: _FakeA2AClient | None = None,
    security_log_writer: _ListSecurityLogWriter | None = None,
):
    """Invoke ``retract`` with ``datetime.now`` frozen to ``fixed_now``."""
    from datetime import datetime as _dt

    import app.core.retraction as retraction_mod


    class _FrozenDateTime(_dt):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    retraction_mod.datetime = _FrozenDateTime  # type: ignore[attr-defined]
    try:
        return retract(
            platform=platform,
            message_id=message_id,
            sent_at=sent_at,
            telegram_client=telegram_client,
            messenger_client=messenger_client,
            line_client=line_client,
            whatsapp_client=whatsapp_client,
            web_ws_pusher=web_ws_pusher,
            a2a_client=a2a_client,
            security_log_writer=security_log_writer,
        )
    finally:
        retraction_mod.datetime = _dt  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 2. Telegram retraction past the 48-hour window → apology sent +
#    retraction_failed logged (security_logs).
#
# Spec input: platform="telegram"; hours_since_send="49".
#   SRS FR-17: "Telegram 48hr 視窗過期 → 補發道歉訊息 + 記錄
#                retraction_failed 至 security_logs".
#
# Telegram's Bot API refuses deleteMessage for messages older than 48h
# with HTTP 400 — a real client wrapper surfaces that as an exception.
# GREEN MUST treat both branches (window-expired, client-raised) as a
# fail-secure apology + audit log so an injected response doesn't stay
# visible just because the platform API said no.
# ---------------------------------------------------------------------------
def test_fr17_telegram_window_expired_sends_apology():
    platform = "telegram"
    hours_since_send = "49"
    message_id = "tg-msg-002"

    sent_at = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(hours=49)

    tg_client = _FakeTelegramClient()  # not expected to be called
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        telegram_client=tg_client,
        security_log_writer=writer,
    )

    if platform == "telegram" and hours_since_send == "49":
        # Spec fr17-ok predicate applies_to case 1 only — case 2 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # Telegram's deleteMessage MUST NOT be attempted past the 48h
    # window — the API would reject it anyway and calling it would
    # waste an HTTP round-trip.
    assert tg_client.delete_calls == [], (
        f"Telegram past-window retraction MUST NOT call "
        f"delete_message (window expired; SRS FR-17: '48hr 視窗過期 "
        f"→ 補發道歉'); observed calls={tg_client.delete_calls!r}"
    )

    # Fail-secure path: method=apology, apology_sent=True, success=False.
    assert getattr(result, "method", None) == "apology", (
        f"past-window Telegram retraction MUST fall back to "
        f"method='apology'; got method={getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "apology_sent", None) is True, (
        f"past-window Telegram retraction MUST mark apology_sent=True; "
        f"got apology_sent={getattr(result, 'apology_sent', None)!r}"
    )
    assert getattr(result, "success", None) is False, (
        f"past-window retraction is a fail-secure apology, not a "
        f"successful delete; got success="
        f"{getattr(result, 'success', None)!r}"
    )

    # The audit trail MUST record the retraction_failed event so the
    # SOC2 trail reflects the failure.
    matching = [
        ev for ev in writer.events
        if ev.get("event") == "retraction_failed"
    ]
    assert matching, (
        f"past-window Telegram retraction MUST emit a "
        f"'retraction_failed' event to security_logs (SRS FR-17: "
        f"'記錄 retraction_failed 至 security_logs'); observed "
        f"events={writer.events!r}"
    )
    payload = matching[0]
    assert payload.get("platform") == "telegram", (
        f"retraction_failed audit payload MUST include platform="
        f"'telegram'; got payload={payload!r}"
    )


# ---------------------------------------------------------------------------
# 3. Messenger retraction within 10 minutes → DELETE invoked, success=True.
#
# Spec input: platform="messenger"; minutes_since_send="8".
#   SRS FR-17: "Messenger DELETE（10 分鐘內）".
#
# The Facebook Messenger Send API allows the page to delete a message
# within 10 minutes of sending; outside the window the call returns
# an error. A within-window retraction that does not invoke the
# platform DELETE leaves an injected response visible to the user.
# ---------------------------------------------------------------------------
def test_fr17_messenger_retraction_within_10min():
    platform = "messenger"
    minutes_since_send = "8"
    message_id = "msg-mid-001"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(minutes=8)

    msgr_client = _FakeMessengerClient(delete_returns=True)
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        messenger_client=msgr_client,
        security_log_writer=writer,
    )

    if platform == "messenger" and minutes_since_send == "8":
        # Spec fr17-ok predicate applies_to case 1 only — case 3 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # Messenger DELETE MUST have been called exactly once with our id.
    assert msgr_client.delete_calls == [message_id], (
        f"Messenger within-window retraction MUST invoke "
        f"messenger_client.delete_message({message_id!r}) exactly "
        f"once (SRS FR-17: 'Messenger DELETE（10 分鐘內）'); observed "
        f"calls={msgr_client.delete_calls!r}"
    )

    # The result MUST report success + method="delete".
    assert getattr(result, "success", None) is True, (
        f"within-window Messenger delete must succeed; "
        f"got success={getattr(result, 'success', None)!r}"
    )
    assert getattr(result, "method", None) == "delete", (
        f"within-window Messenger retraction MUST use method='delete'; "
        f"got method={getattr(result, 'method', None)!r}"
    )

    # No retraction_failed event on the happy path.
    assert writer.events == [], (
        f"within-window Messenger retraction MUST NOT log "
        f"retraction_failed (the operation succeeded); "
        f"observed events={writer.events!r}"
    )


# ---------------------------------------------------------------------------
# 4. Messenger retraction past the 10-minute window → apology + log.
#
# Spec input: platform="messenger"; minutes_since_send="12".
#   SRS FR-17: "Messenger 10min 視窗過期 → 同 Telegram 補發道歉".
#
# Past the 10-minute window the Messenger Send API refuses DELETE —
# GREEN must NOT call the platform client (saves a guaranteed-failure
# HTTP round-trip) and MUST emit an apology + retraction_failed event.
# ---------------------------------------------------------------------------
def test_fr17_messenger_window_expired_sends_apology():
    platform = "messenger"
    minutes_since_send = "12"
    message_id = "msg-mid-002"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(minutes=12)

    msgr_client = _FakeMessengerClient()
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        messenger_client=msgr_client,
        security_log_writer=writer,
    )

    if platform == "messenger" and minutes_since_send == "12":
        # Spec fr17-ok predicate applies_to case 1 only — case 4 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # Messenger DELETE MUST NOT be attempted past the 10-min window.
    assert msgr_client.delete_calls == [], (
        f"Messenger past-window retraction MUST NOT call "
        f"delete_message (window expired; SRS FR-17: '10min 視窗過期 "
        f"→ 同 Telegram 補發道歉'); observed calls="
        f"{msgr_client.delete_calls!r}"
    )

    # Fail-secure path: method=apology, apology_sent=True.
    assert getattr(result, "method", None) == "apology", (
        f"past-window Messenger retraction MUST fall back to "
        f"method='apology'; got method={getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "apology_sent", None) is True, (
        f"past-window Messenger retraction MUST mark apology_sent="
        f"True; got apology_sent={getattr(result, 'apology_sent', None)!r}"
    )
    assert getattr(result, "success", None) is False, (
        f"past-window retraction is a fail-secure apology, not a "
        f"successful delete; got success="
        f"{getattr(result, 'success', None)!r}"
    )

    # Audit trail MUST record the failure.
    matching = [
        ev for ev in writer.events
        if ev.get("event") == "retraction_failed"
    ]
    assert matching, (
        f"past-window Messenger retraction MUST emit a "
        f"'retraction_failed' event (SRS FR-17); observed events="
        f"{writer.events!r}"
    )
    assert matching[0].get("platform") == "messenger", (
        f"retraction_failed audit payload MUST include platform="
        f"'messenger'; got payload={matching[0]!r}"
    )


# ---------------------------------------------------------------------------
# 5. LINE does not expose a delete-message endpoint → apology, no
#    platform call, no failure log (this is the platform's default,
#    not a fault of our pipeline).
#
# Spec input: platform="line".
#   SRS FR-17: "LINE 不支援刪除 → 補發道歉訊息".
#
# A LINE handler that raises on the missing delete endpoint would
# pollute security_logs with retraction_failed events on EVERY LINE
# send — GREEN must distinguish 'platform doesn't support this' from
# 'platform call failed'.
# ---------------------------------------------------------------------------
def test_fr17_line_no_delete_sends_apology():
    platform = "line"
    message_id = "line-msg-001"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(minutes=2)

    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        line_client=None,  # GREEN MUST NOT require a LINE client
        security_log_writer=writer,
    )

    if platform == "line":
        # Spec fr17-ok predicate applies_to case 1 only — case 5 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # LINE MUST always route to apology — no platform delete API exists.
    assert getattr(result, "method", None) == "apology", (
        f"LINE retraction MUST use method='apology' (SRS FR-17: 'LINE "
        f"不支援刪除 → 補發道歉訊息'); got method="
        f"{getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "apology_sent", None) is True, (
        f"LINE retraction MUST set apology_sent=True; got apology_sent="
        f"{getattr(result, 'apology_sent', None)!r}"
    )

    # Platform-default behaviour (no DELETE available) MUST NOT be
    # logged as a failure — that would produce a permanent alert
    # storm for every LINE interaction.
    assert writer.events == [], (
        f"LINE platform-default apology MUST NOT log retraction_failed "
        f"(this is the platform contract, not a fault); observed "
        f"events={writer.events!r}"
    )


# ---------------------------------------------------------------------------
# 6. WhatsApp does not support message deletion via the Business API →
#    correction message is sent.
#
# Spec input: platform="whatsapp".
#   SRS FR-17: "WhatsApp 受限 → 補發更正".
#
# A WhatsApp handler that calls ``messages.delete`` would fail at the
# API layer; GREEN must short-circuit to a correction message instead.
# ---------------------------------------------------------------------------
def test_fr17_whatsapp_sends_correction():
    platform = "whatsapp"
    message_id = "wa-msg-001"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(minutes=5)

    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        whatsapp_client=None,  # GREEN MUST NOT require a WA client
        security_log_writer=writer,
    )

    if platform == "whatsapp":
        # Spec fr17-ok predicate applies_to case 1 only — case 6 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # WhatsApp MUST always route to a correction message.
    assert getattr(result, "method", None) == "correction", (
        f"WhatsApp retraction MUST use method='correction' (SRS FR-17: "
        f"'WhatsApp 受限 → 補發更正'); got method="
        f"{getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "correction_sent", None) is True, (
        f"WhatsApp retraction MUST set correction_sent=True; got "
        f"correction_sent={getattr(result, 'correction_sent', None)!r}"
    )
    # A correction is the platform-default outcome, not a fault.
    assert writer.events == [], (
        f"WhatsApp platform-default correction MUST NOT log "
        f"retraction_failed; observed events={writer.events!r}"
    )


# ---------------------------------------------------------------------------
# 7. Web platform → WebSocket push replaces the response frame.
#
# Spec input: platform="web"; channel="websocket".
#   SRS FR-17: "Web WebSocket 直接替換".
#
# The web client has an open WS connection; the retraction is an
# in-place replacement of the outgoing frame (the user sees the
# correction live). A web retraction that posts a brand-new message
# instead of replacing the original frame would leave the poisoned
# frame visible alongside the correction.
# ---------------------------------------------------------------------------
def test_fr17_web_ws_replace_response():
    platform = "web"
    channel = "websocket"
    message_id = "ws-frame-001"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(seconds=20)

    ws_pusher = _FakeWebWsPusher(replace_returns=True)
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        web_ws_pusher=ws_pusher,
        security_log_writer=writer,
    )

    if platform == "web" and channel == "websocket":
        # Spec fr17-ok predicate applies_to case 1 only — case 7 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # The web_ws_pusher MUST have received a replace_response call
    # with our message_id so the original frame can be overwritten.
    assert ws_pusher.replace_calls, (
        f"Web WS retraction MUST invoke web_ws_pusher.replace_response "
        f"({message_id!r}, ...) (SRS FR-17: 'Web WebSocket 直接替換'); "
        f"observed calls={ws_pusher.replace_calls!r}"
    )
    called_message_id, called_replacement = ws_pusher.replace_calls[0]
    assert called_message_id == message_id, (
        f"replace_response MUST be called for {message_id!r}; got "
        f"{called_message_id!r}"
    )
    # A non-empty replacement payload is required so the WS frame is
    # actually overwritten (an empty replacement would silently
    # preserve the original frame).
    assert called_replacement is not None and called_replacement != "", (
        f"replace_response MUST include a non-empty replacement payload "
        f"(otherwise the original frame stays visible); got "
        f"replacement={called_replacement!r}"
    )

    # The result MUST report method="ws_replace".
    assert getattr(result, "method", None) == "ws_replace", (
        f"Web retraction MUST use method='ws_replace'; got method="
        f"{getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "success", None) is True, (
        f"Web WS replace must succeed; got success="
        f"{getattr(result, 'success', None)!r}"
    )


# ---------------------------------------------------------------------------
# 8. A2A platform → call mark_revoked and surface revoked: true.
#
# Spec input: platform="a2a"; expected_revoked="true".
#   SRS FR-17: "A2A 回傳 revoked: true".
#
# The JSON-RPC layer must be able to read ``RetractionResult.revoked``
# and reflect it back to the caller as ``{"revoked": true}``. A
# retraction that returns success=True but revoked=False would let an
# injected agent response remain valid on the A2A wire.
# ---------------------------------------------------------------------------
def test_fr17_a2a_revoked_true():
    platform = "a2a"
    expected_revoked = "true"
    message_id = "a2a-rpc-001"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(seconds=30)

    a2a_client = _FakeA2AClient(revoke_returns=True)
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        a2a_client=a2a_client,
        security_log_writer=writer,
    )

    if platform == "a2a" and expected_revoked == "true":
        # Spec fr17-ok predicate applies_to case 1 only — case 8 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # A2A client MUST have been asked to mark the message revoked.
    assert a2a_client.revoke_calls == [message_id], (
        f"A2A retraction MUST invoke a2a_client.mark_revoked("
        f"{message_id!r}) exactly once (SRS FR-17: 'A2A 回傳 "
        f"revoked: true'); observed calls={a2a_client.revoke_calls!r}"
    )

    # The result MUST expose method="revoked" so the JSON-RPC layer
    # can branch on it, AND revoked=True so callers can echo
    # ``revoked: true`` in the response payload.
    assert getattr(result, "method", None) == "revoked", (
        f"A2A retraction MUST use method='revoked'; got method="
        f"{getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "revoked", None) is True, (
        f"A2A retraction MUST set revoked=True so JSON-RPC responses "
        f"can carry 'revoked: true' (SRS FR-17: 'A2A 回傳 revoked: "
        f"true'); got revoked={getattr(result, 'revoked', None)!r}"
    )
    assert getattr(result, "success", None) is True, (
        f"A2A mark_revoked success must surface on RetractionResult; "
        f"got success={getattr(result, 'success', None)!r}"
    )


# ---------------------------------------------------------------------------
# 9. Retraction failure (e.g. telegram client raised an exception)
#    MUST be logged as retraction_failed and MUST emit an apology.
#
# Spec input: retraction_status="failed"; expected_log_event=
#             "retraction_failed".
#   SRS FR-17: "Telegram 48hr 視窗過期或 API 拒絕 → 補發道歉訊息 +
#                記錄 retraction_failed 至 security_logs".
#
# This test exercises the API-rejection branch of the Telegram path
# (client raises within the 48h window). GREEN MUST treat a raised
# exception the same as a window-expired send — both fall to the
# fail-secure apology + audit log. A retraction that lets the
# exception propagate would crash the platform adapter and surface a
# 500 to the user, which is worse than letting the audit log carry
# the failure.
# ---------------------------------------------------------------------------
def test_fr17_retraction_failed_logged():
    retraction_status = "failed"
    expected_log_event = "retraction_failed"
    platform = "telegram"
    message_id = "tg-msg-003"

    sent_at = datetime(2026, 6, 19, 9, 0, 0, tzinfo=timezone.utc)
    fixed_now = sent_at + timedelta(minutes=30)  # within 48h window

    # The Telegram client rejects the call (HTTP 400 surfaced as an
    # exception). GREEN must catch and route to fail-secure.
    tg_client = _FakeTelegramClient(
        delete_raises=RuntimeError("Telegram API 400: message too old")
    )
    writer = _ListSecurityLogWriter()

    result = _call_retract_with_frozen_now(
        platform=platform,
        message_id=message_id,
        sent_at=sent_at,
        fixed_now=fixed_now,
        telegram_client=tg_client,
        security_log_writer=writer,
    )

    if retraction_status == "failed" and expected_log_event == "retraction_failed":
        # Spec fr17-ok predicate applies_to case 1 only — case 9 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # The Telegram client MUST have been called — the fail-secure
    # branch only fires AFTER an attempted delete.
    assert tg_client.delete_calls == [message_id], (
        f"Telegram retraction MUST attempt the platform delete even "
        f"when we expect it to fail (we want the exception path "
        f"exercised); observed calls={tg_client.delete_calls!r}"
    )

    # Fail-secure: method=apology + apology_sent=True.
    assert getattr(result, "method", None) == "apology", (
        f"Telegram client-rejection path MUST fall back to "
        f"method='apology' (SRS FR-17: 'API 拒絕 → 補發道歉訊息'); "
        f"got method={getattr(result, 'method', None)!r}"
    )
    assert getattr(result, "apology_sent", None) is True, (
        f"client-rejection fail-secure MUST set apology_sent=True; "
        f"got apology_sent={getattr(result, 'apology_sent', None)!r}"
    )

    # Audit-trail invariant: the failure MUST be visible in
    # security_logs as event="retraction_failed" so SOC2 picks it up.
    matching = [
        ev for ev in writer.events
        if ev.get("event") == expected_log_event
    ]
    assert matching, (
        f"Telegram client-rejection MUST emit a '{expected_log_event}' "
        f"event to security_logs (SRS FR-17: 'API 拒絕 → 記錄 "
        f"retraction_failed 至 security_logs'); observed events="
        f"{writer.events!r}"
    )
    payload = matching[0]
    assert payload.get("platform") == "telegram", (
        f"retraction_failed audit payload MUST include platform="
        f"'telegram'; got payload={payload!r}"
    )
    assert payload.get("message_id") == message_id, (
        f"retraction_failed audit payload MUST include message_id="
        f"{message_id!r}; got payload={payload!r}"
    )
