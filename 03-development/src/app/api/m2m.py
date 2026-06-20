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

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

# Token format: m2m_ prefix + 32 bytes random → 64 lowercase hex chars.
_TOKEN_BYTES = 32
# Client ID suffix length in bytes (random hex).
_CLIENT_ID_BYTES = 8

# In-memory token store keyed by client_id. Each entry holds the
# SHA-256 hash of the raw token (never the plaintext), the creation
# metadata, and the revocation flag.
_TOKEN_STORE: dict[str, dict] = {}

# Reverse lookup from SHA-256 hash back to client_id so
# validate_token() can check validity without iterating the store.
_HASH_LOOKUP: dict[str, str] = {}


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

    _TOKEN_STORE[client_id] = {
        "hash": token_hash,
        "client_name": client_name,
        "scopes": scopes,
        "expires_at": expires_at,
        "revoked": False,
    }
    _HASH_LOOKUP[token_hash] = client_id

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
    if client_id in _TOKEN_STORE:
        _TOKEN_STORE[client_id]["revoked"] = True
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
    if datetime.now(timezone.utc) > expires_at:
        return False

    return True
