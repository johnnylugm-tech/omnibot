"""[FR-07] Tests for UnifiedMessage data structure.

Citations:
  SRS.md FR-07
  TEST_SPEC.md FR-07
"""
import datetime
import pytest


def test_fr07_unified_message_telegram_valid():
    """[FR-07] UnifiedMessage created with platform=telegram, message_type=text, content=hello."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="u123",
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={"update_id": 1},
        received_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    assert msg is not None
    assert msg.platform == Platform.TELEGRAM
    assert msg.message_type == MessageType.TEXT
    assert msg.content == "hello"


def test_fr07_unified_message_frozen_immutable():
    """[FR-07] Attempting to mutate content raises error (frozen=True)."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="u123",
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={},
        received_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    with pytest.raises((AttributeError, TypeError)):
        msg.content = "mutated"  # type: ignore


def test_fr07_unified_message_all_platforms_valid():
    """[FR-07] All 6 platforms telegram,line,messenger,whatsapp,web,a2a can create UnifiedMessage."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType

    for p in [Platform.TELEGRAM, Platform.LINE, Platform.MESSENGER,
              Platform.WHATSAPP, Platform.WEB, Platform.AGENT]:
        msg = UnifiedMessage(
            platform=p,
            platform_user_id="u1",
            message_type=MessageType.TEXT,
            content="test",
            raw_payload={},
            received_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        assert msg.platform == p


def test_fr07_must_not_mutate_frozen_dataclass():
    """[FR-07] Setting content='hacked' on frozen dataclass raises FrozenInstanceError."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType
    from dataclasses import FrozenInstanceError

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="u1",
        message_type=MessageType.TEXT,
        content="original",
        raw_payload={},
        received_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        msg.content = "hacked"  # type: ignore
