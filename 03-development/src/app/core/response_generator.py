"""[FR-50] ResponseGenerator — pre-canned reply templates + render helper.

Spec source: 02-architecture/TEST_SPEC.md (FR-50)
SRS source : SRS.md FR-50 (Module 9: Response Generator)

FR-50 -- Template System：
    ``ResponseTemplate（name, platform, emotion_tone, template）`` 預設
    模板三個：``rule_default``（``{answer}``）、``rag_default``（附
    「📌 此回覆根據相關知識庫內容生成」）、``escalate``（附案件編號）。
    三個預設模板存在且格式正確；variable interpolation 正確。

Public surface pinned by this module:

    - ``ResponseTemplate`` — frozen dataclass with the four fields named
      in SRS FR-50 (``name``, ``platform``, ``emotion_tone``, ``template``).
    - ``ResponseGenerator.DEFAULT_TEMPLATES`` — class-level dict keyed
      by template name. The three required keys are ``"rule_default"``,
      ``"rag_default"`` and ``"escalate"``.
    - ``ResponseGenerator.render(template, **vars)`` — substitutes
      ``{var}`` placeholders via ``str.format(**vars)`` and returns the
      rendered string.

Citations:
    - SRS.md FR-50 -- "Template System：ResponseTemplate（name, platform, emotion_tone, template）" (line 113).
    - SRS.md FR-50 -- "預設模板：rule_default（{answer}）、rag_default（附「📌 此回覆根據相關知識庫內容生成」）、escalate（附案件編號）" (line 113).
    - SRS.md FR-50 -- acceptance "三個預設模板存在且格式正確；variable interpolation 正確" (line 113).
    - SRS.md FR-50 -- implementation_functions: "ResponseGenerator.DEFAULT_TEMPLATES" (line 113).
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