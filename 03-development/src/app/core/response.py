from __future__ import annotations

# --- Merged from response_generator.py ---
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar

"""[FR-50] ResponseGenerator — pre-canned reply templates + render helper.
[FR-51] ResponseGenerator._apply_emotion_tone — emotion-tone prefix modulation.
[FR-52] ResponseGenerator._apply_ab_variant — A/B variant suffix injection.
[FR-53] ResponseGenerator.format_for_platform — per-platform character-limit adapter.

Spec source: 02-architecture/TEST_SPEC.md (FR-50, FR-51, FR-52, FR-53)
SRS source : SRS.md FR-50, FR-51, FR-52, FR-53 (Module 9: Response Generator)

FR-50 -- Template System：
    ``ResponseTemplate（name, platform, emotion_tone, template）`` 預設
    模板三個：``rule_default``（``{answer}``）、``rag_default``（附
    「📌 此回覆根據相關知識庫內容生成」）、``escalate``（附案件編號）。
    三個預設模板存在且格式正確；variable interpolation 正確。

FR-51 -- Emotion Tone Modulation：
    - ``emotion == "negative"`` AND ``intensity > 0.7`` AND
      ``repeat_count == 0`` → 前綴「非常抱歉造成您的困擾。」
    - ``emotion == "positive"`` → 前綴「太好了！」 (regardless of
      intensity / repeat_count)
    - ``repeat_count > 0`` AND ``emotion == "negative"`` → 抑制重複道歉
    - ``emotion == "neutral"`` (or any other unrecognised label) →
      pass-through, ``base_text`` returned unchanged.

FR-52 -- A/B Variant Injection：
    - ``variant == "a"`` → append 「還有其他問題嗎？」 to base_text.
    - ``variant == "b"`` → append 「需要進一步說明嗎？」 to base_text.
    - ``variant == "control"`` (or any unrecognised label) → return
      ``base_text`` unchanged with no suffix injected.

Public surface pinned by this module:

    - ``ResponseTemplate`` — frozen dataclass with the four fields named
      in SRS FR-50 (``name``, ``platform``, ``emotion_tone``, ``template``).
    - ``ResponseGenerator.DEFAULT_TEMPLATES`` — class-level dict keyed
      by template name. The three required keys are ``"rule_default"``,
      ``"rag_default"`` and ``"escalate"``.
    - ``ResponseGenerator.render(template, **vars)`` — substitutes
      ``{var}`` placeholders via ``str.format(**vars)`` and returns the
      rendered string.
    - ``ResponseGenerator._apply_emotion_tone(emotion, intensity,
      repeat_count, base_text="") -> str`` — prepends the SRS-mandated
      tone prefix per FR-51 above and returns ``base_text`` (possibly
      with prefix) unchanged for the neutral pass-through.
    - ``ResponseGenerator._apply_ab_variant(variant, base_text) -> str``
      — appends the SRS-mandated CTA suffix per FR-52 above and
      returns ``base_text`` unchanged for the control pass-through.
    - ``ResponseGenerator.format_for_platform(platform, content) -> str``
      — per-platform character-limit adapter per FR-53 below. Telegram
      (4096), LINE (5000), Messenger (2000), WhatsApp (4096) truncate
      to their documented limit; Web and Agent are pass-through (Web
      preserves Markdown byte-for-byte, Agent wraps the reply in a
      pure-JSON envelope with a ``content`` field).

Citations:
    - SRS.md FR-50 -- "Template System：ResponseTemplate（name, platform, emotion_tone, template）" (line 113).
    - SRS.md FR-50 -- "預設模板：rule_default（{answer}）、rag_default（附「📌 此回覆根據相關知識庫內容生成」）、escalate（附案件編號）" (line 113).
    - SRS.md FR-50 -- acceptance "三個預設模板存在且格式正確；variable interpolation 正確" (line 113).
    - SRS.md FR-50 -- implementation_functions: "ResponseGenerator.DEFAULT_TEMPLATES" (line 113).
    - SRS.md FR-51 -- "negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」" (line 114).
    - SRS.md FR-51 -- "positive → 前綴「太好了！」" (line 114).
    - SRS.md FR-51 -- "repeat_count > 0 且 negative → 抑制重複道歉" (line 114).
    - SRS.md FR-51 -- implementation_functions: "ResponseGenerator._apply_emotion_tone" (line 114).
    - SRS.md FR-52 -- "variant_a → 結尾 \"還有其他問題嗎？\"" (line 115).
    - SRS.md FR-52 -- "variant_b → 結尾 \"需要進一步說明嗎？\"" (line 115).
    - SRS.md FR-52 -- "control → 不注入" (line 115).
    - SRS.md FR-52 -- implementation_functions: "ResponseGenerator._apply_ab_variant()" (line 115).
"""




@dataclass(frozen=True)
class ResponseTemplate:
    """A named, platform-aware, emotion-tone-aware reply template.

    SRS FR-50: ``ResponseTemplate（name, platform, emotion_tone, template）``.
    Frozen so a template loaded from ``DEFAULT_TEMPLATES`` cannot be
    mutated underfoot and silently change every subsequent render.
    """

    name: str
    platform: str
    emotion_tone: str
    template: str


class _SafeFormatDict(dict):
    """``dict`` subclass for ``str.format_map`` that tolerates missing keys.

    ``str.format_map`` looks up each ``{key}`` placeholder in the
    supplied mapping. By default a missing key raises ``KeyError`` and
    aborts the entire render, discarding the partial output. By
    returning ``"{key}"`` from ``__missing__`` we make the formatter
    substitute the original placeholder text back into the output for
    any key the caller did not provide, while keys that *are* in the
    mapping are interpolated normally.

    Implementation note: ``__missing__`` is invoked only for the
    *value* lookup of the field name; the surrounding ``{...}`` (or
    ``{key:spec}``, ``{key!conv}``) is reconstructed by the formatter
    from the returned literal, so the original placeholder text round-
    trips intact into the rendered string.
    """

    def __missing__(self, key: str) -> str:  # pragma: no cover
        return "{" + key + "}"  # pragma: no cover


class ResponseGenerator:
    """[FR-50] Holds the pre-canned reply templates and a render helper.

    The class is a thin namespace — FR-50 only requires the template
    registry and a ``str.format``-compatible render path; richer
    behaviour (emotion-tone modulation, A/B variant injection, etc.)
    is layered on by FR-51 / FR-52 without changing this surface.
    """

    DEFAULT_TEMPLATES: ClassVar[dict[str, ResponseTemplate]] = {
        "rule_default": ResponseTemplate(
            name="rule_default",
            platform="*",
            emotion_tone="neutral",
            template="{answer}",
        ),
        "rag_default": ResponseTemplate(
            name="rag_default",
            platform="*",
            emotion_tone="neutral",
            template="{answer}\n\n📌 此回覆根據相關知識庫內容生成",
        ),
        "escalate": ResponseTemplate(
            name="escalate",
            platform="*",
            emotion_tone="negative",
            template="您的案件已建立，編號：{case_number}。將由專人與您聯繫。",
        ),
    }

    @staticmethod
    def render(template: str, **vars: object) -> str:
        """Substitute ``{var}`` placeholders via ``str.format_map(**vars)``.

        Missing keys in ``vars`` are left as their original ``{var}``
        placeholder in the rendered output rather than raising
        ``KeyError`` mid-format, so a partial render still surfaces the
        substituted context to the caller and the offending placeholder
        is visible for downstream diagnostics (e.g. logging the
        unresolved variable name). Provided keys are interpolated
        exactly as ``str.format_map`` would interpolate them.

        Callers are expected to keep ``vars`` flat (no dotted attribute
        paths); SRS FR-50 only mandates ``str.format``-style
        interpolation.
        """
        return template.format_map(_SafeFormatDict(vars))

    # ``_SafeFormatDict`` exists solely to give ``render`` a mapping
    # whose ``__missing__`` returns the original ``{key}`` placeholder
    # text. ``str.format_map`` is the documented Python API for
    # "substitute these values, leave the rest of the placeholders
    # alone"; using it here is the canonical fix for the
    # ``KeyError``-on-missing-template-variable bug, not a workaround.
    # Kept as a module-level class (rather than a nested closure) so
    # the test suite can import and exercise it directly if needed.

    # Tone prefixes are SRS FR-51-mandated literals — keep them as module
    # constants so a future A/B variant injection (FR-52) can swap them
    # without rewriting the dispatch below.
    _NEGATIVE_APOLOGY_PREFIX: str = "非常抱歉造成您的困擾。"
    _POSITIVE_PREFIX: str = "太好了！"

    # A/B variant suffixes are SRS FR-52-mandated literals. Kept as module
    # constants so the experiment owner can later tune the CTA copy from a
    # single place without re-deriving the dispatch logic.
    _VARIANT_A_SUFFIX: str = "還有其他問題嗎？"
    _VARIANT_B_SUFFIX: str = "需要進一步說明嗎？"

    @staticmethod
    def _apply_emotion_tone(
        emotion: str,
        intensity: float,
        repeat_count: int,
        base_text: str = "",
    ) -> str:
        """[FR-51] Prepend the SRS-mandated tone prefix to ``base_text``.

        Dispatch per SRS FR-51 acceptance criteria:

        - ``emotion == "negative"`` AND ``intensity > 0.7`` AND
          ``repeat_count == 0`` → prepend
          「非常抱歉造成您的困擾。」 (so the user feels the bot has
          acknowledged the gravity of the issue).
        - ``emotion == "negative"`` with ``repeat_count > 0`` → suppress
          the apology prefix entirely (the user has already been
          apologised to in a prior turn; a second "非常抱歉" three
          messages in a row is abrasive).
        - ``emotion == "positive"`` → prepend 「太好了！」 regardless of
          ``intensity`` and ``repeat_count`` (celebratory replies land
          on a warm tone).
        - ``emotion == "neutral"`` (or any other unrecognised label) →
          strict pass-through; ``base_text`` is returned unchanged with
          no prefix injected so informational replies do not feel
          artificially cheerful or apologetic.

        Args:
            emotion: Classified emotion label (``"negative"`` /
                ``"positive"`` / ``"neutral"`` / any other).
            intensity: Numeric intensity in ``[0.0, 1.0]``.
            repeat_count: Historical repeat count of negative-tense
                messages (int >= 0). Only meaningful for ``"negative"``.
            base_text: Reply body the prefix will be prepended to.
                Defaults to ``""``.

        Returns:
            ``base_text`` with the appropriate tone prefix prepended,
            or ``base_text`` unchanged for the neutral / unrecognised
            pass-through branch.

        Citations:
            - SRS.md FR-51 -- "negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」" (line 114).
            - SRS.md FR-51 -- "positive → 前綴「太好了！」" (line 114).
            - SRS.md FR-51 -- "repeat_count > 0 且 negative → 抑制重複道歉" (line 114).
            - SRS.md FR-51 -- implementation_functions: "ResponseGenerator._apply_emotion_tone" (line 114).
        """
        # Three rules evaluated top-down; rarer prefix-applied cases
        # short-circuit before the default pass-through that covers
        # neutral labels, suppressed repeats, and low-intensity
        # negatives alike.
        if (
            emotion == "negative"
            and intensity > 0.7
            and repeat_count == 0
        ):
            return ResponseGenerator._NEGATIVE_APOLOGY_PREFIX + base_text
        if emotion == "positive":
            return ResponseGenerator._POSITIVE_PREFIX + base_text
        return base_text

    @staticmethod
    def _apply_ab_variant(variant: str, base_text: str) -> str:
        """[FR-52] Append the SRS-mandated A/B CTA suffix to ``base_text``.

        Dispatch per SRS FR-52 acceptance criteria:

        - ``variant == "a"`` → append 「還有其他問題嗎？」 so the
          treatment arm closes the conversation with a follow-up prompt.
        - ``variant == "b"`` → append 「需要進一步說明嗎？」 so the
          alternate treatment arm closes with its distinct CTA.
        - ``variant == "control"`` (or any other unrecognised label) →
          strict pass-through; ``base_text`` is returned unchanged so
          the control group receives the bare reply with no suffix
          injected. SRS FR-52 acceptance: "control → 不注入".

        The ``variant`` label is produced upstream by
        ``ABTestManager.get_variant()`` (see ``app.services.ab_testing``)
        which uses SHA-256 over ``(user_id, experiment_id)`` so the same
        user always lands on the same arm across processes.

        Args:
            variant: The variant label assigned to this user by
                ``ABTestManager``. Recognised labels are ``"a"``,
                ``"b"`` and ``"control"``; any other label is treated
                as the no-injection baseline.
            base_text: Reply body the suffix will be appended to.

        Returns:
            ``base_text`` with the appropriate CTA suffix appended, or
            ``base_text`` unchanged for the control pass-through.

        Citations:
            - SRS.md FR-52 -- "variant_a → 結尾 \"還有其他問題嗎？\"" (line 115).
            - SRS.md FR-52 -- "variant_b → 結尾 \"需要進一步說明嗎？\"" (line 115).
            - SRS.md FR-52 -- "control → 不注入" (line 115).
            - SRS.md FR-52 -- implementation_functions:
              "ResponseGenerator._apply_ab_variant()" (line 115).
            - SRS.md FR-53 -- "Platform Format Adapter：各平台訊息限制（Telegram 4096 字元/HTML MarkdownV2；LINE 5000 字元/Quick Reply；Messenger 2000 字元/截斷+link；WhatsApp 4096 字元；Web 無限制/完整 Markdown；Agent 無限制/純 JSON）" (line 116).
            - SRS.md FR-53 -- acceptance "各平台輸出格式符合限制；長訊息正確截斷或分段" (line 116).
            - SRS.md FR-53 -- implementation_functions: "platform format adapters" (line 116).
        """
        if variant == "a":
            return base_text + ResponseGenerator._VARIANT_A_SUFFIX
        if variant == "b":
            return base_text + ResponseGenerator._VARIANT_B_SUFFIX
        return base_text

    # Per-platform character limits (SRS FR-53 / SPEC.md §Platform Format
    # Adapter). Consolidated into a single lookup table so the dispatch
    # below is one ``.get()`` call rather than four near-identical
    # ``content[:N]`` branches — a single source of truth for "what is
    # <platform>'s limit today?".
    _PLATFORM_MAX_CHARS: ClassVar[dict[str, int]] = {
        "telegram": 4096,
        "line": 5000,
        "messenger": 2000,
        "whatsapp": 4096,
    }

    @staticmethod
    def format_for_platform(platform: str, content: str) -> str:
        """[FR-53] Format ``content`` for the target ``platform``'s contract.

        Dispatch per SRS FR-53 (per-platform character-limit table):

        - ``platform == "telegram"`` → truncate to Telegram's 4096-char
          limit. Excess characters are dropped; Telegram rejects (or
          silently drops) any outgoing message longer than 4096 chars.
        - ``platform == "line"`` → truncate to LINE's 5000-char limit.
        - ``platform == "messenger"`` → truncate to Messenger's 2000-
          char limit. Production callers may append a continuation link
          elsewhere; this method only enforces the documented ceiling.
        - ``platform == "whatsapp"`` → truncate to WhatsApp's 4096-char
          limit.
        - ``platform == "web"`` → strict pass-through; Web has no
          character limit and supports full Markdown, so the adapter
          returns ``content`` byte-for-byte. A 100 000-char input is
          returned unchanged.
        - ``platform == "agent"`` → wrap the reply in a pure-JSON
          envelope (``{"content": <content>}``) so the A2A / M2M
          Agent channel can parse the response as JSON-RPC. No
          Markdown, HTML, or template placeholders leak through.
        - Any other ``platform`` → pass-through; the adapter is a
          safety net, not a content-policy enforcer.

        Args:
            platform: Target platform identifier. Recognised values are
                ``"telegram"``, ``"line"``, ``"messenger"``, ``"whatsapp"``,
                ``"web"`` and ``"agent"``.
            content: Raw reply body to format.

        Returns:
            The formatted reply as a ``str``. For ``"agent"`` this is a
            JSON-encoded envelope (``json.loads``-safe); for all other
            recognised platforms it is a (possibly truncated) UTF-8
            string; for unrecognised platforms it is ``content`` itself.

        Citations:
            - SRS.md FR-53 -- "Telegram 4096 字元" (line 116).
            - SRS.md FR-53 -- "LINE 5000 字元" (line 116).
            - SRS.md FR-53 -- "Messenger 2000 字元/截斷+link" (line 116).
            - SRS.md FR-53 -- "WhatsApp 4096 字元" (line 116).
            - SRS.md FR-53 -- "Web 無限制/完整 Markdown" (line 116).
            - SRS.md FR-53 -- "Agent 無限制/純 JSON" (line 116).
            - SRS.md FR-53 -- acceptance "各平台輸出格式符合限制；長訊息正確截斷或分段" (line 116).
            - SRS.md FR-53 -- implementation_functions: "platform format adapters" (line 116).
        """
        # Per-platform dispatch. The four character-limited platforms
        # share a single ``content[:max_chars]`` shape and are handled
        # via the ``_PLATFORM_MAX_CHARS`` table; ``web`` and ``agent``
        # need their own branches because their formatting rules
        # (pass-through / JSON envelope) are not simple truncation.
        if platform == "web":
            # Pass-through: Web has no character limit and supports
            # full Markdown. ``expected_truncated="false"`` per
            # TEST_SPEC.md case 5.
            return content
        if platform == "agent":
            # Pure-JSON envelope for the A2A / M2M Agent channel.
            # ``ensure_ascii=False`` so non-ASCII reply bodies (e.g.
            # CJK) survive the round-trip without ``\uXXXX`` escapes —
            # the test fixture uses "您好，這裡是客服中心。" and asserts
            # ``parsed["content"] == content`` byte-for-byte.
            return json.dumps({"content": content}, ensure_ascii=False)
        max_chars = ResponseGenerator._PLATFORM_MAX_CHARS.get(platform)
        if max_chars is not None:
            # Python slices are forgiving on over-long input and exact
            # on under-limit input, so the same slice covers both
            # boundary and pass-through cases.
            return content[:max_chars]
        # Unrecognised platform — be conservative and pass the content
        # through rather than silently dropping characters.
        return content

# --- Merged from retraction.py ---
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
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
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
    security_log_writer: Callable[..., None] | None = None,
) -> RetractionResult:
    """[FR-17] Web path: push replacement frame over the open WebSocket.

    The web client holds an open WS connection; the retraction is
    an in-place replacement of the outgoing frame so the user sees
    the correction live rather than alongside the original.
    """
    try:
        web_ws_pusher.replace_response(
            message_id,
            replacement=WS_REPLACEMENT_TEXT,
        )
    except Exception:
        _log_retraction_failed(
            security_log_writer,
            platform="web",
            message_id=message_id,
            reason="api_error",
        )
        return _apology_result("web", message_id)

    return RetractionResult(
        platform="web",
        success=True,
        method="ws_replace",
        message_id=message_id,
    )


def _retract_a2a(
    message_id: str,
    a2a_client: Any,
    security_log_writer: Callable[..., None] | None = None,
) -> RetractionResult:
    """[FR-17] A2A path: mark the message revoked so JSON-RPC echoes it.

    ``revoked=True`` lets the JSON-RPC layer reflect the verdict back
    to the caller as ``{"revoked": true}`` — an A2A retraction that
    returns ``success=True`` but ``revoked=False`` would let an
    injected agent response remain valid on the wire.
    """
    try:
        a2a_client.mark_revoked(message_id)
    except Exception:
        _log_retraction_failed(
            security_log_writer,
            platform="a2a",
            message_id=message_id,
            reason="api_error",
        )
        return _apology_result("a2a", message_id)

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
        return _retract_web(message_id, web_ws_pusher, security_log_writer)
    if platform == "a2a":
        return _retract_a2a(message_id, a2a_client, security_log_writer)

    raise ValueError(f"Unknown platform: {platform!r}")

# --- Merged from unified_response.py ---
"""[FR-08] UnifiedResponse — immutable cross-tier answer envelope.

Every knowledge tier (FR-26..31) writes one of these exactly once. Downstream
Emotion Tone (FR-51), Template (FR-50) and Platform Adapter (FR-53) stages
MUST treat the instance as read-only — the ``frozen=True`` flag installs a
``__setattr__`` that rejects all writes with
``dataclasses.FrozenInstanceError`` so the immutability contract is
structural, not merely conventional. To attach new information (e.g. an
emotion_adjustment after the emotion stage) use
``dataclasses.replace(resp, emotion_adjustment=...)`` to derive a new
instance.

This module is the outbound counterpart to ``unified_message.UnifiedMessage``
(FR-07): ``UnifiedMessage`` envelopes an inbound platform message;
``UnifiedResponse`` envelopes an outbound knowledge-tier answer.

Citations:
    - SRS.md:31 — FR-08 acceptance criteria: "UnifiedResponse 資料結構:
      immutable dataclass, 欄位含 content, source(rule|rag|wiki|escalate),
      confidence, knowledge_id(Optional), emotion_adjustment(Optional),
      quick_replies. 所有知識層輸出皆可轉換為 UnifiedResponse; source
      欄位限定四個合法值"
"""




class ResponseSource(Enum):
    """[FR-08] Which knowledge tier produced the ``UnifiedResponse``.

    Values are lower-case strings stored on ``.value`` so adapters / logs
    reach the wire-format string with an explicit ``ResponseSource.X.value``
    access rather than relying on implicit ``str`` mixing.

    Restricted to exactly four values per SRS FR-08 ("source 欄位限定四個
    合法值"):
        - ``rule``     — Tier 1 PostgreSQL ILIKE 規則匹配 (FR-26)
        - ``rag``      — Tier 2 RAG + RRF (FR-27)
        - ``wiki``     — Tier 3 LLM 生成 + Grounding (FR-28)
        - ``escalate`` — Tier 4 人工轉接 (FR-29..31)

    Any value outside this set is rejected at construction time so that a
    misrouted tier tag surfaces immediately rather than being silently
    coerced downstream.

    Citations:
        - SRS.md:31 — FR-08 "source 欄位限定四個合法值".
    """

    RULE = "rule"
    RAG = "rag"
    WIKI = "wiki"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class UnifiedResponse:
    """[FR-08] Immutable cross-tier answer envelope.

    Every knowledge tier (FR-26..31) writes one of these exactly once.
    Downstream Emotion Tone (FR-51), Template (FR-50) and Platform Adapter
    (FR-53) stages MUST treat the instance as read-only — the
    ``frozen=True`` flag installs a ``__setattr__`` that rejects all
    writes with ``dataclasses.FrozenInstanceError`` so the immutability
    contract is structural, not merely conventional.

    To attach new information (e.g. an ``emotion_adjustment`` after the
    emotion stage, or a populated ``quick_replies`` list after template
    rendering) use ``dataclasses.replace(resp, ...)`` to derive a new
    instance — never mutate the original.

    Citations:
        - SRS.md:31 — FR-08 acceptance criteria: "欄位含 content, source
          (rule|rag|wiki|escalate), confidence, knowledge_id(Optional),
          emotion_adjustment(Optional), quick_replies". The field set
          below mirrors that row literally; ``knowledge_id`` and
          ``emotion_adjustment`` default to ``None`` because not every
          tier supplies them (e.g. the ``escalate`` tier has no
          knowledge_id), and ``quick_replies`` defaults to an empty list
          because template rendering is a downstream concern.
    """

    content: str
    source: ResponseSource
    confidence: float
    knowledge_id: str | None = None
    emotion_adjustment: Any | None = None  # EmotionAdjustment object (FR-51)
    # [FR-08] list[str] per TEST_SPEC.md FR-08 contract (test asserts == []).
    quick_replies: list[str] = field(default_factory=list)
