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
def test_fr49_get_context_empty_history():
    from app.core.pipeline import get_context, _CONTEXT_HISTORY
    _CONTEXT_HISTORY.clear()
    result = get_context("conv-99")
    assert result["conversation_id"] == "conv-99"
    assert result["history"] == []
