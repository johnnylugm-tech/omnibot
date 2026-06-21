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





class BaseWebhookAdapter:
    pass

