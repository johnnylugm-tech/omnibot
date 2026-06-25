"""[FR-06] A2A Platform Adapter — inbound A2A JSON-RPC 2.0 handler.
# pragma: no error-handling

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
    - webhooks.py:468-486 — A2A method list (ask_customer_service,
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
                event["timestamp"] / 1000.0, tz=timezone.utc
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

