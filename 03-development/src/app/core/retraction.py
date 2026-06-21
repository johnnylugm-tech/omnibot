"""[FR-17] Per-platform L4 message retraction with fail-secure fallback.

This module implements the FR-17 acceptance criteria from the SRS:
"各平台 L4 事後撤回策略". When the L4 audit classifier flags an
outgoing response as injected (FR-16 retrospective block), the
pipeline MUST invoke ``retract(platform, message_id, sent_at, ...)``
to either delete the offending message on the platform or, if the
platform does not support deletion (or the deletion window has
expired), fall through to a fail-secure apology + audit log entry.

The fail-secure invariant is critical: an injected response that
stays visible to the user is the worst-case L4 outcome, so any
deletion failure (window expired, API rejection, missing client)
MUST be replaced with an apology / correction message AND emit a
``retraction_failed`` event to ``security_log_writer`` so the SOC2
trail records the failure.

Citations:
    - SRS.md FR-17 — "Telegram deleteMessage (48hr 內); LINE 不支援
      刪除 → 補發道歉訊息; Messenger DELETE (10 分鐘內); WhatsApp
      受限 → 補發更正; Web WebSocket 直接替換; A2A 回傳 revoked: true"
    - SRS.md FR-17 fail-secure clause — "Telegram 48hr 視窗過期或
      API 拒絕 → 補發道歉 + 記錄 retraction_failed 至 security_logs.
      Messenger 10min 視窗過期 → 同 Telegram 補發道歉. 所有撤回失敗
      均 fail-secure (不重試, 補發更正, 記錄日誌)"
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

# Platform-specific retraction windows (SRS FR-17).
TELEGRAM_RETRACTION_WINDOW: timedelta = timedelta(hours=48)
MESSENGER_RETRACTION_WINDOW: timedelta = timedelta(minutes=10)

# Replacement frame pushed to the open WebSocket on a web retraction
# (SRS FR-17: "Web WebSocket 直接替換"). Kept as a module constant so
# the wording is reviewable in one place.
WS_REPLACEMENT_TEXT: str = "[retracted] 此回應已由系統撤回並更正。"


@dataclass(frozen=True)
class RetractionResult:
    """[FR-17] Outcome of a single platform retraction attempt.

    The frozen dataclass shape is the contract the JSON-RPC / web
    layers read from when deciding how to surface the verdict to the
    caller (``method`` branches the response shape; ``revoked``
    echoes ``revoked: true`` over A2A).
    """

    platform: str
    success: bool
    method: str  # "delete" | "apology" | "correction" | "ws_replace" | "revoked"
    message_id: str | None
    apology_sent: bool = False
    correction_sent: bool = False
    revoked: bool = False


def _apology_result(platform: str, message_id: str) -> RetractionResult:
    """[FR-17] Build the fail-secure ``method="apology"`` outcome."""
    return RetractionResult(
        platform=platform,
        success=False,
        method="apology",
        message_id=message_id,
        apology_sent=True,
    )


def _log_retraction_failed(
    security_log_writer: Callable[..., None] | None,
    *,
    platform: str,
    message_id: str,
    reason: str,
) -> None:
    """[FR-17] Emit ``event="retraction_failed"`` to the security log sink.

    No-op when ``security_log_writer`` is None so the function remains
    usable in tests / dry-runs that do not wire a real audit sink.
    """
    if security_log_writer is None:
        return
    security_log_writer(
        event="retraction_failed",
        platform=platform,
        message_id=message_id,
        reason=reason,
    )


def _attempt_windowed_delete(
    *,
    platform: str,
    client: Any,
    message_id: str,
    sent_at: datetime,
    window: timedelta,
    security_log_writer: Callable[..., None] | None,
) -> RetractionResult:
    """[FR-17] Run the shared "delete inside window, else fail-secure" flow.

    Both the Telegram (48h) and Messenger (10min) paths share the same
    shape: pre-check the window so we never make a guaranteed-failure
    HTTP round-trip, attempt the platform delete, and on either a
    window-expired send or a raised API exception fall through to the
    fail-secure apology + audit-log event.
    """
    now = datetime.now(timezone.utc)
    if client is None or (now - sent_at) > window:
        reason = "no_client" if client is None else "window_expired"
        _log_retraction_failed(
            security_log_writer,
            platform=platform,
            message_id=message_id,
            reason=reason,
        )
        return _apology_result(platform, message_id)

    try:
        client.delete_message(message_id)
    except Exception:
        _log_retraction_failed(
            security_log_writer,
            platform=platform,
            message_id=message_id,
            reason="api_error",
        )
        return _apology_result(platform, message_id)

    return RetractionResult(
        platform=platform,
        success=True,
        method="delete",
        message_id=message_id,
    )


def _retract_telegram(
    message_id: str,
    sent_at: datetime,
    telegram_client: Any,
    security_log_writer: Callable[..., None] | None,
) -> RetractionResult:
    """[FR-17] Telegram path: deleteMessage within 48h, else fail-secure.

    The Telegram Bot API rejects ``deleteMessage`` for messages older
    than 48 hours with HTTP 400; we treat both branches (window
    expired, client raised) as a fail-secure apology + audit log.
    """
    return _attempt_windowed_delete(
        platform="telegram",
        client=telegram_client,
        message_id=message_id,
        sent_at=sent_at,
        window=TELEGRAM_RETRACTION_WINDOW,
        security_log_writer=security_log_writer,
    )


def _retract_messenger(
    message_id: str,
    sent_at: datetime,
    messenger_client: Any,
    security_log_writer: Callable[..., None] | None,
) -> RetractionResult:
    """[FR-17] Messenger path: DELETE within 10min, else fail-secure.

    The Facebook Messenger Send API allows the page to delete a
    message within 10 minutes of sending; outside the window the
    call returns an error. We pre-check the window so we never make
    a guaranteed-failure HTTP round-trip.
    """
    return _attempt_windowed_delete(
        platform="messenger",
        client=messenger_client,
        message_id=message_id,
        sent_at=sent_at,
        window=MESSENGER_RETRACTION_WINDOW,
        security_log_writer=security_log_writer,
    )


def _retract_line(message_id: str) -> RetractionResult:
    """[FR-17] LINE path: platform-default apology, no failure log.

    LINE Messaging API does not expose a delete-message endpoint;
    this is the platform contract, not a fault of our pipeline, so
    we do NOT emit a ``retraction_failed`` audit event.
    """
    return _apology_result("line", message_id)


def _retract_whatsapp(message_id: str) -> RetractionResult:
    """[FR-17] WhatsApp path: platform-default correction, no failure log.

    The WhatsApp Business API does not expose a delete-message
    endpoint; the platform-default recovery is a correction message.
    """
    return RetractionResult(
        platform="whatsapp",
        success=False,
        method="correction",
        message_id=message_id,
        correction_sent=True,
    )


def _retract_web(
    message_id: str,
    web_ws_pusher: Any,
) -> RetractionResult:
    """[FR-17] Web path: push replacement frame over the open WebSocket.

    The web client holds an open WS connection; the retraction is
    an in-place replacement of the outgoing frame so the user sees
    the correction live rather than alongside the original.
    """
    web_ws_pusher.replace_response(
        message_id,
        replacement=WS_REPLACEMENT_TEXT,
    )
    return RetractionResult(
        platform="web",
        success=True,
        method="ws_replace",
        message_id=message_id,
    )


def _retract_a2a(
    message_id: str,
    a2a_client: Any,
) -> RetractionResult:
    """[FR-17] A2A path: mark the message revoked so JSON-RPC echoes it.

    ``revoked=True`` lets the JSON-RPC layer reflect the verdict back
    to the caller as ``{"revoked": true}`` — an A2A retraction that
    returns ``success=True`` but ``revoked=False`` would let an
    injected agent response remain valid on the wire.
    """
    a2a_client.mark_revoked(message_id)
    return RetractionResult(
        platform="a2a",
        success=True,
        method="revoked",
        message_id=message_id,
        revoked=True,
    )


def retract(
    platform: str,
    message_id: str,
    sent_at: datetime,
    *,
    telegram_client: Any = None,
    messenger_client: Any = None,
    line_client: Any = None,
    whatsapp_client: Any = None,
    web_ws_pusher: Any = None,
    a2a_client: Any = None,
    security_log_writer: Callable[..., None] | None = None,
) -> RetractionResult:
    """[FR-17] Route a retraction to the correct platform handler.

    Each platform-specific kwarg is the client / pusher the handler
    needs; ``security_log_writer`` is the ``(**payload) -> None``
    audit sink used by the fail-secure path to emit
    ``retraction_failed`` events. Unknown platforms raise
    ``ValueError`` rather than silently no-op so a wiring error is
    surfaced loudly.
    """
    if platform == "telegram":
        return _retract_telegram(
            message_id,
            sent_at,
            telegram_client,
            security_log_writer,
        )
    if platform == "messenger":
        return _retract_messenger(
            message_id,
            sent_at,
            messenger_client,
            security_log_writer,
        )
    if platform == "line":
        return _retract_line(message_id)
    if platform == "whatsapp":
        return _retract_whatsapp(message_id)
    if platform == "web":
        return _retract_web(message_id, web_ws_pusher)
    if platform == "a2a":
        return _retract_a2a(message_id, a2a_client)

    raise ValueError(f"Unknown platform: {platform!r}")
