"""[FR-07] UnifiedMessage — immutable cross-platform message envelope.

This module defines the single canonical envelope every adapter (FR-01..06)
and downstream PALADIN / Knowledge / DST stage reads. It exists so that the
six adapter implementations do not each invent their own internal message
type and so that cross-platform routing can be expressed once.

The envelope is a ``@dataclass(frozen=True)`` — once an adapter writes the
record, downstream code MUST treat it as read-only. Any "edit" (e.g. attaching
a DST slot, or stamping a unified_user_id after identity resolution) must be
expressed as a new instance via ``dataclasses.replace`` rather than by mutating
the original.

Citations:
    - SRS.md:30 — FR-07 acceptance criteria: "UnifiedMessage 資料結構：
      immutable dataclass，欄位含 platform(Platform enum), platform_user_id,
      unified_user_id(Optional), message_type(MessageType enum), content,
      raw_payload, received_at, reply_token(LINE 特有)。所有平台訊息皆可
      建立合法 UnifiedMessage 實例；frozen=True 確保不可變"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Platform(str, Enum):
    """[FR-07] The originating channel of a ``UnifiedMessage``.

    Values are lower-case strings so they round-trip cleanly through JSON
    without an explicit ``.value`` access in adapters / logs.

    Citations:
        - SRS.md:30 — FR-07 lists ``platform(Platform enum)`` as one of the
          envelope's required fields; FR-01..06 (telegram / line / messenger /
          whatsapp / web / a2a) all map into this enum.
    """

    TELEGRAM = "telegram"
    LINE = "line"
    MESSENGER = "messenger"
    WHATSAPP = "whatsapp"
    WEB = "web"
    A2A = "a2a"


class MessageType(str, Enum):
    """[FR-07] Payload classification inside a ``UnifiedMessage``.

    Citations:
        - SRS.md:30 — FR-07 lists ``message_type(MessageType enum)`` as one of
          the envelope's required fields; FR-100 multimedia messages map into
          the IMAGE / STICKER / LOCATION / FILE members below.
    """

    TEXT = "text"
    IMAGE = "image"
    STICKER = "sticker"
    LOCATION = "location"
    FILE = "file"


@dataclass(frozen=True)
class UnifiedMessage:
    """[FR-07] Immutable cross-platform message envelope.

    Every platform adapter writes one of these exactly once. Downstream PALADIN
    / Knowledge / DST stages MUST treat the instance as read-only — the
    ``frozen=True`` flag installs a ``__setattr__`` that rejects all writes
    with ``dataclasses.FrozenInstanceError`` so the immutability contract is
    structural, not merely conventional.

    To attach new information (e.g. resolved ``unified_user_id``) use
    ``dataclasses.replace(msg, unified_user_id="...")`` to derive a new
    instance.

    Citations:
        - SRS.md:30 — FR-07 acceptance criteria: "所有平台訊息皆可建立合法
          UnifiedMessage 實例；frozen=True 確保不可變". The field set below
          (platform / platform_user_id / unified_user_id / message_type /
          content / raw_payload / received_at / reply_token) is the literal
          list from that row; ``reply_token`` is None for every platform
          except LINE (SRS: "reply_token(LINE 特有)").
    """

    platform: Platform
    platform_user_id: str
    unified_user_id: str | None
    message_type: MessageType
    content: str
    raw_payload: Any
    received_at: datetime
    reply_token: str | None  # LINE-only; None on every other platform
