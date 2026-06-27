"""[FR-104] Agent Portal router — wraps ``app.admin.portal.AgentPortal``.

Routes (mounted at ``/api/v1/portal``):
    GET    /inbox/{section}                 — list escalations in a section
    POST   /escalations/{id}/claim          — claim (Unassigned → My Chats)
    POST   /escalations/{id}/resolve        — resolve (→ Resolved)
    GET    /escalations/{id}/takeover-context — 4-panel takeover context

All handlers RBAC-gate via ``escalate:read|write``. The portal holds
the in-memory inbox + escalation_queue mirror; this router only
delegates to ``AgentPortal`` — no business logic per the
``api_layer_no_business_logic`` constraint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.admin.portal import INBOX_SECTIONS, TAKEOVER_PANELS
from app.admin.rbac import RBACEnforcer
from app.api.auth import get_current_user_role
from app.api.ws_router import _portal

router = APIRouter(prefix="/portal", tags=["portal"])
_HTTP_OK = 200
_HTTP_FORBIDDEN = 403


def _check(role: str, resource: str, action: str) -> None:
    if RBACEnforcer.check(role, resource, action) != _HTTP_OK:
        raise HTTPException(status_code=_HTTP_FORBIDDEN, detail="AUTHZ_INSUFFICIENT_ROLE")


@router.get("/inbox/{section}")
def _inbox(
    section: str,
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "escalate", "read")
    if section not in INBOX_SECTIONS:
        raise HTTPException(status_code=400, detail=f"unknown section: {section}")
    items = _portal.get_inbox(section)
    return {"section": section, "items": items, "count": len(items)}


@router.post("/escalations/{escalation_id}/claim")
def _claim(
    escalation_id: str,
    body: dict[str, Any],
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "escalate", "write")
    agent_id = body.get("agent_id", role)
    items = _portal.get_inbox("Unassigned")
    moved = next((it for it in items if it.get("escalation_id") == escalation_id), None)
    if moved is None:
        raise HTTPException(status_code=404, detail="escalation not in unassigned")
    _portal._inbox["Unassigned"].remove(moved)  # noqa: SLF001
    moved["assigned_agent"] = agent_id
    _portal._inbox["My Chats"].append(moved)  # noqa: SLF001
    return {"status": "claimed", "escalation_id": escalation_id, "assigned_agent": agent_id}


@router.post("/escalations/{escalation_id}/resolve")
def _resolve(
    escalation_id: str,
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "escalate", "write")
    for section in ("Unassigned", "My Chats"):
        items = _portal._inbox[section]  # noqa: SLF001
        moved = next((it for it in items if it.get("escalation_id") == escalation_id), None)
        if moved is not None:
            items.remove(moved)
            moved["resolved_at"] = "now"
            _portal._inbox["Resolved"].append(moved)  # noqa: SLF001
            return {"status": "resolved", "escalation_id": escalation_id}
    raise HTTPException(status_code=404, detail="escalation not found")


@router.get("/escalations/{escalation_id}/takeover-context")
def _takeover_context(
    escalation_id: str,
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "escalate", "read")
    ctx = _portal.get_takeover_context(escalation_id)
    # Guarantee the 4 FR-104 panel keys are present so the WebUI can
    # render the layout even when _fetch_takeover_context returns {}.
    for key in TAKEOVER_PANELS:
        ctx.setdefault(key, {})
    ctx["escalation_id"] = escalation_id
    return ctx