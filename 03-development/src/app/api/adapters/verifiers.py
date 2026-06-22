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
import hashlib
import hmac
import json
import time

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
from app.api.adapters.utils import _b64url_decode, _verify_challenge  # noqa: E402


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
            - 03-development/tests/test_fr108.py:968-975 — contract
        """
        return _verify_challenge(mode, token, challenge, self._verify_token)

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

