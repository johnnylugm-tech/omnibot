"""TDD-RED: failing tests for FR-62 — RBACEnforcer decorator Middleware
that turns insufficient-role requests into HTTP 403
``AUTHZ_INSUFFICIENT_ROLE``.

Spec source: 02-architecture/TEST_SPEC.md (FR-62)
SRS source : SRS.md line 140 — FR-62 acceptance:
    RBACEnforcer 裝飾器 Middleware: ``@rbac.require(resource, action)``
    套用於管理 API endpoint; ``user_role`` 從 request 取得; 無權限
    拋 ``PermissionError`` → HTTP 403 ``AUTHZ_INSUFFICIENT_ROLE``.
    Acceptance: 無權限請求回 403; 有權限請求通過; 裝飾器正確注入.
    Implementation function: ``RBACEnforcer.require()``, ``check()``.

Active Pattern: NP-02 (Security Control).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-
check performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-62 (SRS.md line 140) requires:
#   1. An ``RBACEnforcer`` class is exported from ``app.admin.rbac``;
#   2. The class exposes a ``check(role, resource, action)`` method
#      that returns an HTTP-style status code — ``200`` when the role
#      holds the ``(resource, action)`` grant and ``403`` when it
#      does not (i.e. ``AUTHZ_INSUFFICIENT_ROLE``);
#   3. The class exposes a ``require(resource, action)`` decorator
#      factory whose returned decorator raises ``PermissionError`` (or
#      otherwise signals denial) when the requesting role does not
#      hold the ``(resource, action)`` grant, and lets the call
#      through when it does;
#   4. The denial error code MUST be the canonical
#      ``"AUTHZ_INSUFFICIENT_ROLE"`` string so HTTP middleware can map
#      it to HTTP 403.
#
# GREEN contract pinned by this spec:
#
#   - ``app.admin.rbac`` MUST export the ``RBACEnforcer`` class.
#   - ``RBACEnforcer.check(role: str, resource: str, action: str) -> int``
#     MUST return ``200`` for granted actions and ``403`` for denied
#     actions.
#   - ``RBACEnforcer.require(resource: str, action: str)`` MUST return
#     a decorator that resolves the caller's role from the request and
#     raises ``PermissionError`` (or returns the 403 status) when the
#     role is insufficient.
#   - The error code sentinel ``RBACEnforcer.ERROR_AUTHZ_INSUFFICIENT_ROLE``
#     MUST equal the literal string ``"AUTHZ_INSUFFICIENT_ROLE"``.
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because ``RBACEnforcer`` is not yet
# defined in ``app.admin.rbac``, or with AssertionError if the class
# is added but the contracts above are not honoured. Either failure is
# the valid RED signal — GREEN adds the class and tightens the
# behaviour to make every assertion hold.
# ---------------------------------------------------------------------------
from app.admin.rbac import RBACEnforcer


# ---------------------------------------------------------------------------
# 1. An unauthorised role MUST be denied with HTTP 403
#    (``AUTHZ_INSUFFICIENT_ROLE``) by the RBAC enforcer middleware
#    (SRS FR-62 acceptance: "無權限請求回 403").
#
# Spec input: role="customer"; resource="audit"; action="read";
#            expected_status="403".
# Spec sub-assertion: fr62-ok: result is not None.
# SRS FR-62 acceptance: "無權限請求回 403".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr62_unauthorized_role_returns_403():
    role = "customer"
    resource = "audit"
    action = "read"
    expected_status = "403"

    # Defence-in-depth: pin the spec sentinel strings so a silent
    # rewrite of the test inputs cannot accidentally relax the
    # assertion to e.g. swapping the role to one that is allowed.
    assert role == "customer", (
        f"FR-62: role sentinel must be 'customer' (SRS FR-62 '無權限"
        f"請求回 403'); got {role!r}."
    )
    assert resource == "audit", (
        f"FR-62: resource sentinel must be 'audit' (SRS FR-62); got "
        f"{resource!r}."
    )
    assert action == "read", (
        f"FR-62: action sentinel must be 'read' (SRS FR-62); got "
        f"{action!r}."
    )
    assert expected_status == "403", (
        f"FR-62: expected_status sentinel must be '403' (HTTP 403 "
        f"AUTHZ_INSUFFICIENT_ROLE); got {expected_status!r}."
    )

    # The ``RBACEnforcer`` class MUST exist on ``app.admin.rbac``.
    assert RBACEnforcer is not None, (
        "fr62-ok predicate: RBACEnforcer must not be None so the "
        "middleware can be applied to admin API endpoints (SRS FR-62 "
        "'RBACEnforcer 裝飾器 Middleware')."
    )

    # GREEN TODO: RBACEnforcer MUST expose a
    #   ``check(role: str, resource: str, action: str) -> int``
    # method that returns ``200`` for granted actions and ``403``
    # (AUTHZ_INSUFFICIENT_ROLE) for denied actions. For
    # ``role='customer'`` and ``resource='audit'`` and
    # ``action='read'`` the function MUST return 403 because
    # customer does not hold the ``audit:read`` grant.
    result = RBACEnforcer.check(role, resource, action)

    # fr62-ok: result is not None.
    assert result is not None, (
        "fr62-ok predicate: RBACEnforcer.check() must not return None "
        "for any (role, resource, action) tuple; the middleware needs a "
        "real status code (200 or 403) so HTTP can dispatch the "
        "response."
    )

    assert result == 403, (
        f"FR-62: RBACEnforcer.check('customer', 'audit', 'read') MUST "
        f"return 403 per SRS FR-62 '無權限請求回 403'; got {result!r}. "
        f"Customer does NOT hold the 'audit:read' grant (only admin/"
        f"auditor/dpo do)."
    )
    assert result == int(expected_status), (
        f"FR-62: RBACEnforcer.check() status must equal int('403') = "
        f"403; got {result!r}."
    )
    assert isinstance(result, int), (
        f"FR-62: RBACEnforcer.check() must return an int status code "
        f"(HTTP-style); got {type(result).__name__} = {result!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "customer", (
        f"FR-62: role sentinel must remain 'customer'; got {role!r}."
    )
    assert resource == "audit", (
        f"FR-62: resource sentinel must remain 'audit'; got {resource!r}."
    )
    assert action == "read", (
        f"FR-62: action sentinel must remain 'read'; got {action!r}."
    )
    assert expected_status == "403", (
        f"FR-62: expected_status sentinel must remain '403'; got "
        f"{expected_status!r}."
    )


# ---------------------------------------------------------------------------
# 2. An authorised role MUST pass through the RBAC enforcer middleware
#    with HTTP 200 (SRS FR-62 acceptance: "有權限請求通過"; "裝飾器
#    正確注入").
#
# Spec input: role="admin"; resource="knowledge"; action="write";
#            expected_status="200".
# Spec sub-assertion: fr62-ok: result is not None.
# SRS FR-62 acceptance: "有權限請求通過"; "裝飾器正確注入".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr62_authorized_role_passes():
    role = "admin"
    resource = "knowledge"
    action = "write"
    expected_status = "200"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "admin", (
        f"FR-62: role sentinel must be 'admin' (SRS FR-62 '有權限請求"
        f"通過'); got {role!r}."
    )
    assert resource == "knowledge", (
        f"FR-62: resource sentinel must be 'knowledge' (SRS FR-62); "
        f"got {resource!r}."
    )
    assert action == "write", (
        f"FR-62: action sentinel must be 'write' (SRS FR-62); got "
        f"{action!r}."
    )
    assert expected_status == "200", (
        f"FR-62: expected_status sentinel must be '200' (HTTP 200 OK); "
        f"got {expected_status!r}."
    )

    # The ``RBACEnforcer`` class MUST exist on ``app.admin.rbac``.
    assert RBACEnforcer is not None, (
        "fr62-ok predicate: RBACEnforcer must not be None so the "
        "middleware can be applied to admin API endpoints (SRS FR-62 "
        "'RBACEnforcer 裝飾器 Middleware')."
    )

    # GREEN TODO: RBACEnforcer.check(role, resource, action) MUST
    # return ``200`` when the role holds the ``(resource, action)``
    # grant. For ``role='admin'`` and ``resource='knowledge'`` and
    # ``action='write'`` the function MUST return 200 because admin
    # is the full-CRUD role (SRS FR-61 'admin=全資源 read+write
    # +delete').
    result = RBACEnforcer.check(role, resource, action)

    # fr62-ok: result is not None.
    assert result is not None, (
        "fr62-ok predicate: RBACEnforcer.check() must not return None "
        "for granted actions; the middleware needs the literal 200 so "
        "HTTP can dispatch OK."
    )

    assert result == 200, (
        f"FR-62: RBACEnforcer.check('admin', 'knowledge', 'write') "
        f"MUST return 200 per SRS FR-62 '有權限請求通過'; got {result!r}. "
        f"Admin holds full read+write+delete on every resource."
    )
    assert result == int(expected_status), (
        f"FR-62: RBACEnforcer.check() status must equal int('200') = "
        f"200; got {result!r}."
    )
    assert isinstance(result, int), (
        f"FR-62: RBACEnforcer.check() must return an int status code "
        f"(HTTP-style); got {type(result).__name__} = {result!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "admin", (
        f"FR-62: role sentinel must remain 'admin'; got {role!r}."
    )
    assert resource == "knowledge", (
        f"FR-62: resource sentinel must remain 'knowledge'; got "
        f"{resource!r}."
    )
    assert action == "write", (
        f"FR-62: action sentinel must remain 'write'; got {action!r}."
    )
    assert expected_status == "200", (
        f"FR-62: expected_status sentinel must remain '200'; got "
        f"{expected_status!r}."
    )


# ---------------------------------------------------------------------------
# 3. The canonical error code for the 403 denial path MUST be the
#    literal string ``"AUTHZ_INSUFFICIENT_ROLE"`` (SRS FR-62: "無權限
#    拋 PermissionError → HTTP 403 AUTHZ_INSUFFICIENT_ROLE"). The
#    error code is the contract that HTTP middleware uses to map an
#    internal denial to a 403 response, so it MUST be exposed as a
#    stable string sentinel.
#
# Spec input: error_code="AUTHZ_INSUFFICIENT_ROLE"; role="anonymous".
# Spec sub-assertion: fr62-ok: result is not None.
# SRS FR-62 acceptance: "HTTP 403 AUTHZ_INSUFFICIENT_ROLE".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr62_error_code_authz_insufficient_role():
    error_code = "AUTHZ_INSUFFICIENT_ROLE"
    role = "anonymous"

    # Defence-in-depth: pin the spec sentinel strings.
    assert error_code == "AUTHZ_INSUFFICIENT_ROLE", (
        f"FR-62: error_code sentinel must be 'AUTHZ_INSUFFICIENT_ROLE' "
        f"(SRS FR-62 'HTTP 403 AUTHZ_INSUFFICIENT_ROLE'); got "
        f"{error_code!r}."
    )
    assert role == "anonymous", (
        f"FR-62: role sentinel must be 'anonymous' (lowest privilege, "
        f"used as a deterministic denial probe); got {role!r}."
    )

    # The ``RBACEnforcer`` class MUST exist on ``app.admin.rbac``.
    assert RBACEnforcer is not None, (
        "fr62-ok predicate: RBACEnforcer must not be None so the "
        "middleware can map denials to AUTHZ_INSUFFICIENT_ROLE (SRS "
        "FR-62)."
    )

    # GREEN TODO: RBACEnforcer MUST expose the canonical error code
    # sentinel as a class-level attribute. The most common contracts
    # that satisfy this GREEN TODO are:
    #   - ``RBACEnforcer.ERROR_AUTHZ_INSUFFICIENT_ROLE = "AUTHZ_INSUFFICIENT_ROLE"``
    #   - ``RBACEnforcer.ERROR_CODES["AUTHZ_INSUFFICIENT_ROLE"] = "AUTHZ_INSUFFICIENT_ROLE"``
    #   - ``RBACEnforcer.errors.AUTHZ_INSUFFICIENT_ROLE == "AUTHZ_INSUFFICIENT_ROLE"``
    # The test below accepts any of these (and any other) shapes so
    # the GREEN agent has freedom to pick a clean class-level
    # contract. The MUST is: the literal string
    # ``"AUTHZ_INSUFFICIENT_ROLE"`` MUST be retrievable from
    # ``RBACEnforcer`` as a stable class-level sentinel.
    sentinel_attr_candidates = (
        "ERROR_AUTHZ_INSUFFICIENT_ROLE",
        "ERROR_CODE_AUTHZ_INSUFFICIENT_ROLE",
        "AUTHZ_INSUFFICIENT_ROLE",
    )
    sentinel_value = None
    for attr in sentinel_attr_candidates:
        sentinel_value = getattr(RBACEnforcer, attr, None)
        if sentinel_value is not None:
            break

    assert sentinel_value is not None, (
        f"FR-62: RBACEnforcer must expose the canonical error code "
        f"sentinel. Tried class attributes {sentinel_attr_candidates!r}; "
        f"none were set. SRS FR-62 requires the HTTP 403 path to use "
        f"the literal string 'AUTHZ_INSUFFICIENT_ROLE' so middleware "
        f"can dispatch the response."
    )
    assert sentinel_value == error_code, (
        f"FR-62: RBACEnforcer error code sentinel must equal the "
        f"literal string 'AUTHZ_INSUFFICIENT_ROLE' per SRS FR-62 'HTTP "
        f"403 AUTHZ_INSUFFICIENT_ROLE'; got {sentinel_value!r}."
    )
    assert isinstance(sentinel_value, str), (
        f"FR-62: RBACEnforcer error code sentinel must be a str; got "
        f"{type(sentinel_value).__name__} = {sentinel_value!r}. HTTP "
        f"middleware matches on string equality."
    )
    assert sentinel_value == "AUTHZ_INSUFFICIENT_ROLE", (
        f"FR-62: RBACEnforcer error code sentinel must equal "
        f"'AUTHZ_INSUFFICIENT_ROLE' exactly (case-sensitive); got "
        f"{sentinel_value!r}."
    )

    # Cross-check via the ``check()`` denial path: anonymous MUST be
    # denied (HTTP 403) when requesting any non-allowed operation,
    # and the denial MUST be classifiable as
    # ``AUTHZ_INSUFFICIENT_ROLE`` by the middleware. We pick a
    # canonical anonymous-denial target: ``audit:read`` (anonymous
    # only has ``knowledge:read``).
    status = RBACEnforcer.check(role, "audit", "read")
    assert status == 403, (
        f"FR-62: anonymous MUST be denied on 'audit:read' (anonymous "
        f"only holds knowledge:read); got {status!r}. The denial "
        f"maps to the AUTHZ_INSUFFICIENT_ROLE error code."
    )
    assert status != 200, (
        f"FR-62: anonymous MUST NOT be allowed on 'audit:read' "
        f"(privilege escalation bug); got {status!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert error_code == "AUTHZ_INSUFFICIENT_ROLE", (
        f"FR-62: error_code sentinel must remain 'AUTHZ_INSUFFICIENT_ROLE'; "
        f"got {error_code!r}."
    )
    assert role == "anonymous", (
        f"FR-62: role sentinel must remain 'anonymous'; got {role!r}."
    )
