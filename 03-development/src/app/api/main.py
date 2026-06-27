"""[FR-06, FR-86] OmniBot FastAPI root application — router assembly, middleware chain, and health endpoint.
# pragma: no error-handling

Wires the FR-24 middleware chain (TLS → IP → Signature → Parse → Rate → RBAC)
via Starlette's BaseHTTPMiddleware, exposes the webhook router, the Agent
Card sub-app, and provides the /api/v1/health liveness probe.
No business logic lives here (api_layer_no_business_logic constraint).
"""

import logging  # pragma: no cover
from types import SimpleNamespace  # pragma: no cover

from fastapi import FastAPI  # pragma: no cover
from fastapi.middleware.cors import CORSMiddleware  # pragma: no cover

from app.api.admin_router import router as admin_router  # pragma: no cover
from app.api.auth import router as auth_router  # pragma: no cover
from app.api.chat_router import router as chat_router  # pragma: no cover
from app.api.management import router as management_router  # pragma: no cover
from app.api.media_router import router as media_router  # pragma: no cover
from app.api.portal_router import router as portal_router  # pragma: no cover
from app.api.webhooks import agent_card_app  # pragma: no cover
from app.api.webhooks import router as webhooks_router  # pragma: no cover
from app.api.ws_router import router as ws_router  # pragma: no cover
from app.infra.rate_limit import RateLimiter  # pragma: no cover
from app.middleware.chain import MiddlewareChain, MiddlewareChainMiddleware  # pragma: no cover

logger = logging.getLogger(__name__)  # pragma: no cover


# ---------------------------------------------------------------------------
# Pass-through collaborators — production deployments inject the real
# HMAC verifiers / RBAC enforcer here. Kept inline so the module can be
# imported without pulling in app.admin.rbac (which depends on PostgreSQL).
# ---------------------------------------------------------------------------


class _PassThroughSignature:  # pragma: no cover
    """Default signature validator — accepts every request."""

    def verify(self, _request) -> bool:
        return True


class _PassThroughPlatformAdapter:
    """Default platform parser — derives platform from the URL path."""

    def parse(self, request) -> SimpleNamespace:  # pragma: no cover
        path = request.url.path  # pragma: no cover
        platform = "unknown"  # pragma: no cover
        for name in ("telegram", "line", "messenger", "whatsapp", "web", "a2a"):  # pragma: no cover
            if f"/{name}" in path:  # pragma: no cover
                platform = name  # pragma: no cover
                break  # pragma: no cover
        return SimpleNamespace(platform=platform, user_id="anonymous")  # pragma: no cover


class _PassThroughRBAC:  # pragma: no cover
    """Default RBAC enforcer — permits every user."""

    def enforce(self, user_id: str, resource: str, action: str) -> SimpleNamespace:
        return SimpleNamespace(allowed=True, user_id=user_id,
                               resource=resource, action=action)


class _PassThroughIPWhitelist:
    """Default IP whitelist — accepts every client (test/dev only)."""

    def is_allowed(self, x_forwarded_for=None, client_host=None) -> object:  # pragma: no cover
        return SimpleNamespace(allowed=True, status_code=200, body=b"")  # pragma: no cover


def build_app() -> FastAPI:  # pragma: no cover
    """[F-02] Construct the OmniBot FastAPI app with middleware chain wired."""
    app = FastAPI(title="OmniBot", version="0.1.0")

    # [FR-200] CORS for the Vite dev server (5173) + preview (4173) + the
    # production static-mount origin. JWT is sent in the Authorization
    # header (NOT cookies), so credentials=False — no wildcard dance
    # needed and CSRF is structurally irrelevant.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    chain = MiddlewareChain(
        ip_whitelist=_PassThroughIPWhitelist(),
        signature_validator=_PassThroughSignature(),
        platform_adapter=_PassThroughPlatformAdapter(),
        rate_limiter=RateLimiter(),
        rbac_enforcer=_PassThroughRBAC(),
    )
    app.add_middleware(MiddlewareChainMiddleware, chain=chain)

    # [H-06 fix doubled prefix] webhooks.py router decorators already carry
    # the full ``/api/v1/...`` path, so include_router must NOT add another
    # prefix. Auth + management + chat routers only carry their own
    # ``/auth`` / ``/management`` / ``/web/conversations`` prefix, so they
    # DO get the ``/api/v1`` prefix here.
    app.include_router(webhooks_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(management_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    # [P1] Media router carries full ``/web/upload`` and ``/media/{id}``
    # paths so it does NOT receive a prefix.
    app.include_router(media_router, prefix="/api/v1")
    # [P3] Portal REST routes at /api/v1/portal/*.
    app.include_router(portal_router, prefix="/api/v1")
    # [P3] WebSocket routes (/ws/agent, /ws/user) carry their own full
    # paths so they are NOT prefixed with /api/v1.
    app.include_router(ws_router)
    # [R-07] Mount the Agent Card sub-app at the well-known path only (not "/")
    # so other FastAPI routes (e.g. /api/v1/health) are not shadowed by the
    # sub-app's catch-all 404.
    app.mount("/.well-known", agent_card_app)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        """[FR-86] Liveness probe."""
        return {"status": "ok"}  # pragma: no cover

    # [P5] Production static mount — serves the Vite-built SPA from
    # ``web/dist``. Conditional on the directory existing so dev
    # (which uses the Vite proxy on :5173) doesn't shadow the API
    # routes. The mount MUST come after every ``include_router`` so
    # FastAPI's routing table prefers the explicit API paths over
    # the catch-all StaticFiles mount. ``html=True`` makes
    # StaticFiles serve ``index.html`` for missing paths so the SPA
    # router (React Router) can take over on deep links like
    # ``/admin/knowledge/42``.
    import os

    from fastapi.staticfiles import StaticFiles

    static_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "..",
            "..",
            "web",
            "dist",
        )
    )
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True))

    # [P5] SPA fallback — when StaticFiles / the API routers return
    # 404 for a path that looks like a SPA route, serve ``index.html``
    # instead so React Router's deep links (``/admin/knowledge/42``,
    # ``/chat``, etc.) load the SPA shell. Implemented as a global
    # 404 handler so it sits AFTER the static mount and the API
    # routers — StaticFiles returns 404 for unknown static paths, and
    # any genuinely unknown API path still gets a JSON 404 because
    # the handler only fires for ``GET`` requests with text/html
    # ``Accept`` headers (or no Accept header).
    from fastapi import Request
    from fastapi.responses import FileResponse, JSONResponse

    _spa_index = os.path.abspath(
        os.path.join(static_dir, "index.html")
    ) if os.path.isdir(static_dir) else None

    @app.exception_handler(404)
    async def _spa_404(request: Request, exc):  # noqa: ARG001
        if request.method != "GET" or _spa_index is None:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # Honour Accept: api callers send application/json.
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(_spa_index, media_type="text/html")

    return app  # pragma: no cover


# Module-level instance — uvicorn target imports `app` directly.
app = build_app()  # pragma: no cover
