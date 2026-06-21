"""[FR-01] Telegram Webhook Adapter — maps Telegram Update into UnifiedMessage.

Parses a Telegram Bot API Update JSON payload and produces a
``UnifiedMessage`` for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-01 — "解析 update_id + message，映射為 UnifiedMessage"
    - TEST_SPEC.md FR-01:98-101 — TelegramWebhookAdapter contract
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.unified_message import MessageType, Platform, UnifiedMessage


class TelegramWebhookAdapter:
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
