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

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    # [FR-08] tuple (not list) because ``frozen=True`` only blocks attribute
    # reassignment; a list field could still be mutated in place via
    # ``resp.quick_replies.append(...)``, bypassing the immutability contract
    # for downstream stages (FR-50 template, FR-53 adapter). ``__post_init__``
    # coerces any list passed in by the caller into a tuple.
    quick_replies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # [FR-08] Structural immutability — a frozen dataclass rejects field
        # assignment, so we must use ``object.__setattr__`` to coerce the
        # caller's list into a tuple exactly once at construction time.
        if not isinstance(self.quick_replies, tuple):
            object.__setattr__(self, "quick_replies", tuple(self.quick_replies))
