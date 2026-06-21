"""[FR-02] LINE Webhook Adapter — maps LINE events array into UnifiedMessage.

Parses a LINE Messaging API webhook events array and produces a list of
``UnifiedMessage`` instances for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md:25 — FR-02 "解析 events 陣列，映射為 UnifiedMessage"
    - SRS.md:433-435 — implementation_functions: line_adapter
    - TEST_SPEC.md FR-02 — LineWebhookAdapter contract:
      process_events(self, events_payload: list[dict]) -> list[UnifiedMessage]
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.unified_message import MessageType, Platform, UnifiedMessage


class LineWebhookAdapter:
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
                event["timestamp"] / 1000.0, tz=UTC
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
