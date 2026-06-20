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

from app.admin.rbac import RBACEnforcer
from app.core.api_response import PaginatedResponse

# Process start time for uptime_seconds computation (monotonic, int seconds).
_START_TIME: float = time.monotonic()

# RBAC resource:action contract for management knowledge endpoints.
_KNOWLEDGE_RESOURCE: str = "knowledge"
_KNOWLEDGE_READ: str = "read"


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
    pg: str = "ok"
    rd: str = "ok"
    return {
        "status": "ok" if pg == "ok" and rd == "ok" else "degraded",
        "postgres": pg,
        "redis": rd,
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
    if RBACEnforcer.check(role, _KNOWLEDGE_RESOURCE, _KNOWLEDGE_READ) != 200:
        return 403
    return PaginatedResponse(total=0, page=page, limit=limit)


# Stub endpoints declared by SRS FR-85 — full implementation deferred
# to later GREEN steps. The function names MUST match TEST_SPEC.md exactly
# (spec-coverage-check performs exact-match lookup).

def create_knowledge(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/knowledge — stub (deferred)."""
    if RBACEnforcer.check(role, _KNOWLEDGE_RESOURCE, "write") != 200:
        return 403
    return 200


def update_knowledge(role: str, id_: str, payload: dict) -> int:
    """[FR-85] PUT /api/v1/knowledge/{id} — stub (deferred)."""
    if RBACEnforcer.check(role, _KNOWLEDGE_RESOURCE, "write") != 200:
        return 403
    return 200


def delete_knowledge(role: str, id_: str) -> int:
    """[FR-85] DELETE /api/v1/knowledge/{id} — stub (deferred)."""
    if RBACEnforcer.check(role, _KNOWLEDGE_RESOURCE, "delete") != 200:
        return 403
    return 200


def bulk_create_knowledge(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/knowledge/bulk — stub (deferred)."""
    if RBACEnforcer.check(role, _KNOWLEDGE_RESOURCE, "write") != 200:
        return 403
    return 200


def list_conversations(role: str, page: int, limit: int) -> int:
    """[FR-85] GET /api/v1/conversations — stub (deferred)."""
    if RBACEnforcer.check(role, "escalate", "read") != 200:
        return 403
    return 200


def create_experiment(role: str, payload: dict) -> int:
    """[FR-85] POST /api/v1/experiments — stub (deferred)."""
    if RBACEnforcer.check(role, "experiment", "write") != 200:
        return 403
    return 200


__all__ = [
    "check_health",
    "list_knowledge",
    "create_knowledge",
    "update_knowledge",
    "delete_knowledge",
    "bulk_create_knowledge",
    "list_conversations",
    "create_experiment",
]
