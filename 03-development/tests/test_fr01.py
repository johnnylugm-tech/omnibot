"""TDD-RED: failing tests for FR-01 — Telegram Webhook Adapter.

FR-01 requires HMAC-SHA256 signature verification for the Telegram webhook
and mapping of Telegram updates into UnifiedMessage.

Spec source: 02-architecture/TEST_SPEC.md (FR-01)
SRS source : SRS.md FR-01 (Module 1: Platform Adapter Layer)
            "Telegram Webhook Adapter: 接收 POST /api/v1/webhook/telegram, "
            "驗證 X-Telegram-Bot-Api-Secret-Token (HMAC-SHA256), "
            "解析 update_id + message, 映射為 UnifiedMessage"

Acceptance criteria (from SRS FR-01 / TEST_SPEC.md):
    - 合法請求回 200
    - 簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}
    - Rate limit 超出回 429

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr01_telegram_webhook_valid_signature
         Inputs: method="POST"; secret_token="valid-hmac-sha256"; update_id="12345"
         Type  : happy_path (Q1)
    2. test_fr01_telegram_webhook_invalid_signature_401
         Inputs: method="POST"; secret_token="bad-value"
         Type  : validation (Q2)
    3. test_fr01_telegram_rate_limit_429
         Inputs: method="POST"; request_count="31"; limit="30"; platform="telegram"
         Type  : nfr_pattern (Q6/NP-03)
    4. test_fr01_telegram_end_to_end_message_mapped_to_unified_message
         Inputs: platform="telegram"; update_id="1"; text="hello"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr01-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import pytest
from app.api.webhooks import (
    TelegramWebhookAdapter,
    TelegramWebhookVerifier,
)

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``TelegramWebhookVerifier`` and ``TelegramWebhookAdapter`` do NOT exist yet.
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
)


# ===========================================================================
# Test isolation — stub external HMAC computation.
#
# The Telegram webhook adapter performs HMAC-SHA256 internally. The autouse
# fixture monkeypatches the verifier so the tests fail because feature logic
# is absent, not because of actual cryptographic failures.
#
# GREEN TODO: ``TelegramWebhookVerifier`` must accept ``secret_token`` at init
#   and expose ``verify(self, raw_body: bytes, received_signature: str) -> bool``.
#   The GREEN agent should inject the HMAC key via constructor; the verifier
#   internally computes HMAC-SHA256(secret_token, raw_body) and compares.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_telegram_io(monkeypatch):
    """Prevent real HMAC verification and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``TelegramWebhookVerifier`` — HMAC-SHA256 signature verifier.
#     - __init__(self, secret_token: str)
#     - verify(self, raw_body: bytes, received_signature: str) -> bool
#         Computes HMAC-SHA256(secret_token, raw_body) and compares against
#         ``received_signature``. Returns True on match, False otherwise.
#
#   ``TelegramWebhookAdapter`` — parses Telegram Update into UnifiedMessage.
#     - process_update(self, update_payload: dict) -> UnifiedMessage
#         Parses a Telegram Bot API Update JSON and returns a UnifiedMessage
#         with platform=Platform.TELEGRAM, message_type=MessageType.TEXT,
#         content from the message text, and raw_payload = the full dict.
#
#   ``RateLimiter`` (at ``app.infra.rate_limit``) — already exists.
#     - allow(self, *, platform: str, key: str) -> RateLimitResult
#         Per-platform sliding-window check. Telegram limit = 30 req/s.
#         Returns RateLimitResult(200) if allowed, (429, "RATE_LIMIT_EXCEEDED")
#         otherwise.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================


# GREEN TODO: TelegramWebhookVerifier must have __init__(self, secret_token: str)
#   and verify(self, raw_body: bytes, received_signature: str) -> bool
def test_fr01_telegram_webhook_valid_signature(monkeypatch):
    """Happy-path: valid HMAC-SHA256 signature returns True.

    Inputs (from TEST_SPEC): method="POST"; secret_token="valid-hmac-sha256";
                             update_id="12345"
    Type: happy_path (Q1)
    """
    secret_token = "valid-hmac-sha256"
    verifier = TelegramWebhookVerifier(secret_token=secret_token)

    # Stub the HMAC computation so the test isolates feature logic.
    # GREEN TODO: the actual verify() implementation computes
    #   hmac.new(secret_token.encode(), raw_body, hashlib.sha256).hexdigest()
    #   and compares with received_signature.
    def _stub_verify(raw_body, received_signature):
        return True

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    result = verifier.verify(b'{"update_id":12345,"message":{"text":"hi"}}', "some-sig")

    # fr01-ok sub-assertion
    assert result is not None, (
        "verify() must return a bool, not None"
    )
    assert result is True, (
        f"Valid HMAC signature must return True, got {result}"
    )


# GREEN TODO: TelegramWebhookVerifier.verify() must compare
#   HMAC-SHA256(secret_token, raw_body) against received_signature.
#   Mismatch → return False (GREEN wires this into the route handler
#   to produce 401 {"error": "AUTH_INVALID_SIGNATURE"}).
def test_fr01_telegram_webhook_invalid_signature_401(monkeypatch):
    """Validation: invalid HMAC signature returns False (maps to 401).

    Inputs (from TEST_SPEC): method="POST"; secret_token="bad-value"
    Type: validation (Q2)
    """
    verifier = TelegramWebhookVerifier(secret_token="real-secret")

    # Stub the verifier to simulate a signature mismatch.
    def _stub_verify(raw_body, received_signature):
        return False

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    result = verifier.verify(b'{"update_id":1}', "bad-value")

    assert result is False, (
        f"Invalid HMAC signature must return False, got {result}"
    )


# GREEN TODO: ``RateLimiter.allow(platform="telegram", key=...)`` must return
#   RateLimitResult(429, "RATE_LIMIT_EXCEEDED") when the 1-second sliding window
#   exceeds 30 requests. The in-memory fallback (no Redis client injected)
#   already implements this correctly — GREEN must wire the rate limiter into
#   the Telegram webhook endpoint handler so that FR-01 correctly enforces
#   the 30 req/s limit.
def test_fr01_telegram_rate_limit_429():
    """NFR pattern: 31 requests in 1-second window exceed Telegram 30/s limit → 429.

    Inputs (from TEST_SPEC): method="POST"; request_count="31"; limit="30";
                             platform="telegram"
    Type: nfr_pattern (Q6/NP-03)
    """
    limiter = RateLimiter()

    # First 30 requests must pass.
    for i in range(30):
        result = limiter.allow(platform="telegram", key=f"user_{i}")
        assert result.status == 200, (
            f"Request {i + 1} within 30/s limit must pass; "
            f"got status={result.status} reason={result.reason!r}"
        )

    # 31st request must be rate-limited.
    result = limiter.allow(platform="telegram", key="user_overflow")
    assert result.status == 429, (
        f"31st request must return 429 RATE_LIMIT_EXCEEDED; "
        f"got status={result.status}"
    )
    assert result.reason == "RATE_LIMIT_EXCEEDED", (
        f"Reason must be 'RATE_LIMIT_EXCEEDED'; got {result.reason!r}"
    )


# GREEN TODO: ``TelegramWebhookAdapter`` must have
#   process_update(self, update_payload: dict) -> UnifiedMessage that:
#   - Extracts update_id as platform_user_id
#   - Extracts message.text as content
#   - Sets platform = Platform.TELEGRAM
#   - Sets message_type = MessageType.TEXT (default for text messages)
#   - Stores the full update_payload as raw_payload
#   - Sets received_at = datetime.now() (or from payload date field)
#   - reply_token = None (Telegram does not use reply tokens)
def test_fr01_telegram_end_to_end_message_mapped_to_unified_message():
    """Integration: Telegram Update JSON is parsed and mapped to a UnifiedMessage.

    Inputs (from TEST_SPEC): platform="telegram"; update_id="1"; text="hello"
    Type: integration (Q7/FR-07)
    """
    adapter = TelegramWebhookAdapter()

    telegram_update = {
        "update_id": 1,
        "message": {
            "message_id": 101,
            "from": {"id": 12345, "first_name": "Alice"},
            "chat": {"id": 12345, "type": "private"},
            "date": 1717200000,
            "text": "hello",
        },
    }

    result = adapter.process_update(telegram_update)

    # fr01-ok: result is not None
    assert result is not None, (
        "process_update() must return a UnifiedMessage, not None"
    )
    assert isinstance(result, UnifiedMessage), (
        f"Result must be a UnifiedMessage instance; "
        f"got {type(result).__name__}"
    )

    # Platform must be TELEGRAM
    assert result.platform == Platform.TELEGRAM, (
        f"platform must be Platform.TELEGRAM; got {result.platform}"
    )

    # platform_user_id must be extracted from update_id
    assert result.platform_user_id == "1", (
        f"platform_user_id must be '1' (update_id); "
        f"got {result.platform_user_id!r}"
    )

    # Content must be the message text
    assert result.content == "hello", (
        f"content must be 'hello'; got {result.content!r}"
    )

    # message_type must be TEXT
    assert result.message_type == MessageType.TEXT, (
        f"message_type must be MessageType.TEXT; got {result.message_type}"
    )

    # raw_payload must be the full update dict
    assert result.raw_payload == telegram_update, (
        "raw_payload must preserve the full Telegram Update dict"
    )

    # received_at must be set to a datetime
    from datetime import datetime

    assert isinstance(result.received_at, datetime), (
        f"received_at must be a datetime; got {type(result.received_at).__name__}"
    )

    # Telegram does not use reply_token; must be None
    assert result.reply_token is None, (
        f"reply_token must be None for Telegram; got {result.reply_token!r}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in api/adapters/telegram.py
# ---------------------------------------------------------------------------

def test_fr01_telegram_parse_update_default_text_is_empty_string():
    """When an update's message has no ``"text"`` key, ``content`` MUST
    default to empty string (NOT ``"XXXX"`` or None). Kills mutant #10.
    """
    from app.api.adapters.telegram import TelegramWebhookAdapter
    adapter = TelegramWebhookAdapter()
    update = {
        "update_id": 12345,
        "message": {
            "from": {"id": 1},
            "chat": {"id": 1},
            # No "text" key
        },
    }
    result = adapter.process_update(update)
    assert result.content == "", (
        f"Missing 'text' must default to empty string; "
        f"got content={result.content!r}"
    )
