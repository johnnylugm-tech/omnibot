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

import base64

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------
import base64 as _base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, FastAPI

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
# Module-level functions (NOT BaseWebhookAdapter methods) so any
# adapter or verifier can call them without instantiating the class.
# Previously these helpers lived in WebJwtVerifier and were
# self-imported via ``from app.api.webhooks import _b64url_decode``;
# that circular import broke when ``webhooks.py`` was split across
# multiple modules. Centralising them at module scope removes the
# cycle and keeps the helper signatures stable for downstream
# callers (``app.api.auth`` and ``WebJwtVerifier``).
# ------------------------------------------------------------------



from app.api.adapters.base import BaseWebhookAdapter


_WHATSAPP_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "sticker": MessageType.STICKER,
    "location": MessageType.LOCATION,
}

class WhatsAppWebhookAdapter(BaseWebhookAdapter):
    """[FR-04] Handles WhatsApp webhook GET challenge and POST entry parsing.

    Citations:
        - SRS.md FR-04 — adapter GET verification + POST mapping
        - TEST_SPEC.md FR-04:141-147 — handle_challenge contract
        - TEST_SPEC.md FR-04:234-245 — parse_messages contract
    """

    def __init__(self, verify_token: str) -> None:
        """Initialise with the WhatsApp verify token.

        Citations:
            - TEST_SPEC.md FR-04:141 — __init__(self, verify_token: str)
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
            - TEST_SPEC.md FR-04:142-147 — handle_challenge validation logic
            - SRS.md FR-04 — "GET 驗證（hub.challenge）"
        """
        if hub_mode != "subscribe":
            raise ValueError(
                f"Invalid hub.mode: expected 'subscribe', got {hub_mode!r}"
            )
        if hub_verify_token != self._verify_token:
            raise ValueError("Verify token mismatch")
        return hub_challenge

    def parse_messages(self, payload: dict) -> list[UnifiedMessage]:
        """Parse WhatsApp webhook payload into UnifiedMessage instances.

        Citations:
            - TEST_SPEC.md FR-04:234-245 — parse_messages mapping spec
            - SRS.md FR-04 — WhatsApp entry → UnifiedMessage mapping
        """
        return [self._build_unified_message(msg) for msg in self._iter_messages(payload)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_messages(payload: dict):
        """Yield each WhatsApp message dict from the nested payload structure.

        Navigates ``payload["entry"][i]["changes"][j]["value"]["messages"]``.
        """
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                yield from value.get("messages") or []

    @staticmethod
    def _build_unified_message(message: dict) -> UnifiedMessage:
        """Build a UnifiedMessage from a single WhatsApp message dict.

        Mapping:
            - ``message["from"]`` → ``platform_user_id``
            - ``message["text"]["body"]`` → ``content`` (text messages)
            - ``platform`` = ``Platform.WHATSAPP``
            - ``message_type`` = mapped from ``message["type"]``
            - ``raw_payload`` = the full message dict
            - ``received_at`` = message timestamp (epoch string → datetime UTC)
            - ``reply_token`` = ``None`` (WhatsApp has no reply_token concept)
        """
        platform_user_id = message.get("from", "")
        content = message.get("text", {}).get("body", "")
        msg_type_str = message.get("type", "text")
        message_type = _WHATSAPP_TYPE_MAP.get(msg_type_str, MessageType.TEXT)
        timestamp_str = message.get("timestamp", "0")
        try:
            ts = int(timestamp_str)
        except ValueError:
            ts = 0
        received_at = datetime.fromtimestamp(ts, tz=timezone.utc)

        return UnifiedMessage(
            platform=Platform.WHATSAPP,
            platform_user_id=platform_user_id,
            unified_user_id=None,
            message_type=message_type,
            content=content,
            raw_payload=message,
            received_at=received_at,
            reply_token=None,
        )

