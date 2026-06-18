"""Integration tests: message processing pipeline — adapters → models → DST → response."""
import datetime


def test_unified_message_to_api_response_flow():
    """UnifiedMessage created from adapter payload flows to ApiResponse."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType
    from src.models.unified_response import UnifiedResponse, ResponseSource
    from src.models.api_response import ApiResponse

    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="user123",
        message_type=MessageType.TEXT,
        content="Hello bot!",
        raw_payload={"update_id": 1},
        received_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assert msg.platform == Platform.TELEGRAM
    assert msg.content == "Hello bot!"
    assert msg.unified_user_id is None

    resp = UnifiedResponse(content="Hi!", source=ResponseSource.RULE, confidence=0.9)
    assert resp.source == ResponseSource.RULE

    api_resp: ApiResponse[str] = ApiResponse(success=True, data=resp.content)
    assert api_resp.success is True
    assert api_resp.data == "Hi!"


def test_all_platforms_and_message_types():
    """All 6 Platform and all 7 MessageType values are valid UnifiedMessage inputs."""
    from src.models.unified_message import UnifiedMessage, Platform, MessageType

    now = datetime.datetime.now(datetime.timezone.utc)
    platforms = [Platform.TELEGRAM, Platform.LINE, Platform.MESSENGER,
                 Platform.WHATSAPP, Platform.WEB, Platform.AGENT]
    types = [MessageType.TEXT, MessageType.IMAGE, MessageType.STICKER,
             MessageType.LOCATION, MessageType.FILE, MessageType.AUDIO, MessageType.VIDEO]

    for platform in platforms:
        for msg_type in types:
            msg = UnifiedMessage(
                platform=platform,
                platform_user_id="u",
                message_type=msg_type,
                content="test",
                raw_payload={},
                received_at=now,
            )
            assert msg.platform == platform
            assert msg.message_type == msg_type


def test_adapter_verify_and_parse_pipeline():
    """Each adapter verifies and parses a payload without raising."""
    from src.adapters.telegram import TelegramWebhookVerifier
    from src.adapters.line import LineWebhookVerifier
    from src.adapters.messenger import MessengerWebhookVerifier
    from src.adapters.whatsapp import WhatsAppWebhookVerifier
    from src.adapters.web import WebPlatformAdapter
    from src.adapters.a2a import A2APlatformAdapter

    tg = TelegramWebhookVerifier(bot_token="tok:123")
    assert tg.verify(b"{}", "sig") is True
    parsed = tg.parse({"message": {"text": "hi"}})
    assert isinstance(parsed, dict)

    line = LineWebhookVerifier(channel_secret="secret")
    assert line.verify(b"{}", "sig") is True

    fb = MessengerWebhookVerifier(app_secret="appsecret")
    assert fb.verify(b"{}", "sig") is True
    fb_parsed = fb.parse({"entry": [{"messaging": []}]})
    assert isinstance(fb_parsed, dict)

    wa = WhatsAppWebhookVerifier(app_secret="wasecret", verify_token="watoken")
    assert wa.verify(b"{}", "sig") is True

    web = WebPlatformAdapter(session_ttl=1800)
    accepted = web.accept("sess-001")
    assert accepted is True
    web.close("sess-001")

    a2a = A2APlatformAdapter(agent_id="agent-001")
    sent = a2a.send({"action": "ping"})
    assert sent is True
    received = a2a.receive({"event": "pong"})
    assert received == {"event": "pong"}


def test_dialogue_state_transition_flow():
    """DialogueStateMachine + SlotFiller + ContextWindowManager work together."""
    from src.dst.dialogue_state import DialogueStateMachine, SlotFiller, ContextWindowManager

    dsm = DialogueStateMachine()
    assert dsm.state == "idle"
    new_state = dsm.transition("greet")
    assert isinstance(new_state, str)

    filler = SlotFiller()
    slots = filler.extract("book a flight to Taipei", [{"name": "destination", "type": "city"}])
    assert isinstance(slots, dict)

    ctx_mgr = ContextWindowManager(max_tokens=2048)
    ctx_mgr.add({"role": "user", "content": "Hello"})
    ctx_mgr.add({"role": "assistant", "content": "Hi!"})
    context = ctx_mgr.get_context()
    assert len(context) == 2
    assert context[0]["role"] == "user"


def test_emotion_analysis_and_tracking_pipeline():
    """EmotionAnalyzer classifies text; EmotionTracker records and trends."""
    from src.emotion.analyzer import EmotionAnalyzer, EmotionResult
    from src.emotion.tracker import EmotionTracker

    analyzer = EmotionAnalyzer()
    result = analyzer.analyze("I am very happy today!")
    assert isinstance(result, EmotionResult)
    assert isinstance(result.label, str)
    assert 0.0 <= result.score <= 1.0

    tracker = EmotionTracker()
    tracker.update(1, result.label, result.score)
    tracker.update(2, "neutral", 0.9)
    trend = tracker.trend()
    assert isinstance(trend, str)


def test_escalation_and_response_generation():
    """EscalationManager + ResponseGenerator integration."""
    from src.escalation.manager import EscalationManager
    from src.response.generator import ResponseGenerator

    escalation = EscalationManager()
    should = escalation.should_escalate({"sentiment": "negative", "turns": 10})
    assert should is False

    ticket = escalation.escalate("session-001", "user requested human")
    assert "ticket_id" in ticket
    assert "status" in ticket

    generator = ResponseGenerator()
    response = generator.generate("What is OmniBot?", [{"content": "OmniBot is a chatbot."}])
    assert isinstance(response, str)

    rendered = generator.render("Hello {name}!", {"name": "World"})
    assert rendered == "Hello World!"
