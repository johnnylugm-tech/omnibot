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

from __future__ import annotations

import base64
import hashlib
import hmac


class LineWebhookVerifier:
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
