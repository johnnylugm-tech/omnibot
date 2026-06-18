"""[FR-07] UnifiedMessage — immutable dataclass for cross-platform messages.

Citations:
  SRS.md FR-07: UnifiedMessage 資料結構：immutable dataclass，欄位含 platform(Platform enum),
    platform_user_id, unified_user_id(Optional), message_type(MessageType enum), content,
    raw_payload, received_at, reply_token(LINE 特有)
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class Platform(Enum):
    """[FR-07] Six supported platforms."""

    TELEGRAM = "telegram"
    LINE = "line"
    MESSENGER = "messenger"
    WHATSAPP = "whatsapp"
    WEB = "web"
    AGENT = "agent"


class MessageType(Enum):
    """[FR-07] Message content types."""

    TEXT = "text"
    IMAGE = "image"
    STICKER = "sticker"
    LOCATION = "location"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True)
class UnifiedMessage:
    """[FR-07] Immutable cross-platform message container.

    Citations:
      SRS.md FR-07
    """

    platform: Platform
    platform_user_id: str
    message_type: MessageType
    content: str
    raw_payload: Any
    received_at: datetime.datetime
    unified_user_id: Optional[str] = None
    reply_token: Optional[str] = None
