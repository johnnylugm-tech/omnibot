"""[FR-01] Telegram Webhook HMAC-SHA256 Signature Verifier.

Verifies the ``X-Telegram-Bot-Api-Secret-Token`` header against the raw
request body using HMAC-SHA256 as required by the Telegram Bot API.

Citations:
    - SRS.md FR-01 — "驗證 X-Telegram-Bot-Api-Secret-Token（HMAC-SHA256）"
    - TEST_SPEC.md FR-01 — TelegramWebhookVerifier contract:
      __init__(self, secret_token: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""

from __future__ import annotations

import hashlib
import hmac


class TelegramWebhookVerifier:
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
