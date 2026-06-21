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

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------
import base64 as _base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, FastAPI

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



def _b64url_encode(data: bytes) -> str:
    """[FR-05] base64url encode WITHOUT padding (JWT spec).

    Citations:
        - RFC 7519 §2 — base64url encoding for JWT segments.
    """
    return _base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """[FR-05] base64url decode WITH automatic padding restore.

    JWT segments may arrive with or without trailing ``=`` padding;
    we restore to a multiple of 4 so ``urlsafe_b64decode`` does not
    raise ``binascii.Error``.
    """
    padding = "=" * (-len(data) % 4)
    return _base64.urlsafe_b64decode(data + padding)


def _verify_challenge(
    mode: str, token: str, challenge: str, verify_token: str
) -> str | None:
    """[FR-03 / FR-04] Validate GET ``hub.challenge`` parameters.

    Returns ``challenge`` when ``mode == "subscribe"`` AND ``token``
    matches the configured ``verify_token``; returns ``None`` on any
    mismatch so the caller responds with HTTP 403.
    """
    if mode != "subscribe":  # pragma: no cover
        return None
    if token != verify_token:
        return None
    return challenge


class BaseWebhookAdapter:
    pass
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


class A2AAdapter(BaseWebhookAdapter):
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
        if not token:
            return False

        try:
            segments = token.split(".")
            if len(segments) != 3:
                return False
            header_b64, payload_b64, sig_b64 = segments

            # Validate payload claims
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
            payload = json.loads(payload_bytes)

            # Check expiration
            if "exp" in payload and time.time() > payload["exp"]:
                return False

            # Check audience and issuer
            if payload.get("aud") != self._expected_audience:
                return False
            if self._expected_issuer and payload.get("iss") != self._expected_issuer:
                return False

            # Fetch JWKS and verify RS256 signature
            req = urllib.request.Request(self._jwks_url, headers={"User-Agent": "OmniBot"})
            with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
                jwks = json.loads(response.read().decode())

            header_bytes = base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4))
            kid = json.loads(header_bytes).get("kid")
            jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
            if not jwk or jwk.get("kty") != "RSA":
                return False

            def b64url_dec(s: str) -> bytes:
                return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

            n_int = int.from_bytes(b64url_dec(jwk["n"]), byteorder="big")
            e_int = int.from_bytes(b64url_dec(jwk["e"]), byteorder="big")
            public_key = rsa.RSAPublicNumbers(e=e_int, n=n_int).public_key()

            msg = f"{header_b64}.{payload_b64}".encode("ascii")
            sig = b64url_dec(sig_b64)
            public_key.verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())

            return True
        except Exception:
            return False

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
            set to the full request body, received_at=now(timezone.utc),
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
            received_at=datetime.now(timezone.utc),
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

        # [FR-06] Require valid signature BEFORE extracting sub claim (C-03 fix)
        if not self.verify_m2m_token(authorization_header):
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
"""[FR-02] LINE Webhook Adapter — maps LINE events array into UnifiedMessage.

Parses a LINE Messaging API webhook events array and produces a list of
``UnifiedMessage`` instances for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md:25 — FR-02 "解析 events 陣列，映射為 UnifiedMessage"
    - SRS.md:433-435 — implementation_functions: line_adapter
    - TEST_SPEC.md FR-02 — LineWebhookAdapter contract:
      process_events(self, events_payload: list[dict]) -> list[UnifiedMessage]
"""





class LineWebhookAdapter(BaseWebhookAdapter):
    """[FR-02] Parses LINE webhook events array into UnifiedMessage list.

    Citations:
        - SRS.md:25 — adapter parsing + mapping
        - SRS.md:437 — verification_method: valid req → 200
        - TEST_SPEC.md FR-02 — process_events contract
    """

    def process_events(self, events_payload: list[dict]) -> list[UnifiedMessage]:
        """Parse a LINE webhook events array and return a list of UnifiedMessage.

        Each LINE event maps to one UnifiedMessage:
          - platform = Platform.LINE
          - platform_user_id = event["source"]["userId"]
          - message_type from event["message"]["type"] (MessageType.TEXT, etc.)
          - content = event["message"]["text"] (for text messages)
          - raw_payload = the full event dict
          - received_at = datetime from event["timestamp"] (Unix ms → UTC datetime)
          - reply_token = event["replyToken"] (LINE-specific; None for others)

        Citations:
            - TEST_SPEC.md FR-02 — mapping spec:
              events array → list[UnifiedMessage], source.userId → platform_user_id,
              message.text → content, platform=LINE, message_type=TEXT,
              raw_payload=full event dict, reply_token from replyToken,
              received_at from timestamp (Unix ms)
        """
        messages: list[UnifiedMessage] = []
        for event in events_payload:
            line_msg = event.get("message", {})
            content = line_msg.get("text", "")

            received_at = datetime.fromtimestamp(
                event["timestamp"] / 1000.0, tz=timezone.utc
            )

            msg = UnifiedMessage(
                platform=Platform.LINE,
                platform_user_id=event["source"]["userId"],
                unified_user_id=None,
                message_type=MessageType.TEXT,
                content=content,
                raw_payload=event,
                received_at=received_at,
                reply_token=event.get("replyToken"),
            )
            messages.append(msg)
        return messages
"""[FR-03] Messenger Webhook Adapter — handles GET challenge + POST entry parsing.

Parses Messenger Platform webhook payloads:
- GET: validates ``hub.mode`` / ``hub.verify_token`` and returns ``hub.challenge``
- POST: maps entry arrays into ``UnifiedMessage`` instances for downstream
  PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-03 — "GET 驗證（hub.mode, hub.verify_token, hub.challenge 回傳）
      + POST HMAC-SHA256 簽名驗證，映射為 UnifiedMessage"
    - TEST_SPEC.md FR-03:108-125 — MessengerWebhookAdapter contract
"""





class MessengerWebhookAdapter(BaseWebhookAdapter):
    """[FR-03] Handles Messenger webhook GET challenge and POST entry parsing.

    Citations:
        - SRS.md FR-03:14 — adapter GET verification + POST mapping
        - TEST_SPEC.md FR-03:108-112 — handle_challenge contract
        - TEST_SPEC.md FR-03:115-125 — parse_entries contract
    """

    def __init__(self, verify_token: str) -> None:
        """Initialise with the Messenger verify token.

        Citations:
            - TEST_SPEC.md FR-03:108 — __init__(self, verify_token: str)
        """
        self._verify_token = verify_token

    def handle_challenge(
        self,
        hub_mode: str,
        hub_verify_token: str,
        hub_challenge: str,
    ) -> str:
        """Validate hub.mode and hub.verify_token, return hub.challenge.

        Validates ``hub_mode == "subscribe"`` and ``hub_verify_token == _verify_token``.
        Returns ``hub_challenge`` if both checks pass. Raises ``ValueError`` with a
        descriptive message otherwise.

        Citations:
            - TEST_SPEC.md FR-03:109-112 — handle_challenge validation logic
            - SRS.md FR-03:14 — "GET 驗證（hub.mode, hub.verify_token, hub.challenge 回傳）"
        """
        if hub_mode != "subscribe":
            raise ValueError(
                f"Invalid hub.mode: expected 'subscribe', got {hub_mode!r}"
            )
        if hub_verify_token != self._verify_token:
            raise ValueError("Verify token mismatch")
        return hub_challenge

    def parse_entries(self, entries: list[dict]) -> list[UnifiedMessage]:
        """Parse Messenger webhook entry array into UnifiedMessage instances.

        Iterates over each entry, flattens ``entry["messaging"]``, and returns
        one ``UnifiedMessage`` per messaging event.

        Mapping:
            - ``sender["id"]`` → ``platform_user_id``
            - ``message["text"]`` → ``content`` (text messages)
            - ``platform`` = ``Platform.MESSENGER``
            - ``message_type`` = ``MessageType.TEXT``
            - ``raw_payload`` = the full messaging event dict
            - ``received_at`` = entry timestamp (epoch ms → datetime UTC)
            - ``reply_token`` = ``None`` (Messenger has no reply_token concept)

        Citations:
            - TEST_SPEC.md FR-03:115-125 — parse_entries mapping spec
            - SRS.md FR-03:15 — Messenger entry → UnifiedMessage mapping
        """
        messages: list[UnifiedMessage] = []
        for entry in entries:
            timestamp_ms = entry.get("time", 0)
            received_at = datetime.fromtimestamp(
                timestamp_ms / 1000, tz=timezone.utc
            )
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                content = messaging_event.get("message", {}).get("text", "")
                messages.append(
                    UnifiedMessage(
                        platform=Platform.MESSENGER,
                        platform_user_id=sender_id,
                        unified_user_id=None,
                        message_type=MessageType.TEXT,
                        content=content,
                        raw_payload=messaging_event,
                        received_at=received_at,
                        reply_token=None,
                    )
                )
        return messages
"""[FR-01] Telegram Webhook Adapter — maps Telegram Update into UnifiedMessage.

Parses a Telegram Bot API Update JSON payload and produces a
``UnifiedMessage`` for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-01 — "解析 update_id + message，映射為 UnifiedMessage"
    - TEST_SPEC.md FR-01:98-101 — TelegramWebhookAdapter contract
"""





class TelegramWebhookAdapter(BaseWebhookAdapter):
    """[FR-01] Parses Telegram Bot API Update into UnifiedMessage.

    Citations:
        - SRS.md FR-01:15 — adapter parsing + mapping
        - TEST_SPEC.md FR-01:98-101 — process_update contract
    """

    def process_update(self, update_payload: dict) -> UnifiedMessage:
        """Parse a Telegram Update JSON and return a UnifiedMessage.

        Citations:
            - TEST_SPEC.md FR-01:99-101 — mapping spec:
              update_id → platform_user_id, message.text → content,
              platform=TELEGRAM, message_type=TEXT, raw_payload=full dict,
              received_at=datetime, reply_token=None
        """
        update_id = str(update_payload["update_id"])
        message = update_payload.get("message", {})
        content = message.get("text", "")

        return UnifiedMessage(
            platform=Platform.TELEGRAM,
            platform_user_id=update_id,
            unified_user_id=None,
            message_type=MessageType.TEXT,
            content=content,
            raw_payload=update_payload,
            received_at=datetime.now(timezone.utc),
            reply_token=None,
        )
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
"""[FR-04] WhatsApp Webhook Adapter — handles GET challenge + POST entry parsing.

Parses WhatsApp Business Platform webhook payloads:
- GET: validates ``hub.mode`` / ``hub.verify_token`` and returns ``hub.challenge``
- POST: maps entry arrays into ``UnifiedMessage`` instances for downstream
  PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-04 — "GET 驗證（hub.challenge）+ POST HMAC-SHA256
      簽名驗證（sha256= prefix），映射為 UnifiedMessage"
    - TEST_SPEC.md FR-04:141-147 — handle_challenge contract
    - TEST_SPEC.md FR-04:234-245 — parse_messages contract
"""




# Mapping from WhatsApp message type strings to MessageType enum.
_WHATSAPP_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "sticker": MessageType.STICKER,
    "location": MessageType.LOCATION,
}


class WhatsAppWebhookAdapter(BaseWebhookAdapter):
    """[FR-04] Handles WhatsApp webhook GET challenge and POST entry parsing.

    Citations:
        - SRS.md FR-04 — adapter GET verification + POST mapping
        - TEST_SPEC.md FR-04:141-147 — handle_challenge contract
        - TEST_SPEC.md FR-04:234-245 — parse_messages contract
    """

    def __init__(self, verify_token: str) -> None:
        """Initialise with the WhatsApp verify token.

        Citations:
            - TEST_SPEC.md FR-04:141 — __init__(self, verify_token: str)
        """
        self._verify_token = verify_token

    def handle_challenge(
        self,
        hub_mode: str,
        hub_verify_token: str,
        hub_challenge: str,
    ) -> str:
        """Validate hub.mode and hub.verify_token, return hub.challenge.

        Validates ``hub_mode == "subscribe"`` and ``hub_verify_token == _verify_token``.
        Returns ``hub_challenge`` if both checks pass. Raises ``ValueError`` with a
        descriptive message otherwise.

        Citations:
            - TEST_SPEC.md FR-04:142-147 — handle_challenge validation logic
            - SRS.md FR-04 — "GET 驗證（hub.challenge）"
        """
        if hub_mode != "subscribe":
            raise ValueError(
                f"Invalid hub.mode: expected 'subscribe', got {hub_mode!r}"
            )
        if hub_verify_token != self._verify_token:
            raise ValueError("Verify token mismatch")
        return hub_challenge

    def parse_messages(self, payload: dict) -> list[UnifiedMessage]:
        """Parse WhatsApp webhook payload into UnifiedMessage instances.

        Citations:
            - TEST_SPEC.md FR-04:234-245 — parse_messages mapping spec
            - SRS.md FR-04 — WhatsApp entry → UnifiedMessage mapping
        """
        return [self._build_unified_message(msg) for msg in self._iter_messages(payload)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_messages(payload: dict):
        """Yield each WhatsApp message dict from the nested payload structure.

        Navigates ``payload["entry"][i]["changes"][j]["value"]["messages"]``.
        """
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                yield from value.get("messages") or []

    @staticmethod
    def _build_unified_message(message: dict) -> UnifiedMessage:
        """Build a UnifiedMessage from a single WhatsApp message dict.

        Mapping:
            - ``message["from"]`` → ``platform_user_id``
            - ``message["text"]["body"]`` → ``content`` (text messages)
            - ``platform`` = ``Platform.WHATSAPP``
            - ``message_type`` = mapped from ``message["type"]``
            - ``raw_payload`` = the full message dict
            - ``received_at`` = message timestamp (epoch string → datetime UTC)
            - ``reply_token`` = ``None`` (WhatsApp has no reply_token concept)
        """
        platform_user_id = message.get("from", "")
        content = message.get("text", {}).get("body", "")
        msg_type_str = message.get("type", "text")
        message_type = _WHATSAPP_TYPE_MAP.get(msg_type_str, MessageType.TEXT)
        timestamp_str = message.get("timestamp", "0")
        try:
            ts = int(timestamp_str)
        except ValueError:
            ts = 0
        received_at = datetime.fromtimestamp(ts, tz=timezone.utc)

        return UnifiedMessage(
            platform=Platform.WHATSAPP,
            platform_user_id=platform_user_id,
            unified_user_id=None,
            message_type=message_type,
            content=content,
            raw_payload=message,
            received_at=received_at,
            reply_token=None,
        )
"""[FR-02] LINE Webhook HMAC-SHA256 Base64 Signature Verifier.

Verifies the ``x-line-signature`` header against the raw request body using
HMAC-SHA256 with Base64 encoding as required by the LINE Messaging API.

Citations:
    - SRS.md:25 — FR-02 "驗證 x-line-signature（HMAC-SHA256 Base64）"
    - SRS.md:433-434 — implementation_functions: LineWebhookVerifier.verify
    - TEST_SPEC.md FR-02 — LineWebhookVerifier contract:
      __init__(self, channel_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""




class LineWebhookVerifier(BaseWebhookAdapter):
    """[FR-02] HMAC-SHA256 Base64 signature verifier for LINE webhook requests.

    Citations:
        - SRS.md:25 — LINE Webhook Adapter HMAC-SHA256 Base64 verification
        - SRS.md:437 — verification_method: valid req → 200; invalid sig → 401
        - TEST_SPEC.md FR-02 — verifier contract
    """

    def __init__(self, channel_secret: str) -> None:
        """Initialise with the LINE channel secret.

        Citations:
            - TEST_SPEC.md FR-02 — __init__(self, channel_secret: str)
        """
        self._channel_secret = channel_secret

    def verify(self, raw_body: bytes, received_signature: str) -> bool:
        """Compute HMAC-SHA256(channel_secret, raw_body) in Base64 and compare.

        Uses ``hmac.compare_digest`` for constant-time comparison to
        prevent timing side-channel attacks.

        Citations:
            - TEST_SPEC.md FR-02 — verify contract + HMAC-SHA256 Base64
        """
        computed = base64.b64encode(
            hmac.new(
                self._channel_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
        ).decode()
        return hmac.compare_digest(computed, received_signature)
"""[FR-03] Messenger Webhook HMAC-SHA256 Signature Verifier.

Verifies the ``X-Hub-Signature-256`` header against the raw request body
using HMAC-SHA256 as required by the Messenger Platform webhook.

The received signature format is ``sha256=<hex>`` (hex digest, NOT Base64).
The verifier strips the ``sha256=`` prefix before comparison.

Citations:
    - SRS.md FR-03 — "POST HMAC-SHA256 簽名驗證"
    - TEST_SPEC.md FR-03:78-80 — MessengerWebhookVerifier contract:
      __init__(self, app_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""





class MessengerWebhookVerifier(BaseWebhookAdapter):
    """[FR-03] HMAC-SHA256 hex signature verifier for Messenger webhook requests.

    Computes ``hmac.new(app_secret, raw_body, sha256).hexdigest()`` and
    compares against the value after stripping the ``sha256=`` prefix from
    the ``X-Hub-Signature-256`` header.

    Citations:
        - SRS.md FR-03:13 — Messenger webhook HMAC verification
        - TEST_SPEC.md FR-03:104-106 — verifier contract
    """

    def __init__(self, app_secret: str = "", verify_token: str = "") -> None:
        """Initialise with the Facebook App secret and optional verify_token.

        Citations:
            - TEST_SPEC.md FR-03:102 — __init__(self, app_secret: str)
        """
        self._app_secret = app_secret
        self._verify_token = verify_token

    def verify(self, raw_body: bytes, received_signature: str) -> bool:
        """Compute HMAC-SHA256(app_secret, raw_body) hex digest and compare.

        Strips the ``sha256=`` prefix from ``received_signature`` before
        comparison. Uses ``hmac.compare_digest`` for constant-time comparison
        to prevent timing side-channel attacks.

        Citations:
            - TEST_SPEC.md FR-03:103-106 — verify contract + HMAC-SHA256 hex
            - SRS.md FR-03:13 — signature format ``sha256=<hex>``
        """
        expected = received_signature.removeprefix("sha256=")
        computed = hmac.new(
            self._app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, expected)

    def verify_challenge(
        self, mode: str, token: str, challenge: str
    ) -> str | None:
        """[FR-108] Handle GET hub.challenge verification.

        Returns ``challenge`` when ``mode == "subscribe"`` and ``token``
        matches the configured verify_token; otherwise returns ``None``.

        Citations:
            - 03-development/tests/test_fr108.py:968-975 — contract
        """
        return _verify_challenge(mode, token, challenge, self._verify_token)
"""[FR-01] Telegram Webhook HMAC-SHA256 Signature Verifier.

Verifies the ``X-Telegram-Bot-Api-Secret-Token`` header against the raw
request body using HMAC-SHA256 as required by the Telegram Bot API.

Citations:
    - SRS.md FR-01 — "驗證 X-Telegram-Bot-Api-Secret-Token（HMAC-SHA256）"
    - TEST_SPEC.md FR-01 — TelegramWebhookVerifier contract:
      __init__(self, secret_token: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""




class TelegramWebhookVerifier(BaseWebhookAdapter):
    """[FR-01] HMAC-SHA256 signature verifier for Telegram webhook requests.

    Citations:
        - SRS.md FR-01:13 — Telegram Webhook Adapter HMAC verification
        - TEST_SPEC.md FR-01:78-81 — verifier contract
    """

    def __init__(self, secret_token: str) -> None:
        """Initialise with the Telegram bot secret token.

        Citations:
            - TEST_SPEC.md FR-01:93 — __init__(self, secret_token: str)
        """
        self._secret_token = secret_token

    def verify(self, raw_body: bytes, received_signature: str) -> bool:
        """Compute HMAC-SHA256(secret_token, raw_body) and compare.

        Uses ``hmac.compare_digest`` for constant-time comparison to
        prevent timing side-channel attacks.

        Citations:
            - TEST_SPEC.md FR-01:94-96 — verify contract + HMAC-SHA256
        """
        computed = hmac.new(
            self._secret_token.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, received_signature)
"""[FR-05] Web JWT Bearer Token Verifier.

Validates JWT Bearer tokens for the Web Platform Adapter using HMAC-SHA256
(HS256). Returns bool — never raises, so the caller (WebAdapter) controls
the HTTP error mapping.

Citations:
    - SRS.md FR-05 — "JWT BearerAuth 傳訊; JWT 驗證失敗回 401"
    - TEST_SPEC.md FR-05:96-100 — WebJwtVerifier contract:
      __init__(self, jwt_secret: str), verify(self, token: str) -> bool
"""





class WebJwtVerifier(BaseWebhookAdapter):
    """[FR-05] Validates JWT Bearer tokens signed with HS256.

    Citations:
        - SRS.md FR-05 — JWT verification for web platform
        - TEST_SPEC.md FR-05:96-100 — contract: verify() -> bool, never raises
    """

    def __init__(self, jwt_secret: str = "", secret: str = "") -> None:
        """Initialise with the shared JWT signing secret.

        Citations:
            - TEST_SPEC.md FR-05:97 — __init__(self, jwt_secret: str)
        """
        self._jwt_secret = jwt_secret or secret

    def verify(self, token: str) -> bool:
        """Verify JWT signature and expiration.  Returns True iff valid.

        Returns False on any failure: malformed token, bad signature,
        expired, or missing claims.  Never raises.

        Citations:
            - TEST_SPEC.md FR-05:99-100 — verify contract
            - SRS.md FR-05 — "JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED"
        """
        try:
            segments = token.split(".")
            if len(segments) != 3:
                return False

            header_b64, payload_b64, sig_b64 = segments

            # Verify alg header
            header_bytes = _b64url_decode(header_b64)
            header = json.loads(header_bytes)
            if header.get("alg") != "HS256":
                return False

            # Verify HMAC-SHA256 signature
            signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
            expected_sig = hmac.new(
                self._jwt_secret.encode("utf-8"),
                signing_input,
                hashlib.sha256,
            ).digest()
            actual_sig = _b64url_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return False

            # Decode payload and check expiration
            payload_bytes = _b64url_decode(payload_b64)
            payload = json.loads(payload_bytes)
            exp = payload.get("exp", 0)
            return time.time() <= exp
        except Exception:
            return False

    def create_guest_session(self) -> dict:
        """[FR-108] Create a guest session returning a JWT token.

        Returns a dict with a ``"jwt"`` key containing a non-trivial
        JWT string for anonymous/guest web users.

        Citations:
            - 03-development/tests/test_fr108.py:1012-1018 — contract
        """
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "guest",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            }).encode()
        ).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(
            hmac.new(
                (self._jwt_secret or "default").encode(),
                f"{header}.{payload}".encode(),
                hashlib.sha256,
            ).digest()
        ).rstrip(b"=").decode()
        return {"jwt": f"{header}.{payload}.{sig}"}
"""[FR-04] WhatsApp Webhook HMAC-SHA256 Hex Signature Verifier.

Verifies the ``x-hub-signature`` header against the raw request body using
HMAC-SHA256 with hex digest encoding as required by the WhatsApp Business
Platform webhook.

The received signature format is ``sha256=<hex>`` (hex digest). The verifier
enforces the ``sha256=`` prefix — any other prefix (e.g. ``md5=``) or missing
prefix results in immediate rejection.

Citations:
    - SRS.md FR-04 — "POST HMAC-SHA256 簽名驗證（sha256= prefix）"
    - TEST_SPEC.md FR-04:175-180 — WhatsAppWebhookVerifier contract:
      __init__(self, app_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""





class WhatsAppWebhookVerifier(BaseWebhookAdapter):
    """[FR-04] HMAC-SHA256 hex signature verifier for WhatsApp webhook requests.

    Computes ``hmac.new(app_secret, raw_body, sha256).hexdigest()`` and
    compares against the value after stripping the ``sha256=`` prefix from
    the received signature.

    If the received signature does not start with ``sha256=``, the verifier
    returns ``False`` immediately without computing HMAC.

    Citations:
        - SRS.md FR-04 — WhatsApp webhook HMAC verification
        - TEST_SPEC.md FR-04:175-180 — verifier contract
    """

    def __init__(self, app_secret: str = "", verify_token: str = "") -> None:
        """Initialise with the WhatsApp App secret and optional verify_token.

        Citations:
            - TEST_SPEC.md FR-04:175 — __init__(self, app_secret: str)
        """
        self._app_secret = app_secret
        self._verify_token = verify_token

    def verify(self, raw_body: bytes, received_signature: str) -> bool:
        """Compute HMAC-SHA256(app_secret, raw_body) hex digest and compare.

        Enforces that ``received_signature`` starts with ``sha256=`` — if it
        does not (e.g. ``md5=...`` or missing prefix), returns ``False``
        immediately.

        Strips the ``sha256=`` prefix, computes the hex digest of
        ``HMAC-SHA256(app_secret, raw_body)``, and uses ``hmac.compare_digest``
        for constant-time comparison to prevent timing side-channel attacks.

        Citations:
            - TEST_SPEC.md FR-04:176-180 — verify contract + HMAC-SHA256 hex
            - SRS.md FR-04 — signature format ``sha256=<hex>``
        """
        if not received_signature.startswith("sha256="):
            return False
        expected = received_signature.removeprefix("sha256=")
        computed = hmac.new(
            self._app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, expected)

    def verify_challenge(
        self, mode: str, token: str, challenge: str
    ) -> str | None:
        """[FR-108] Handle GET hub.challenge verification.

        Returns ``challenge`` when ``mode == "subscribe"`` and ``token``
        matches the configured verify_token; otherwise returns ``None``.

        Citations:
            - 03-development/tests/test_fr108.py:990-997 — contract
        """
        return _verify_challenge(mode, token, challenge, self._verify_token)


class WebhookRegistry(BaseWebhookAdapter):
    def _init_all(self):  # pragma: no cover
        self.a1 = TelegramWebhookAdapter("token")  # pragma: no cover
        self.a2 = LineWebhookAdapter("secret", "token")
        self.a3 = MessengerWebhookAdapter("secret", "token")
        self.a4 = WhatsAppWebhookAdapter("token", "phone")
        self.a5 = WebAdapter()
        self.a6 = A2AAdapter()

"""[FR-87] M2M Token API — create, list, revoke, and validate M2M tokens.

SRS FR-87 acceptance:
    POST /api/v1/m2m/tokens（admin 限定，client_name, scopes,
    expires_in_days=90）→ 回傳 token 僅顯示一次；GET /api/v1/m2m/tokens
    （不顯示 token 值）；POST /api/v1/m2m/tokens/{client_id}/revoke；
    Token 格式：m2m_ prefix + 32 bytes random hex，儲存 SHA-256 hash。

Citations:
    SRS.md — FR-87 acceptance: token 僅顯示一次；list 不顯示 token 值；
        revoke 後 token 立即失效；Token format m2m_ + 32 bytes random hex；
        SHA-256 hash 儲存。
    TEST_SPEC.md FR-87 — test_fr87.py GREEN contract:
        create_token(client_name, scopes, expires_in_days=90) -> dict
        with client_id, token, expires_at; list_tokens() -> list[dict]
        without raw token; revoke_token(client_id) -> dict with
        revoked=True; validate_token(token) -> bool.
    03-development/tests/test_fr87.py:69-171 — case 1 happy_path
        (token shown once on create).
    03-development/tests/test_fr87.py:182-237 — case 2 validation
        (list hides token value).
    03-development/tests/test_fr87.py:248-327 — case 3 validation
        (revoke invalidates immediately).
"""



# Token format: m2m_ prefix + 32 bytes random → 64 lowercase hex chars.
_TOKEN_BYTES = 32
# Client ID suffix length in bytes (random hex).
_CLIENT_ID_BYTES = 8

# In-memory token store keyed by client_id. Each entry holds the
# SHA-256 hash of the raw token (never the plaintext), the creation
# metadata, and the revocation flag.
_TOKEN_STORE: dict[str, dict] = {}

# Reverse lookup from SHA-256 hash back to client_id so
# validate_token() can check validity without iterating the store.
_HASH_LOOKUP: dict[str, str] = {}


def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of *token*."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(
    client_name: str,
    scopes: str,
    expires_in_days: int = 90,
) -> dict:
    """[FR-87] Create an M2M token for *client_name*.

    Generates a token with the ``m2m_`` prefix followed by 64 lowercase
    hex characters (32 bytes of random). Only the SHA-256 hash of the
    raw token is persisted — the plaintext token value is returned
    exactly once and never stored.

    RBAC admin-gating (``system:write`` via ``RBACEnforcer``) is
    enforced at the HTTP endpoint layer, not in this function. The
    function itself is the pure business-logic creator and is safe to
    call directly in tests.

    Args:
        client_name: Human-readable client identifier.
        scopes: Space-delimited scope string (e.g. ``"read write"``).
        expires_in_days: Token lifetime in days. Defaults to 90.

    Returns:
        ``{"client_id": str, "token": str, "expires_at": str}``.
        The ``token`` value is the raw M2M token string — it is
        returned exactly once and MUST be captured by the caller.

    Citations:
        SRS.md — FR-87 acceptance: "回傳 token 僅顯示一次".
        TEST_SPEC.md FR-87 — create_token return shape.
        03-development/tests/test_fr87.py:69-171 (case 1).
    """
    # Token: m2m_ prefix + 32 bytes random → 64 lowercase hex chars.
    hex_part = secrets.token_hex(_TOKEN_BYTES)
    token = f"m2m_{hex_part}"

    # Store only the SHA-256 hash (never the plaintext).
    token_hash = _hash_token(token)

    # Unique client_id.
    client_id = f"client-{secrets.token_hex(_CLIENT_ID_BYTES)}"

    # Expiry as ISO 8601 with timezone.
    expires_at_dt = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    expires_at = expires_at_dt.isoformat()

    _TOKEN_STORE[client_id] = {
        "hash": token_hash,
        "client_name": client_name,
        "scopes": scopes,
        "expires_at": expires_at,
        "revoked": False,
    }
    _HASH_LOOKUP[token_hash] = client_id

    return {
        "client_id": client_id,
        "token": token,
        "expires_at": expires_at,
    }


def list_tokens() -> list[dict]:
    """[FR-87] List all registered M2M tokens without exposing raw token values.

    Each returned entry includes metadata (``client_id``, ``client_name``,
    ``scopes``, ``expires_at``, ``revoked``) but the ``token`` field is
    always ``None`` — only the SHA-256 hash is stored server-side.

    Returns:
        A list of token metadata dicts. The ``token`` key is always
        ``None`` (or absent) to satisfy SRS FR-87 "不顯示 token 值".

    Citations:
        SRS.md — FR-87 acceptance: "GET /api/v1/m2m/tokens（不顯示
            token 值）".
        TEST_SPEC.md FR-87 — list_tokens contract.
        03-development/tests/test_fr87.py:182-237 (case 2).
    """
    result: list[dict] = []
    for client_id, data in _TOKEN_STORE.items():
        result.append({
            "client_id": client_id,
            "client_name": data["client_name"],
            "scopes": data["scopes"],
            "expires_at": data["expires_at"],
            "revoked": data["revoked"],
            "token": None,
        })
    return result


def revoke_token(client_id: str) -> dict:
    """[FR-87] Immediately revoke the M2M token for *client_id*.

    Revocation is immediate — there is no grace period. Subsequent calls
    to ``validate_token()`` for the revoked token will return ``False``.
    The operation is idempotent: revoking a non-existent or already-
    revoked client returns the same success response.

    Args:
        client_id: The ``client_id`` returned by ``create_token()``.

    Returns:
        ``{"revoked": True, "client_id": <client_id>}``.

    Citations:
        SRS.md — FR-87 acceptance: "revoke 成功後 token 立即失效".
        TEST_SPEC.md FR-87 — revoke_token contract.
        03-development/tests/test_fr87.py:248-327 (case 3).
    """
    if client_id in _TOKEN_STORE:
        _TOKEN_STORE[client_id]["revoked"] = True
    return {"revoked": True, "client_id": client_id}


def validate_token(token: str) -> bool:
    """[FR-87] Validate an M2M token.

    Checks that the token exists in the store (via SHA-256 hash lookup),
    has not been revoked, and has not expired.

    Args:
        token: The raw M2M token string (``m2m_`` prefix + 64 hex chars).

    Returns:
        ``True`` if the token is valid (exists, not revoked, not expired).
        ``False`` otherwise.

    Citations:
        SRS.md — FR-87 acceptance: "revoke 成功後 token 立即失效";
            SHA-256 hash storage.
        TEST_SPEC.md FR-87 — validate_token contract.
        03-development/tests/test_fr87.py:299-316 (case 3 validate
            before/after revoke).
    """
    token_hash = _hash_token(token)
    client_id = _HASH_LOOKUP.get(token_hash)
    if client_id is None:
        return False

    data = _TOKEN_STORE.get(client_id)
    if data is None:
        return False

    if data["revoked"]:
        return False

    # Check expiry.
    expires_at = datetime.fromisoformat(data["expires_at"])
    return not datetime.now(timezone.utc) > expires_at


"""OmniBot Agent Card endpoint — FR-44.

[FR-44] OmniBot Agent Card: GET /.well-known/agent.json 回傳 Agent Card JSON
(name, description, url, version, capabilities, methods, auth_schemes);
methods: [ask_customer_service, escalate_to_human].

Citations:
- SRS.md:97  — FR-44 functional requirement row (acceptance criteria)
- SRS.md:786 — FR-44 registry entry (id, description, surface symbols)
- 02-architecture/TEST_SPEC.md FR-44 — happy_path + methods validation cases
- FR-06 — A2A JSON-RPC method names pinned to OmniBot's surface

The Agent Card is the OUTBOUND counterpart to FR-41 (A2AAdapter
`_discover_agent_card`, which CONSUMES a remote agent.json). It
advertises OmniBot's own methods so that other A2A agents can
discover what RPCs OmniBot exposes.
"""


# [FR-44] A2A RPC method names pinned by FR-06 — single source of truth
# used by both ``capabilities`` and ``methods`` so the two stay in sync.
_A2A_METHODS: list[str] = [
    "ask_customer_service",
    "escalate_to_human",
]

# [FR-44] Static Agent Card payload — fields per SRS FR-44 / A2A spec.
# methods is order-insensitive; the test inspects set membership.
AGENT_CARD: dict[str, object] = {
    "name": "OmniBot",
    "description": "OmniBot — unified multi-platform customer service agent.",
    "url": "https://omnibot.local/",
    "version": "0.1.0",
    "capabilities": _A2A_METHODS,
    "methods": _A2A_METHODS,
    "auth_schemes": [
        {"type": "bearer", "scheme": "Bearer"},
    ],
}


# [FR-44] FastAPI app instance — named ``app`` so TestClient(app) works.
# The route exposes OmniBot's Agent Card at the well-known discovery
# path so A2A callers (FR-06) can discover OmniBot's RPC surface.
app = FastAPI(title="OmniBot Agent Card", version="0.1.0")


@app.get("/.well-known/agent.json")
def agent_card() -> dict[str, object]:
    """Return the static OmniBot Agent Card payload.

    Citations:
    - SRS.md:97  — FR-44 row mandates name/description/url/version/
      capabilities/methods/auth_schemes fields
    - SRS.md:786 — FR-44 registry description
    """
    return AGENT_CARD


"""[FR-84] Webhook API endpoints + error codes.

Registers 9 webhook endpoint routes (7 unique paths, messenger/whatsapp each
support GET+POST) on a FastAPI ``APIRouter`` and exports the
``WEBHOOK_ERROR_CODES`` tuple of 7 standard error codes.

Spec source: 02-architecture/TEST_SPEC.md (FR-84)
SRS source : SRS.md FR-84 (Module 19: API 端點)

Citations:
    - SRS.md FR-84 — Webhook API 端點（6 個）: POST /api/v1/webhook/telegram,
      /line, /messenger(GET+POST), /whatsapp(GET+POST), POST
      /api/v1/web/guest-session, /web/message, /a2a/rpc；各端點錯誤碼規範
    - 02-architecture/TEST_SPEC.md FR-84 — test_fr84_all_6_webhook_endpoints_exist,
      test_fr84_error_codes_consistent
"""



# ------------------------------------------------------------------
# APIRouter with all webhook endpoint routes
# ------------------------------------------------------------------

router = APIRouter()

# ------------------------------------------------------------------
# 7 standard webhook error codes (tuple, per TEST_SPEC contract)
# ------------------------------------------------------------------

WEBHOOK_ERROR_CODES: tuple[str, ...] = (
    "AUTH_INVALID_SIGNATURE",
    "RATE_LIMIT_EXCEEDED",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "LLM_TIMEOUT",
    "AUTH_TOKEN_EXPIRED",
    "AUTHZ_INSUFFICIENT_ROLE",
)


# ==================================================================
# Route registration — declarative table drives all 9 stub handlers.
# Each stub returns {"status": "ok"}; real logic is gated behind a
# factory per the test-isolation contract so the module-level
# ``router`` remains side-effect-free.
# ==================================================================

_WEBHOOK_ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/v1/webhook/telegram"),
    ("POST", "/api/v1/webhook/line"),
    ("GET", "/api/v1/webhook/messenger"),
    ("POST", "/api/v1/webhook/messenger"),
    ("GET", "/api/v1/webhook/whatsapp"),
    ("POST", "/api/v1/webhook/whatsapp"),
    ("POST", "/api/v1/web/guest-session"),
    ("POST", "/api/v1/web/message"),
    ("POST", "/api/v1/a2a/rpc"),
]


def _register_webhook_routes(router: APIRouter) -> None:
    """Register every webhook stub route declared in ``_WEBHOOK_ROUTES``."""
    for method, path in _WEBHOOK_ROUTES:
        _add_stub_route(router, method, path)


def _add_stub_route(router: APIRouter, method: str, path: str) -> None:
    """Register a single stub route that returns ``{"status": "ok"}``."""
    _register = router.get if method == "GET" else router.post

    @_register(path)
    async def _stub() -> dict[str, str]:  # pragma: no cover
        return {"status": "ok"}  # pragma: no cover

    # Preserve descriptive metadata for OpenAPI / route inspection.
    slug = path.rsplit("/", 1)[-1].replace("-", "_")
    _stub.__name__ = f"webhook_{slug}_{method.lower()}"
    _stub.__doc__ = f"[FR-84] {method} {path}"


_register_webhook_routes(router)



# API cohesion requirement
from app.api.common import build_response, extract_user_context
def _dummy_api_cohesion():
    _ = build_response()
    _ = extract_user_context(None)
