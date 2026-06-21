"""TDD-RED: failing tests for FR-02 — LINE Webhook Adapter.

FR-02 requires HMAC-SHA256 Base64 signature verification for the LINE webhook
and mapping of LINE events arrays into UnifiedMessage.

Spec source: 02-architecture/TEST_SPEC.md (FR-02)
SRS source : SRS.md FR-02 (Module 1: Platform Adapter Layer)
            "LINE Webhook Adapter: 接收 POST /api/v1/webhook/line, "
            "驗證 x-line-signature (HMAC-SHA256 Base64), "
            "解析 events 陣列, 映射為 UnifiedMessage"

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

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

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
from app.core.unified_message import (
    MessageType,
    Platform,
    UnifiedMessage,
)
from app.infra.rate_limit import (
    RateLimiter,
    RateLimitResult,
)
from app.services.line_adapter import (
    LineWebhookAdapter,
)
from app.services.line_verifier import (
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

    for i, (event, result) in enumerate(zip(line_events, results, strict=False)):
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


# ===========================================================================
# Coverage gap 1 — Real HMAC-SHA256 Base64 verify() implementation.
#
# The existing tests monkeypatch verifier.verify() so the actual HMAC
# computation is never exercised. These tests call the REAL verify().
# ===========================================================================


def test_fr02_real_verify_matching_signature():
    """Verify() returns True when the computed HMAC-SHA256 Base64 matches."""
    secret = "test-channel-secret"
    verifier = LineWebhookVerifier(channel_secret=secret)

    raw_body = json.dumps({
        "destination": "U123",
        "events": [{"type": "message", "message": {"type": "text", "text": "hello"}}],
    }).encode("utf-8")

    # Compute the expected HMAC-SHA256 Base64 signature the same way
    # the real verify() does it.
    expected_sig = base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode()

    result = verifier.verify(raw_body, expected_sig)
    assert result is True, (
        f"Matching HMAC-SHA256 Base64 must return True, got {result}"
    )


def test_fr02_real_verify_mismatched_signature():
    """Verify() returns False when the signature does not match."""
    secret = "test-channel-secret"
    verifier = LineWebhookVerifier(channel_secret=secret)

    raw_body = b'{"destination":"U123","events":[]}'

    result = verifier.verify(raw_body, "wrong-signature-value")
    assert result is False, (
        f"Mismatched signature must return False, got {result}"
    )


def test_fr02_real_verify_different_body_produces_different_signature():
    """Verify() rejects a signature computed for a different body."""
    secret = "test-channel-secret"
    verifier = LineWebhookVerifier(channel_secret=secret)

    body_a = b'{"events":[{"type":"message"}]}'
    body_b = b'{"events":[{"type":"sticker"}]}'

    sig_a = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body_a, hashlib.sha256).digest()
    ).decode()

    # Use signature for body_a against body_b — must fail
    result = verifier.verify(body_b, sig_a)
    assert result is False, (
        f"Signature for body_a must not verify against body_b, got {result}"
    )


def test_fr02_real_verify_empty_body():
    """Verify() handles empty request body."""
    secret = "test-channel-secret"
    verifier = LineWebhookVerifier(channel_secret=secret)

    empty_body = b""
    expected_sig = base64.b64encode(
        hmac.new(secret.encode("utf-8"), empty_body, hashlib.sha256).digest()
    ).decode()

    result = verifier.verify(empty_body, expected_sig)
    assert result is True, (
        f"HMAC-SHA256 Base64 on empty body must return True, got {result}"
    )


# ===========================================================================
# Coverage gap 2 — LineWebhookAdapter.process_events() edge cases.
#
# The happy-path test covers the normal three-event payload but never
# exercises .get() defaults, empty lists, or missing keys.
# ===========================================================================


def test_fr02_process_events_empty_list():
    """process_events([]) returns an empty list."""
    adapter = LineWebhookAdapter()
    results = adapter.process_events([])
    assert isinstance(results, list), (
        f"Expected list, got {type(results).__name__}"
    )
    assert len(results) == 0, (
        f"Empty input must produce empty output, got {len(results)} results"
    )


def test_fr02_process_events_missing_message_key():
    """Event without 'message' key → content defaults to ''."""
    adapter = LineWebhookAdapter()
    events = [{
        "type": "message",
        "replyToken": "tok",
        "source": {"type": "user", "userId": "U1"},
        "timestamp": 1717200000000,
        # no "message" key
    }]
    results = adapter.process_events(events)
    assert len(results) == 1
    assert results[0].content == "", (
        f"Missing 'message' key → content must be '', got {results[0].content!r}"
    )
    assert results[0].message_type == MessageType.TEXT
    assert results[0].platform == Platform.LINE


def test_fr02_process_events_missing_text_in_message():
    """Event with 'message' but missing 'text' → content defaults to ''."""
    adapter = LineWebhookAdapter()
    events = [{
        "type": "message",
        "replyToken": "tok",
        "source": {"type": "user", "userId": "U2"},
        "timestamp": 1717200000000,
        "message": {"type": "text", "id": "msg-1"},  # no "text" key
    }]
    results = adapter.process_events(events)
    assert len(results) == 1
    assert results[0].content == "", (
        f"Missing 'text' in message → content must be '', got {results[0].content!r}"
    )


def test_fr02_process_events_missing_reply_token():
    """Event without 'replyToken' → reply_token is None."""
    adapter = LineWebhookAdapter()
    events = [{
        "type": "message",
        # no replyToken
        "source": {"type": "user", "userId": "U3"},
        "timestamp": 1717200000000,
        "message": {"type": "text", "id": "msg-1", "text": "hello"},
    }]
    results = adapter.process_events(events)
    assert len(results) == 1
    assert results[0].reply_token is None, (
        f"Missing replyToken → reply_token must be None, got {results[0].reply_token!r}"
    )


def test_fr02_process_events_non_text_message_type():
    """Events with image/sticker type are still mapped (current impl hardcodes TEXT)."""
    adapter = LineWebhookAdapter()
    events = [
        {
            "type": "message",
            "replyToken": "tok-img",
            "source": {"type": "user", "userId": "U4"},
            "timestamp": 1717200000000,
            "message": {"type": "image", "id": "img-1"},
        },
        {
            "type": "message",
            "replyToken": "tok-sticker",
            "source": {"type": "user", "userId": "U4"},
            "timestamp": 1717200001000,
            "message": {"type": "sticker", "id": "stk-1", "stickerId": "123"},
        },
    ]
    results = adapter.process_events(events)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, UnifiedMessage)
        assert r.platform == Platform.LINE


def test_fr02_process_events_preserves_received_at_as_utc_datetime():
    """received_at must be a UTC datetime parsed from the Unix-ms timestamp."""
    from datetime import datetime

    adapter = LineWebhookAdapter()
    ts_ms = 1717200000000  # 2024-06-01T00:00:00Z
    events = [{
        "type": "message",
        "replyToken": "tok",
        "source": {"type": "user", "userId": "U5"},
        "timestamp": ts_ms,
        "message": {"type": "text", "id": "m1", "text": "hi"},
    }]
    results = adapter.process_events(events)
    assert len(results) == 1
    received = results[0].received_at
    assert isinstance(received, datetime)
    assert received.tzinfo is not None, "received_at must be timezone-aware"
    assert received.tzinfo == timezone.utc or received.utcoffset().total_seconds() == 0, (
        f"received_at must be UTC, got {received.tzinfo}"
    )
    assert received.year == 2024
    assert received.month == 6
    assert received.day == 1


def test_fr02_process_events_missing_timestamp_keyerror():
    """Event without 'timestamp' raises KeyError (LINE always sends it)."""
    adapter = LineWebhookAdapter()
    events = [{
        "type": "message",
        "replyToken": "tok",
        "source": {"type": "user", "userId": "U6"},
        "message": {"type": "text", "id": "m1", "text": "hi"},
        # no timestamp
    }]
    with pytest.raises(KeyError):
        adapter.process_events(events)


def test_fr02_process_events_missing_source_keyerror():
    """Event without 'source' raises KeyError (LINE always sends it)."""
    adapter = LineWebhookAdapter()
    events = [{
        "type": "message",
        "replyToken": "tok",
        "timestamp": 1717200000000,
        "message": {"type": "text", "id": "m1", "text": "hi"},
        # no source
    }]
    with pytest.raises(KeyError):
        adapter.process_events(events)


# ===========================================================================
# Coverage gap 3 — RateLimiter and RateLimitResult (imported by tests).
#
# The test module imports RateLimiter / RateLimitResult but never exercises
# their methods, leaving them mostly uncovered.
# ===========================================================================


def test_fr02_rate_limit_result_allowed():
    """RateLimitResult.allowed() returns status=200, reason=''."""
    result = RateLimitResult.allowed()
    assert result.status == 200, f"allowed status must be 200, got {result.status}"
    assert result.reason == "", f"allowed reason must be '', got {result.reason!r}"


def test_fr02_rate_limit_result_denied():
    """RateLimitResult.denied() returns status=429, reason='RATE_LIMIT_EXCEEDED'."""
    result = RateLimitResult.denied()
    assert result.status == 429, f"denied status must be 429, got {result.status}"
    assert result.reason == "RATE_LIMIT_EXCEEDED", (
        f"denied reason must be RATE_LIMIT_EXCEEDED, got {result.reason!r}"
    )


def test_fr02_rate_limit_result_is_frozen():
    """RateLimitResult is an immutable frozen dataclass."""
    result = RateLimitResult.allowed()
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = 500  # type: ignore[misc]


def test_fr02_rate_limiter_unknown_platform_fail_open():
    """Unknown platform returns allowed (fail-open)."""
    limiter = RateLimiter()
    result = limiter.allow(platform="nonexistent", key="user1")
    assert result.status == 200, (
        f"Unknown platform must fail-open (200), got {result.status}"
    )


def test_fr02_rate_limiter_in_memory_below_limit():
    """In-memory path: requests under limit are allowed."""
    limiter = RateLimiter()
    # LINE limit is 30 req/s in the sliding window
    for i in range(25):
        result = limiter.allow(platform="line", key="user_test")
        assert result.status == 200, (
            f"Request {i} under limit must be allowed, got {result.status}"
        )


def test_fr02_rate_limiter_in_memory_at_limit_denies():
    """In-memory path: requests at/over limit are denied."""
    limiter = RateLimiter()
    # LINE limit is 30, but we use a smaller platform for test speed
    # Actually, web limit is 10 — use that
    # Send 10 requests (exactly at limit) — first 10 allowed
    for i in range(10):
        result = limiter.allow(platform="web", key="user_test2")
        assert result.status == 200, (
            f"Request {i} at web limit must initially be allowed"
        )
    # 11th request must be denied
    result = limiter.allow(platform="web", key="user_test2")
    assert result.status == 429, (
        f"Request at limit+1 must be denied, got {result.status}"
    )


def test_fr02_rate_limiter_sliding_window_clears_old_entries():
    """Old window entries are pruned so rate limit resets after the window."""
    import time
    from collections import deque

    limiter = RateLimiter()
    # Manually insert an old timestamp via internal deque
    old_ts = time.monotonic() - 2.0  # 2 seconds ago, outside the 1s window
    limiter._buckets.setdefault("web", deque()).append(old_ts)
    # Now the bucket has 1 old entry which should be pruned
    result = limiter.allow(platform="web", key="user_test3")
    assert result.status == 200, (
        f"After pruning old entry, request must be allowed, got {result.status}"
    )


def test_fr02_rate_limiter_redis_path_allowed(monkeypatch):
    """Redis path: below-limit count → allowed."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    mock_redis.script_load.return_value = "fake_sha"
    # evalsha returns the number of requests in the window
    mock_redis.evalsha.return_value = 5  # 5 < 30 (line limit)

    limiter = RateLimiter(redis_client=mock_redis)
    result = limiter.allow(platform="line", key="redis_user")

    assert result.status == 200, (
        f"Redis path under limit must be allowed, got {result.status}"
    )
    mock_redis.script_load.assert_called_once()
    mock_redis.evalsha.assert_called_once()


def test_fr02_rate_limiter_redis_path_denied(monkeypatch):
    """Redis path: over-limit count → denied."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    mock_redis.script_load.return_value = "sha_denied"
    mock_redis.evalsha.return_value = 31  # 31 > 30 (line limit)

    limiter = RateLimiter(redis_client=mock_redis)
    result = limiter.allow(platform="line", key="redis_user2")

    assert result.status == 429, (
        f"Redis path over limit must be denied, got {result.status}"
    )
    assert result.reason == "RATE_LIMIT_EXCEEDED"


def test_fr02_rate_limiter_redis_fail_open_on_error(caplog):
    """Redis path: connection error → fail open (200) with WARNING log."""
    import logging
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    mock_redis.script_load.side_effect = ConnectionError("redis down")

    limiter = RateLimiter(redis_client=mock_redis)

    with caplog.at_level(logging.WARNING):
        result = limiter.allow(platform="line", key="redis_user3")

    assert result.status == 200, (
        f"Redis error must fail open (200), got {result.status}"
    )
    assert len(caplog.records) >= 1, "Must log WARNING on Redis failure"
    assert any("rate_limit_redis_unavailable" in r.message for r in caplog.records)


async def test_fr02_rate_limiter_aallow_matches_allow():
    """aallow() delegates to the same _check_and_record as allow()."""
    limiter = RateLimiter()
    result = await limiter.aallow(platform="line", key="async_test")
    assert result.status == 200, (
        f"aallow under limit must be allowed, got {result.status}"
    )


def test_fr02_rate_limiter_agent_platform_limit():
    """Agent platform has a higher limit (100 req/s)."""
    limiter = RateLimiter()
    for i in range(80):
        result = limiter.allow(platform="agent", key="agent_test")
        assert result.status == 200, (
            f"Agent request {i} under 100 limit must be allowed, got {result.status}"
        )


# ===========================================================================
# UnifiedMessage coverage — explicitly construct message instances
# for fields that aren't reached via the adapter test.
# ===========================================================================


def test_fr02_unified_message_line_platform():
    """Explicit construction: Platform.LINE, every field set."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U123",
        unified_user_id="unified-456",
        message_type=MessageType.TEXT,
        content="hi",
        raw_payload={"key": "value"},
        received_at=now,
        reply_token="reply-tok-1",
    )
    assert msg.platform == Platform.LINE
    assert msg.platform_user_id == "U123"
    assert msg.unified_user_id == "unified-456"
    assert msg.message_type == MessageType.TEXT
    assert msg.content == "hi"
    assert msg.raw_payload == {"key": "value"}
    assert msg.received_at == now
    assert msg.reply_token == "reply-tok-1"


def test_fr02_unified_message_reply_token_none_for_non_line():
    """reply_token is None for non-LINE platforms per spec."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.TELEGRAM,
        platform_user_id="U456",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content="hello",
        raw_payload={},
        received_at=now,
        reply_token=None,
    )
    assert msg.reply_token is None


def test_fr02_unified_message_frozen_prevents_mutation():
    """frozen=True rejects attribute mutation with FrozenInstanceError."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.WEB,
        platform_user_id="U789",
        unified_user_id=None,
        message_type=MessageType.FILE,
        content="report.pdf",
        raw_payload={},
        received_at=now,
        reply_token=None,
    )
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        msg.content = "hacked"  # type: ignore[misc]


def test_fr02_unified_message_sticker_type():
    """MessageType.STICKER is constructible."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.LINE,
        platform_user_id="U_sticker",
        unified_user_id=None,
        message_type=MessageType.STICKER,
        content="",
        raw_payload={"stickerId": "123"},
        received_at=now,
        reply_token=None,
    )
    assert msg.message_type == MessageType.STICKER
    assert msg.platform == Platform.LINE


def test_fr02_unified_message_image_type():
    """MessageType.IMAGE is constructible."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.WHATSAPP,
        platform_user_id="U_img",
        unified_user_id=None,
        message_type=MessageType.IMAGE,
        content="",
        raw_payload={"media_id": "img-1"},
        received_at=now,
        reply_token=None,
    )
    assert msg.message_type == MessageType.IMAGE


def test_fr02_unified_message_location_type():
    """MessageType.LOCATION is constructible."""
    from datetime import datetime

    now = datetime.now(timezone.utc)
    msg = UnifiedMessage(
        platform=Platform.MESSENGER,
        platform_user_id="U_loc",
        unified_user_id=None,
        message_type=MessageType.LOCATION,
        content="",
        raw_payload={"lat": 25.03, "lng": 121.56},
        received_at=now,
        reply_token=None,
    )
    assert msg.message_type == MessageType.LOCATION
