"""OmniBot Agent Card endpoint — FR-44.

[FR-44] OmniBot Agent Card: GET /.well-known/agent.json 回傳 Agent Card JSON
(name, description, url, version, capabilities, methods, auth_schemes);
methods: [ask_customer_service, escalate_to_human].

Citations:
- SRS.md:97  — FR-44 functional requirement row (acceptance criteria)
- SRS.md:786 — FR-44 registry entry (id, description, surface symbols)
- 02-architecture/TEST_SPEC.md FR-44 — happy_path + methods validation cases
- FR-06 — A2A JSON-RPC method names pinned to OmniBot's surface

The Agent Card is the OUTBOUND counterpart to FR-41 (A2AAdapter
`_discover_agent_card`, which CONSUMES a remote agent.json). It
advertises OmniBot's own methods so that other A2A agents can
discover what RPCs OmniBot exposes.
"""
from __future__ import annotations

from fastapi import FastAPI

# [FR-44] A2A RPC method names pinned by FR-06 — single source of truth
# used by both ``capabilities`` and ``methods`` so the two stay in sync.
_A2A_METHODS: list[str] = [
    "ask_customer_service",
    "escalate_to_human",
]

# [FR-44] Static Agent Card payload — fields per SRS FR-44 / A2A spec.
# methods is order-insensitive; the test inspects set membership.
AGENT_CARD: dict[str, object] = {
    "name": "OmniBot",
    "description": "OmniBot — unified multi-platform customer service agent.",
    "url": "https://omnibot.local/",
    "version": "0.1.0",
    "capabilities": _A2A_METHODS,
    "methods": _A2A_METHODS,
    "auth_schemes": [
        {"type": "bearer", "scheme": "Bearer"},
    ],
}


# [FR-44] FastAPI app instance — named ``app`` so TestClient(app) works.
# The route exposes OmniBot's Agent Card at the well-known discovery
# path so A2A callers (FR-06) can discover OmniBot's RPC surface.
app = FastAPI(title="OmniBot Agent Card", version="0.1.0")


@app.get("/.well-known/agent.json")
def agent_card() -> dict[str, object]:
    """Return the static OmniBot Agent Card payload.

    Citations:
    - SRS.md:97  — FR-44 row mandates name/description/url/version/
      capabilities/methods/auth_schemes fields
    - SRS.md:786 — FR-44 registry description
    """
    return AGENT_CARD
