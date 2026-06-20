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

from __future__ import annotations

from datetime import datetime, timezone

from app.core.unified_message import MessageType, Platform, UnifiedMessage


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
        results: list[UnifiedMessage] = []
        for entry in entries:
            timestamp_ms = entry.get("time", 0)
            received_at = datetime.fromtimestamp(
                timestamp_ms / 1000.0, tz=timezone.utc
            )
            for msg in entry.get("messaging", []):
                sender_id = msg["sender"]["id"]
                content = msg.get("message", {}).get("text", "")
                results.append(
                    UnifiedMessage(
                        platform=Platform.MESSENGER,
                        platform_user_id=sender_id,
                        unified_user_id=None,
                        message_type=MessageType.TEXT,
                        content=content,
                        raw_payload=msg,
                        received_at=received_at,
                        reply_token=None,
                    )
                )
        return results
