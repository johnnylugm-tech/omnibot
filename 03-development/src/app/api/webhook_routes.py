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
# Route handlers (stubs — real logic gated behind factory per test
# isolation contract so module-level ``router`` is side-effect-free)
# ==================================================================


@router.post("/api/v1/webhook/telegram")
async def webhook_telegram_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/webhook/telegram — Telegram bot webhook."""
    return {"status": "ok"}


@router.post("/api/v1/webhook/line")
async def webhook_line_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/webhook/line — LINE bot webhook."""
    return {"status": "ok"}


@router.get("/api/v1/webhook/messenger")
async def webhook_messenger_get() -> dict[str, str]:
    """[FR-84] GET /api/v1/webhook/messenger — Messenger webhook verification."""
    return {"status": "ok"}


@router.post("/api/v1/webhook/messenger")
async def webhook_messenger_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/webhook/messenger — Messenger webhook event."""
    return {"status": "ok"}


@router.get("/api/v1/webhook/whatsapp")
async def webhook_whatsapp_get() -> dict[str, str]:
    """[FR-84] GET /api/v1/webhook/whatsapp — WhatsApp webhook verification."""
    return {"status": "ok"}


@router.post("/api/v1/webhook/whatsapp")
async def webhook_whatsapp_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/webhook/whatsapp — WhatsApp webhook event."""
    return {"status": "ok"}


@router.post("/api/v1/web/guest-session")
async def web_guest_session_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/web/guest-session — Create web chat guest session."""
    return {"status": "ok"}


@router.post("/api/v1/web/message")
async def web_message_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/web/message — Web chat message."""
    return {"status": "ok"}


@router.post("/api/v1/a2a/rpc")
async def a2a_rpc_post() -> dict[str, str]:
    """[FR-84] POST /api/v1/a2a/rpc — A2A JSON-RPC endpoint."""
    return {"status": "ok"}
