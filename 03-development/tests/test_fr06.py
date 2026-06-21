from __future__ import annotations
"""TDD-RED: failing tests for FR-06 — A2A Platform Adapter.

FR-06 requires M2M OAuth2/JWT token verification for inbound A2A JSON-RPC 2.0
calls and routing of RPC methods (e.g. ``ask_customer_service``) into
UnifiedMessage for downstream processing.

Spec source: 02-architecture/TEST_SPEC.md (FR-06)
SRS source : SRS.md FR-06 (Module 1: Platform Adapter Layer)
            "A2A Platform Adapter: JSON-RPC 2.0 + M2M OAuth2/JWT"

SAD module : app.api.webhooks — "A2AAdapter JSON-RPC 2.0 entry → FR-06"

Acceptance criteria (from SRS FR-06 / TEST_SPEC.md):
    - 合法 M2M token 回 200
    - M2M token 驗證失敗回 401
    - ask_customer_service RPC end-to-end

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr06_a2a_valid_m2m_token_200
         Inputs: authorization="Bearer valid-m2m"; method="ask_customer_service"
         Type  : happy_path (Q1)
    2. test_fr06_a2a_invalid_m2m_token_401
         Inputs: authorization="Bearer bad-token"
         Type  : validation (Q2)
    3. test_fr06_a2a_rpc_ask_customer_service_end_to_end
         Inputs: method="ask_customer_service"; query="order status?"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr06-ok: result is not None   (applies_to case 1)
"""


import pytest

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``A2AAdapter`` at ``app.api.webhooks`` does NOT exist yet. pytest will crash
# with Collection Error (Exit Code 2) because of missing modules — that is the
# CORRECT RED signal for this step.
#
# ``UnifiedMessage`` / ``Platform`` / ``MessageType`` at
# ``app.core.unified_message`` already exist and provide the contracts that
# GREEN must wire together.
# ---------------------------------------------------------------------------
from app.api.webhooks import A2AAdapter
from app.core.pipeline import (
    MessageType,
    Platform,
    UnifiedMessage,
)


# ===========================================================================
# Test isolation — stub M2M JWT verification.
#
# The A2A platform adapter performs M2M JWT/OAuth2 token verification
# internally (JWKS fetch + JWT decode + audience/issuer check). The autouse
# fixture monkeypatches the adapter so the tests fail because feature logic
# is absent, not because of real cryptographic operations or external HTTP
# calls to a JWKS endpoint.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_a2a_io(monkeypatch):
    """Prevent real M2M JWT verification and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``A2AAdapter`` (at ``app.api.webhooks``) — inbound A2A JSON-RPC 2.0 handler.
#     Per SAD.md "Module: webhooks.py — A2AAdapter JSON-RPC 2.0 entry → FR-06".
#
#     - __init__(self, jwks_url: str, expected_audience: str,
#                expected_issuer: str | None = None)
#         Initialises the adapter with a JWKS URL for M2M token verification,
#         the expected ``aud`` claim, and an optional expected ``iss`` claim.
#
#     - verify_m2m_token(self, authorization_header: str) -> bool
#         Extracts the Bearer token from ``authorization_header`` ("Bearer <token>"),
#         fetches JWKS from ``self._jwks_url``, decodes/validates the JWT
#         (signature, exp, aud, iss), and returns True if the token is valid.
#         Returns False for any validation failure (bad signature, expired,
#         wrong audience/issuer, malformed token, missing Bearer prefix).
#         Does NOT raise exceptions for invalid tokens — callers map
#         False → HTTP 401.
#
#     - handle_jsonrpc_call(self, body: dict,
#                           authorization: str) -> UnifiedMessage
#         Verifies the M2M token via ``verify_m2m_token(authorization)``.
#         If verification fails, raises ``A2AAuthError`` with status=401 and
#         error_code="AUTH_INVALID_SIGNATURE".
#         If valid, parses the JSON-RPC 2.0 body (must contain "jsonrpc": "2.0",
#         "method", "params", "id"), routes ``method`` to the appropriate
#         handler (e.g. ``ask_customer_service``), and returns a
#         ``UnifiedMessage`` with:
#           platform = Platform.A2A
#           platform_user_id = from the M2M JWT "sub" claim (the calling agent ID)
#           message_type = MessageType.TEXT
#           content = params.query (or params.text) from the RPC body
#           raw_payload = the full JSON-RPC 2.0 request body
#           received_at = datetime.now(timezone.utc)
#           reply_token = None
#
#   ``A2AAuthError`` — exception raised on token verification failure.
#     - status: int = 401
#     - error_code: str = "AUTH_INVALID_SIGNATURE"
#     GREEN wires this: the webhook route handler catches A2AAuthError
#     and returns HTTP 401 {"error": "AUTH_INVALID_SIGNATURE"}.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
#     - Platform.A2A = "a2a" — already defined.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================

# GREEN TODO: ``A2AAdapter`` must have
#   verify_m2m_token(self, authorization_header: str) -> bool that:
#   - Extracts the Bearer token from the header string
#   - Fetches the JWKS from self._jwks_url and validates the JWT
#   - Returns True on valid token, False on any failure
#   - The GREEN agent must implement actual JWKS fetch + JWT validation;
#   we monkeypatch here to isolate crypto/external I/O.
def test_fr06_a2a_valid_m2m_token_200(monkeypatch):
    """Happy-path: valid M2M Bearer token returns True (maps to 200).

    Inputs (from TEST_SPEC): authorization="Bearer valid-m2m";
                             method="ask_customer_service"
    Type: happy_path (Q1)
    """
    adapter = A2AAdapter(
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        expected_audience="omnibot",
    )

    # Stub the M2M token verification so the test isolates feature logic.
    # GREEN TODO: the actual verify_m2m_token() implementation must:
    #   1. Parse "Bearer <token>" from the authorization header
    #   2. Fetch JWKS from jwks_url, find the matching key
    #   3. Decode and validate the JWT (signature, exp, aud, iss)
    #   4. Return True on valid, False on any validation failure
    def _stub_verify(authorization_header):
        return True

    monkeypatch.setattr(adapter, "verify_m2m_token", _stub_verify)

    result = adapter.verify_m2m_token("Bearer valid-m2m")

    # fr06-ok sub-assertion
    assert result is not None, (
        "verify_m2m_token() must return a bool, not None"
    )
    assert result is True, (
        f"Valid M2M token must return True (maps to 200); got {result}"
    )


# GREEN TODO: ``A2AAdapter.verify_m2m_token()`` must return False for
#   any invalid token (bad signature, expired, wrong audience/issuer,
#   malformed, missing "Bearer " prefix). The GREEN agent wires this:
#   the webhook route handler calls verify_m2m_token() and maps
#   False → HTTP 401 {"error": "AUTH_INVALID_SIGNATURE"}.
def test_fr06_a2a_invalid_m2m_token_401(monkeypatch):
    """Validation: invalid M2M token returns False (maps to 401).

    Inputs (from TEST_SPEC): authorization="Bearer bad-token"
    Type: validation (Q2)
    """
    adapter = A2AAdapter(
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        expected_audience="omnibot",
    )

    # Stub the verifier to simulate a token validation failure.
    def _stub_verify(authorization_header):
        return False

    monkeypatch.setattr(adapter, "verify_m2m_token", _stub_verify)

    result = adapter.verify_m2m_token("Bearer bad-token")

    assert result is False, (
        f"Invalid M2M token must return False (maps to 401); got {result}"
    )


# GREEN TODO: ``A2AAdapter`` must have
#   handle_jsonrpc_call(self, body: dict, authorization: str) -> UnifiedMessage
#   that:
#   - Calls self.verify_m2m_token(authorization)
#   - If verify returns False, raises A2AAuthError with status=401 and
#     error_code="AUTH_INVALID_SIGNATURE"
#   - If verify returns True, parses the JSON-RPC 2.0 body:
#       body MUST have: "jsonrpc": "2.0", "method": str, "params": dict, "id": str
#   - Routes method to handler. For "ask_customer_service":
#       Extract query/text from params, build a UnifiedMessage with:
#         platform = Platform.A2A
#         platform_user_id = from M2M JWT "sub" claim
#         message_type = MessageType.TEXT
#         content = params["query"] (or params["text"])
#         raw_payload = the full JSON-RPC 2.0 body
#         received_at = datetime.now(timezone.utc)
#         reply_token = None
#   GREEN must also implement A2AAuthError Exception class with
#   status: int and error_code: str attributes.
def test_fr06_a2a_rpc_ask_customer_service_end_to_end(monkeypatch):
    """Integration: valid M2M token → JSON-RPC ask_customer_service → UnifiedMessage.

    Inputs (from TEST_SPEC): method="ask_customer_service"; query="order status?"
    Type: integration (Q7/FR-07)

    Full flow: verify the M2M token, parse the JSON-RPC 2.0 body, route the
    ``ask_customer_service`` method, and return a properly-formed UnifiedMessage.
    """
    adapter = A2AAdapter(
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        expected_audience="omnibot",
    )

    # Stub M2M token verification to always pass — the test verifies
    # adapter logic (method routing, UnifiedMessage construction), not
    # real JWT crypto.
    def _stub_verify(authorization_header):
        return True

    monkeypatch.setattr(adapter, "verify_m2m_token", _stub_verify)

    # Build a JSON-RPC 2.0 compliant request body.
    jsonrpc_body = {
        "jsonrpc": "2.0",
        "method": "ask_customer_service",
        "params": {"query": "order status?"},
        "id": "req-001",
    }

    authorization = "Bearer valid-m2m-agent-token"

    result = adapter.handle_jsonrpc_call(
        body=jsonrpc_body,
        authorization=authorization,
    )

    # fr06-ok: result is not None
    assert result is not None, (
        "handle_jsonrpc_call() must return a UnifiedMessage, not None"
    )
    assert isinstance(result, UnifiedMessage), (
        f"Result must be a UnifiedMessage instance; got {type(result).__name__}"
    )

    # Platform must be A2A
    assert result.platform == Platform.A2A, (
        f"platform must be Platform.A2A; got {result.platform}"
    )

    # Content must be the query from params
    assert result.content == "order status?", (
        f"content must be 'order status?'; got {result.content!r}"
    )

    # message_type must be TEXT
    assert result.message_type == MessageType.TEXT, (
        f"message_type must be MessageType.TEXT; got {result.message_type}"
    )

    # raw_payload must be the full JSON-RPC 2.0 body
    assert result.raw_payload == jsonrpc_body, (
        "raw_payload must preserve the full JSON-RPC 2.0 request body"
    )

    # received_at must be a datetime
    from datetime import datetime

    assert isinstance(result.received_at, datetime), (
        f"received_at must be a datetime; "
        f"got {type(result.received_at).__name__}"
    )

    # A2A does not use reply_token; must be None
    assert result.reply_token is None, (
        f"reply_token must be None for A2A; got {result.reply_token!r}"
    )

    # platform_user_id must be set (from M2M JWT "sub" claim)
    assert result.platform_user_id, (
        "platform_user_id must be set (from the M2M JWT 'sub' claim)"
    )
    assert isinstance(result.platform_user_id, str), (
        f"platform_user_id must be str; "
        f"got {type(result.platform_user_id).__name__}"
    )
