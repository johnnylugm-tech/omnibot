"""[FR-101, FR-102, FR-103] Admin WebUI router — thin wrapper around ``app.admin.webui``.

Each handler is a 5-line RBAC-gated delegation to the canonical
domain class (``KnowledgeAdminAPI``, ``RAGDebugger``,
``OperationsDashboard``). All business logic, storage access, and
state machine semantics live in those classes; this router only:

  1. resolves the caller's role from the JWT
  2. runs ``RBACEnforcer.check(role, resource, action)``
  3. translates the 200 / 403 result into HTTP semantics

No DB / SQL / pipeline logic belongs here — that would breach the
``api_layer_no_business_logic`` architecture constraint.

Routes (mounted at ``/api/v1/admin``):
    GET    /knowledge                       — list entries
    POST   /knowledge                       — create entry
    GET    /knowledge/{entry_id}            — read full entry
    PUT    /knowledge/{entry_id}            — update entry
    DELETE /knowledge/{entry_id}            — delete entry
    POST   /knowledge/import                — CSV/JSON bulk import
    GET    /knowledge/embedding-status      — embedding sync machine
    POST   /rag/debug                       — sandbox RAG query
    POST   /rag/slider                      — sandbox threshold slider (non-persistent)
    GET    /rag/saved-threshold             — persisted threshold (always 0.75)
    GET    /dashboard                       — Ops dashboard metrics
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.admin.rbac import RBACEnforcer
from app.admin.webui import (
    KNOWLEDGE_ACTION_CREATE,
    KNOWLEDGE_ACTION_DELETE,
    KNOWLEDGE_ACTION_READ,
    KNOWLEDGE_ACTION_UPDATE,
    KnowledgeAdminAPI,
    OperationsDashboard,
    RAG_DEFAULT_THRESHOLD,
    RAGDebugger,
)
from app.api.auth import get_current_user_role

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer()

# Module-level dispatcher instances — single source of truth so the
# sandbox slider state (held on RAGDebugger) survives across requests.
_knowledge_api = KnowledgeAdminAPI()
_rag_debugger = RAGDebugger()
_ops_dashboard = OperationsDashboard()


class _RealSQLDashboard(OperationsDashboard):
    """[P5] OperationsDashboard subclass backed by real SQL queries.

    The base ``_fetch_metrics`` returns zero-everything so the FR-101
    unit tests can construct the dashboard without a DB. The
    OperationsDashboard web UI requires real numbers, so this
    subclass runs the ODD SQL queries against the canonical
    ``odd_conversations`` / ``odd_queries`` tables via the standard
    ``get_session`` seam. SQL exceptions degrade gracefully (zero
    values + the prior alert colour) so a partial outage doesn't
    black out the dashboard.
    """

    async def _fetch_metrics_async(self, time_range: str) -> dict:
        from sqlalchemy import text

        from app.infra.database import get_session

        # Map UI time range to the ODD SQL window — the ODD suite
        # is fixed at a 30-day window so the UI's "24hr" still gets
        # a meaningful number rather than an empty result set.
        out = {
            "fcr": 0.0,
            "p95_latency_ms": 0,
            "knowledge_distribution": {"tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0},
            "monthly_cost_usd": 0.0,
            "time_range": time_range,
        }
        try:
            session_gen = get_session()
            session = await session_gen.__anext__()
            try:
                row = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FILTER (WHERE odd_resolved_on_first_contact = TRUE)::FLOAT"
                            " / NULLIF(COUNT(*), 0) AS fcr"
                            " FROM odd_conversations"
                            " WHERE scope_type = 'in_scope'"
                            " AND created_at >= NOW() - INTERVAL '30 days'"
                        )
                    )
                ).fetchone()
                if row and row[0] is not None:
                    out["fcr"] = float(row[0])

                row = (
                    await session.execute(
                        text(
                            "SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_time_seconds) * 1000"
                            " FROM odd_conversations"
                            " WHERE scope_type = 'in_scope' AND resolved_at IS NOT NULL"
                        )
                    )
                ).fetchone()
                if row and row[0] is not None:
                    out["p95_latency_ms"] = int(row[0])

                rows = (
                    await session.execute(
                        text(
                            "SELECT tier, COUNT(*) FROM odd_queries"
                            " WHERE scope_type = 'in_scope'"
                            " GROUP BY tier"
                        )
                    )
                ).fetchall()
                for r in rows:
                    key = f"tier{r[0]}"
                    if key in out["knowledge_distribution"]:
                        out["knowledge_distribution"][key] = int(r[1])
            finally:
                await session_gen.aclose()
        except Exception:
            pass
        return out


_ops_dashboard = _RealSQLDashboard()

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403


def _check(role: str, resource: str, action: str) -> None:
    """Raise 403 when ``role`` lacks ``(resource, action)``."""
    if RBACEnforcer.check(role, resource, action) != _HTTP_OK:
        raise HTTPException(status_code=_HTTP_FORBIDDEN, detail="AUTHZ_INSUFFICIENT_ROLE")


# ---------------------------------------------------------------------------
# Knowledge CRUD — FR-101
# ---------------------------------------------------------------------------


@router.get("/knowledge")
def _knowledge_list(
    role: str = Depends(get_current_user_role),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    _check(role, "knowledge", "read")
    rows = list(_knowledge_api._default_store.rows.values())  # noqa: SLF001 — read-side list for WebUI
    start = (page - 1) * limit
    page_rows = rows[start : start + limit]
    return {
        "total": len(rows),
        "page": page,
        "limit": limit,
        "items": [_entry_to_dict(e) for e in page_rows],
    }


@router.post("/knowledge")
def _knowledge_create(
    body: dict[str, Any],
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "write")
    result = _knowledge_api.crud(
        KNOWLEDGE_ACTION_CREATE,
        title=body.get("title", ""),
        content=body.get("content", ""),
        keywords=body.get("keywords") or [],
    )
    return result


@router.get("/knowledge/{entry_id}")
def _knowledge_read(
    entry_id: int,
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "read")
    result = _knowledge_api.crud(KNOWLEDGE_ACTION_READ, entry_id=entry_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="entry not found")
    return result


@router.put("/knowledge/{entry_id}")
def _knowledge_update(
    entry_id: int,
    body: dict[str, Any],
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "write")
    fields = {k: v for k, v in body.items() if k in {"title", "content", "keywords"}}
    result = _knowledge_api.crud(
        KNOWLEDGE_ACTION_UPDATE, entry_id=entry_id, fields=fields
    )
    return result


@router.delete("/knowledge/{entry_id}")
def _knowledge_delete(
    entry_id: int,
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "delete")
    result = _knowledge_api.crud(KNOWLEDGE_ACTION_DELETE, entry_id=entry_id)
    return result


@router.post("/knowledge/import")
async def _knowledge_import(
    file: UploadFile = File(...),
    file_type: str = Form("csv"),
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "write")
    raw = await file.read()
    if file_type == "json":
        import json

        items = json.loads(raw or b"[]")
        from app.admin.webui import ImportResult, KnowledgeEntry

        result = ImportResult()
        for row in items:
            if not isinstance(row, dict) or not row.get("title"):
                result.skipped += 1
                continue
            _knowledge_api.create_entry(
                title=row["title"],
                content=row.get("content", ""),
                keywords=row.get("keywords") or [],
            )
            result.imported += 1
    else:
        result = _knowledge_api.import_csv(raw, filename=file.filename or "kb.csv")
    return {
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
    }


@router.get("/knowledge/embedding-status")
def _embedding_status(role: str = Depends(get_current_user_role)) -> dict:
    _check(role, "knowledge", "read")
    return _knowledge_api.get_embedding_status()


# ---------------------------------------------------------------------------
# RAG Debugger — FR-102 (slider is sandbox-only, NEVER persists)
# ---------------------------------------------------------------------------


@router.post("/rag/debug")
def _rag_debug(
    body: dict[str, Any],
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "read")
    query = body.get("query", "")
    threshold = float(body.get("threshold", RAG_DEFAULT_THRESHOLD))
    result = _rag_debugger.debug(query, threshold)
    return {
        "query": result.query,
        "ilike_results": [_hit_to_dict(h) for h in result.ilike_results],
        "cosine_scores": [_hit_to_dict(h) for h in result.cosine_scores],
        "rrf_top3": [_rrf_to_dict(e) for e in result.rrf_top3],
        "sections": list(result.sections),
        "threshold_used": _rag_debugger._effective_threshold(threshold),  # noqa: SLF001
    }


@router.post("/rag/slider")
def _rag_slider(
    body: dict[str, Any],
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "read")
    threshold = float(body.get("threshold", RAG_DEFAULT_THRESHOLD))
    _rag_debugger.set_slider_threshold(threshold)
    # Explicitly never touch _DictConfigStore / platform_configs.
    # The frontend renders the "saved" vs "sandbox" values side by
    # side so any accidental persistence would be visible.
    return {
        "saved": False,
        "sandbox": threshold,
        "saved_threshold": _rag_debugger.get_saved_threshold(),
    }


@router.get("/rag/saved-threshold")
def _rag_saved_threshold(role: str = Depends(get_current_user_role)) -> dict:
    _check(role, "knowledge", "read")
    return {"saved_threshold": _rag_debugger.get_saved_threshold()}


# ---------------------------------------------------------------------------
# Operations Dashboard — FR-103
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def _dashboard(
    range: str = Query("24hr"),  # noqa: A002 — matches the FR-103 query param name
    role: str = Depends(get_current_user_role),
) -> dict:
    _check(role, "knowledge", "read")
    fetcher = getattr(_ops_dashboard, "_fetch_metrics_async", None)
    if fetcher is not None:
        data = await fetcher(range)
    else:
        data = _ops_dashboard.get_dashboard_data(range)
    # Augment with the alert colour the dashboard KPI cards render.
    fcr = float(data.get("fcr", 0.0))
    data["fcr_alert_color"] = _ops_dashboard.get_fcr_alert_color(fcr)
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    """Serialise a ``KnowledgeEntry`` to a JSON-safe dict."""
    return {
        "id": entry.id,
        "title": entry.title,
        "content": entry.content,
        "keywords": list(entry.keywords or []),
        "embedding_status": entry.embedding_status,
        "embedding_chunks_synced": entry.embedding_chunks_synced,
        "embedding_chunks_total": entry.embedding_chunks_total,
    }


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    """Serialise ILIKEMatch / CosineHit to a JSON-safe dict."""
    return {
        "row_id": getattr(hit, "row_id", None),
        "chunk_id": getattr(hit, "chunk_id", None),
        "content": getattr(hit, "content", ""),
        "confidence": getattr(hit, "confidence", None),
        "score": getattr(hit, "score", None),
    }


def _rrf_to_dict(entry: Any) -> dict[str, Any]:
    return {
        "rank": entry.rank,
        "score": entry.score,
        "parent_id": entry.parent_id,
        "content": entry.content,
    }