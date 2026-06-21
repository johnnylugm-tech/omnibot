"""[FR-108] Shared webhook challenge verification — DRY refactor.

Both Messenger and WhatsApp webhook verifiers implement the same
Meta-platform webhook challenge protocol: when ``mode == "subscribe"``
and the verification ``token`` matches the configured secret, the
platform expects the ``challenge`` value echoed back; otherwise the
verification is rejected.

Extracted from the previously-duplicated ``verify_challenge`` methods in
:class:`~app.services.messenger_verifier.MessengerWebhookVerifier` and
:class:`~app.services.whatsapp_verifier.WhatsAppWebhookVerifier`.

Citations:
    - 03-development/tests/test_fr108.py:968-975 (messenger contract)
    - 03-development/tests/test_fr108.py:990-997 (whatsapp contract)
"""

from __future__ import annotations


def _verify_challenge(
    mode: str,
    token: str,
    challenge: str,
    verify_token: str,
) -> str | None:
    """Verify a Meta-platform webhook challenge and return the response.

    Returns ``challenge`` when ``mode == "subscribe"`` and ``token``
    matches ``verify_token``; otherwise returns ``None``.
    """
    if mode == "subscribe" and token == verify_token:
        return challenge
    return None
