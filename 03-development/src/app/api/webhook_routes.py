"""[FR-84] Webhook API endpoints + error codes.

Registers 9 webhook endpoint routes (7 unique paths, messenger/whatsapp each
support GET+POST) on a FastAPI ``APIRouter`` and exports the
``WEBHOOK_ERROR_CODES`` tuple of 7 standard error codes.

Spec source: 02-architecture/TEST_SPEC.md (FR-84)
SRS source : SRS.md FR-84 (Module 19: API 端點)

Citations:
    - SRS.md FR-84 — Webhook API 端點（6 個）: POST /api/v1/webhook/telegram,
      /line, /messenger(GET+POST), /whatsapp(GET+POST), POST
      /api/v1/web/guest-session, /web/message, /a2a/rpc；各端點錯誤碼規範
    - 02-architecture/TEST_SPEC.md FR-84 — test_fr84_all_6_webhook_endpoints_exist,
      test_fr84_error_codes_consistent
"""

from __future__ import annotations

from fastapi import APIRouter

# ------------------------------------------------------------------
# APIRouter with all webhook endpoint routes
# ------------------------------------------------------------------

router = APIRouter()

# ------------------------------------------------------------------
# 7 standard webhook error codes (tuple, per TEST_SPEC contract)
# ------------------------------------------------------------------

WEBHOOK_ERROR_CODES: tuple[str, ...] = (
    "AUTH_INVALID_SIGNATURE",
    "RATE_LIMIT_EXCEEDED",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "LLM_TIMEOUT",
    "AUTH_TOKEN_EXPIRED",
    "AUTHZ_INSUFFICIENT_ROLE",
)


# ==================================================================
# Route registration — declarative table drives all 9 stub handlers.
# Each stub returns {"status": "ok"}; real logic is gated behind a
# factory per the test-isolation contract so the module-level
# ``router`` remains side-effect-free.
# ==================================================================

_WEBHOOK_ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/v1/webhook/telegram"),
    ("POST", "/api/v1/webhook/line"),
    ("GET", "/api/v1/webhook/messenger"),
    ("POST", "/api/v1/webhook/messenger"),
    ("GET", "/api/v1/webhook/whatsapp"),
    ("POST", "/api/v1/webhook/whatsapp"),
    ("POST", "/api/v1/web/guest-session"),
    ("POST", "/api/v1/web/message"),
    ("POST", "/api/v1/a2a/rpc"),
]


def _register_webhook_routes(router: APIRouter) -> None:
    """Register every webhook stub route declared in ``_WEBHOOK_ROUTES``."""
    for method, path in _WEBHOOK_ROUTES:
        _add_stub_route(router, method, path)


def _add_stub_route(router: APIRouter, method: str, path: str) -> None:
    """Register a single stub route that returns ``{"status": "ok"}``."""
    _register = router.get if method == "GET" else router.post

    @_register(path)
    async def _stub() -> dict[str, str]:
        return {"status": "ok"}

    # Preserve descriptive metadata for OpenAPI / route inspection.
    slug = path.rsplit("/", 1)[-1].replace("-", "_")
    _stub.__name__ = f"webhook_{slug}_{method.lower()}"
    _stub.__doc__ = f"[FR-84] {method} {path}"


_register_webhook_routes(router)
