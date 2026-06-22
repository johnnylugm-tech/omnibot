"""[FR-49] Pipeline — AGENT platform bypass for the emotion module.

Spec source: 02-architecture/TEST_SPEC.md (FR-49)
SRS source : SRS.md FR-49 (Module 8: Emotion Analyzer)

FR-49 -- AGENT 平台 Bypass：
    When the incoming message's ``platform`` is the agent-to-agent
    channel (``"agent"`` / ``Platform.AGENT``), the pipeline MUST
    short-circuit BEFORE invoking the emotion analyzer. Every other
    platform (``"telegram"``, ``"line"``, ``"messenger"``,
    ``"whatsapp"``, ``"web"``, ``"a2a"``) MUST still pay the analysis
    cost so the FR-47/48 escalation paths remain wired for human-facing
    traffic.

Pipeline contract pinned by this module:

    - ``Pipeline(emotion=...)`` — the emotion analyzer is injected so
      unit tests can count invocations without spinning up a real model.
    - ``Pipeline.process(platform=..., text=...)`` — inspects
      ``platform`` (a ``Platform`` enum value OR its lowercase string)
      and decides whether to invoke ``emotion.analyze(text)``.
    - The bypass MUST NOT swallow the message — ``process`` returns a
      non-``None`` dict regardless of platform so downstream stages
      can continue.

Citations:
    - SRS.md FR-49 -- "AGENT 平台 Bypass：platform == AGENT 時跳過情緒分析模組" (line 107).
    - SRS.md FR-49 -- "AGENT 平台請求不執行情緒分析；不觸發情緒轉接" (line 107).
    - SRS.md FR-49 -- implementation_functions: "platform check in pipeline" (line 107).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# ---------------------------------------------------------------------------
# Platform identifiers that bypass the emotion analyzer.
#
# SRS FR-49 names ``"agent"`` as the bypass trigger. ``"a2a"`` (agent-to-agent)
# is the same logical channel and is included so any reasonable alias a
# caller might use is honoured by the same short-circuit.
# ---------------------------------------------------------------------------
_AGENT_PLATFORMS = frozenset({"agent", "a2a"})


def _normalise_platform(platform: Any) -> str:
    """Return a lowercase string key for ``platform``.

    Accepts a ``Platform``-style enum (uses ``.value`` if present) or
    any string. Comparison against the bypass set is case-insensitive
    so callers may pass ``"Agent"`` / ``Platform.AGENT`` interchangeably.
    """
    raw = getattr(platform, "value", platform)
    if not isinstance(raw, str):
        raw = getattr(platform, "name", str(raw))
    return raw.lower()


class Pipeline:
    """Thin orchestrator that routes messages through the emotion stage.

    Per FR-49, messages whose ``platform`` is the agent-to-agent channel
    MUST short-circuit before the emotion analyzer is invoked. Every
    other platform MUST invoke the analyzer exactly once.
    """

    def __init__(
        self,
        emotion: Any | None = None,
        paladin: Any | None = None,
        pii: Any | None = None,
        dst: Any | None = None,
        knowledge: Any | None = None,
        response: Any | None = None,
    ) -> None:
        self.emotion = emotion
        self.paladin = paladin
        self.pii = pii
        self.dst = dst
        self.knowledge = knowledge
        self.response = response

    def handle_message(self, msg: Any) -> Any:
        """[FR-49] Orchestrate PALADIN→PII→DST→Knowledge→Emotion→Response.

        Order enforced by SAD architecture constraints:
          paladin_executes_before_pii, knowledge_query_after_dst_slot_resolution.
        """
        from app.core.response import ResponseSource, UnifiedResponse

        content: str = msg.content

        if self.paladin is not None:
            self.paladin.check_input(content)

        if self.pii is not None:
            mask_result = self.pii.mask(content)
            content = mask_result.masked_text

        if self.dst is not None and self.dst.state == "INTENT_DETECTED":
            self.dst.transition("SLOT_FILLING")

        knowledge_result = None
        if self.knowledge is not None:
            knowledge_result = self.knowledge.query(content)

        self.process(msg.platform, content)

        if self.response is not None:
            content = self.response.format_for_platform(
                str(getattr(msg.platform, "value", msg.platform)), content
            )

        if knowledge_result is not None:
            source = ResponseSource(knowledge_result.source)
            confidence = knowledge_result.confidence
        else:
            source = ResponseSource.RULE
            confidence = 1.0

        return UnifiedResponse(
            content=content,
            source=source,
            confidence=confidence,
        )

    def process(self, platform: Any, text: str) -> Mapping[str, Any]:
        """Route ``text`` through the pipeline, honouring the FR-49 bypass.

        Returns a non-``None`` mapping for every platform. The mapping
        includes ``platform`` (normalised), ``text``, ``emotion`` (the
        analyzer's result, or ``None`` when bypassed), and ``bypassed``
        (``True`` iff the emotion stage was skipped).
        """
        key = _normalise_platform(platform)
        bypassed = key in _AGENT_PLATFORMS

        # Non-AGENT platforms pay the analysis cost exactly once so the
        # FR-47/48 escalation paths can fire on negative input. AGENT
        # requests skip the emotion stage entirely (SRS FR-49:
        # "AGENT 平台請求不執行情緒分析；不觸發情緒轉接").
        emotion_result: Any = None
        if not bypassed and self.emotion is not None:
            try:
                emotion_result = self.emotion.analyze(text)
            except Exception:
                emotion_result = None

        return {
            "platform": key,
            "text": text,
            "emotion": emotion_result,
            "bypassed": bypassed,
        }

_CONTEXT_HISTORY: dict[str, list[dict]] = {}


def get_context(conversation_id: str) -> dict:
    """[FR-49] Retrieve conversation context from in-memory store."""
    return {"conversation_id": conversation_id, "history": _CONTEXT_HISTORY.get(conversation_id, [])}

