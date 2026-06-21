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

from __future__ import annotations

import hashlib
import hmac

from app.services._webhook_utils import _verify_challenge


class WhatsAppWebhookVerifier:
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
