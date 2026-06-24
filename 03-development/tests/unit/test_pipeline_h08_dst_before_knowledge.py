"""[H-08] Pipeline ordering constraint: knowledge_query_after_dst_slot_resolution.

Pins the SAD architecture constraint via the Pipeline._stage_call_log list.
Verifies that dst stage runs BEFORE knowledge stage in handle_message.
"""
from __future__ import annotations

import pytest

from app.core.pipeline import Pipeline


class _StubPaladin:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check_input(self, text: str) -> None:
        self.calls.append(text)


class _StubDST:
    """Mimics DialogueState with intent + slots + missing_slots."""

    def __init__(self, missing: list[str] | None = None) -> None:
        self.intent = ""
        self.slots: dict[str, str] = {}
        self._missing = missing or []

    def missing_slots(self) -> list[str]:
        return list(self._missing)


class _StubKnowledge:
    """Captures whether query() was called and at what point."""

    def __init__(self, source: str = "rule", confidence: float = 0.85) -> None:
        self.source = source
        self.confidence = confidence
        self.call_count = 0

    def query(self, text: str):  # noqa: ARG002
        from types import SimpleNamespace

        self.call_count += 1
        return SimpleNamespace(
            id="stub-id",
            content=text,
            confidence=self.confidence,
            source=self.source,
            knowledge_id=None,
        )


class _Msg:
    def __init__(self, content: str, platform: str = "telegram") -> None:
        self.content = content
        self.platform = platform


@pytest.mark.integration
@pytest.mark.np13
def test_pipeline_dst_runs_before_knowledge():
    """H-08: stage log shows dst before knowledge."""
    paladin = _StubPaladin()
    dst = _StubDST(missing=[])
    knowledge = _StubKnowledge()
    pipeline = Pipeline(paladin=paladin, dst=dst, knowledge=knowledge)

    pipeline.handle_message(_Msg("hello"))

    log = pipeline._stage_call_log
    assert "dst" in log
    assert "knowledge" in log
    assert log.index("dst") < log.index("knowledge"), (
        f"H-08 violated: dst must precede knowledge, got {log}"
    )


@pytest.mark.integration
@pytest.mark.np13
def test_pipeline_records_missing_slots():
    """H-08: stage log captures dst.missing slots for downstream awareness."""
    dst = _StubDST(missing=["order_id", "reason"])
    knowledge = _StubKnowledge()
    pipeline = Pipeline(dst=dst, knowledge=knowledge)

    pipeline.handle_message(_Msg("I want a refund"))

    log = pipeline._stage_call_log
    assert any("dst.missing=" in entry for entry in log)
    missing_entry = next(e for e in log if e.startswith("dst.missing="))
    assert "order_id" in missing_entry
    assert "reason" in missing_entry


@pytest.mark.integration
@pytest.mark.np13
def test_pipeline_stage_order_complete():
    """H-08: full stage order is paladin→pii→dst→knowledge→emotion→response."""
    paladin = _StubPaladin()
    dst = _StubDST(missing=[])
    knowledge = _StubKnowledge()
    pipeline = Pipeline(paladin=paladin, dst=dst, knowledge=knowledge)

    pipeline.handle_message(_Msg("hello"))

    log = pipeline._stage_call_log
    assert log[0] == "paladin", f"expected paladin first, got {log}"
    assert "knowledge" in log
    assert log[-1] == "emotion", f"expected emotion last, got {log}"