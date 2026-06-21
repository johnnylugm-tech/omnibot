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

from __future__ import annotations

import hashlib
import hmac

from app.services._webhook_utils import _verify_challenge


class MessengerWebhookVerifier:
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
