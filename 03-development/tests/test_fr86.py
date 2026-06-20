"""TDD-RED: failing tests for FR-86 — Auth & User API (JWT login + refresh
+ role management).

Spec source: 02-architecture/TEST_SPEC.md (FR-86)
SRS source : SRS.md FR-86

Acceptance criteria (from SRS FR-86):
    Auth & User API：POST /api/v1/auth/login（回傳 JWT access + refresh
    token）；POST /api/v1/auth/refresh；GET/POST /api/v1/users；
    POST/DELETE /api/v1/users/{user_id}/roles（admin 限定）。login 失敗
    回 401；role 管理需 system:write 權限；refresh token 正常換發。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from app.admin.rbac import RBACEnforcer

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-86 (SRS.md) requires:
#   1. ``app.api.auth`` exports auth endpoint handlers:
#      - ``login(username: str, password: str) -> dict`` returning
#        ``{"access": str, "refresh": str}`` on success, or an HTTP 401
#        status on invalid credentials.
#      - ``assign_role_to_user(user_id: str, role: str, caller_role: str)``
#        that enforces ``system:write`` permission via RBACEnforcer.
#   2. Login endpoint ``POST /api/v1/auth/login`` authenticates user
#      credentials and issues both an access JWT and a refresh token.
#   3. Invalid credentials MUST produce HTTP 401 (NP-01 active).
#   4. Role management endpoints (POST/DELETE /api/v1/users/{user_id}/roles)
#      MUST verify the caller holds ``system:write`` permission before
#      mutating role assignments.
#
# GREEN contract pinned by this spec:
#   - ``app.api.auth`` MUST be a package or module.
#   - ``app.api.auth.login(username: str, password: str) -> dict | int``
#     MUST validate credentials and return a dict with ``access`` and
#     ``refresh`` string keys on success, or ``401`` (int) on failure.
#   - ``app.api.auth.assign_role_to_user(user_id: str, role: str,
#     caller_role: str)`` MUST call
#     ``RBACEnforcer.check(caller_role, 'system', 'write')`` and return
#     403 when the caller lacks ``system:write``.
#
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because ``app.api.auth`` does not exist yet. That is the
# valid RED signal — GREEN adds the module and tightens the behaviour to
# make every assertion hold.
# ---------------------------------------------------------------------------
from app.api.auth import assign_role_to_user, login


# ============================================================================
# 1. Login with valid credentials MUST return a dict containing both an
#    ``access`` JWT and a ``refresh`` token (happy_path).
#
# Spec input: username="admin"; password="correct";
#            expected_tokens="access,refresh".
# Spec sub-assertion: fr86-ok: result is not None.
# SRS FR-86 acceptance:
#    "POST /api/v1/auth/login（回傳 JWT access + refresh token）".
# Test type: happy_path (Q1 derivation).
# Active Pattern: NP-01 (auth 401).
# ============================================================================
def test_fr86_login_returns_jwt_and_refresh():
    username = "admin"
    password = "correct"
    expected_tokens = "access,refresh"

    # Defence-in-depth: pin the spec sentinel strings.
    assert username == "admin", (
        "FR-86: username sentinel must be 'admin' (SRS FR-86 login "
        f"credential probe); got {username!r}."
    )
    assert password == "correct", (
        "FR-86: password sentinel must be 'correct' (valid credential "
        f"probe per TEST_SPEC.md FR-86 case 1); got {password!r}."
    )
    assert expected_tokens == "access,refresh", (
        "FR-86: expected_tokens sentinel must be 'access,refresh' (SRS "
        "FR-86 requires both access JWT and refresh token in login "
        f"response); got {expected_tokens!r}."
    )

    # GREEN TODO: ``login(username, password)`` MUST validate credentials
    # and, on success, return a dict with ``access`` (str) and ``refresh``
    # (str) keys. The access token is a short-lived JWT; the refresh token
    # is a longer-lived opaque token used to obtain new access tokens via
    # ``POST /api/v1/auth/refresh``.
    result = login(username=username, password=password)

    # fr86-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr86-ok predicate: login() must not return None for valid "
        "credentials; the login endpoint must always produce a response."
    )

    assert isinstance(result, dict), (
        "FR-86: login() must return a dict with token keys on success; "
        f"got type={type(result).__name__}."
    )

    required_token_keys = expected_tokens.split(",")
    for key in required_token_keys:
        assert key in result, (
            f"FR-86: login() result MUST contain key {key!r} per SRS "
            f"FR-86 '回傳 JWT access + refresh token'; got "
            f"keys={sorted(result.keys())!r}."
        )

    # Type contract: both access and refresh are non-empty strings.
    assert isinstance(result["access"], str), (
        "FR-86: 'access' token must be a str (JWT); got "
        f"{type(result['access']).__name__}."
    )
    assert len(result["access"]) > 0, (
        "FR-86: 'access' token must be non-empty; got empty string."
    )
    assert isinstance(result["refresh"], str), (
        "FR-86: 'refresh' token must be a str; got "
        f"{type(result['refresh']).__name__}."
    )
    assert len(result["refresh"]) > 0, (
        "FR-86: 'refresh' token must be non-empty; got empty string."
    )

    # Access and refresh tokens MUST be distinct.
    assert result["access"] != result["refresh"], (
        "FR-86: access token and refresh token MUST be distinct values; "
        "they are different credentials with different lifetimes and "
        "purposes."
    )

    # Sentinels MUST be preserved per spec.
    assert username == "admin", (
        f"FR-86: username sentinel must remain 'admin'; got {username!r}."
    )
    assert password == "correct", (
        f"FR-86: password sentinel must remain 'correct'; got {password!r}."
    )
    assert expected_tokens == "access,refresh", (
        f"FR-86: expected_tokens sentinel must remain 'access,refresh'; "
        f"got {expected_tokens!r}."
    )


# ============================================================================
# 2. Login with invalid credentials MUST produce HTTP 401 (validation).
#
# Spec input: username="admin"; password="wrong";
#            expected_status="401".
# SRS FR-86 acceptance:
#    "login 失敗回 401".
# Test type: validation (Q2 derivation).
# Active Pattern: NP-01 (auth 401).
# ============================================================================
def test_fr86_login_failure_401():
    username = "admin"
    password = "wrong"
    expected_status = "401"

    # Defence-in-depth: pin the spec sentinel strings.
    assert username == "admin", (
        "FR-86: username sentinel must be 'admin' (SRS FR-86 login "
        f"credential probe); got {username!r}."
    )
    assert password == "wrong", (
        "FR-86: password sentinel must be 'wrong' (invalid credential "
        f"probe per TEST_SPEC.md FR-86 case 2); got {password!r}."
    )
    assert expected_status == "401", (
        "FR-86: expected_status sentinel must be '401' (HTTP 401 "
        f"Unauthorized per NP-01); got {expected_status!r}."
    )

    # GREEN TODO: ``login(username, password)`` MUST return 401 (int) when
    # credentials are invalid. The function MUST NOT leak whether the
    # username or password was wrong — always return the same 401 for any
    # invalid credential combination to prevent user enumeration.
    result = login(username=username, password=password)

    # The result must not be None even on failure.
    assert result is not None, (
        "FR-86: login() must not return None for invalid credentials; "
        "the endpoint must always produce a response."
    )

    # GREEN TODO: On invalid credentials, login() MUST return the integer
    # 401 (HTTP Unauthorized). GREEN must decide whether the function
    # returns a bare int, a response object with status_code, or raises
    # an exception. This assertion encodes the simplest contract: return
    # 401 directly.
    assert result == 401, (
        f"FR-86: login() with invalid credentials MUST return 401 per "
        f"SRS FR-86 'login 失敗回 401'; got {result!r}."
    )
    assert result == int(expected_status), (
        f"FR-86: login() status must equal int('401') = 401; got "
        f"{result!r}."
    )
    assert isinstance(result, int), (
        f"FR-86: login() must return an int status code (HTTP-style) on "
        f"auth failure; got {type(result).__name__} = {result!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert username == "admin", (
        f"FR-86: username sentinel must remain 'admin'; got {username!r}."
    )
    assert password == "wrong", (
        f"FR-86: password sentinel must remain 'wrong'; got {password!r}."
    )
    assert expected_status == "401", (
        f"FR-86: expected_status sentinel must remain '401'; got "
        f"{expected_status!r}."
    )


# ============================================================================
# 3. Role management operations MUST require ``system:write`` permission
#    (validation).
#
# Spec input: action="assign_role"; role="customer";
#            expected_permission="system:write".
# SRS FR-86 acceptance:
#    "role 管理需 system:write 權限".
# Test type: validation (Q2 derivation).
# Active Pattern: NP-02 (authz 403).
# ============================================================================
def test_fr86_role_management_requires_system_write():
    action = "assign_role"
    role = "customer"
    expected_permission = "system:write"

    # Defence-in-depth: pin the spec sentinel strings.
    assert action == "assign_role", (
        "FR-86: action sentinel must be 'assign_role' (SRS FR-86 role "
        f"management operation); got {action!r}."
    )
    assert role == "customer", (
        "FR-86: role sentinel must be 'customer' (low-privilege role "
        f"probe per NP-02); got {role!r}."
    )
    assert expected_permission == "system:write", (
        "FR-86: expected_permission sentinel must be 'system:write' "
        "(required permission for role management per SRS FR-86); got "
        f"{expected_permission!r}."
    )

    # The ``RBACEnforcer`` class MUST exist on ``app.admin.rbac``.
    assert RBACEnforcer is not None, (
        "FR-86: RBACEnforcer must not be None so that role management "
        "endpoints can verify system:write permission."
    )

    # GREEN TODO: ``RBACEnforcer.check(role='customer',
    # resource='system', action='write')`` MUST return 403 because the
    # customer role does not hold the ``system:write`` grant. Only admin
    # (and potentially editor) roles hold ``system:write`` per the FR-60
    # / FR-61 permission matrix.
    permission_result = RBACEnforcer.check(role, "system", "write")

    assert permission_result is not None, (
        "FR-86: RBACEnforcer.check('customer', 'system', 'write') must "
        "not return None; the RBAC system must return a status code "
        "(200 or 403) for every (role, resource, action) tuple."
    )

    assert permission_result == 403, (
        f"FR-86: RBACEnforcer.check('customer', 'system', 'write') MUST "
        f"return 403 — customer role does not hold the 'system:write' "
        f"grant required for role management per SRS FR-86; got "
        f"{permission_result!r}."
    )
    assert isinstance(permission_result, int), (
        f"FR-86: RBACEnforcer.check() must return an int status code; "
        f"got {type(permission_result).__name__} = {permission_result!r}."
    )

    # GREEN TODO: ``assign_role_to_user(user_id='user-001', role='agent',
    # caller_role='customer')`` MUST invoke
    # ``RBACEnforcer.check('customer', 'system', 'write')`` internally
    # and return 403 when the caller lacks permission. The function
    # signature is: assign_role_to_user(user_id: str, role: str,
    # caller_role: str) -> int (status code).
    assign_result = assign_role_to_user(
        user_id="user-001", role="agent", caller_role=role
    )

    assert assign_result is not None, (
        "FR-86: assign_role_to_user() must not return None; the endpoint "
        "must always produce a response (200 on success or 403 on "
        "permission denied)."
    )

    assert assign_result == 403, (
        f"FR-86: assign_role_to_user(caller_role='customer') MUST return "
        f"403 because the customer role lacks system:write permission "
        f"per SRS FR-86 'role 管理需 system:write 權限'; got "
        f"{assign_result!r}."
    )
    assert isinstance(assign_result, int), (
        f"FR-86: assign_role_to_user() must return an int status code; "
        f"got {type(assign_result).__name__} = {assign_result!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert action == "assign_role", (
        f"FR-86: action sentinel must remain 'assign_role'; got {action!r}."
    )
    assert role == "customer", (
        f"FR-86: role sentinel must remain 'customer'; got {role!r}."
    )
    assert expected_permission == "system:write", (
        f"FR-86: expected_permission sentinel must remain 'system:write'; "
        f"got {expected_permission!r}."
    )
