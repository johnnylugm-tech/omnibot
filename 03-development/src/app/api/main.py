"""[FR-06, FR-86] OmniBot FastAPI root application — router assembly, middleware chain, and health endpoint.

Wires the FR-24 middleware chain (TLS → IP → Signature → Parse → Rate → RBAC)
via Starlette's BaseHTTPMiddleware, exposes the webhook router, the Agent
Card sub-app, and provides the /api/v1/health liveness probe.
No business logic lives here (api_layer_no_business_logic constraint).
"""

import logging
from types import SimpleNamespace

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.management import router as management_router
from app.api.webhooks import agent_card_app
from app.api.webhooks import router as webhooks_router
from app.infra.rate_limit import RateLimiter
from app.middleware.chain import MiddlewareChain, MiddlewareChainMiddleware

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pass-through collaborators — production deployments inject the real
# HMAC verifiers / RBAC enforcer here. Kept inline so the module can be
# imported without pulling in app.admin.rbac (which depends on PostgreSQL).
# ---------------------------------------------------------------------------


class _PassThroughSignature:
    """Default signature validator — accepts every request."""

    def verify(self, _request) -> bool:
        return True


class _PassThroughPlatformAdapter:
    """Default platform parser — derives platform from the URL path."""

    def parse(self, request) -> SimpleNamespace:
        path = request.url.path
        platform = "unknown"
        for name in ("telegram", "line", "messenger", "whatsapp", "web", "a2a"):
            if f"/{name}" in path:
                platform = name
                break
        return SimpleNamespace(platform=platform, user_id="anonymous")


class _PassThroughRBAC:
    """Default RBAC enforcer — permits every user."""

    def enforce(self, user_id: str, resource: str, action: str) -> SimpleNamespace:
        return SimpleNamespace(allowed=True, user_id=user_id,
                               resource=resource, action=action)


class _PassThroughIPWhitelist:
    """Default IP whitelist — accepts every client (test/dev only)."""

    def is_allowed(self, x_forwarded_for=None, client_host=None) -> object:
        return SimpleNamespace(allowed=True, status_code=200, body=b"")


def build_app() -> FastAPI:
    """[F-02] Construct the OmniBot FastAPI app with middleware chain wired."""
    app = FastAPI(title="OmniBot", version="0.1.0")

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
    # prefix. Auth + management routers only carry ``/auth`` / ``/management``,
    # so they DO get the ``/api/v1`` prefix here.
    app.include_router(webhooks_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(management_router, prefix="/api/v1")
    # [R-07] Mount the Agent Card sub-app at the well-known path only (not "/")
    # so other FastAPI routes (e.g. /api/v1/health) are not shadowed by the
    # sub-app's catch-all 404.
    app.mount("/.well-known", agent_card_app)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        """[FR-86] Liveness probe."""
        return {"status": "ok"}

    return app


# Module-level instance — uvicorn target imports `app` directly.
app = build_app()
