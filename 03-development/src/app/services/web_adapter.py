"""[FR-05] Web Platform Adapter — guest sessions + JWT Bearer messaging.

Implements POST /api/v1/web/guest-session (anonymous guest JWT) and
POST /api/v1/web/message (JWT BearerAuth message delivery) per SRS FR-05.

Citations:
    - SRS.md FR-05 — "Web Platform Adapter: POST /api/v1/web/guest-session
      初始化匿名連線回傳 Guest JWT; POST /api/v1/web/message 使用 JWT BearerAuth
      傳訊"
    - TEST_SPEC.md FR-05:82-92 — WebAdapter contract:
      __init__, create_guest_session() -> dict, process_message() -> UnifiedMessage
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime

from app.core.unified_message import MessageType, Platform, UnifiedMessage
from app.services.web_verifier import WebJwtVerifier


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to a base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode a base64url string (no padding) to bytes."""
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data)


class WebAuthError(Exception):
    """[FR-05] Authentication failure raised by WebAdapter.process_message().

    Citations:
        - SRS.md FR-05 — "JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED"
        - TEST_SPEC.md FR-05:89 — WebAuthError with status 401
    """

    def __init__(self, status: int, error_code: str) -> None:
        self.status = status
        self.error_code = error_code
        super().__init__(error_code)


class WebAdapter:
    """[FR-05] Web platform adapter: guest sessions + JWT-authenticated messaging.

    Citations:
        - SRS.md FR-05 — "Web Platform Adapter: POST /api/v1/web/guest-session
          初始化匿名連線回傳 Guest JWT; POST /api/v1/web/message 使用 JWT
          BearerAuth 傳訊"
        - TEST_SPEC.md FR-05:82-92 — full contract
    """

    def __init__(self, jwt_secret: str, jwt_expiry_seconds: int = 3600) -> None:
        """Initialise the adapter with a JWT secret and optional expiry.

        Citations:
            - TEST_SPEC.md FR-05:83 — __init__(self, jwt_secret, jwt_expiry_seconds=3600)
        """
        self._jwt_secret = jwt_secret
        self._jwt_expiry_seconds = jwt_expiry_seconds
        self._verifier = WebJwtVerifier(jwt_secret)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_guest_session(self) -> dict:
        """Generate an anonymous guest session returning a signed JWT.

        Returns:
            dict with keys ``"token"`` (JWT string) and ``"expires_in"``
            (expiry seconds as int).

        Citations:
            - TEST_SPEC.md FR-05:84-87 — create_guest_session() -> dict contract
            - SRS.md FR-05 — "guest-session 回 200 含 JWT"
        """
        guest_id = "guest-" + secrets.token_hex(16)

        now = int(time.time())
        payload = {
            "sub": guest_id,
            "iat": now,
            "exp": now + self._jwt_expiry_seconds,
        }

        token = self._make_jwt(payload)
        return {"token": token, "expires_in": self._jwt_expiry_seconds}

    def process_message(self, jwt_token: str, content: str) -> UnifiedMessage:
        """Validate JWT and produce a UnifiedMessage for downstream stages.

        Raises:
            WebAuthError: if the JWT is invalid or expired (status=401,
                error_code="AUTH_TOKEN_EXPIRED").

        Citations:
            - TEST_SPEC.md FR-05:88-92 — process_message contract
            - SRS.md FR-05 — "JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED"
        """
        if not self._verifier.verify(jwt_token):
            raise WebAuthError(401, "AUTH_TOKEN_EXPIRED")

        payload = self._decode_jwt_payload(jwt_token)
        platform_user_id = payload["sub"]

        return UnifiedMessage(
            platform=Platform.WEB,
            platform_user_id=platform_user_id,
            unified_user_id=None,
            message_type=MessageType.TEXT,
            content=content,
            raw_payload={"content": content},
            received_at=datetime.now(UTC),
            reply_token=None,
        )

    # ------------------------------------------------------------------
    # Internal JWT helpers
    # ------------------------------------------------------------------

    def _make_jwt(self, payload: dict) -> str:
        """Build and sign a JWT with HS256."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(
            self._jwt_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        sig_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def _decode_jwt_payload(self, token: str) -> dict:
        """Extract and decode the payload segment of a JWT.

        The caller must have already verified the token; this method
        does not re-validate the signature or expiration.
        """
        segments = token.split(".")
        payload_b64 = segments[1]
        return json.loads(_b64url_decode(payload_b64))
