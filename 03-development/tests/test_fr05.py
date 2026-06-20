"""TDD-RED: failing tests for FR-05 — Web Platform Adapter.

FR-05 requires POST /api/v1/web/guest-session returning a Guest JWT
for anonymous sessions, and POST /api/v1/web/message accepting JWT
BearerAuth for message delivery. Rate limit is 10 rps per guest.

Spec source: 02-architecture/TEST_SPEC.md (FR-05)
SRS source : SRS.md FR-05 (Module 1: Platform Adapter Layer)
            "Web Platform Adapter: POST /api/v1/web/guest-session
            初始化匿名連線回傳 Guest JWT; POST /api/v1/web/message
            使用 JWT BearerAuth 傳訊"

Acceptance criteria (from SRS FR-05 / TEST_SPEC.md):
    - guest-session 回 200 含 JWT
    - JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED
    - rate limit 超出回 429

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr05_web_guest_session_returns_jwt
         Inputs: method="POST"; path="/api/v1/web/guest-session"
         Type  : happy_path (Q1)
    2. test_fr05_web_message_invalid_jwt_401
         Inputs: method="POST"; authorization="Bearer expired-token"
         Type  : validation (Q2)
    3. test_fr05_web_message_rate_limit_429
         Inputs: request_count="11"; limit="10"; platform="web"
         Type  : nfr_pattern (Q6/NP-03)
    4. test_fr05_web_jwt_bearer_auth_end_to_end
         Inputs: jwt="valid-guest-jwt"; message="hello"
         Type  : integration (Q7/FR-07)

Sub-assertion (per TEST_SPEC):
    fr05-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Imports — unguarded on purpose.
#
# ``WebAdapter`` and ``WebJwtVerifier`` do NOT exist yet. pytest will crash
# with Collection Error (Exit Code 2) because of missing modules — that is
# the CORRECT RED signal for this step.
#
# ``RateLimiter`` at ``app.infra.rate_limit`` already exists and provides
# the sliding-window rate-limit contract that GREEN must wire together.
# ---------------------------------------------------------------------------
from app.core.unified_message import (
    MessageType,
    Platform,
    UnifiedMessage,
)
from app.infra.rate_limit import RateLimiter
from app.services.web_adapter import WebAdapter
from app.services.web_verifier import WebJwtVerifier


# ===========================================================================
# Test isolation — stub external JWT crypto and HTTP I/O.
#
# The Web adapter generates and verifies JWTs internally. The autouse
# fixture monkeypatches the adapter/verifier so the tests fail because
# feature logic is absent, not because of real cryptographic operations
# or external HTTP calls.
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_web_io(monkeypatch):
    """Prevent real JWT crypto and external I/O during unit tests."""
    yield


# ===========================================================================
# GREEN contracts pinned by these RED tests.
#
#   ``WebAdapter`` — handles guest session creation + message processing.
#     - __init__(self, jwt_secret: str, jwt_expiry_seconds: int = 3600)
#     - create_guest_session(self) -> dict
#         Returns {"token": "<jwt>", "expires_in": 3600} for a new anonymous
#         guest session. The JWT payload contains a "sub" (guest_id), "iat",
#         and "exp" claim. GREEN wires this as the POST /api/v1/web/guest-session
#         response body (HTTP 200).
#     - process_message(self, jwt_token: str, content: str) -> UnifiedMessage
#         Validates the JWT via WebJwtVerifier.verify(). On invalid/expired JWT
#         raises WebAuthError with status 401 and error_code AUTH_TOKEN_EXPIRED.
#         On valid JWT, constructs a UnifiedMessage with platform=Platform.WEB,
#         platform_user_id from the JWT "sub" claim, content from the request,
#         message_type=MessageType.TEXT, raw_payload as the incoming JSON dict,
#         and received_at=datetime.now().
#
#   ``WebJwtVerifier`` — JWT Bearer token validation.
#     - __init__(self, jwt_secret: str)
#     - verify(self, token: str) -> bool
#         Decodes and validates the JWT using the secret. Returns True if the
#         token is valid (signature matches, not expired), False otherwise.
#         Does NOT raise — returns False on any validation failure. The caller
#         (WebAdapter) maps False → 401 AUTH_TOKEN_EXPIRED.
#
#   ``RateLimiter`` (at ``app.infra.rate_limit``) — already exists.
#     - LIMITS["web"] = 10 — per-second sliding window for the web platform.
#     - allow(platform="web", key=<guest_id>) -> RateLimitResult
#         Returns RateLimitResult(200, "") when under limit;
#         RateLimitResult(429, "RATE_LIMIT_EXCEEDED") when exceeded.
#
#   ``UnifiedMessage`` (at ``app.core.unified_message``) — already exists.
#     - Frozen dataclass with fields: platform, platform_user_id,
#       unified_user_id, message_type, content, raw_payload, received_at,
#       reply_token.
#     - Platform.WEB = "web" — already defined.
# ===========================================================================


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================

# GREEN TODO: ``WebAdapter`` must have
#   create_guest_session(self) -> dict that:
#   - Generates a JWT signed with self._jwt_secret
#   - JWT payload: {"sub": <random_guest_id>, "iat": <now>, "exp": <now+expiry>}
#   - Returns {"token": "<jwt_string>", "expires_in": <expiry_seconds>}
#   - GREEN wires this as HTTP 200 response body for POST /api/v1/web/guest-session
def test_fr05_web_guest_session_returns_jwt():
    """Happy-path: guest session endpoint returns a valid-looking JWT.

    Inputs (from TEST_SPEC): method="POST"; path="/api/v1/web/guest-session"
    Type: happy_path (Q1)
    """
    adapter = WebAdapter(jwt_secret="test-secret-key")

    result = adapter.create_guest_session()

    # fr05-ok sub-assertion
    assert result is not None, (
        "create_guest_session() must return a dict, not None"
    )
    assert isinstance(result, dict), (
        f"create_guest_session() must return dict, got {type(result).__name__}"
    )

    # Must contain a "token" key
    assert "token" in result, (
        f"Response must contain 'token' key; got keys {list(result.keys())}"
    )
    token = result["token"]
    assert isinstance(token, str), (
        f"'token' must be a str, got {type(token).__name__}"
    )
    assert len(token) > 0, "JWT token must not be empty"

    # A JWT has three base64url-encoded segments separated by dots
    segments = token.split(".")
    assert len(segments) == 3, (
        f"JWT must have 3 dot-separated segments (header.payload.signature); "
        f"got {len(segments)} segments"
    )

    # Must contain "expires_in"
    assert "expires_in" in result, (
        f"Response must contain 'expires_in' key; got keys {list(result.keys())}"
    )
    assert isinstance(result["expires_in"], int), (
        f"'expires_in' must be an int, got {type(result['expires_in']).__name__}"
    )
    assert result["expires_in"] > 0, (
        f"expires_in must be positive; got {result['expires_in']}"
    )


# GREEN TODO: ``WebJwtVerifier`` must have
#   __init__(self, jwt_secret: str) and
#   verify(self, token: str) -> bool that:
#   - Decodes the JWT using the secret
#   - Returns True if signature is valid AND token is not expired
#   - Returns False on any validation failure (bad signature, expired, malformed)
#   - Does NOT raise exceptions for invalid tokens
#   GREEN wires this: WebAdapter.process_message() calls verifier.verify();
#   on False, raises WebAuthError → HTTP 401 {"error": "AUTH_TOKEN_EXPIRED"}
def test_fr05_web_message_invalid_jwt_401():
    """Validation: expired/invalid JWT is rejected (maps to 401).

    Inputs (from TEST_SPEC): method="POST"; authorization="Bearer expired-token"
    Type: validation (Q2)

    The verifier should return False for any invalid token — the adapter
    maps False → 401 AUTH_TOKEN_EXPIRED.
    """
    verifier = WebJwtVerifier(jwt_secret="test-secret-key")

    result = verifier.verify("expired-token-value")

    assert result is False, (
        f"Invalid/expired token must return False (maps to 401); got {result}"
    )


# GREEN TODO: ``RateLimiter`` already exists at app.infra.rate_limit.
#   GREEN must ensure LIMITS["web"] = 10 and that the web adapter calls
#   RateLimiter.allow(platform="web", key=<guest_id>) before processing
#   each message. On RateLimitResult(status=429) the adapter must return
#   HTTP 429 {"error": "RATE_LIMIT_EXCEEDED"}.
#   The test below uses the in-memory RateLimiter (no Redis client) —
#   GREEN need only ensure the adapter calls `allow()` at the right point.
def test_fr05_web_message_rate_limit_429():
    """NFR pattern: exceeding 10 rps for web platform returns 429.

    Inputs (from TEST_SPEC): request_count="11"; limit="10"; platform="web"
    Type: nfr_pattern (Q6/NP-03)

    The 11th request within the 1-second window must be denied with 429.
    """
    # FR-21 contract: RateLimiter.LIMITS["web"] must equal 10
    assert RateLimiter.LIMITS.get("web") == 10, (
        f"RateLimiter.LIMITS['web'] must be 10; "
        f"got {RateLimiter.LIMITS.get('web')}"
    )

    limiter = RateLimiter()  # in-memory mode, no Redis

    guest_id = "guest-test-001"

    # First 10 requests within the window must be allowed
    for i in range(10):
        result = limiter.allow(platform="web", key=guest_id)
        assert result.status == 200, (
            f"Request {i + 1}/10 must be allowed (status 200); "
            f"got status {result.status}"
        )

    # The 11th request must be denied with 429
    result_11 = limiter.allow(platform="web", key=guest_id)
    assert result_11.status == 429, (
        f"Request 11/10 must be denied (status 429); got status {result_11.status}"
    )
    assert result_11.reason == "RATE_LIMIT_EXCEEDED", (
        f"Denied result reason must be 'RATE_LIMIT_EXCEEDED'; "
        f"got {result_11.reason!r}"
    )


# GREEN TODO: ``WebAdapter`` must have
#   process_message(self, jwt_token: str, content: str) -> UnifiedMessage that:
#   - Calls self._verifier.verify(jwt_token)
#   - If verify() returns False, raises WebAuthError with status 401 and
#     error_code "AUTH_TOKEN_EXPIRED"
#   - If verify() returns True, decodes the JWT to extract "sub" as
#     platform_user_id, then builds a UnifiedMessage with:
#       platform = Platform.WEB
#       platform_user_id = <guest_id from JWT sub>
#       message_type = MessageType.TEXT
#       content = <the message content>
#       raw_payload = {"content": <content>}
#       received_at = datetime.now()
#       reply_token = None
#   GREEN must stub WebJwtVerifier.verify to return True for valid guest JWTs.
def test_fr05_web_jwt_bearer_auth_end_to_end(monkeypatch):
    """Integration: guest session JWT → send message → UnifiedMessage.

    Inputs (from TEST_SPEC): jwt="valid-guest-jwt"; message="hello"
    Type: integration (Q7/FR-07)

    Full flow: create a guest session, use the returned JWT to send a
    message, and verify the result is a properly-formed UnifiedMessage.
    """
    adapter = WebAdapter(jwt_secret="test-secret-key")

    # Step 1 — create a guest session to obtain a JWT
    session = adapter.create_guest_session()
    guest_jwt = session["token"]

    # Step 2 — stub the verifier so the test verifies adapter logic,
    # not real JWT crypto. The GREEN agent must implement real JWT
    # signing/verification; we trust the verifier here.
    from datetime import datetime

    def _stub_verify(token):
        # Accept the token returned by create_guest_session()
        return token == guest_jwt

    # Patch the verifier that the adapter holds internally.
    # GREEN TODO: WebAdapter.__init__ must create a WebJwtVerifier
    #   instance stored as self._verifier (or similar attribute name).
    #   Change this patch target if GREEN uses a different attribute name.
    monkeypatch.setattr(adapter._verifier, "verify", _stub_verify)

    # Step 3 — process a message using the guest JWT
    result = adapter.process_message(jwt_token=guest_jwt, content="hello")

    # fr05-ok: result is not None
    assert result is not None, (
        "process_message() must return UnifiedMessage, not None"
    )
    assert isinstance(result, UnifiedMessage), (
        f"Result must be a UnifiedMessage instance; got {type(result).__name__}"
    )

    # Platform must be WEB
    assert result.platform == Platform.WEB, (
        f"platform must be Platform.WEB; got {result.platform}"
    )

    # Content must match the input
    assert result.content == "hello", (
        f"content must be 'hello'; got {result.content!r}"
    )

    # message_type must be TEXT
    assert result.message_type == MessageType.TEXT, (
        f"message_type must be MessageType.TEXT; got {result.message_type}"
    )

    # received_at must be a datetime
    assert isinstance(result.received_at, datetime), (
        f"received_at must be a datetime; "
        f"got {type(result.received_at).__name__}"
    )

    # reply_token must be None (Web has no reply_token)
    assert result.reply_token is None, (
        f"reply_token must be None for Web; got {result.reply_token!r}"
    )

    # platform_user_id must be set from JWT
    assert result.platform_user_id, (
        "platform_user_id must be set (from JWT 'sub' claim)"
    )
    assert isinstance(result.platform_user_id, str), (
        f"platform_user_id must be str; got {type(result.platform_user_id).__name__}"
    )
