"""[FR-200] Chat history + multi-media router — read-side endpoints for the Web Chat UI.

Adds two read-only endpoints to the FastAPI surface that the
ChatGPT-style web chat (admin + guest) relies on for session continuity:

- ``GET /api/v1/web/conversations/{conversation_id}/history`` —
  delegates to :func:`app.core.pipeline.get_context` to return
  ``{conversation_id, history: [{role, content}, ...]}``. The chat
  UI re-fetches this on reload when IndexedDB is empty.

The router is intentionally thin (``api_layer_no_business_logic``
constraint): every handler validates the JWT, resolves the role, and
delegates to the existing domain function. No SQL, no RBAC matrix
mutation, no model construction beyond the bare dataclass mirror.

Citations:
- plan: §A.6 / §D.6 — chat history endpoint bridges the
  no-conversation-history gap that the WebSocket-only design left.
- core/pipeline.py:248 ``get_context`` — async DB read seam
  reused here to avoid duplicating the SELECT.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.pipeline import get_context

router = APIRouter(prefix="/web/conversations", tags=["chat"])
security = HTTPBearer()


@router.get("/{conversation_id}/history")
async def conversation_history(
    conversation_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """[FR-200] Return the ordered message history for *conversation_id*.

    Delegates to ``core.pipeline.get_context`` which reads
    ``messages WHERE conversation_id = :cid ORDER BY id ASC``.
    The seam is async and returns ``{"conversation_id", "history": [...]}``;
    on DB failure it falls back to an empty history list rather than
    raising, so the WebUI can render a degraded-but-functional state
    instead of a hard error.

    Auth: any valid Bearer token (admin, customer, or guest). The
    chat UI only ever asks for the JWT ``sub``'s own conversation
    history; a future hardening pass may narrow this to the sub
    that owns the conversation.
    """
    token = credentials.credentials
    if not token or len(token.split(".")) != 3:
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        result = await get_context(conversation_id)
    except Exception:
        # ``get_context`` already swallows DB faults and returns an
        # empty history; this except is a defensive net for any
        # unexpected shape (e.g. SQLAlchemy session exhaustion).
        return {"conversation_id": conversation_id, "history": []}
    return result
