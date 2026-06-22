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
# Module-level functions so any
# adapter or verifier can call them without instantiating the class.
# Previously these helpers lived in WebJwtVerifier and were
# self-imported via ``from app.api.webhooks import _b64url_decode``;
# that circular import broke when ``webhooks.py`` was split across
# multiple modules. Centralising them at module scope removes the
# cycle and keeps the helper signatures stable for downstream
# callers (``app.api.auth`` and ``WebJwtVerifier``).
# ------------------------------------------------------------------





class MessengerWebhookAdapter:
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

