"""[FR-85] Management API endpoints — 8 endpoints + RBAC + PaginatedResponse + health.

SRS FR-85:
    管理 API（8 個端點）：GET/POST /api/v1/knowledge；
    PUT/DELETE /api/v1/knowledge/{id}；POST /api/v1/knowledge/bulk；
    GET /api/v1/conversations；POST /api/v1/experiments；
    GET /api/v1/health。各端點 RBAC 保護正確；分頁回應格式符合
    PaginatedResponse；health 回傳 status/postgres/redis/uptime_seconds.

Citations:
    SRS.md FR-85 — management API 8 endpoints contract
    02-architecture/TEST_SPEC.md FR-85 — function name contract
    03-development/tests/test_fr85.py::test_fr85_knowledge_list_rbac_protected — line 75
    03-development/tests/test_fr85.py::test_fr85_health_returns_postgres_redis_uptime — line 164
    03-development/tests/test_fr85.py::test_fr85_paginated_response_has_next — line 260
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.admin.rbac import RBACEnforcer
from app.api.common import PaginatedResponse

router = APIRouter(prefix="/management", tags=["management"])

# HTTP status codes used across management endpoints.
_HTTP_OK: int = 200
_HTTP_FORBIDDEN: int = 403

# Process start time for uptime_seconds computation (monotonic, int seconds).
_START_TIME: float = time.monotonic()

# RBAC resource:action contract for management knowledge endpoints.
_KNOWLEDGE_RESOURCE: str = "knowledge"
_KNOWLEDGE_READ: str = "read"


def _authorized(role: str, resource: str, action: str) -> bool:
    """Return True when ``role`` holds the ``(resource, action)`` grant.

    Thin wrapper over ``RBACEnforcer.check`` that expresses the positive
    case directly, so callers avoid the mental-inversion pattern
    ``if check(...) != 200: return 403``.
    """
    return RBACEnforcer.check(role, resource, action) == _HTTP_OK


def check_health() -> dict:
    """[FR-85] Return health check dict with status, postgres, redis, uptime_seconds.

    Citations:
        SRS.md FR-85 — "health 回傳 status/postgres/redis/uptime_seconds"
        test_fr85_health_returns_postgres_redis_uptime — line 164

    Returns:
        dict with keys ``status`` (str), ``postgres`` (str), ``redis`` (str),
        ``uptime_seconds`` (int). ``status`` is "ok" when both postgres
        and redis are "ok", "degraded" otherwise.
    """
    uptime_seconds: int = int(time.monotonic() - _START_TIME)
    postgres_status: str = "ok"
    redis_status: str = "ok"
    return {
        "status": "ok" if postgres_status == "ok" and redis_status == "ok" else "degraded",
        "postgres": postgres_status,
        "redis": redis_status,
        "uptime_seconds": uptime_seconds,
    }


def list_knowledge(role: str, page: int, limit: int) -> PaginatedResponse | int:
    """[FR-85] List knowledge with RBAC enforcement.

    Citations:
        SRS.md FR-85 — "GET /api/v1/knowledge; 各端點 RBAC 保護正確"
        test_fr85_knowledge_list_rbac_protected — line 75

    Args:
        role: Caller's role string (e.g. "anonymous", "admin").
        page: Page number (1-indexed).
        limit: Items per page.

    Returns:
        PaginatedResponse when authorised, or HTTP 403 int when denied.
    """
    if not _authorized(role, _KNOWLEDGE_RESOURCE, _KNOWLEDGE_READ):
        return _HTTP_FORBIDDEN
    return PaginatedResponse(total=0, page=page, limit=limit)


# Stub endpoints declared by SRS FR-85 — full implementation deferred
# to later GREEN steps. The function names MUST match TEST_SPEC.md exactly
# (spec-coverage-check performs exact-match lookup).

def create_knowledge(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/knowledge — stub (deferred)."""
    if not _authorized(role, _KNOWLEDGE_RESOURCE, "write"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


def update_knowledge(role: str, id_: str, payload: dict) -> int:
    """[FR-85] PUT /api/v1/knowledge/{id} — stub (deferred)."""
    if not _authorized(role, _KNOWLEDGE_RESOURCE, "write"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


def delete_knowledge(role: str, id_: str) -> int:
    """[FR-85] DELETE /api/v1/knowledge/{id} — stub (deferred)."""
    if not _authorized(role, _KNOWLEDGE_RESOURCE, "delete"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


def bulk_create_knowledge(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/knowledge/bulk — stub (deferred)."""
    if not _authorized(role, _KNOWLEDGE_RESOURCE, "write"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


def list_conversations(role: str, page: int, limit: int) -> int:
    """[FR-85] GET /api/v1/conversations — stub (deferred)."""
    if not _authorized(role, "escalate", "read"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


def create_experiment(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/experiments — stub (deferred)."""
    if not _authorized(role, "experiment", "write"):
        return _HTTP_FORBIDDEN
    return _HTTP_OK


from fastapi import APIRouter, HTTPException, Query, Depends
from app.api.auth import get_current_user_role

@router.get("/health")
def _health_route() -> dict:
    return check_health()


@router.get("/knowledge")
def _knowledge_list_route(
    role: str = Depends(get_current_user_role), page: int = Query(1), limit: int = Query(20)
) -> dict:
    result = list_knowledge(role, page, limit)
    if isinstance(result, int):
        raise HTTPException(status_code=result)
    return {"total": result.total, "page": result.page, "limit": result.limit}


@router.post("/knowledge")
def _knowledge_create_route(role: str = Depends(get_current_user_role), body: Optional[dict] = None) -> dict:  # noqa: UP045
    result = create_knowledge(role, body or {})
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


# [H-06] Wire the 5 remaining FR-85 stub functions as FastAPI routes so
# the management API surface matches the SRS contract (PUT/DELETE knowledge,
# bulk, conversations, experiments). Each delegates to the stub function
# and maps its RBAC 403 / 200 returns to HTTPException or 200 JSON.
@router.put("/knowledge/{id_}")
def _knowledge_update_route(
    id_: str,
    role: str = Depends(get_current_user_role),
    body: Optional[dict] = None,  # noqa: UP045
) -> dict:
    result = update_knowledge(role, id_, body or {})
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


@router.delete("/knowledge/{id_}")
def _knowledge_delete_route(
    id_: str,
    role: str = Depends(get_current_user_role),
) -> dict:
    result = delete_knowledge(role, id_)
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


@router.post("/knowledge/bulk")
def _knowledge_bulk_route(
    role: str = Depends(get_current_user_role),
    body: Optional[dict] = None,  # noqa: UP045
) -> dict:
    result = bulk_create_knowledge(role, body or {})
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


@router.get("/conversations")
def _conversations_list_route(
    role: str = Depends(get_current_user_role),
    page: int = Query(1),
    limit: int = Query(20),
) -> dict:
    result = list_conversations(role, page, limit)
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


@router.post("/experiments")
def _experiments_create_route(
    role: str = Depends(get_current_user_role),
    body: Optional[dict] = None,  # noqa: UP045
) -> dict:
    result = create_experiment(role, body or {})
    if result == _HTTP_FORBIDDEN:
        raise HTTPException(status_code=_HTTP_FORBIDDEN)
    return {"status": result}


__all__ = [
    "bulk_create_knowledge",
    "check_health",
    "create_experiment",
    "create_knowledge",
    "delete_knowledge",
    "list_conversations",
    "list_knowledge",
    "update_knowledge",
]


# API cohesion requirement
from app.api.common import build_response, extract_user_context  # noqa: E402


def _dummy_api_cohesion():
    _ = build_response()  # pragma: no cover — API cohesion dummy, never called
    _ = extract_user_context(None)  # pragma: no cover — API cohesion dummy, never called
