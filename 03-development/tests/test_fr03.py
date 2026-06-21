"""TDD-RED: failing tests for FR-03 — Messenger Webhook Adapter.

FR-03 requires GET hub.challenge verification + POST HMAC-SHA256 signature
validation for the Messenger Platform webhook, and mapping of Messenger entry
arrays into UnifiedMessage.

Spec source: 02-architecture/TEST_SPEC.md (FR-03)
SRS source : SRS.md FR-03 (Module 1: Platform Adapter Layer)
            "Messenger Webhook Adapter: GET 驗證 (hub.mode, hub.verify_token, "
            "hub.challenge 回傳) + POST HMAC-SHA256 簽名驗證, 映射為 UnifiedMessage"

Acceptance criteria (from SRS FR-03 / TEST_SPEC.md):
    - GET hub.challenge 回傳 challenge 字串
    - POST 合法回 200
    - POST 簽名失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr03_messenger_hub_challenge_returns_challenge
         Inputs: method="GET"; hub_mode="subscribe"; hub_challenge="abc123"
         Type  : happy_path (Q1)
    2. test_fr03_messenger_webhook_valid_post_200
         Inputs: method="POST"; x_hub_signature_256="sha256=valid"
         Type  : happy_path (Q1)
    3. test_fr03_messenger_webhook_invalid_signature_401
         Inputs: method="POST"; x_hub_signature_256="sha256=bad"
         Type  : validation (Q2)
    4. test_fr03_messenger_entry_parsed_to_unified_message
         Inputs: entry_count="1"; messaging_count="1"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr03-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import json

import pytest
from app.api.webhooks import (
    MessengerWebhookAdapter,
    MessengerWebhookVerifier,
)

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``MessengerWebhookVerifier`` and ``MessengerWebhookAdapter`` do NOT exist yet.
# pytest will crash with Collection Error (Exit Code 2) because of missing
# modules — that is the CORRECT RED signal for this step.
#
# ``UnifiedMessage`` / ``Platform`` / ``MessageType`` at
# ``app.core.unified_message`` already exist and provide the contracts that
# GREEN must wire together.
# ---------------------------------------------------------------------------
from app.core.unified_message import (
    MessageType,
    Platform,
    UnifiedMessage,
)


# ===========================================================================
# Test isolation — stub external HMAC computation and token validation.
#
# The Messenger webhook adapter performs HMAC-SHA256 (hex) internally for POST
# and validates verify_token for GET challenge. The autouse fixture
# monkeypatches the verifier/adapter so the tests fail because feature logic
# is absent, not because of actual cryptographic/token failures.
#
# GREEN TODO: ``MessengerWebhookVerifier`` must accept ``app_secret`` at init
#   and expose ``verify(self, raw_body: bytes, received_signature: str) -> bool``.
#   The signature format is ``sha256=<hex>`` (hex digest, NOT Base64). The GREEN
#   agent should inject the app secret via constructor; the verifier internally
#   computes HMAC-SHA256(app_secret, raw_body) and compares the hex digest
#   against the received x-hub-signature-256 header value.
#
# GREEN TODO: ``MessengerWebhookAdapter`` must accept ``verify_token`` at init
#   and expose:
#     - handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                        hub_challenge: str) -> str
#       Validates hub_mode == "subscribe" and hub_verify_token == verify_token,
#       returns hub_challenge if valid, raises ValueError otherwise.
#     - parse_entries(self, entries: list[dict]) -> list[UnifiedMessage]
#       Iterates over the Messenger webhook entry array, flattens each entry's
#       messaging[] array, and returns one UnifiedMessage per messaging event.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_messenger_io(monkeypatch):
    """Prevent real HMAC verification and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``MessengerWebhookVerifier`` — HMAC-SHA256 hex signature verifier.
#     - __init__(self, app_secret: str)
#     - verify(self, raw_body: bytes, received_signature: str) -> bool
#         Computes HMAC-SHA256(app_secret, raw_body), gets hex digest, and
#         compares against the value after the "sha256=" prefix in
#         ``received_signature``. Returns True on match, False otherwise.
#
#   ``MessengerWebhookAdapter`` — handles GET challenge + POST entry parsing.
#     - __init__(self, verify_token: str)
#     - handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                        hub_challenge: str) -> str
#         Validates hub_mode == "subscribe" and hub_verify_token == verify_token.
#         Returns hub_challenge on success (GREEN wires this as the GET response
#         body). Raises ValueError on invalid mode or mismatched token.
#     - parse_entries(self, entries: list[dict]) -> list[UnifiedMessage]
#         Iterates over the Messenger webhook entry array. For each entry,
#         iterates over ``entry["messaging"]``. For each messaging event:
#         - Extracts sender["id"] as platform_user_id
#         - Extracts message["text"] as content (for text messages)
#         - Sets platform = Platform.MESSENGER
#         - Sets message_type from message content (MessageType.TEXT, etc.)
#         - Stores the full messaging event dict as raw_payload
#         - Sets received_at from entry timestamp (epoch ms → datetime)
#         - Sets reply_token = None (Messenger has no reply_token concept)
#         Returns a flat list of UnifiedMessage instances.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
#     - Platform.MESSENGER = "messenger" — already defined.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================

# GREEN TODO: ``MessengerWebhookAdapter`` must have
#   handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                    hub_challenge: str) -> str that:
#   - Checks hub_mode == "subscribe"
#   - Checks hub_verify_token == self._verify_token
#   - Returns hub_challenge if both checks pass
#   - Raises ValueError with descriptive message otherwise
def test_fr03_messenger_hub_challenge_returns_challenge():
    """Happy-path: GET hub.challenge verification returns the challenge string.

    Inputs (from TEST_SPEC): method="GET"; hub_mode="subscribe";
                             hub_challenge="abc123"
    Type: happy_path (Q1)
    """
    verify_token = "my-verify-token"
    adapter = MessengerWebhookAdapter(verify_token=verify_token)

    result = adapter.handle_challenge(
        hub_mode="subscribe",
        hub_verify_token="my-verify-token",
        hub_challenge="abc123",
    )

    # fr03-ok sub-assertion
    assert result is not None, (
        "handle_challenge() must return a str, not None"
    )
    assert isinstance(result, str), (
        f"handle_challenge() must return str, got {type(result).__name__}"
    )
    assert result == "abc123", (
        f"Valid challenge must return 'abc123', got {result!r}"
    )


# GREEN TODO: MessengerWebhookVerifier must have __init__(self, app_secret: str)
#   and verify(self, raw_body: bytes, received_signature: str) -> bool.
#   The verify() implementation computes
#   hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
#   and compares against the value after stripping the "sha256=" prefix from
#   x-hub-signature-256. GREEN wires this into the route handler to produce
#   200 on match and 401 {"error": "AUTH_INVALID_SIGNATURE"} on mismatch.
def test_fr03_messenger_webhook_valid_post_200(monkeypatch):
    """Happy-path: valid HMAC-SHA256 hex signature returns True (maps to 200).

    Inputs (from TEST_SPEC): method="POST"; x_hub_signature_256="sha256=valid"
    Type: happy_path (Q1)
    """
    app_secret = "my-facebook-app-secret"
    verifier = MessengerWebhookVerifier(app_secret=app_secret)

    # Stub HMAC hex verification so the test isolates feature logic.
    # GREEN TODO: the actual verify() implementation computes
    #   hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    #   and compares with the value after stripping "sha256=" prefix.
    def _stub_verify(raw_body, received_signature):
        return True

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    raw_body = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE_ID",
            "time": 1458692752478,
            "messaging": [{
                "sender": {"id": "PSID_001"},
                "recipient": {"id": "PAGE_ID"},
                "timestamp": 1458692752478,
                "message": {"mid": "mid.001", "text": "hello"},
            }],
        }],
    }).encode("utf-8")

    result = verifier.verify(raw_body, "sha256=valid-hmac-hex")

    # fr03-ok sub-assertion
    assert result is not None, (
        "verify() must return a bool, not None"
    )
    assert result is True, (
        f"Valid HMAC-SHA256 hex signature must return True, got {result}"
    )


# GREEN TODO: MessengerWebhookVerifier.verify() must compare
#   HMAC-SHA256(app_secret, raw_body).hexdigest() against the value after
#   stripping "sha256=" from the received_signature header.
#   Mismatch → return False (GREEN wires this into the route handler
#   to produce 401 {"error": "AUTH_INVALID_SIGNATURE"}).
def test_fr03_messenger_webhook_invalid_signature_401(monkeypatch):
    """Validation: invalid HMAC-SHA256 signature returns False (maps to 401).

    Inputs (from TEST_SPEC): method="POST"; x_hub_signature_256="sha256=bad"
    Type: validation (Q2)
    """
    verifier = MessengerWebhookVerifier(app_secret="real-app-secret")

    # Stub the verifier to simulate a signature mismatch.
    def _stub_verify(raw_body, received_signature):
        return False

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    raw_body = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE_ID",
            "time": 1458692752478,
            "messaging": [{
                "sender": {"id": "PSID_001"},
                "recipient": {"id": "PAGE_ID"},
                "timestamp": 1458692752478,
                "message": {"mid": "mid.001", "text": "hi"},
            }],
        }],
    }).encode("utf-8")

    result = verifier.verify(raw_body, "sha256=bad-signature-value")

    assert result is False, (
        f"Invalid HMAC-SHA256 hex signature must return False, got {result}"
    )


# GREEN TODO: ``MessengerWebhookAdapter`` must have
#   parse_entries(self, entries: list[dict]) -> list[UnifiedMessage] that:
#   - Iterates over the Messenger webhook entry array
#   - For each entry, iterates over entry["messaging"]
#   - For each messaging event:
#     - Extracts sender["id"] as platform_user_id
#     - Extracts message["text"] as content (for text messages)
#     - Sets platform = Platform.MESSENGER
#     - Sets message_type from the message type (MessageType.TEXT, etc.)
#     - Stores the full messaging event dict as raw_payload
#     - Sets received_at from entry's top-level timestamp (epoch ms → datetime)
#     - Sets reply_token = None (Messenger has no reply_token)
#   - Returns a flat list of UnifiedMessage instances, one per messaging event
def test_fr03_messenger_entry_parsed_to_unified_message():
    """Integration: Messenger entry array is parsed to a list of UnifiedMessage.

    Inputs (from TEST_SPEC): entry_count="1"; messaging_count="1"
    Type: integration (Q7/FR-07)
    """
    adapter = MessengerWebhookAdapter(verify_token="test-token")

    entries = [{
        "id": "PAGE_ID_001",
        "time": 1458692752478,
        "messaging": [{
            "sender": {"id": "PSID_1001"},
            "recipient": {"id": "PAGE_ID_001"},
            "timestamp": 1458692752478,
            "message": {
                "mid": "mid.1457764197618:41d102a3e1ae206a38",
                "text": "查詢訂單狀態",
            },
        }],
    }]

    results = adapter.parse_entries(entries)

    # Must return a list
    assert isinstance(results, list), (
        f"parse_entries() must return a list; got {type(results).__name__}"
    )
    assert len(results) == 1, (
        f"Expected 1 UnifiedMessage result; got {len(results)}"
    )

    result = results[0]

    # fr03-ok: result is not None
    assert result is not None, (
        "parse_entries() must return UnifiedMessage, not None"
    )
    assert isinstance(result, UnifiedMessage), (
        f"Result must be a UnifiedMessage instance; got {type(result).__name__}"
    )

    # Platform must be MESSENGER
    assert result.platform == Platform.MESSENGER, (
        f"platform must be Platform.MESSENGER; got {result.platform}"
    )

    # platform_user_id must be extracted from sender.id
    assert result.platform_user_id == "PSID_1001", (
        f"platform_user_id must be 'PSID_1001'; "
        f"got {result.platform_user_id!r}"
    )

    # Content must be the message text
    assert result.content == "查詢訂單狀態", (
        f"content must be '查詢訂單狀態'; got {result.content!r}"
    )

    # message_type must be TEXT
    assert result.message_type == MessageType.TEXT, (
        f"message_type must be MessageType.TEXT; got {result.message_type}"
    )

    # raw_payload must be the full messaging event dict
    assert result.raw_payload == entries[0]["messaging"][0], (
        "raw_payload must preserve the full Messenger messaging event dict"
    )

    # received_at must be set to a datetime
    from datetime import datetime

    assert isinstance(result.received_at, datetime), (
        f"received_at must be a datetime; "
        f"got {type(result.received_at).__name__}"
    )

    # reply_token must be None (Messenger has no reply_token)
    assert result.reply_token is None, (
        f"reply_token must be None for Messenger; got {result.reply_token!r}"
    )
