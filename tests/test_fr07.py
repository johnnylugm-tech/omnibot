"""[FR-07] TDD-RED: failing tests for UnifiedMessage data structure.

Citations:
  SRS.md FR-07
  TEST_SPEC.md FR-07
"""
import pytest


def test_fr07_unified_message_creation():
    """[FR-07] UnifiedMessage can be constructed with all required fields."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType
    import datetime

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="u123",
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={"update_id": 1, "message": {"text": "hello"}},
        received_at=datetime.datetime.utcnow(),
    )
    assert msg.platform == Platform.TELEGRAM
    assert msg.platform_user_id == "u123"
    assert msg.content == "hello"


def test_fr07_unified_message_frozen():
    """[FR-07] UnifiedMessage is immutable (frozen=True)."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType
    import datetime

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="u123",
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={},
        received_at=datetime.datetime.utcnow(),
    )
    with pytest.raises((AttributeError, TypeError)):
        msg.content = "changed"  # type: ignore


def test_fr07_unified_message_optional_fields():
    """[FR-07] unified_user_id and reply_token are optional."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType
    import datetime

    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="u456",
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={},
        received_at=datetime.datetime.utcnow(),
        unified_user_id=None,
        reply_token="replyabc123",
    )
    assert msg.reply_token == "replyabc123"
    assert msg.unified_user_id is None


def test_fr07_platform_enum_all_platforms():
    """[FR-07] Platform enum covers all 6 platforms."""
    from src.models.unified_message import Platform

    expected = {"TELEGRAM", "LINE", "MESSENGER", "WHATSAPP", "WEB", "AGENT"}
    actual = {p.name for p in Platform}
    assert expected == actual


def test_fr07_message_type_enum():
    """[FR-07] MessageType enum includes TEXT and other types."""
    from src.models.unified_message import MessageType

    assert hasattr(MessageType, "TEXT")
