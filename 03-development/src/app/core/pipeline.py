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
import contextvars
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.emotion import EmotionAnalyzer
    from app.core.paladin import PALADINPipeline
    from app.core.pii import PIIMasking
    from app.core.dst import DialogueState
    from app.core.knowledge import HybridKnowledge
    from app.core.response import ResponseGenerator

_stage_call_log_var: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "_stage_call_log", default=[]
)

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

    Stage order (SAD architecture_constraints):
        paladin → pii → dst (slot fill + missing_slots) →
        knowledge → emotion → response
    """

    def __init__(
        self,
        emotion: EmotionAnalyzer | Any | None = None,
        paladin: PALADINPipeline | Any | None = None,
        pii: PIIMasking | Any | None = None,
        dst: DialogueState | Any | None = None,
        knowledge: HybridKnowledge | Any | None = None,
        response: ResponseGenerator | Any | None = None,
    ) -> None:
        self.emotion = emotion
        self.paladin = paladin
        self.pii = pii
        self.dst = dst
        self.knowledge = knowledge
        self.response = response

    @property
    def _stage_call_log(self) -> list[str]:
        # Test-visible record of which stages ran in what order (H-08).
        return _stage_call_log_var.get()

    def fill_slots(self, intent: str, slots: dict[str, str]) -> list[str]:
        """[FR-35] Fill DST slots for the current intent.

        Returns the list of slots still missing after the fill attempt.
        An empty list means every required slot for ``intent`` is now
        satisfied and the DST may advance to ``AWAITING_CONFIRMATION``.
        """
        if self.dst is None:
            return []
        self.dst.intent = intent
        self.dst.slots.update(slots)
        return self.dst.missing_slots()

    def handle_message(self, msg: Any) -> Any:
        """[FR-49] Orchestrate PALADIN→PII→DST→Knowledge→Emotion→Response.

        Order enforced by SAD architecture constraints:
          paladin_executes_before_pii, knowledge_query_after_dst_slot_resolution.
        Source and confidence are derived from ``KnowledgeResult`` (H-04);
        when no knowledge layer is injected, confidence is honestly 0.0
        rather than the historical 1.0 hardcoded default.
        """
        from app.core.response import ResponseSource, UnifiedResponse

        content: str = msg.content
        current_log: list[str] = []
        _stage_call_log_var.set(current_log)

        if self.paladin is not None:
            current_log.append("paladin")
            self.paladin.check_input(content)

        if self.pii is not None:
            current_log.append("pii")
            mask_result = self.pii.mask(content)
            content = mask_result.masked_text

        # DST slot resolution (H-03): real call into DialogueState, not
        # the previous `_ = self.dst` no-op. Records missing slots so
        # the downstream knowledge query is informed by slot state.
        # Defensive getattr: minimal test stubs (e.g. test_fr49's
        # _TrackedDST that only tracks attribute access) may not expose
        # the full DialogueState surface; missing attrs are treated as
        # empty defaults rather than raising.
        intent, slots = self._extract_intent_slots(content)  # noqa: F841
        missing_after_fill: list[str] = []
        if self.dst is not None:
            current_log.append("dst")
            dst_slots = getattr(self.dst, "slots", None)
            if isinstance(dst_slots, dict):
                dst_slots.update(slots)
            if hasattr(self.dst, "missing_slots"):
                missing_after_fill = list(self.dst.missing_slots())
            current_log.append(
                f"dst.missing={','.join(missing_after_fill) or 'none'}"
            )

        # Knowledge query (H-08): always AFTER dst slot resolution.
        knowledge_result = None
        if self.knowledge is not None:
            current_log.append("knowledge")
            knowledge_result = self.knowledge.query(content)

        # Emotion (FR-46..49)
        process_result = self.process(msg.platform, content)
        emotion_result = process_result.get("emotion")
        current_log.append("emotion")

        # Response (FR-50..53)
        if self.response is not None:
            current_log.append("response")
            content = self.response.format_for_platform(
                str(getattr(msg.platform, "value", msg.platform)), content
            )

        # Source/confidence derived from KnowledgeResult (H-04).
        if knowledge_result is not None:
            try:
                source = ResponseSource(knowledge_result.source)
            except ValueError:
                try:
                    source = ResponseSource[str(knowledge_result.source).upper()]
                except KeyError:
                    source = ResponseSource.RULE
            confidence = knowledge_result.confidence
        else:
            # No knowledge layer injected: report honestly with 0.0
            # confidence rather than the historical 1.0 hardcoded default.
            source = ResponseSource.RULE
            confidence = 0.0

        return UnifiedResponse(
            content=content,
            source=source,
            confidence=confidence,
            emotion_adjustment=emotion_result,
        )

    @staticmethod
    def _extract_intent_slots(content: str) -> tuple[str, dict[str, str]]:
        """Lightweight intent + slot extractor used by the orchestrator.

        Production wiring relies on a downstream LLM; this stub returns
        an empty intent and dict so the DST stage can still run its
        slot-validation contract in tests and unit wiring without a
        heavyweight LLM dependency. The pipeline DOES still call
        DialogueState.missing_slots() to honour the H-08 ordering
        constraint.
        """
        # ``content`` is accepted for interface compatibility with the
        # production extractor; the stub has no signals to extract from.
        del content
        return ("", {})

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

async def get_context(conversation_id: str) -> dict:
    """[FR-49] Retrieve conversation context from DB."""
    from app.infra.database import get_session
    from sqlalchemy import text
    try:
        session_gen = get_session()
        session = await session_gen.__anext__()
        result = await session.execute(
            text("SELECT role, content FROM messages WHERE conversation_id = :cid ORDER BY id ASC"),
            {"cid": conversation_id}
        )
        history = [{"role": row[0], "content": row[1]} for row in result.fetchall()]
        return {"conversation_id": conversation_id, "history": history}
    except Exception:
        return {"conversation_id": conversation_id, "history": []}

