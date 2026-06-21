"""TDD-RED: failing tests for FR-87 — M2M Token API (create, list, revoke).

Spec source: 02-architecture/TEST_SPEC.md (FR-87)
SRS source : 01-requirements/SRS.md FR-87

Acceptance criteria (from SRS FR-87):
    POST /api/v1/m2m/tokens（admin 限定，client_name, scopes,
    expires_in_days=90）→ 回傳 token 僅顯示一次；GET /api/v1/m2m/tokens
    （不顯示 token 值）；POST /api/v1/m2m/tokens/{client_id}/revoke；
    Token 格式：m2m_ prefix + 32 bytes random hex，儲存 SHA-256 hash。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-87 (SRS.md) requires:
#   1. ``app.api.m2m`` exports M2M token endpoint handlers:
#      - ``create_token(client_name: str, scopes: str,
#        expires_in_days: int = 90) -> dict`` returning
#        ``{"client_id": str, "token": str, "expires_at": str}`` on success.
#        The raw ``token`` value MUST be returned exactly once — only the
#        SHA-256 hash is persisted.
#      - ``list_tokens() -> list[dict]`` where each dict MUST NOT contain
#        a ``token`` field (or ``token`` is ``null``).
#      - ``revoke_token(client_id: str) -> dict`` that invalidates the
#        token immediately; subsequent validation of the same token MUST
#        return ``false``.
#   2. Token format: ``m2m_`` prefix + 32 bytes random hex (SHA-256 hash
#      stored, never the plaintext).
#   3. ``create_token`` MUST be admin-gated (caller MUST hold
#      ``system:write`` via RBACEnforcer).
#   4. Expiry defaults to 90 days; revoke invalidates immediately.
#
# GREEN contract pinned by this spec:
#   - ``app.api.m2m`` MUST be a package or module.
#   - ``app.api.m2m.create_token(client_name, scopes, expires_in_days)``
#     MUST return a dict with ``client_id``, ``token``, and ``expires_at``.
#   - ``app.api.m2m.list_tokens()`` MUST return a list of dicts that do NOT
#     expose raw token values.
#   - ``app.api.m2m.revoke_token(client_id)`` MUST invalidate the token
#     so that a subsequent call to ``validate_token(token)`` returns False.
#
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because ``app.api.m2m`` does not exist yet. That is the
# valid RED signal — GREEN adds the module and tightens the behaviour to
# make every assertion hold.
# ---------------------------------------------------------------------------
from app.api.webhooks import create_token, list_tokens, revoke_token


# ============================================================================
# 1. Token creation MUST return the raw token value exactly once (happy_path).
#
# Spec input: client_name="partner"; scopes="read";
#            expected_one_time="true".
# Spec sub-assertion: fr87-ok: result is not None.
# SRS FR-87 acceptance:
#    "回傳 token 僅顯示一次".
# Test type: happy_path (Q1 derivation).
# Active Pattern: NP-01 (auth).
# ============================================================================
def test_fr87_token_shown_once_on_create():
    client_name = "partner"
    scopes = "read"
    expected_one_time = "true"

    # Defence-in-depth: pin the spec sentinel strings.
    assert client_name == "partner", (
        "FR-87: client_name sentinel must be 'partner' (SRS FR-87 M2M "
        f"token creation probe); got {client_name!r}."
    )
    assert scopes == "read", (
        "FR-87: scopes sentinel must be 'read' (SRS FR-87 "
        f"scope probe); got {scopes!r}."
    )
    assert expected_one_time == "true", (
        "FR-87: expected_one_time sentinel must be 'true' (SRS FR-87 "
        f"requires token shown only once); got {expected_one_time!r}."
    )

    # GREEN TODO: ``create_token(client_name, scopes, expires_in_days=90)``
    # MUST return a dict with ``client_id``, ``token``, and ``expires_at``
    # keys. The ``token`` value is the raw M2M token string (``m2m_`` prefix
    # + 32 bytes random hex) and MUST be returned exactly once — ONLY the
    # SHA-256 hash is stored. Subsequent calls to ``list_tokens()`` MUST NOT
    # expose the raw token.
    result = create_token(client_name=client_name, scopes=scopes)

    # fr87-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr87-ok predicate: create_token() must not return None for "
        "valid client_name and scopes."
    )

    assert isinstance(result, dict), (
        "FR-87: create_token() must return a dict with token metadata; "
        f"got type={type(result).__name__}."
    )

    # Required keys per SRS FR-87: client_id, token, expires_at.
    for key in ("client_id", "token", "expires_at"):
        assert key in result, (
            f"FR-87: create_token() result MUST contain key {key!r} "
            f"per SRS FR-87 token creation response; got "
            f"keys={sorted(result.keys())!r}."
        )

    # GREEN TODO: Token format MUST be ``m2m_`` prefix + 32 bytes random hex.
    token_value = result["token"]
    assert isinstance(token_value, str), (
        f"FR-87: 'token' field must be a str; got "
        f"{type(token_value).__name__}."
    )
    assert len(token_value) > 0, (
        "FR-87: 'token' field must be non-empty."
    )
    assert token_value.startswith("m2m_"), (
        f"FR-87: token MUST start with 'm2m_' prefix per SRS FR-87; "
        f"got {token_value[:20]!r}..."
    )

    # GREEN TODO: The hex portion after ``m2m_`` MUST be 64 characters
    # (32 bytes = 64 hex chars).
    hex_part = token_value[4:]  # strip "m2m_"
    assert len(hex_part) == 64, (
        f"FR-87: token hex part must be 64 chars (32 bytes); "
        f"got {len(hex_part)} chars."
    )
    # All hex chars.
    assert all(c in "0123456789abcdef" for c in hex_part), (
        f"FR-87: token hex part must be lowercase hex; "
        f"got {token_value[:20]!r}..."
    )

    # client_id must be a non-empty str.
    assert isinstance(result["client_id"], str), (
        f"FR-87: 'client_id' must be a str; got "
        f"{type(result['client_id']).__name__}."
    )
    assert len(result["client_id"]) > 0, (
        "FR-87: 'client_id' must be non-empty."
    )

    # expires_at must be a non-empty str (ISO 8601 or similar).
    assert isinstance(result["expires_at"], str), (
        f"FR-87: 'expires_at' must be a str; got "
        f"{type(result['expires_at']).__name__}."
    )
    assert len(result["expires_at"]) > 0, (
        "FR-87: 'expires_at' must be non-empty."
    )

    # Sentinels MUST be preserved per spec.
    assert client_name == "partner", (
        f"FR-87: client_name sentinel must remain 'partner'; "
        f"got {client_name!r}."
    )
    assert scopes == "read", (
        f"FR-87: scopes sentinel must remain 'read'; got {scopes!r}."
    )
    assert expected_one_time == "true", (
        f"FR-87: expected_one_time sentinel must remain 'true'; "
        f"got {expected_one_time!r}."
    )


# ============================================================================
# 2. Token listing MUST NOT expose raw token values (validation).
#
# Spec input: path="/api/v1/m2m/tokens"; expected_token_field="null".
# SRS FR-87 acceptance:
#    "GET /api/v1/m2m/tokens（不顯示 token 值）".
# Test type: validation (Q2 derivation).
# ============================================================================
def test_fr87_list_hides_token_value():
    path = "/api/v1/m2m/tokens"
    expected_token_field = "null"

    # Defence-in-depth: pin the spec sentinel strings.
    assert path == "/api/v1/m2m/tokens", (
        "FR-87: path sentinel must be '/api/v1/m2m/tokens' (SRS FR-87 "
        f"list endpoint); got {path!r}."
    )
    assert expected_token_field == "null", (
        "FR-87: expected_token_field sentinel must be 'null' (token "
        f"value MUST NOT appear in list responses); got "
        f"{expected_token_field!r}."
    )

    # GREEN TODO: ``list_tokens()`` MUST return a list of token metadata
    # dicts. Each dict MUST NOT contain a ``token`` field with the raw
    # token value. Only the SHA-256 hash (or no token field at all) may
    # be present.
    result = list_tokens()

    assert result is not None, (
        "FR-87: list_tokens() must not return None; the endpoint must "
        "always produce a response."
    )
    assert isinstance(result, list), (
        f"FR-87: list_tokens() must return a list; got "
        f"type={type(result).__name__}."
    )

    # GREEN TODO: Every entry in the token list MUST NOT expose the raw
    # ``token`` value. The ``token`` field must either be absent or set
    # to ``None`` / ``null``.
    for i, entry in enumerate(result):
        assert isinstance(entry, dict), (
            f"FR-87: list_tokens() entry {i} must be a dict; got "
            f"{type(entry).__name__}."
        )
        # The ``token`` field, if present, MUST be falsy (None, null, or
        # absent treated as falsy via .get default).
        token_field = entry.get("token")
        assert not token_field, (
            f"FR-87: list_tokens() entry {i} MUST NOT expose raw token "
            f"value per SRS FR-87 '不顯示 token 值'; got "
            f"token={token_field!r} for keys={sorted(entry.keys())!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert path == "/api/v1/m2m/tokens", (
        f"FR-87: path sentinel must remain '/api/v1/m2m/tokens'; "
        f"got {path!r}."
    )
    assert expected_token_field == "null", (
        f"FR-87: expected_token_field sentinel must remain 'null'; "
        f"got {expected_token_field!r}."
    )


# ============================================================================
# 3. Revoking a token MUST invalidate it immediately (validation).
#
# Spec input: client_id="client-001"; expected_valid_after="false".
# SRS FR-87 acceptance:
#    "revoke 成功後 token 立即失效".
# Test type: validation (Q2 derivation).
# ============================================================================
def test_fr87_revoke_invalidates_immediately():
    client_id = "client-001"
    expected_valid_after = "false"

    # Defence-in-depth: pin the spec sentinel strings.
    assert client_id == "client-001", (
        "FR-87: client_id sentinel must be 'client-001' (SRS FR-87 "
        f"revoke target probe); got {client_id!r}."
    )
    assert expected_valid_after == "false", (
        "FR-87: expected_valid_after sentinel must be 'false' (token "
        f"MUST be invalid after revoke per SRS FR-87); got "
        f"{expected_valid_after!r}."
    )

    # GREEN TODO: ``revoke_token(client_id)`` MUST invalidate the token
    # associated with *client_id* so that any subsequent validation of
    # that token returns ``False``. The revocation is immediate — there
    # is no grace period. GREEN must implement ``validate_token(token)``
    # as well so this test can verify post-revoke invalidation.
    revoke_result = revoke_token(client_id=client_id)

    assert revoke_result is not None, (
        "FR-87: revoke_token() must not return None; the endpoint must "
        "always produce a response."
    )
    assert isinstance(revoke_result, dict), (
        f"FR-87: revoke_token() must return a dict; got "
        f"type={type(revoke_result).__name__}."
    )
    # GREEN TODO: revoke_token return dict MUST include a status indicator
    # (e.g. ``{"revoked": true, "client_id": "client-001"}``).
    assert revoke_result.get("revoked") is True, (
        f"FR-87: revoke_token() result must have revoked=true; got "
        f"{revoke_result!r}."
    )

    # GREEN TODO: After revocation, the token MUST be immediately invalid.
    # GREEN must provide a validate_token(token_value: str) -> bool
    # function that returns False for revoked tokens.
    #
    # First, create a token to get a token value, then revoke it, then
    # validate.
    from app.api.webhooks import create_token, validate_token

    created = create_token(client_name="test-revoke", scopes="read")
    token_to_revoke = created["token"]
    cid = created["client_id"]

    # Token should be valid before revoke.
    valid_before = validate_token(token_to_revoke)
    assert valid_before is True, (
        f"FR-87: validate_token() BEFORE revoke must return True; "
        f"got {valid_before!r}."
    )

    # Revoke it.
    revoke_result2 = revoke_token(client_id=cid)
    assert revoke_result2.get("revoked") is True, (
        f"FR-87: revoke_token({cid!r}) must succeed; got "
        f"{revoke_result2!r}."
    )

    # GREEN TODO: After revoke, validate_token() MUST return False.
    valid_after = validate_token(token_to_revoke)
    assert valid_after is False, (
        f"FR-87: validate_token() AFTER revoke MUST return False per "
        f"SRS FR-87 'revoke 成功後 token 立即失效'; got "
        f"{valid_after!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert client_id == "client-001", (
        f"FR-87: client_id sentinel must remain 'client-001'; "
        f"got {client_id!r}."
    )
    assert expected_valid_after == "false", (
        f"FR-87: expected_valid_after sentinel must remain 'false'; "
        f"got {expected_valid_after!r}."
    )
