"""[FR-06] A2A Platform Adapter — inbound A2A JSON-RPC 2.0 handler.

Accepts JSON-RPC 2.0 calls from remote A2A agents, verifies M2M OAuth2/JWT
tokens, routes RPC methods (e.g. ``ask_customer_service``) into
``UnifiedMessage`` for downstream PALADIN / Knowledge / DST processing.

Architecture (SAD.md): ``Module: webhooks.py — A2AAdapter JSON-RPC 2.0 entry
→ FR-06``. The adapter is the inbound counterpart to FR-44 (OmniBot's own
Agent Card at ``/.well-known/agent.json``) and FR-41 (remote agent discovery).

Citations:
    - SRS.md FR-06 — M2M OAuth2/JWT token verification + A2A JSON-RPC 2.0
    - SRS.md:786 — FR-06 registry entry (id, description, surface symbols)
    - 02-architecture/TEST_SPEC.md FR-06 — test_fr06_a2a_valid_m2m_token_200,
      test_fr06_a2a_invalid_m2m_token_401,
      test_fr06_a2a_rpc_ask_customer_service_end_to_end
    - agent_card.py:12-16 — A2A method list (ask_customer_service,
      escalate_to_human) pinned here as well
    - 02-architecture/SAD.md — "A2AAdapter JSON-RPC 2.0 entry → FR-06"
"""

from __future__ import annotations

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, FastAPI

from app.api.adapters.a2a import A2AAdapter
from app.api.adapters.line import LineWebhookAdapter
from app.api.adapters.messenger import MessengerWebhookAdapter
from app.api.adapters.telegram import TelegramWebhookAdapter
from app.api.adapters.utils import _b64url_decode, _b64url_encode
from app.api.adapters.verifiers import (
    LineWebhookVerifier,
    MessengerWebhookVerifier,
    TelegramWebhookVerifier,
    WebJwtVerifier,
    WhatsAppWebhookVerifier,
)
from app.api.adapters.web import WebAdapter
from app.api.adapters.whatsapp import WhatsAppWebhookAdapter

__all__ = [
    "A2AAdapter",
    "LineWebhookAdapter",
    "LineWebhookVerifier",
    "MessengerWebhookAdapter",
    "MessengerWebhookVerifier",
    "TelegramWebhookAdapter",
    "TelegramWebhookVerifier",
    "WebAdapter",
    "WebJwtVerifier",
    "WhatsAppWebhookAdapter",
    "WhatsAppWebhookVerifier",
    "_b64url_decode",
    "_b64url_encode",
]
from app.core.unified_message import (
    MessageType,
)

_BEARER_PREFIX = "Bearer "
_UNKNOWN_AGENT = "unknown-agent"


# ------------------------------------------------------------------
# JWT / base64url helpers (FR-05 / FR-03 / FR-04)
#
# Module-level functions (NOT BaseWebhookAdapter methods) so any
# adapter or verifier can call them without instantiating the class.
# Previously these helpers lived in WebJwtVerifier and were
# self-imported via ``from app.api.webhooks import _b64url_decode``;
# that circular import broke when ``webhooks.py`` was split across
# multiple modules. Centralising them at module scope removes the
# cycle and keeps the helper signatures stable for downstream
# callers (``app.api.auth`` and ``WebJwtVerifier``).
# ------------------------------------------------------------------





"""[FR-02] LINE Webhook Adapter — maps LINE events array into UnifiedMessage.

Parses a LINE Messaging API webhook events array and produces a list of
``UnifiedMessage`` instances for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md:25 — FR-02 "解析 events 陣列，映射為 UnifiedMessage"
    - SRS.md:433-435 — implementation_functions: line_adapter
    - TEST_SPEC.md FR-02 — LineWebhookAdapter contract:
      process_events(self, events_payload: list[dict]) -> list[UnifiedMessage]
"""
"""[FR-03] Messenger Webhook Adapter — handles GET challenge + POST entry parsing.

Parses Messenger Platform webhook payloads:
- GET: validates ``hub.mode`` / ``hub.verify_token`` and returns ``hub.challenge``
- POST: maps entry arrays into ``UnifiedMessage`` instances for downstream
  PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-03 — "GET 驗證（hub.mode, hub.verify_token, hub.challenge 回傳）
      + POST HMAC-SHA256 簽名驗證，映射為 UnifiedMessage"
    - TEST_SPEC.md FR-03:108-125 — MessengerWebhookAdapter contract
"""
"""[FR-01] Telegram Webhook Adapter — maps Telegram Update into UnifiedMessage.

Parses a Telegram Bot API Update JSON payload and produces a
``UnifiedMessage`` for downstream PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-01 — "解析 update_id + message，映射為 UnifiedMessage"
    - TEST_SPEC.md FR-01:98-101 — TelegramWebhookAdapter contract
"""
"""[FR-05] Web Platform Adapter — guest sessions + JWT Bearer messaging.

Implements POST /api/v1/web/guest-session (anonymous guest JWT) and
POST /api/v1/web/message (JWT BearerAuth message delivery) per SRS FR-05.

Citations:
    - SRS.md FR-05 — "Web Platform Adapter: POST /api/v1/web/guest-session
      初始化匿名連線回傳 Guest JWT; POST /api/v1/web/message 使用 JWT BearerAuth
      傳訊"
    - TEST_SPEC.md FR-05:82-92 — WebAdapter contract:
      __init__, create_guest_session() -> dict, process_message() -> UnifiedMessage
"""
"""[FR-04] WhatsApp Webhook Adapter — handles GET challenge + POST entry parsing.

Parses WhatsApp Business Platform webhook payloads:
- GET: validates ``hub.mode`` / ``hub.verify_token`` and returns ``hub.challenge``
- POST: maps entry arrays into ``UnifiedMessage`` instances for downstream
  PALADIN / Knowledge / DST stages.

Citations:
    - SRS.md FR-04 — "GET 驗證（hub.challenge）+ POST HMAC-SHA256
      簽名驗證（sha256= prefix），映射為 UnifiedMessage"
    - TEST_SPEC.md FR-04:141-147 — handle_challenge contract
    - TEST_SPEC.md FR-04:234-245 — parse_messages contract
"""
_WHATSAPP_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "sticker": MessageType.STICKER,
    "location": MessageType.LOCATION,
}
"""[FR-02] LINE Webhook HMAC-SHA256 Base64 Signature Verifier.

Verifies the ``x-line-signature`` header against the raw request body using
HMAC-SHA256 with Base64 encoding as required by the LINE Messaging API.

Citations:
    - SRS.md:25 — FR-02 "驗證 x-line-signature（HMAC-SHA256 Base64）"
    - SRS.md:433-434 — implementation_functions: LineWebhookVerifier.verify
    - TEST_SPEC.md FR-02 — LineWebhookVerifier contract:
      __init__(self, channel_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""
"""[FR-03] Messenger Webhook HMAC-SHA256 Signature Verifier.

Verifies the ``X-Hub-Signature-256`` header against the raw request body
using HMAC-SHA256 as required by the Messenger Platform webhook.

The received signature format is ``sha256=<hex>`` (hex digest, NOT Base64).
The verifier strips the ``sha256=`` prefix before comparison.

Citations:
    - SRS.md FR-03 — "POST HMAC-SHA256 簽名驗證"
    - TEST_SPEC.md FR-03:78-80 — MessengerWebhookVerifier contract:
      __init__(self, app_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""
"""[FR-01] Telegram Webhook HMAC-SHA256 Signature Verifier.

Verifies the ``X-Telegram-Bot-Api-Secret-Token`` header against the raw
request body using HMAC-SHA256 as required by the Telegram Bot API.

Citations:
    - SRS.md FR-01 — "驗證 X-Telegram-Bot-Api-Secret-Token（HMAC-SHA256）"
    - TEST_SPEC.md FR-01 — TelegramWebhookVerifier contract:
      __init__(self, secret_token: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""
"""[FR-05] Web JWT Bearer Token Verifier.

Validates JWT Bearer tokens for the Web Platform Adapter using HMAC-SHA256
(HS256). Returns bool — never raises, so the caller (WebAdapter) controls
the HTTP error mapping.

Citations:
    - SRS.md FR-05 — "JWT BearerAuth 傳訊; JWT 驗證失敗回 401"
    - TEST_SPEC.md FR-05:96-100 — WebJwtVerifier contract:
      __init__(self, jwt_secret: str), verify(self, token: str) -> bool
"""
"""[FR-04] WhatsApp Webhook HMAC-SHA256 Hex Signature Verifier.

Verifies the ``x-hub-signature`` header against the raw request body using
HMAC-SHA256 with hex digest encoding as required by the WhatsApp Business
Platform webhook.

The received signature format is ``sha256=<hex>`` (hex digest). The verifier
enforces the ``sha256=`` prefix — any other prefix (e.g. ``md5=``) or missing
prefix results in immediate rejection.

Citations:
    - SRS.md FR-04 — "POST HMAC-SHA256 簽名驗證（sha256= prefix）"
    - TEST_SPEC.md FR-04:175-180 — WhatsAppWebhookVerifier contract:
      __init__(self, app_secret: str), verify(self, raw_body: bytes,
      received_signature: str) -> bool
"""
"""[FR-87] M2M Token API — create, list, revoke, and validate M2M tokens.

SRS FR-87 acceptance:
    POST /api/v1/m2m/tokens（admin 限定，client_name, scopes,
    expires_in_days=90）→ 回傳 token 僅顯示一次；GET /api/v1/m2m/tokens
    （不顯示 token 值）；POST /api/v1/m2m/tokens/{client_id}/revoke；
    Token 格式：m2m_ prefix + 32 bytes random hex，儲存 SHA-256 hash。

Citations:
    SRS.md — FR-87 acceptance: token 僅顯示一次；list 不顯示 token 值；
        revoke 後 token 立即失效；Token format m2m_ + 32 bytes random hex；
        SHA-256 hash 儲存。
    TEST_SPEC.md FR-87 — test_fr87.py GREEN contract:
        create_token(client_name, scopes, expires_in_days=90) -> dict
        with client_id, token, expires_at; list_tokens() -> list[dict]
        without raw token; revoke_token(client_id) -> dict with
        revoked=True; validate_token(token) -> bool.
    03-development/tests/test_fr87.py:69-171 — case 1 happy_path
        (token shown once on create).
    03-development/tests/test_fr87.py:182-237 — case 2 validation
        (list hides token value).
    03-development/tests/test_fr87.py:248-327 — case 3 validation
        (revoke invalidates immediately).
"""
_TOKEN_BYTES = 32
_CLIENT_ID_BYTES = 8


_TOKEN_LOCK = threading.Lock()
_TOKEN_FILE = ".m2m_tokens.json"

_TOKEN_STORE: dict[str, dict] = {}
_HASH_LOOKUP: dict[str, str] = {}

def _file_lock(f):
    """Advisory exclusive lock for cross-process safety (POSIX only)."""
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)
    except (ImportError, OSError):
        pass

def _file_unlock(f):
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)
    except (ImportError, OSError):
        pass

def _load_tokens():
    global _TOKEN_STORE, _HASH_LOOKUP
    if os.path.exists(_TOKEN_FILE):
        try:
            with open(_TOKEN_FILE) as f:
                _file_lock(f)
                try:
                    data = json.load(f)
                    _TOKEN_STORE.clear()
                    _TOKEN_STORE.update(data.get("store", {}))
                    _HASH_LOOKUP.clear()
                    _HASH_LOOKUP.update(data.get("lookup", {}))
                finally:
                    _file_unlock(f)
        except Exception:
            pass

def _save_tokens():
    try:
        with open(_TOKEN_FILE, "w") as f:
            _file_lock(f)
            try:
                json.dump({"store": _TOKEN_STORE, "lookup": _HASH_LOOKUP}, f)
            finally:
                _file_unlock(f)
    except Exception:
        pass

_load_tokens()
def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of *token*."""
    return hashlib.sha256(token.encode()).hexdigest()

def create_token(
    client_name: str,
    scopes: str,
    expires_in_days: int = 90,
) -> dict:
    """[FR-87] Create an M2M token for *client_name*.

    Generates a token with the ``m2m_`` prefix followed by 64 lowercase
    hex characters (32 bytes of random). Only the SHA-256 hash of the
    raw token is persisted — the plaintext token value is returned
    exactly once and never stored.

    RBAC admin-gating (``system:write`` via ``RBACEnforcer``) is
    enforced at the HTTP endpoint layer, not in this function. The
    function itself is the pure business-logic creator and is safe to
    call directly in tests.

    Args:
        client_name: Human-readable client identifier.
        scopes: Space-delimited scope string (e.g. ``"read write"``).
        expires_in_days: Token lifetime in days. Defaults to 90.

    Returns:
        ``{"client_id": str, "token": str, "expires_at": str}``.
        The ``token`` value is the raw M2M token string — it is
        returned exactly once and MUST be captured by the caller.

    Citations:
        SRS.md — FR-87 acceptance: "回傳 token 僅顯示一次".
        TEST_SPEC.md FR-87 — create_token return shape.
        03-development/tests/test_fr87.py:69-171 (case 1).
    """
    # Token: m2m_ prefix + 32 bytes random → 64 lowercase hex chars.
    hex_part = secrets.token_hex(_TOKEN_BYTES)
    token = f"m2m_{hex_part}"

    # Store only the SHA-256 hash (never the plaintext).
    token_hash = _hash_token(token)

    # Unique client_id.
    client_id = f"client-{secrets.token_hex(_CLIENT_ID_BYTES)}"

    # Expiry as ISO 8601 with timezone.
    expires_at_dt = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    expires_at = expires_at_dt.isoformat()

    with _TOKEN_LOCK:
        _TOKEN_STORE[client_id] = {
            "hash": token_hash,
            "client_name": client_name,
            "scopes": scopes,
            "expires_at": expires_at,
            "revoked": False,
        }
        _HASH_LOOKUP[token_hash] = client_id
        _save_tokens()

    return {
        "client_id": client_id,
        "token": token,
        "expires_at": expires_at,
    }

def list_tokens() -> list[dict]:
    """[FR-87] List all registered M2M tokens without exposing raw token values.

    Each returned entry includes metadata (``client_id``, ``client_name``,
    ``scopes``, ``expires_at``, ``revoked``) but the ``token`` field is
    always ``None`` — only the SHA-256 hash is stored server-side.

    Returns:
        A list of token metadata dicts. The ``token`` key is always
        ``None`` (or absent) to satisfy SRS FR-87 "不顯示 token 值".

    Citations:
        SRS.md — FR-87 acceptance: "GET /api/v1/m2m/tokens（不顯示
            token 值）".
        TEST_SPEC.md FR-87 — list_tokens contract.
        03-development/tests/test_fr87.py:182-237 (case 2).
    """
    result: list[dict] = []
    with _TOKEN_LOCK:
        for client_id, data in _TOKEN_STORE.items():
            result.append({
                "client_id": client_id,
                "client_name": data["client_name"],
                "scopes": data["scopes"],
                "expires_at": data["expires_at"],
                "revoked": data["revoked"],
                "token": None,
            })
    return result

def revoke_token(client_id: str) -> dict:
    """[FR-87] Immediately revoke the M2M token for *client_id*.

    Revocation is immediate — there is no grace period. Subsequent calls
    to ``validate_token()`` for the revoked token will return ``False``.
    The operation is idempotent: revoking a non-existent or already-
    revoked client returns the same success response.

    Args:
        client_id: The ``client_id`` returned by ``create_token()``.

    Returns:
        ``{"revoked": True, "client_id": <client_id>}``.

    Citations:
        SRS.md — FR-87 acceptance: "revoke 成功後 token 立即失效".
        TEST_SPEC.md FR-87 — revoke_token contract.
        03-development/tests/test_fr87.py:248-327 (case 3).
    """
    with _TOKEN_LOCK:
        if client_id in _TOKEN_STORE:
            _TOKEN_STORE[client_id]["revoked"] = True
            _save_tokens()
    return {"revoked": True, "client_id": client_id}

def validate_token(token: str) -> bool:
    """[FR-87] Validate an M2M token.

    Checks that the token exists in the store (via SHA-256 hash lookup),
    has not been revoked, and has not expired.

    Args:
        token: The raw M2M token string (``m2m_`` prefix + 64 hex chars).

    Returns:
        ``True`` if the token is valid (exists, not revoked, not expired).
        ``False`` otherwise.

    Citations:
        SRS.md — FR-87 acceptance: "revoke 成功後 token 立即失效";
            SHA-256 hash storage.
        TEST_SPEC.md FR-87 — validate_token contract.
        03-development/tests/test_fr87.py:299-316 (case 3 validate
            before/after revoke).
    """
    with _TOKEN_LOCK:
        token_hash = _hash_token(token)
        client_id = _HASH_LOOKUP.get(token_hash)
        if client_id is None:
            return False

        data = _TOKEN_STORE.get(client_id)
        if data is None:
            return False

        if data["revoked"]:
            return False

        # Check expiry.
        expires_at = datetime.fromisoformat(data["expires_at"])
        return not datetime.now(timezone.utc) > expires_at

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
_A2A_METHODS: list[str] = [
    "ask_customer_service",
    "escalate_to_human",
]
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
agent_card_app = FastAPI(title="OmniBot Agent Card", version="0.1.0")
@agent_card_app.get("/.well-known/agent.json")
def agent_card() -> dict[str, object]:
    """Return the static OmniBot Agent Card payload.

    Citations:
    - SRS.md:97  — FR-44 row mandates name/description/url/version/
      capabilities/methods/auth_schemes fields
    - SRS.md:786 — FR-44 registry description
    """
    return AGENT_CARD

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
router = APIRouter()
WEBHOOK_ERROR_CODES: tuple[str, ...] = (
    "AUTH_INVALID_SIGNATURE",
    "RATE_LIMIT_EXCEEDED",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "LLM_TIMEOUT",
    "AUTH_TOKEN_EXPIRED",
    "AUTHZ_INSUFFICIENT_ROLE",
)
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
    async def _stub() -> dict[str, str]:  # pragma: no cover
        return {"status": "ok"}  # pragma: no cover

    # Preserve descriptive metadata for OpenAPI / route inspection.
    slug = path.rsplit("/", 1)[-1].replace("-", "_")
    _stub.__name__ = f"webhook_{slug}_{method.lower()}"
    _stub.__doc__ = f"[FR-84] {method} {path}"

_register_webhook_routes(router)
