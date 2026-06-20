"""[FR-50] ResponseGenerator — pre-canned reply templates + render helper.
[FR-51] ResponseGenerator._apply_emotion_tone — emotion-tone prefix modulation.

Spec source: 02-architecture/TEST_SPEC.md (FR-50, FR-51)
SRS source : SRS.md FR-50, FR-51 (Module 9: Response Generator)

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

Citations:
    - SRS.md FR-50 -- "Template System：ResponseTemplate（name, platform, emotion_tone, template）" (line 113).
    - SRS.md FR-50 -- "預設模板：rule_default（{answer}）、rag_default（附「📌 此回覆根據相關知識庫內容生成」）、escalate（附案件編號）" (line 113).
    - SRS.md FR-50 -- acceptance "三個預設模板存在且格式正確；variable interpolation 正確" (line 113).
    - SRS.md FR-50 -- implementation_functions: "ResponseGenerator.DEFAULT_TEMPLATES" (line 113).
    - SRS.md FR-51 -- "negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」" (line 114).
    - SRS.md FR-51 -- "positive → 前綴「太好了！」" (line 114).
    - SRS.md FR-51 -- "repeat_count > 0 且 negative → 抑制重複道歉" (line 114).
    - SRS.md FR-51 -- implementation_functions: "ResponseGenerator._apply_emotion_tone" (line 114).
"""

from __future__ import annotations

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
        if emotion == "negative":
            # Repeat-suppression takes priority: even at intensity > 0.7,
            # a prior apology already landed on the user. Returning
            # ``base_text`` unchanged guarantees "非常抱歉" is absent.
            if repeat_count > 0:
                return base_text
            if intensity > 0.7:
                return ResponseGenerator._NEGATIVE_APOLOGY_PREFIX + base_text
            return base_text
        if emotion == "positive":
            return ResponseGenerator._POSITIVE_PREFIX + base_text
        # "neutral" (or any unrecognised label) is a strict pass-through.
        return base_text