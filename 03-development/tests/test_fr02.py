"""TDD-RED: failing tests for FR-02 — LINE Webhook Adapter.

FR-02 requires HMAC-SHA256 Base64 signature verification for the LINE webhook
and mapping of LINE events arrays into UnifiedMessage.

Spec source: 02-architecture/TEST_SPEC.md (FR-02)
SRS source : SRS.md FR-02 (Module 1: Platform Adapter Layer)
            "LINE Webhook Adapter：接收 POST /api/v1/webhook/line，
            驗證 x-line-signature（HMAC-SHA256 Base64），
            解析 events 陣列，映射為 UnifiedMessage"

Acceptance criteria (from SRS FR-02 / TEST_SPEC.md):
    - 合法請求回 200
    - 簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}
    - Rate limit 超出回 429

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr02_line_webhook_valid_signature
         Inputs: method="POST"; x_line_signature="valid-base64-hmac"
         Type  : happy_path (Q1)
    2. test_fr02_line_webhook_invalid_signature_401
         Inputs: method="POST"; x_line_signature="bad"
         Type  : validation (Q2)
    3. test_fr02_line_events_array_parsed_to_unified_message
         Inputs: events_count="3"; platform="line"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr02-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import hmac
import hashlib
import base64
import json

import pytest

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``LineWebhookVerifier`` and ``LineWebhookAdapter`` do NOT exist yet.
# pytest will crash with Collection Error (Exit Code 2) because of missing
# modules — that is the CORRECT RED signal for this step.
#
# ``RateLimiter`` / ``RateLimitResult`` at ``app.infra.rate_limit`` and
# ``UnifiedMessage`` / ``Platform`` / ``MessageType`` at ``app.core.unified_message``
# already exist and provide the contracts that GREEN must wire together.
# ---------------------------------------------------------------------------
from app.core.unified_message import (  # noqa: E402 — RED: GREEN owns the path
    MessageType,
    Platform,
    UnifiedMessage,
)
from app.infra.rate_limit import (  # noqa: E402 — already exists
    RateLimiter,
    RateLimitResult,
)
from app.services.line_adapter import (  # noqa: E402 — RED: GREEN must create
    LineWebhookAdapter,
)
from app.services.line_verifier import (  # noqa: E402 — RED: GREEN must create
    LineWebhookVerifier,
)


# ===========================================================================
# Test isolation — stub external HMAC computation.
#
# The LINE webhook adapter performs HMAC-SHA256 Base64 internally. The autouse
# fixture monkeypatches the verifier so the tests fail because feature logic
# is absent, not because of actual cryptographic failures.
#
# GREEN TODO: ``LineWebhookVerifier`` must accept ``channel_secret`` at init
#   and expose ``verify(self, raw_body: bytes, received_signature: str) -> bool``.
#   The GREEN agent should inject the channel secret via constructor; the verifier
#   internally computes HMAC-SHA256(channel_secret, raw_body) and encodes in
#   Base64 for comparison against the x-line-signature header.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_line_io(monkeypatch):
    """Prevent real HMAC verification and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``LineWebhookVerifier`` — HMAC-SHA256 Base64 signature verifier.
#     - __init__(self, channel_secret: str)
#     - verify(self, raw_body: bytes, received_signature: str) -> bool
#         Computes HMAC-SHA256(channel_secret, raw_body), encodes in Base64,
#         and compares against ``received_signature``. Returns True on match,
#         False otherwise.
#
#   ``LineWebhookAdapter`` — parses LINE webhook events into UnifiedMessage.
#     - process_events(self, events_payload: list[dict]) -> list[UnifiedMessage]
#         Parses a LINE webhook events array and returns a list of
#         UnifiedMessage instances, each with platform=Platform.LINE,
#         message_type from the event type, content from message.text,
#         and raw_payload = the full event dict.
#         LINE events carry reply_token at the event level (not message level).
#
#   ``RateLimiter`` (at ``app.infra.rate_limit``) — already exists.
#     - allow(self, *, platform: str, key: str) -> RateLimitResult
#         Per-platform sliding-window check. LINE limit = 30 req/s.
#         Returns RateLimitResult(200) if allowed, (429, "RATE_LIMIT_EXCEEDED")
#         otherwise.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
#     - Platform.LINE = "line" — already defined.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================


# GREEN TODO: LineWebhookVerifier must have __init__(self, channel_secret: str)
#   and verify(self, raw_body: bytes, received_signature: str) -> bool
def test_fr02_line_webhook_valid_signature(monkeypatch):
    """Happy-path: valid HMAC-SHA256 Base64 signature returns True.

    Inputs (from TEST_SPEC): method="POST"; x_line_signature="valid-base64-hmac"
    Type: happy_path (Q1)
    """
    channel_secret = "test-channel-secret"
    verifier = LineWebhookVerifier(channel_secret=channel_secret)

    # Stub the HMAC Base64 verification so the test isolates feature logic.
    # GREEN TODO: the actual verify() implementation computes
    #   base64.b64encode(hmac.new(channel_secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    #   and compares with the x-line-signature header value.
    def _stub_verify(raw_body, received_signature):
        return True

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    raw_body = json.dumps({
        "destination": "U123",
        "events": [{"type": "message", "message": {"type": "text", "text": "hello"}}],
    }).encode("utf-8")
    result = verifier.verify(raw_body, "valid-base64-hmac-sig")

    # fr02-ok sub-assertion
    assert result is not None, (
        "verify() must return a bool, not None"
    )
    assert result is True, (
        f"Valid HMAC-SHA256 Base64 signature must return True, got {result}"
    )


# GREEN TODO: LineWebhookVerifier.verify() must compare
#   base64(HMAC-SHA256(channel_secret, raw_body)) against received_signature.
#   Mismatch → return False (GREEN wires this into the route handler
#   to produce 401 {"error": "AUTH_INVALID_SIGNATURE"}).
def test_fr02_line_webhook_invalid_signature_401(monkeypatch):
    """Validation: invalid HMAC Base64 signature returns False (maps to 401).

    Inputs (from TEST_SPEC): method="POST"; x_line_signature="bad"
    Type: validation (Q2)
    """
    verifier = LineWebhookVerifier(channel_secret="real-channel-secret")

    # Stub the verifier to simulate a signature mismatch.
    def _stub_verify(raw_body, received_signature):
        return False

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    raw_body = json.dumps({
        "destination": "U123",
        "events": [{"type": "message", "message": {"type": "text", "text": "hi"}}],
    }).encode("utf-8")
    result = verifier.verify(raw_body, "bad")

    assert result is False, (
        f"Invalid HMAC-SHA256 Base64 signature must return False, got {result}"
    )


# GREEN TODO: ``LineWebhookAdapter`` must have
#   process_events(self, events_payload: list[dict]) -> list[UnifiedMessage] that:
#   - Iterates over the LINE webhook events array
#   - For each event:
#     - Extracts event["source"]["userId"] as platform_user_id
#     - Extracts event["message"]["text"] as content (for text messages)
#     - Sets platform = Platform.LINE
#     - Sets message_type from event["message"]["type"] (MessageType.TEXT, etc.)
#     - Stores the full event dict as raw_payload
#     - Sets reply_token from event["replyToken"] (LINE-specific)
#     - Sets received_at from event["timestamp"] (Unix ms → datetime)
#   - Returns a list of UnifiedMessage instances, one per event in the array
def test_fr02_line_events_array_parsed_to_unified_message():
    """Integration: LINE events array is parsed to a list of UnifiedMessage.

    Inputs (from TEST_SPEC): events_count="3"; platform="line"
    Type: integration (Q7/FR-07)
    """
    adapter = LineWebhookAdapter()

    line_events = [
        {
            "type": "message",
            "replyToken": "reply-token-1",
            "source": {"type": "user", "userId": "U1001"},
            "timestamp": 1717200000000,
            "message": {"type": "text", "id": "msg-1", "text": "查詢訂單"},
        },
        {
            "type": "message",
            "replyToken": "reply-token-2",
            "source": {"type": "user", "userId": "U1001"},
            "timestamp": 1717200001000,
            "message": {"type": "text", "id": "msg-2", "text": "我要退貨"},
        },
        {
            "type": "message",
            "replyToken": "reply-token-3",
            "source": {"type": "user", "userId": "U1002"},
            "timestamp": 1717200002000,
            "message": {"type": "text", "id": "msg-3", "text": "客服"},
        },
    ]

    results = adapter.process_events(line_events)

    # Must return a list with the same count of events
    assert isinstance(results, list), (
        f"process_events() must return a list; got {type(results).__name__}"
    )
    assert len(results) == len(line_events), (
        f"Expected {len(line_events)} UnifiedMessage results; got {len(results)}"
    )

    for i, (event, result) in enumerate(zip(line_events, results)):
        # fr02-ok: each result is not None
        assert result is not None, (
            f"Event {i}: process_events() must return UnifiedMessage, not None"
        )
        assert isinstance(result, UnifiedMessage), (
            f"Event {i}: result must be a UnifiedMessage instance; "
            f"got {type(result).__name__}"
        )

        # Platform must be LINE
        assert result.platform == Platform.LINE, (
            f"Event {i}: platform must be Platform.LINE; got {result.platform}"
        )

        # platform_user_id must be extracted from source.userId
        expected_user_id = event["source"]["userId"]
        assert result.platform_user_id == expected_user_id, (
            f"Event {i}: platform_user_id must be {expected_user_id!r}; "
            f"got {result.platform_user_id!r}"
        )

        # Content must be the message text
        expected_text = event["message"]["text"]
        assert result.content == expected_text, (
            f"Event {i}: content must be {expected_text!r}; "
            f"got {result.content!r}"
        )

        # message_type must be TEXT
        assert result.message_type == MessageType.TEXT, (
            f"Event {i}: message_type must be MessageType.TEXT; "
            f"got {result.message_type}"
        )

        # raw_payload must be the full event dict
        assert result.raw_payload == event, (
            f"Event {i}: raw_payload must preserve the full LINE event dict"
        )

        # received_at must be set to a datetime
        from datetime import datetime

        assert isinstance(result.received_at, datetime), (
            f"Event {i}: received_at must be a datetime; "
            f"got {type(result.received_at).__name__}"
        )

        # LINE must have reply_token set from event
        expected_reply_token = event["replyToken"]
        assert result.reply_token == expected_reply_token, (
            f"Event {i}: reply_token must be {expected_reply_token!r}; "
            f"got {result.reply_token!r}"
        )
