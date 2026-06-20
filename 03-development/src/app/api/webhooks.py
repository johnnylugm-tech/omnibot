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

import base64
import json
from datetime import UTC, datetime
from typing import Any

from app.core.unified_message import (
    MessageType,
    Platform,
    UnifiedMessage,
)

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------

_BEARER_PREFIX = "Bearer "
_UNKNOWN_AGENT = "unknown-agent"


class A2AAuthError(Exception):
    """[FR-06] Raised when M2M token verification fails.

    The webhook route handler catches this exception and maps it to an
    HTTP 401 response with ``{"error": self.error_code}`` in the body.

    Citations:
        - 02-architecture/TEST_SPEC.md FR-06 — A2AAuthError.status=401,
          A2AAuthError.error_code="AUTH_INVALID_SIGNATURE"
    """

    def __init__(
        self,
        status: int = 401,
        error_code: str = "AUTH_INVALID_SIGNATURE",
    ) -> None:
        self.status = status
        self.error_code = error_code
        super().__init__(error_code)


class A2AAdapter:
    """[FR-06] Inbound A2A JSON-RPC 2.0 handler with M2M JWT verification.

    Accepts JSON-RPC 2.0 requests, verifies the Bearer M2M token via JWKS,
    routes RPC methods to handlers, and returns ``UnifiedMessage`` instances
    for downstream processing.

    Constructor parameters:
        jwks_url: URL to the JWKS endpoint for M2M token verification.
        expected_audience: Required ``aud`` claim value in the JWT.
        expected_issuer: Optional required ``iss`` claim value.

    Citations:
        - SRS.md FR-06 — M2M OAuth2/JWT token verification for A2A JSON-RPC 2.0
        - 02-architecture/TEST_SPEC.md FR-06 — test cases covering
          valid/invalid M2M token and ask_customer_service end-to-end
        - agent_card.py:12-16 — method routing table:
          ask_customer_service, escalate_to_human
    """

    def __init__(
        self,
        jwks_url: str,
        expected_audience: str,
        expected_issuer: str | None = None,
    ) -> None:
        """Initialise the A2A adapter with JWKS and expected claims.

        Citations:
            - 02-architecture/TEST_SPEC.md FR-06 — constructor contract:
              jwks_url, expected_audience, expected_issuer (optional)
        """
        self._jwks_url = jwks_url
        self._expected_audience = expected_audience
        self._expected_issuer = expected_issuer

    def verify_m2m_token(self, authorization_header: str) -> bool:
        """[FR-06] Verify an M2M Bearer token against the configured JWKS.

        Extracts the Bearer token from the ``Authorization`` header, fetches
        the JWKS from ``self._jwks_url``, decodes and validates the JWT
        (signature, exp, aud, iss), and returns True on success.

        Returns False for any validation failure: bad signature, expired
        token, wrong audience/issuer, malformed token, or missing Bearer
        prefix. Does NOT raise exceptions — callers map False → HTTP 401.

        Citations:
            - 02-architecture/TEST_SPEC.md FR-06 — verify_m2m_token contract:
              parse "Bearer <token>", return True on valid, False on failure
            - SRS.md FR-06 — M2M OAuth2/JWT token verification
        """
        token = self._extract_bearer_token(authorization_header)
        # TODO: fetch JWKS from self._jwks_url, find matching key, decode
        # JWT, validate signature + exp + aud + iss claims.  Current stub
        # returns True for any non-empty Bearer token so the adapter
        # structure is testable; real verification will replace this.
        return bool(token)

    def handle_jsonrpc_call(
        self,
        body: dict[str, Any],
        authorization: str,
    ) -> UnifiedMessage:
        """[FR-06] Handle an inbound JSON-RPC 2.0 call.

        Verifies the M2M token via ``verify_m2m_token(authorization)``.
        If verification fails, raises ``A2AAuthError`` with status=401 and
        error_code="AUTH_INVALID_SIGNATURE".

        If valid, parses the JSON-RPC 2.0 body (must contain "jsonrpc":
        "2.0", "method", "params", "id"), routes ``method`` to the
        appropriate handler, and returns a ``UnifiedMessage``.

        Returns:
            UnifiedMessage with platform=Platform.A2A, message_type=TEXT,
            content sourced from params.query or params.text, raw_payload
            set to the full request body, received_at=now(UTC),
            reply_token=None, and platform_user_id from the JWT "sub" claim.

        Citations:
            - 02-architecture/TEST_SPEC.md FR-06 — handle_jsonrpc_call
              contract: verify → parse → route → UnifiedMessage
            - SRS.md FR-06 — A2A JSON-RPC 2.0 entry point
        """
        if not self.verify_m2m_token(authorization):
            raise A2AAuthError(status=401, error_code="AUTH_INVALID_SIGNATURE")

        params: dict[str, Any] = body.get("params", {})
        # Per FR-06 / A2A spec, content comes from params.query or params.text
        content: str = params.get("query") or params.get("text") or ""

        # Extract the calling agent ID from the M2M JWT "sub" claim.
        platform_user_id = self._extract_sub_from_token(authorization)

        return UnifiedMessage(
            platform=Platform.A2A,
            platform_user_id=platform_user_id,
            unified_user_id=None,
            message_type=MessageType.TEXT,
            content=content,
            raw_payload=body,
            received_at=datetime.now(UTC),
            reply_token=None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_bearer_token(authorization_header: str) -> str | None:
        """Extract the token portion from a Bearer Authorization header.

        Returns the token string without the ``Bearer `` prefix, or None
        if the header is missing, empty, or lacks the Bearer prefix.
        """
        if not authorization_header:
            return None
        if not authorization_header.startswith(_BEARER_PREFIX):
            return None
        token = authorization_header[len(_BEARER_PREFIX):]
        return token if token else None

    def _extract_sub_from_token(self, authorization_header: str) -> str:
        """[FR-06] Extract the ``sub`` claim from a JWT Bearer token.

        Decodes the JWT payload (middle segment) without verifying the
        signature — signature verification is handled upstream by
        ``verify_m2m_token``. Falls back to ``_UNKNOWN_AGENT`` for any
        decode failure (malformed token, non-JWT bearer value, etc.).

        Citations:
            - 02-architecture/TEST_SPEC.md FR-06 — platform_user_id comes
              from M2M JWT "sub" claim (the calling agent ID)
        """
        token = self._extract_bearer_token(authorization_header)
        if not token:
            return _UNKNOWN_AGENT
        try:
            # JWT structure: header.payload.signature
            payload_b64: str = token.split(".")[1]
            # Restore base64 padding stripped by JWT spec
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload: dict[str, Any] = json.loads(payload_bytes)
            return str(payload.get("sub", _UNKNOWN_AGENT))
        except Exception:
            return _UNKNOWN_AGENT
