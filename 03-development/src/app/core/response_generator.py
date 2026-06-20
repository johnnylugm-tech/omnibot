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

from __future__ import annotations

import json
from dataclasses import dataclass


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


class ResponseGenerator:
    """[FR-50] Holds the pre-canned reply templates and a render helper.

    The class is a thin namespace — FR-50 only requires the template
    registry and a ``str.format``-compatible render path; richer
    behaviour (emotion-tone modulation, A/B variant injection, etc.)
    is layered on by FR-51 / FR-52 without changing this surface.
    """

    DEFAULT_TEMPLATES: dict[str, ResponseTemplate] = {
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
        """Substitute ``{var}`` placeholders via ``str.format(**vars)``.

        Returns the rendered string for valid inputs. Callers are
        expected to keep ``vars`` flat (no dotted attribute paths);
        SRS FR-50 only mandates ``str.format``-style interpolation.
        """
        return template.format(**vars)

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
    _PLATFORM_MAX_CHARS: dict[str, int] = {
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