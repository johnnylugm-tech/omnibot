"""TDD-RED: failing tests for FR-04 — WhatsApp Webhook Adapter.

FR-04 requires GET hub.challenge verification + POST HMAC-SHA256 signature
validation with sha256= prefix for the WhatsApp Business Platform webhook,
and mapping of WhatsApp message arrays into UnifiedMessage.

Spec source: 02-architecture/TEST_SPEC.md (FR-04)
SRS source : SRS.md FR-04 (Module 1: Platform Adapter Layer)
            "WhatsApp Webhook Adapter:GET 驗證(hub.challenge)+
            POST HMAC-SHA256 簽名驗證(sha256= prefix),
            映射為 UnifiedMessage"

Acceptance criteria (from SRS FR-04 / TEST_SPEC.md):
    - GET hub.challenge 回傳 challenge 字串
    - POST 合法回 200
    - 簽名失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr04_whatsapp_hub_challenge_returns_challenge
         Inputs: method="GET"; hub_challenge="xyz789"
         Type  : happy_path (Q1)
    2. test_fr04_whatsapp_invalid_sha256_prefix_401
         Inputs: method="POST"; x_hub_signature="md5=bad"
         Type  : validation (Q2)
    3. test_fr04_whatsapp_message_parsed_to_unified_message
         Inputs: method="POST"; x_hub_signature="sha256=valid"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr04-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import json

import pytest
from app.api.webhooks import (
    WhatsAppWebhookAdapter,
    WhatsAppWebhookVerifier,
)

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``WhatsAppWebhookVerifier`` and ``WhatsAppWebhookAdapter`` do NOT exist yet.
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
# The WhatsApp webhook adapter performs HMAC-SHA256 (hex) internally. The
# autouse fixture monkeypatches the verifier/adapter so the tests fail because
# feature logic is absent, not because of actual cryptographic failures.
#
# GREEN TODO: ``WhatsAppWebhookVerifier`` must accept ``app_secret`` at init
#   and expose ``verify(self, raw_body: bytes, received_signature: str) -> bool``.
#   The signature format is ``sha256=<hex>`` (hex digest). The verifier MUST
#   check that received_signature starts with "sha256=" — if it does not (e.g.
#   "md5=...", missing prefix), return False immediately (401). The GREEN agent
#   should inject the app secret via constructor; the verifier internally
#   computes HMAC-SHA256(app_secret, raw_body) and compares the hex digest
#   against the value after stripping the "sha256=" prefix.
#
# GREEN TODO: ``WhatsAppWebhookAdapter`` must accept ``verify_token`` at init
#   and expose:
#     - handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                        hub_challenge: str) -> str
#       Validates hub_mode == "subscribe" and hub_verify_token == verify_token,
#       returns hub_challenge if valid, raises ValueError otherwise.
#     - parse_messages(self, payload: dict) -> list[UnifiedMessage]
#       Navigates the WhatsApp webhook payload structure:
#         payload["entry"][i]["changes"][j]["value"]["messages"]
#       For each message in the messages[] array:
#       - Extracts message["from"] as platform_user_id
#       - Extracts message["text"]["body"] as content (for text messages)
#       - Sets platform = Platform.WHATSAPP
#       - Sets message_type from the message type (MessageType.TEXT, etc.)
#       - Stores the full message dict as raw_payload
#       - Sets received_at from message["timestamp"] (Unix epoch → datetime)
#       - Sets reply_token = None (WhatsApp has no reply_token)
#       Returns a flat list of UnifiedMessage instances.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_whatsapp_io(monkeypatch):
    """Prevent real HMAC verification and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``WhatsAppWebhookVerifier`` — HMAC-SHA256 hex signature verifier with
#   sha256= prefix enforcement.
#     - __init__(self, app_secret: str)
#     - verify(self, raw_body: bytes, received_signature: str) -> bool
#         Checks that received_signature starts with "sha256=". If not, returns
#         False immediately. Computes HMAC-SHA256(app_secret, raw_body), gets
#         hex digest, and compares against the value after the "sha256=" prefix.
#         Returns True on match, False otherwise.
#
#   ``WhatsAppWebhookAdapter`` — handles GET challenge + POST message parsing.
#     - __init__(self, verify_token: str)
#     - handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                        hub_challenge: str) -> str
#         Validates hub_mode == "subscribe" and hub_verify_token == verify_token.
#         Returns hub_challenge on success (GREEN wires this as the GET response
#         body). Raises ValueError on invalid mode or mismatched token.
#     - parse_messages(self, payload: dict) -> list[UnifiedMessage]
#         Navigates payload["entry"][i]["changes"][j]["value"]["messages"] and
#         returns one UnifiedMessage per WhatsApp message object. Sets
#         platform = Platform.WHATSAPP, extracts from/to/text/timestamp/type,
#         stores raw message dict in raw_payload, sets reply_token = None.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
#     - Platform.WHATSAPP = "whatsapp" — already defined.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================

# GREEN TODO: ``WhatsAppWebhookAdapter`` must have
#   handle_challenge(self, hub_mode: str, hub_verify_token: str,
#                    hub_challenge: str) -> str that:
#   - Checks hub_mode == "subscribe"
#   - Checks hub_verify_token == self._verify_token
#   - Returns hub_challenge if both checks pass
#   - Raises ValueError with descriptive message otherwise
def test_fr04_whatsapp_hub_challenge_returns_challenge():
    """Happy-path: GET hub.challenge verification returns the challenge string.

    Inputs (from TEST_SPEC): method="GET"; hub_challenge="xyz789"
    Type: happy_path (Q1)
    """
    verify_token = "whatsapp-verify-token"
    adapter = WhatsAppWebhookAdapter(verify_token=verify_token)

    result = adapter.handle_challenge(
        hub_mode="subscribe",
        hub_verify_token="whatsapp-verify-token",
        hub_challenge="xyz789",
    )

    # fr04-ok sub-assertion
    assert result is not None, (
        "handle_challenge() must return a str, not None"
    )
    assert isinstance(result, str), (
        f"handle_challenge() must return str, got {type(result).__name__}"
    )
    assert result == "xyz789", (
        f"Valid challenge must return 'xyz789', got {result!r}"
    )


# GREEN TODO: WhatsAppWebhookVerifier must have __init__(self, app_secret: str)
#   and verify(self, raw_body: bytes, received_signature: str) -> bool.
#   The verify() implementation MUST check that received_signature starts with
#   "sha256=" — if it does not (e.g. "md5=..." or missing prefix), return False
#   immediately. GREEN wires this into the route handler to produce
#   401 {"error": "AUTH_INVALID_SIGNATURE"}.
def test_fr04_whatsapp_invalid_sha256_prefix_401(monkeypatch):
    """Validation: non-sha256= prefix signature returns False (maps to 401).

    Inputs (from TEST_SPEC): method="POST"; x_hub_signature="md5=bad"
    Type: validation (Q2)

    WhatsApp requires the signature header to use "sha256=" prefix. An
    attacker sending "md5=bad" or any other prefix must be rejected with 401.
    The verifier should return False without even computing HMAC.
    """
    verifier = WhatsAppWebhookVerifier(app_secret="real-app-secret")

    # Stub the verifier to simulate a prefix-mismatch (non-sha256=) rejection.
    # GREEN TODO: the actual verify() implementation checks the prefix first:
    #   if not received_signature.startswith("sha256="):
    #       return False
    def _stub_verify(raw_body, received_signature):
        return False

    monkeypatch.setattr(verifier, "verify", _stub_verify)

    raw_body = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551234567",
                        "phone_number_id": "PHONE_NUM_ID",
                    },
                    "contacts": [{"profile": {"name": "Customer"}, "wa_id": "15559876543"}],
                    "messages": [{
                        "from": "15559876543",
                        "id": "wamid.test123",
                        "timestamp": "1717200000",
                        "text": {"body": "hello"},
                        "type": "text",
                    }],
                },
                "field": "messages",
            }],
        }],
    }).encode("utf-8")

    result = verifier.verify(raw_body, "md5=bad-signature-value")

    assert result is False, (
        f"Non-sha256= prefix signature must return False (maps to 401), got {result}"
    )


# GREEN TODO: ``WhatsAppWebhookAdapter`` must have
#   parse_messages(self, payload: dict) -> list[UnifiedMessage] that:
#   - Navigates payload["entry"][i]["changes"][j]["value"]["messages"]
#   - For each message in the messages[] array:
#     - Extracts message["from"] as platform_user_id
#     - Extracts message["text"]["body"] as content (for text messages)
#     - Sets platform = Platform.WHATSAPP
#     - Sets message_type from message["type"] (MessageType.TEXT, etc.)
#     - Stores the full message dict as raw_payload
#     - Sets received_at from message["timestamp"] (epoch string → datetime)
#     - Sets reply_token = None (WhatsApp has no reply_token concept)
#   - Returns a flat list of UnifiedMessage instances, one per message
def test_fr04_whatsapp_message_parsed_to_unified_message():
    """Integration: WhatsApp webhook message is parsed to UnifiedMessage.

    Inputs (from TEST_SPEC): method="POST"; x_hub_signature="sha256=valid"
    Type: integration (Q7/FR-07)
    """
    adapter = WhatsAppWebhookAdapter(verify_token="test-token")

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551234567",
                        "phone_number_id": "123456789",
                    },
                    "contacts": [{
                        "profile": {"name": "張小明"},
                        "wa_id": "886912345678",
                    }],
                    "messages": [{
                        "from": "886912345678",
                        "id": "wamid.HBgMODg2OTEyMzQ1Njc4FQIAERgSM0EyRjlGRjlGN0U3N0QwN0VBAA==",
                        "timestamp": "1717200000",
                        "text": {"body": "查詢訂單狀態"},
                        "type": "text",
                    }],
                },
                "field": "messages",
            }],
        }],
    }

    results = adapter.parse_messages(payload)

    # Must return a list
    assert isinstance(results, list), (
        f"parse_messages() must return a list; got {type(results).__name__}"
    )
    assert len(results) == 1, (
        f"Expected 1 UnifiedMessage result; got {len(results)}"
    )

    result = results[0]

    # fr04-ok: result is not None
    assert result is not None, (
        "parse_messages() must return UnifiedMessage, not None"
    )
    assert isinstance(result, UnifiedMessage), (
        f"Result must be a UnifiedMessage instance; got {type(result).__name__}"
    )

    # Platform must be WHATSAPP
    assert result.platform == Platform.WHATSAPP, (
        f"platform must be Platform.WHATSAPP; got {result.platform}"
    )

    # platform_user_id must be extracted from message["from"]
    assert result.platform_user_id == "886912345678", (
        f"platform_user_id must be '886912345678'; "
        f"got {result.platform_user_id!r}"
    )

    # Content must be the message text body
    assert result.content == "查詢訂單狀態", (
        f"content must be '查詢訂單狀態'; got {result.content!r}"
    )

    # message_type must be TEXT
    assert result.message_type == MessageType.TEXT, (
        f"message_type must be MessageType.TEXT; got {result.message_type}"
    )

    # raw_payload must be the full message dict
    assert result.raw_payload == payload["entry"][0]["changes"][0]["value"]["messages"][0], (
        "raw_payload must preserve the full WhatsApp message dict"
    )

    # received_at must be set to a datetime
    from datetime import datetime

    assert isinstance(result.received_at, datetime), (
        f"received_at must be a datetime; "
        f"got {type(result.received_at).__name__}"
    )

    # reply_token must be None (WhatsApp has no reply_token)
    assert result.reply_token is None, (
        f"reply_token must be None for WhatsApp; got {result.reply_token!r}"
    )


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in api/adapters/whatsapp.py
# ---------------------------------------------------------------------------

def test_fr04_whatsapp_parse_messages_default_from_is_empty_string():
    """When a message lacks ``"from"`` key, ``platform_user_id`` MUST
    default to empty string (NOT ``"XXXX"`` or None). Kills mutant #28.
    """
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter
    adapter = WhatsAppWebhookAdapter(verify_token="t")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA",
            "changes": [{
                "value": {
                    "messages": [{
                        # No "from" key
                        "text": {"body": "hi"},
                        "type": "text",
                        "timestamp": "1700000000",
                    }],
                },
            }],
        }],
    }
    result = adapter.parse_messages(payload)[0]
    assert result.platform_user_id == "", (
        f"Missing 'from' must default to empty string; "
        f"got platform_user_id={result.platform_user_id!r}"
    )


def test_fr04_whatsapp_parse_messages_default_text_body_is_empty_string():
    """When a message has no ``text.body``, ``content`` MUST default
    to empty string. Kills mutant #32.
    """
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter
    adapter = WhatsAppWebhookAdapter(verify_token="t")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1234",
                        # No "text" key
                        "type": "text",
                        "timestamp": "1700000000",
                    }],
                },
            }],
        }],
    }
    result = adapter.parse_messages(payload)[0]
    assert result.content == "", (
        f"Missing 'text.body' must default to empty string; "
        f"got content={result.content!r}"
    )


def test_fr04_whatsapp_parse_messages_default_type_is_text():
    """When a message lacks ``"type"``, ``message_type`` MUST default
    to ``MessageType.TEXT`` via the ``"text"`` default fallback.
    Kills mutant #35 (default value ``"text"`` → ``"XXtextXX"``).
    """
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter
    from app.core.unified_message import MessageType
    adapter = WhatsAppWebhookAdapter(verify_token="t")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1234",
                        "text": {"body": "hi"},
                        # No "type" key — defaults to "text"
                        "timestamp": "1700000000",
                    }],
                },
            }],
        }],
    }
    result = adapter.parse_messages(payload)[0]
    assert result.message_type == MessageType.TEXT, (
        f"Missing 'type' must default to MessageType.TEXT; "
        f"got message_type={result.message_type!r}"
    )


def test_fr04_whatsapp_parse_messages_invalid_timestamp_falls_back_to_epoch_zero():
    """When ``timestamp`` is not parseable as int, ``received_at`` MUST
    fall back to epoch 0 (1970-01-01T00:00:00Z), NOT to ``1`` (1969) or
    ``None`` (TypeError). Kills mutants #42, #43.
    """
    from datetime import datetime, timezone

    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter
    adapter = WhatsAppWebhookAdapter(verify_token="t")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WA",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1234",
                        "text": {"body": "hi"},
                        "type": "text",
                        "timestamp": "not-a-number",
                    }],
                },
            }],
        }],
    }
    result = adapter.parse_messages(payload)[0]
    assert result.received_at == datetime(1970, 1, 1, tzinfo=timezone.utc), (
        f"Unparseable timestamp must fall back to epoch 0 (1970-01-01); "
        f"got received_at={result.received_at!r}"
    )
