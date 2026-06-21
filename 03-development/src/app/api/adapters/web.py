"""[FR-06] A2A Platform Adapter — inbound A2A JSON-RPC 2.0 handler.

Accepts JSON-RPC 2.0 calls from remote A2A agents, verifies M2M OAuth2/JWT
tokens, routes RPC methods (e.g. ``ask_customer_service``) into
``UnifiedMessage`` for downstream PALADIN / Knowledge / DST processing.

Architecture (SAD.md): ``Module: webhooks.py — A2AAdapter JSON-RPC 2.0 entry
→ FR-06``. The adapter is the inbound counterpart to FR-44 (OmniBot's own
Agent Card at ``/.well-known/agent.json``) and FR-41 (remote agent discovery).

Citations:
    - SRS.md FR-06 — M2M OAuth2/JWT token verification + A2A JSON-RPC 2.0
    - SRS.md:786 — FR-06 registry entry (id, description, surface symbols)
    - 02-architecture/TEST_SPEC.md FR-06 — test_fr06_a2a_valid_m2m_token_200,
      test_fr06_a2a_invalid_m2m_token_401,
      test_fr06_a2a_rpc_ask_customer_service_end_to_end
    - agent_card.py:12-16 — A2A method list (ask_customer_service,
      escalate_to_human) pinned here as well
    - 02-architecture/SAD.md — "A2AAdapter JSON-RPC 2.0 entry → FR-06"
"""

from __future__ import annotations

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from app.core.unified_message import (
    MessageType,
    Platform,
    UnifiedMessage,
)

_BEARER_PREFIX = "Bearer "
_UNKNOWN_AGENT = "unknown-agent"


# ------------------------------------------------------------------
# JWT / base64url helpers (FR-05 / FR-03 / FR-04)
#
# Module-level functions (NOT BaseWebhookAdapter methods) so any
# adapter or verifier can call them without instantiating the class.
# Previously these helpers lived in WebJwtVerifier and were
# self-imported via ``from app.api.webhooks import _b64url_decode``;
# that circular import broke when ``webhooks.py`` was split across
# multiple modules. Centralising them at module scope removes the
# cycle and keeps the helper signatures stable for downstream
# callers (``app.api.auth`` and ``WebJwtVerifier``).
# ------------------------------------------------------------------



from app.api.adapters.base import BaseWebhookAdapter  # noqa: E402
from app.api.adapters.utils import _b64url_decode, _b64url_encode  # noqa: E402
from app.api.adapters.verifiers import WebJwtVerifier  # noqa: E402


class WebAuthError(Exception):
    """[FR-05] Authentication failure raised by WebAdapter.process_message().

    Citations:
        - SRS.md FR-05 — "JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED"
        - TEST_SPEC.md FR-05:89 — WebAuthError with status 401
    """

    def __init__(self, status: int, error_code: str) -> None:  # pragma: no cover
        self.status = status
        self.error_code = error_code
        super().__init__(error_code)

class WebAdapter(BaseWebhookAdapter):
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
            received_at=datetime.now(timezone.utc),
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

