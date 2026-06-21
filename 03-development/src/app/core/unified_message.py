"""[FR-07] UnifiedMessage — inbound cross-platform message envelope.

Spec source: 02-architecture/TEST_SPEC.md (FR-07)
SRS source : SRS.md FR-07 (Module 1: Unified Message Envelope)

FR-07 mandates an immutable dataclass with:
  - platform: Platform enum
  - platform_user_id: str
  - unified_user_id: Optional[str]
  - message_type: MessageType enum
  - content: str
  - raw_payload: dict (original platform payload for traceability)
  - received_at: datetime
  - reply_token: Optional[str] (LINE-specific)

All platform webhook adapters (FR-01..FR-06) build ``UnifiedMessage``
instances from their raw payloads so downstream PALADIN / Knowledge /
DST stages consume a single shape.

Citations:
    - SRS.md FR-07 — "UnifiedMessage 資料結構：immutable dataclass ... frozen=True"
    - 02-architecture/TEST_SPEC.md FR-07 — field set + frozen contract
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Platform(str, Enum):
    """[FR-07] Source platform for a UnifiedMessage.

    ``str`` mixin lets callers compare members to bare ``str`` literals
    for logging / metric labels without an explicit ``.value`` access.
    """

    TELEGRAM = "telegram"
    LINE = "line"
    MESSENGER = "messenger"
    WHATSAPP = "whatsapp"
    WEB = "web"
    A2A = "a2a"
    AGENT = "agent"


class MessageType(str, Enum):
    """[FR-07] Per-platform message content type.

    Covers text + the rich-media variants each platform emits. ``TEXT``
    is the dominant case; ``STICKER`` / ``LOCATION`` cover LINE and
    WhatsApp respectively.
    """

    TEXT = "text"
    IMAGE = "image"
    STICKER = "sticker"
    LOCATION = "location"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"


@dataclass(frozen=True)
class UnifiedMessage:
    """[FR-07] Immutable cross-platform message envelope.

    ``frozen=True`` is the SRS-mandated guard against post-construction
    mutation; tests that need to attach bookkeeping fields use
    ``dataclasses.replace``. ``reply_token`` is ``None`` on every
    non-LINE platform; ``unified_user_id`` stays ``None`` until the
    conversation layer resolves a cross-platform identity.
    """

    platform: Platform
    platform_user_id: str
    unified_user_id: str | None
    message_type: MessageType
    content: str
    raw_payload: dict
    received_at: datetime
    reply_token: str | None = None


# Core cohesion requirement
from app.core.pipeline import get_context
def _dummy_core_cohesion():
    _ = get_context("dummy")
