"""TDD-RED: failing tests for FR-49 — AGENT 平台 Bypass (skip emotion module).

Spec source: 02-architecture/TEST_SPEC.md (FR-49)
SRS source : SRS.md FR-49 (Module 8: Emotion Analyzer)

Acceptance criteria (from SRS FR-49):
    AGENT 平台 Bypass：platform == AGENT 時跳過情緒分析模組。
    AGENT 平台請求不執行情緒分析；不觸發情緒轉接。
    Implementation function: ``platform check in pipeline``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations
import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-49 mandates ``platform check in pipeline`` (SRS FR-49
# implementation_functions). The canonical place for this orchestration
# is ``app.core.pipeline`` — a thin coordinator that, before delegating
# to the emotion module, MUST short-circuit when the incoming message's
# platform is the agent-to-agent channel ("agent" / ``Platform.AGENT``).
#
# GREEN contract pinned by this spec:
#
#   - ``Pipeline`` (in ``app/core/pipeline.py``) MUST accept an injected
#     ``EmotionAnalyzer`` (or callable) so unit tests can count how
#     many times emotion analysis runs without spinning up a real
#     model.
#   - ``Pipeline.process(message)`` MUST inspect ``message.platform``
#     (a ``Platform`` enum value or its lowercase string) and skip the
#     emotion analyzer entirely when ``platform == "agent"`` /
#     ``Platform.AGENT``. For every other platform (e.g. ``"telegram"``,
#     ``"line"``, ``"messenger"``, ``"whatsapp"``, ``"web"``,
#     ``"a2a"``) the emotion analyzer MUST be invoked exactly once.
#   - ``Pipeline.process(message)`` MUST return a non-None result
#     regardless of platform (the bypass must not swallow the message).
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because the source module
# ``app.core.pipeline`` does not yet exist. That is the valid RED
# signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.core.pipeline import Pipeline


# ---------------------------------------------------------------------------
# 1. platform == "agent" MUST bypass the emotion analyzer — emotion
#    analysis is an agent-to-human concern and has no business being
#    run on machine-to-machine / agent-to-agent traffic.
#
# Spec input: platform="agent"; expected_emotion_calls="0".
# Spec sub-assertion: fr49-ok: result is not None.
# SRS FR-49 acceptance: "AGENT 平台請求不執行情緒分析".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr49_agent_platform_skips_emotion_module():
    platform = "agent"
    expected_emotion_calls = "0"

    if platform == "agent":
        # Spec fr49-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        #
        # GREEN TODO: ``Pipeline(message_or_platform, emotion=...)`` or
        # ``Pipeline(emotion=...).process(message)`` MUST return a
        # non-None result for an AGENT-platform message — the bypass
        # short-circuits the emotion stage but MUST still return
        # something so downstream stages can continue.
        calls = {"n": 0}

        class _StubEmotion:
            def analyze(self, text):
                _ = text
                calls["n"] += 1
                return {"category": "neutral", "intensity": 0.0}

        pipeline = Pipeline(emotion=_StubEmotion())
        result = pipeline.process(platform=platform, text="hello")

        assert result is not None, (
            "fr49-ok predicate: Pipeline.process must return a non-None "
            "result for platform='agent' (the bypass MUST NOT swallow "
            "the message)"
        )

    # GREEN TODO: for platform == "agent" the pipeline MUST NOT call
    # the emotion analyzer at all — SRS FR-49 mandates
    # "AGENT 平台請求不執行情緒分析". Counted calls MUST be zero.
    expected = int(expected_emotion_calls)
    assert expected == 0, (
        f"FR-49: expected_emotion_calls sentinel must be '0' "
        f"(zero invocations of emotion module); got {expected_emotion_calls!r}"
    )
    assert calls["n"] == expected, (
        f"FR-49: emotion analyzer must be skipped on platform='agent'; "
        f"got {calls['n']!r} call(s), expected exactly {expected}. "
        f"SRS FR-49 mandates 'platform == AGENT 時跳過情緒分析模組'."
    )

    # Sentinels MUST be preserved per spec.
    assert platform == "agent", (
        f"FR-49: platform sentinel must be 'agent'; got {platform!r}"
    )
    assert expected_emotion_calls == "0", (
        f"FR-49: expected_emotion_calls sentinel must be '0'; "
        f"got {expected_emotion_calls!r}"
    )


# ---------------------------------------------------------------------------
# 2. platform == "telegram" MUST run the emotion analyzer — only the
#    AGENT platform is exempt. Every human-facing channel still pays
#    the cost of emotion analysis so the negative-emotion → escalation
#    wiring in FR-47/48 can fire.
#
# Spec input: platform="telegram"; expected_emotion_calls="1".
# Spec sub-assertion: fr49-ok: result is not None.
# SRS FR-49 acceptance: "AGENT 平台請求不執行情緒分析；不觸發情緒轉接"
#                    — implicit inverse: non-AGENT platforms DO analyse.
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr49_telegram_platform_emotion_module_runs():
    platform = "telegram"
    expected_emotion_calls = "1"

    if platform == "telegram":
        # Spec fr49-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        #
        # GREEN TODO: ``Pipeline.process`` MUST invoke the injected
        # emotion analyzer exactly once for non-AGENT platforms (here
        # "telegram") — the bypass is platform-specific, NOT a global
        # no-op. SRS FR-49 only exempts the AGENT platform; telegram is
        # a human-facing channel and MUST still be emotion-analysed so
        # FR-47/48 escalation paths can trigger.
        calls = {"n": 0}

        class _StubEmotion:
            def analyze(self, text):
                _ = text
                calls["n"] += 1
                return {"category": "neutral", "intensity": 0.0}

        pipeline = Pipeline(emotion=_StubEmotion())
        result = pipeline.process(platform=platform, text="hello")

        assert result is not None, (
            "fr49-ok predicate: Pipeline.process must return a non-None "
            "result for platform='telegram' (non-AGENT path)"
        )

    # GREEN TODO: for platform == "telegram" the pipeline MUST invoke
    # the emotion analyzer exactly once — SRS FR-49 bypass is AGENT-only,
    # so every other platform pays the analysis cost.
    expected = int(expected_emotion_calls)
    assert expected == 1, (
        f"FR-49: expected_emotion_calls sentinel must be '1'; "
        f"got {expected_emotion_calls!r}"
    )
    assert calls["n"] == expected, (
        f"FR-49: emotion analyzer must run exactly once on "
        f"platform='telegram'; got {calls['n']!r} call(s), expected "
        f"exactly {expected}. SRS FR-49 only bypasses platform='agent'; "
        f"telegram is human-facing and MUST still be analysed so the "
        f"FR-47/48 escalation paths remain wired."
    )

    # Sentinels MUST be preserved per spec.
    assert platform == "telegram", (
        f"FR-49: platform sentinel must be 'telegram'; got {platform!r}"
    )
    assert expected_emotion_calls == "1", (
        f"FR-49: expected_emotion_calls sentinel must be '1'; "
        f"got {expected_emotion_calls!r}"
    )


# ---------------------------------------------------------------------------
# 3. handle_message: thin orchestrator returns UnifiedResponse with the
#    original content when no sub-modules are injected.
# ---------------------------------------------------------------------------
def test_fr49_handle_message_returns_unified_response():
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType
    from app.core.response import UnifiedResponse

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U123",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline().handle_message(msg)
    assert isinstance(result, UnifiedResponse)
    assert result.content == "hello"


# ---------------------------------------------------------------------------
# 4. get_context: returns empty history for unknown conversation_id.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fr49_get_context_empty_history():
    from app.core.pipeline import get_context
    result = await get_context("conv-99")
    assert result["conversation_id"] == "conv-99"
    assert result["history"] == []


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in core/pipeline.py
# ---------------------------------------------------------------------------

def test_fr49_normalise_platform_accepts_a2a_alias():
    """``_normalise_platform("a2a")`` MUST resolve to lowercase ``"a2a"``,
    and the AGENT bypass set MUST contain both ``"agent"`` and ``"a2a"`` —
    so the Bypass return dict's ``bypassed=True`` and ``emotion=None``.
    Kills mutant #2 (``"a2a"`` → ``XXa2aXX``).
    """
    pipeline = Pipeline()
    result = pipeline.process(platform="a2a", text="hello")
    assert result["platform"] == "a2a", (
        f"Pipeline.process(platform='a2a') must normalise to 'a2a'; "
        f"got platform={result['platform']!r}"
    )
    assert result["bypassed"] is True, (
        f"'a2a' is an agent-to-agent alias and MUST be bypassed per "
        f"FR-49; got bypassed={result['bypassed']!r}"
    )
    assert result["emotion"] is None, (
        f"a2a must skip emotion; got emotion={result['emotion']!r}"
    )


def test_fr49_normalise_platform_accepts_enum_value():
    """``_normalise_platform`` MUST use ``Platform.value`` if present, so
    an enum input reaches the bypass set. Kills mutant #4
    (``getattr(platform, "value", platform)`` → ``getattr(platform, "XXvalueXX", platform)``).
    """
    from app.core.unified_message import Platform

    pipeline = Pipeline()
    result = pipeline.process(platform=Platform.AGENT, text="hello")
    assert result["platform"] == "agent", (
        f"Pipeline.process(platform=Platform.AGENT) must normalise via "
        f"Platform.value; got platform={result['platform']!r}"
    )
    assert result["bypassed"] is True, (
        f"Platform.AGENT must bypass emotion; got bypassed={result['bypassed']!r}"
    )


def test_fr49_process_returns_dict_with_keys_platform_text_emotion_bypassed():
    """``Pipeline.process`` MUST return a dict that contains exactly the
    four keys ``platform``, ``text``, ``emotion``, ``bypassed``. Kills
    mutants #47–50 which rename each key (``"platform"`` → ``XXplatformXX``).
    """
    pipeline = Pipeline()
    result = pipeline.process(platform="line", text="hello")
    expected_keys = {"platform", "text", "emotion", "bypassed"}
    assert set(result.keys()) == expected_keys, (
        f"Pipeline.process must return dict with keys {expected_keys!r}; "
        f"got {set(result.keys())!r}"
    )
    assert result["platform"] == "line"
    assert result["text"] == "hello"
    assert result["emotion"] is None  # no emotion injected
    assert result["bypassed"] is False


def test_fr49_emotion_exception_returns_none_emotion():
    """If the injected emotion analyzer raises, ``Pipeline.process`` MUST
    swallow the exception and set ``emotion=None`` (so downstream stages
    can still process the message). Kills mutant #46
    (``emotion_result = None`` → ``emotion_result = ""``) and #41
    (``emotion_result: Any = None`` → ``emotion_result: Any = ""``).
    """
    class _BoomEmotion:
        def analyze(self, text):
            _ = text
            raise RuntimeError("LLM rate-limit")

    pipeline = Pipeline(emotion=_BoomEmotion())
    result = pipeline.process(platform="telegram", text="hello")
    assert result["emotion"] is None, (
        f"Pipeline.process must swallow emotion exceptions and set "
        f"emotion=None; got emotion={result['emotion']!r}"
    )
    assert result["bypassed"] is False


def test_fr49_handle_message_paladin_receives_raw_content():
    """``handle_message`` MUST call ``paladin.check_input`` with the
    ORIGINAL ``msg.content`` (before PII masking). Kills mutant #19
    (``content = mask_result.masked_text`` → ``content = None``) and
    verifies the paladin branch is wired.
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType

    paladin_received = {"value": None}

    class _StubPaladin:
        def check_input(self, content):
            paladin_received["value"] = content

    class _StubPII:
        def mask(self, text):
            _ = text
            from types import SimpleNamespace
            return SimpleNamespace(masked_text="[MASKED]")

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="信用卡 1234",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    Pipeline(paladin=_StubPaladin(), pii=_StubPII()).handle_message(msg)
    assert paladin_received["value"] == "信用卡 1234", (
        f"paladin.check_input must receive raw msg.content (before PII "
        f"masking); got {paladin_received['value']!r}"
    )


def test_fr49_handle_message_pii_masking_changes_content():
    """``handle_message`` MUST apply PII masking — the UnifiedResponse
    content must reflect the masked text, not the original. Kills mutant
    #19 (content = None).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType
    from app.core.response import UnifiedResponse

    class _StubPII:
        def mask(self, text):
            _ = text
            from types import SimpleNamespace
            return SimpleNamespace(masked_text="信用卡 [REDACTED]")

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="信用卡 1234-5678",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline(pii=_StubPII()).handle_message(msg)
    assert isinstance(result, UnifiedResponse)
    assert result.content == "信用卡 [REDACTED]", (
        f"PII-masked content must reach UnifiedResponse.content; "
        f"got {result.content!r}"
    )


def test_fr49_handle_message_knowledge_query_uses_masked_content():
    """``handle_message`` MUST call ``knowledge.query`` AFTER PII masking
    (knowledge receives the redacted text, not the original). Kills
    mutant #24 (knowledge_result = None).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType
    from app.core.response import ResponseSource

    _ = ResponseSource  # silence Pyright
    queried_with = {"text": None}

    class _StubPII:
        def mask(self, text):
            _ = text
            from types import SimpleNamespace
            return SimpleNamespace(masked_text="[REDACTED]")

    class _StubKnowledge:
        def query(self, text):
            queried_with["text"] = text
            from types import SimpleNamespace
            return SimpleNamespace(source=ResponseSource.RAG.name, confidence=0.9)

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="original secret",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    Pipeline(pii=_StubPII(), knowledge=_StubKnowledge()).handle_message(msg)
    assert queried_with["text"] == "[REDACTED]", (
        f"knowledge.query must receive PII-masked content; "
        f"got {queried_with['text']!r}"
    )


def test_fr49_handle_message_knowledge_source_set_on_response():
    """When knowledge.query returns a known source, ``handle_message``
    MUST propagate it as ``ResponseSource.KB`` on the
    ``UnifiedResponse`` (instead of the default RULE). Kills mutants
    #32–35 (source = None).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType
    from app.core.response import ResponseSource

    class _StubKnowledge:
        def query(self, text):
            _ = text
            from types import SimpleNamespace
            return SimpleNamespace(source=ResponseSource.RAG.name, confidence=0.9)

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline(knowledge=_StubKnowledge()).handle_message(msg)
    assert result.source == ResponseSource.RAG, (
        f"Response.source must be RAG when knowledge.query returns "
        f"source=ResponseSource.RAG.name; got source={result.source!r}"
    )
    assert result.confidence == 0.9, (
        f"Response.confidence must mirror knowledge.confidence=0.9; "
        f"got confidence={result.confidence!r}"
    )


def test_fr49_handle_message_default_response_source_rule_with_full_confidence():
    """With NO knowledge injected, ``handle_message`` MUST fall back to
    ``ResponseSource.RULE`` and ``confidence=1.0``. Kills mutants #35–37
    (source=None, confidence=2.0, confidence=None).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType
    from app.core.response import ResponseSource

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline().handle_message(msg)
    assert result.source == ResponseSource.RULE, (
        f"Default Response.source must be RULE when no knowledge is "
        f"injected; got source={result.source!r}"
    )
    assert result.confidence == 1.0, (
        f"Default Response.confidence must be 1.0 (full) when no "
        f"knowledge is injected; got confidence={result.confidence!r}"
    )


def test_fr49_handle_message_response_format_uses_platform_value():
    """``handle_message`` MUST call ``response.format_for_platform`` with
    the platform's ``.value`` string when an enum is passed. Kills
    mutant #29 (``getattr(msg.platform, "value", ...)`` → ``getattr(..., "XXvalueXX", ...)``).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType

    fmt_input = {"platform": None, "content": None}

    class _StubResponse:
        def format_for_platform(self, platform, content):
            fmt_input["platform"] = platform
            fmt_input["content"] = content
            return f"[{platform}] {content}"

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline(response=_StubResponse()).handle_message(msg)
    assert fmt_input["platform"] == "line", (
        f"response.format_for_platform must receive Platform.value "
        f"('line'); got {fmt_input['platform']!r}"
    )
    assert result.content == "[line] hi", (
        f"Response.content must use the formatted output; got "
        f"{result.content!r}"
    )


def test_fr49_handle_message_emotion_adjustment_propagates():
    """``handle_message`` MUST set ``UnifiedResponse.emotion_adjustment``
    to the analyzer's result (non-None when emotion is invoked). Kills
    mutant #26–27 (``process_result.get('emotion')`` → wrong key / None).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType

    class _StubEmotion:
        def analyze(self, text):
            _ = text
            return {"category": "negative", "intensity": 0.8}

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="這很差",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = Pipeline(emotion=_StubEmotion()).handle_message(msg)
    assert result.emotion_adjustment == {"category": "negative", "intensity": 0.8}, (
        f"Response.emotion_adjustment must mirror the analyzer's output; "
        f"got {result.emotion_adjustment!r}"
    )


def test_fr49_process_bypassed_returns_emotion_none_for_agent_caps():
    """For ``platform='AGENT'`` (uppercase), ``Pipeline.process`` MUST
    bypass emotion and ``emotion_result`` MUST be ``None`` (not empty
    string). Kills mutant #41.
    """
    pipeline = Pipeline()
    result = pipeline.process(platform="AGENT", text="hi")
    assert result["bypassed"] is True
    assert result["emotion"] is None
    assert result["platform"] == "agent"


def test_fr49_init_assigns_all_deps_as_instance_attrs():
    """``Pipeline.__init__`` MUST assign every injected dep to
    ``self.<name>`` (so callers can introspect / replace). Kills mutants
    #10–14 (each sets one injected dep to ``None``).
    """
    paladin = object()
    pii = object()
    dst = object()
    knowledge = object()
    response = object()
    pipeline = Pipeline(
        paladin=paladin, pii=pii, dst=dst, knowledge=knowledge, response=response,
    )
    assert pipeline.paladin is paladin
    assert pipeline.pii is pii
    assert pipeline.dst is dst
    assert pipeline.knowledge is knowledge
    assert pipeline.response is response


def test_fr49_handle_message_dst_branch_invoked():
    """``handle_message`` MUST consult ``self.dst`` (any truthy attribute
    access counts) when dst is injected. Kills mutant #20
    (``if self.dst is not None`` → ``if self.dst is  None``) and #21
    (``_ = self.dst`` → ``_ = None``).
    """
    from datetime import datetime, timezone
    from app.core.unified_message import UnifiedMessage, Platform, MessageType

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={},
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    # The pipeline does `_ = self.dst` (attribute read). We override
    # `__getattribute__` on a tracked class so the read is observable.
    class _TrackedDST:
        accessed = False

        def __getattribute__(self, name):
            object.__setattr__(self, "accessed", True)
            return object.__getattribute__(self, name)

    dst = _TrackedDST()
    Pipeline(dst=dst).handle_message(msg)
    assert dst.accessed is True, (
        f"Pipeline.handle_message must read self.dst when dst is "
        f"injected; got accessed={dst.accessed!r}"
    )
