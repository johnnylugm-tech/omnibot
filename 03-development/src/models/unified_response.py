"""[FR-08] UnifiedResponse — immutable dataclass for knowledge layer output.

Citations:
  SRS.md FR-08: UnifiedResponse 資料結構：immutable dataclass，欄位含 content,
    source(rule|rag|wiki|escalate), confidence, knowledge_id(Optional),
    emotion_adjustment(Optional), quick_replies
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ResponseSource(Enum):
    """[FR-08] Four valid response sources."""

    RULE = "rule"
    RAG = "rag"
    WIKI = "wiki"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class UnifiedResponse:
    """[FR-08] Immutable knowledge-layer response container.

    Citations:
      SRS.md FR-08
    """

    content: str
    source: ResponseSource
    confidence: float = 1.0
    knowledge_id: Optional[str] = None
    emotion_adjustment: Optional[str] = None
    quick_replies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.source, ResponseSource):
            raise ValueError(f"source must be ResponseSource, got {type(self.source).__name__}")
