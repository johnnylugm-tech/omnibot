from __future__ import annotations
"""[FR-60] [FR-61] [FR-62] 7-role RBAC role-permission matrix and
enforcement, plus the ``RBACEnforcer`` decorator middleware.

Citations:
    SRS.md line 138 — FR-60 acceptance: 7 角色 ROLE_PERMISSIONS 完整;
        dpo 有 pii:decrypt; auditor 無 pii:decrypt.
    SRS.md line 139 — FR-61 acceptance: 各角色權限按規格;
        auditor 嘗試 pii:decrypt 回 403; 越界操作被拒絕;
        Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義(不隱含),
        確保 auditor 嘗試 pii:decrypt 時回傳 403.
    SRS.md line 140 — FR-62 acceptance: ``@rbac.require(resource,
        action)`` 套用於管理 API endpoint; ``user_role`` 從 request 取得;
        無權限拋 ``PermissionError`` → HTTP 403
        ``AUTHZ_INSUFFICIENT_ROLE``; 有權限請求通過; 裝飾器正確注入.
    TEST_SPEC.md FR-60 / FR-61 / FR-62 — function contracts pinned by
        test_fr60.py / test_fr61.py / test_fr62.py.
"""


import functools
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# HTTP-style status codes returned by ``enforce``. Mirrors the
# canonical REST semantics: 200 = grant, 403 = authz denial
# (``AUTHZ_INSUFFICIENT_ROLE``).
_HTTP_OK: int = 200
_HTTP_FORBIDDEN: int = 403


@dataclass(frozen=True)
class EnforceResult:
    """[FR-108] Outcome of ``RBACEnforcer.enforce()``.

    Attributes:
        allowed: True when the role holds the resource:action grant.
        status_code: HTTP-style status — 200 on grant, 403 on denial.
    """

    allowed: bool
    status_code: int


# Full resource surface — every role entry MUST enumerate all resources
# so the RBAC enforcer can dispatch ``matrix[role][resource]`` without
# raising ``KeyError``. The nested ``resource -> frozenset-of-actions``
# encoding is the test's primary contract (see test_fr60 / test_fr61
# GREEN TODO notes); frozenset keeps each role's grants immutable so
# callers cannot mutate grants at runtime.
RESOURCES: tuple[str, ...] = (
    "knowledge",
    "escalate",
    "audit",
    "experiment",
    "system",
    "pii",
)

# Action-set sentinels. frozensets are immutable so a single instance
# is safe to reuse across roles and across resources.
_READ_ONLY: frozenset[str] = frozenset({"read"})
_FULL_CRUD: frozenset[str] = frozenset({"read", "write", "delete"})

# Shared empty-grants sentinel. Reusing it keeps every ``pii:none``
# cell in the matrix identical, which is the explicit-not-implicit
# contract demanded by FR-61.
_NONE: frozenset[str] = frozenset()


def _role(grants: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Merge ``grants`` over the full ``RESOURCES`` surface, filling
    every undeclared resource with the empty sentinel.

    The fill step makes the matrix self-describing: every role entry
    carries an explicit key for every resource, so the FR-61 "Explicit
    pii:none 必須在 ROLE_PERMISSIONS 中顯式定義(不隱含)" contract is
    upheld mechanically (e.g. ``auditor['pii']`` is ``_NONE``, not a
    missing key that ``enforce`` would have to special-case).
    """
    return {resource: grants.get(resource, _NONE) for resource in RESOURCES}


ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    # anonymous: no management grants (SRS FR-85 "各端點 RBAC 保護正確").
    # The management API endpoints require a higher-privilege role;
    # anonymous receives HTTP 403 AUTHZ_INSUFFICIENT_ROLE for every
    # management resource (including knowledge:read per FR-85).
    "anonymous": _role({
        "knowledge": _NONE,
    }),

    # customer: read public knowledge, raise escalations (their own).
    # SRS FR-61 "customer=knowledge:read + escalate:write".
    "customer": _role({
        "knowledge": _READ_ONLY,
        "escalate": frozenset({"write"}),
    }),

    # agent: handle customer conversations — read knowledge, raise
    # escalations. SRS FR-61 "agent=knowledge:read + escalate:write".
    "agent": _role({
        "knowledge": _READ_ONLY,
        "escalate": frozenset({"write"}),
    }),

    # editor: curate the knowledge base — read+write knowledge, read
    # escalations and experiments. SRS FR-61
    # "editor=knowledge:read+write + escalate:read + experiment:read".
    "editor": _role({
        "knowledge": frozenset({"read", "write"}),
        "escalate": _READ_ONLY,
        "experiment": _READ_ONLY,
    }),

    # admin: full operational control — read+write+delete on every
    # resource including pii (SRS FR-61 "admin=全資源 read+write+delete").
    # Note: ``pii:read/write/delete`` grants metadata/admin access to
    # the PII store; the legal ``decrypt`` operation remains dpo-only
    # because FR-61 grants are the 3 canonical CRUD verbs and decrypt
    # is intentionally NOT one of them at the admin tier.
    "admin": _role({
        "knowledge": _FULL_CRUD,
        "escalate": _FULL_CRUD,
        "audit": _FULL_CRUD,
        "experiment": _FULL_CRUD,
        "system": _FULL_CRUD,
        "pii": _FULL_CRUD,
    }),

    # auditor: read-only across knowledge/escalate/audit/experiment/system
    # with EXPLICIT pii:none (empty frozenset) per FR-61 "Explicit
    # pii:none 必須在 ROLE_PERMISSIONS 中顯式定義(不隱含)".
    # The empty ``pii`` grant is what makes ``enforce('auditor', 'pii',
    # 'decrypt')`` return 403 — privacy boundary.
    "auditor": _role({
        "knowledge": _READ_ONLY,
        "escalate": _READ_ONLY,
        "audit": _READ_ONLY,
        "experiment": _READ_ONLY,
        "system": _READ_ONLY,
    }),

    # dpo: same read surface as auditor PLUS the sole holder of
    # ``pii:decrypt`` (SRS FR-61 "dpo=同 auditor + pii:decrypt"; FR-60
    # acceptance: "dpo 獨有 pii:decrypt").
    "dpo": _role({
        "knowledge": _READ_ONLY,
        "escalate": _READ_ONLY,
        "audit": _READ_ONLY,
        "experiment": _READ_ONLY,
        "system": _READ_ONLY,
        "pii": frozenset({"decrypt"}),
    }),
}


def enforce(role: str, resource: str, action: str) -> int:
    """Return ``200`` when ``role`` holds the ``resource:action`` grant
    and ``403`` (``AUTHZ_INSUFFICIENT_ROLE``) otherwise.

    The 3-arg signature is canonical for FR-61: callers pass the already
    split halves of a ``"resource:action"`` string. Unknown roles,
    unknown resources, and ungranted actions all map to ``403`` so a
    missing-key ``KeyError`` can never leak role surface to an attacker.
    """
    role_grants = ROLE_PERMISSIONS.get(role)
    if role_grants is None:
        return _HTTP_FORBIDDEN
    resource_grants = role_grants.get(resource)
    if resource_grants is None:
        return _HTTP_FORBIDDEN
    return _HTTP_OK if action in resource_grants else _HTTP_FORBIDDEN


def _resolve_role(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[str, tuple[Any, ...]]:
    """Return ``(role, cleaned_args)`` for ``RBACEnforcer.require`` dispatch.

    Lookup order (SRS FR-62 "``user_role`` 從 request 取得"):
        1. ``kwargs["role"]`` — explicit role override (test hook).
        2. ``kwargs["request"].user_role`` — Flask-style request.
        3. ``args[0].user_role`` — first positional request object.
        4. ``"anonymous"`` — safe default (FR-61 anonymous only holds
           ``knowledge:read`` so any undeclared privilege still maps
           to 403).

    Role-bearing arguments are **consumed** (popped from *kwargs* in
    place for paths 1–2, sliced off *args* for path 3) so they are not
    passed through to the decorated function.
    """
    if "role" in kwargs:
        override = kwargs.pop("role")
        if override is not None and os.environ.get("TESTING") == "1":
            return str(override), args
    request = kwargs.get("request")
    if request is not None and getattr(request, "user_role", None) is not None:
        kwargs.pop("request")
        return str(request.user_role), args
    if args:
        first = args[0]
        if first is not None and getattr(first, "user_role", None) is not None:
            return str(first.user_role), args[1:]
    return "anonymous", args


class RBACEnforcer:
    """[FR-62] RBAC enforcer middleware exposing ``check`` and ``require``.

    Citations:
        SRS.md line 140 — FR-62 acceptance: ``@rbac.require(resource,
            action)`` decorator applied to admin API endpoints;
            ``user_role`` resolved from the request; insufficient role
            raises ``PermissionError`` → HTTP 403
            ``AUTHZ_INSUFFICIENT_ROLE``; authorised requests pass
            through; decorator is correctly injected.

    The class is a thin façade over the module-level ``enforce`` so the
    HTTP middleware can dispatch on a stable sentinel
    (``ERROR_AUTHZ_INSUFFICIENT_ROLE``) and on a stable status code
    (``200`` / ``403``) without coupling to the underlying grant
    matrix.
    """

    # Canonical denial error code. HTTP middleware matches on this
    # exact string to map a ``PermissionError`` to HTTP 403
    # ``AUTHZ_INSUFFICIENT_ROLE`` (SRS FR-62).
    ERROR_AUTHZ_INSUFFICIENT_ROLE: str = "AUTHZ_INSUFFICIENT_ROLE"

    @classmethod
    def check(cls, role: str, resource: str, action: str) -> int:
        """Return ``200`` for granted ``(resource, action)`` else ``403``.

        Mirrors the module-level ``enforce`` so the class is a stable
        entry point for both programmatic checks and the
        ``require`` decorator.
        """
        return enforce(role, resource, action)

    def enforce(self, role: str, resource: str, action: str) -> EnforceResult:
        """[FR-108] Instance-level RBAC enforcement returning ``EnforceResult``.

        Citations:
            - 03-development/tests/test_fr108.py:502-510 — auditor pii:decrypt 403
            - 03-development/tests/test_fr108.py:1079-1088 — customer knowledge:write 403
            - 03-development/tests/test_fr108.py:1099-1109 — editor knowledge:delete 403
        """
        status = enforce(role, resource, action)
        return EnforceResult(
            allowed=(status == _HTTP_OK),
            status_code=status,
        )

    @classmethod
    def require(cls, resource: str, action: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Return a decorator that gates ``func`` on the
        ``(resource, action)`` grant for the caller's role.

        The caller's role is resolved from the wrapped invocation's
        arguments via ``_resolve_role`` (kwargs ``role`` /
        ``request.user_role`` / first-positional ``user_role``;
        defaults to ``"anonymous"``). On denial the decorator raises
        ``PermissionError(cls.ERROR_AUTHZ_INSUFFICIENT_ROLE)`` so
        HTTP middleware can map the failure to a 403
        ``AUTHZ_INSUFFICIENT_ROLE`` response (SRS FR-62).
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                role, args = _resolve_role(args, kwargs)
                if cls.check(role, resource, action) != _HTTP_OK:
                    raise PermissionError(cls.ERROR_AUTHZ_INSUFFICIENT_ROLE)
                return func(*args, **kwargs)

            return wrapper

        return decorator


__all__ = ["RESOURCES", "ROLE_PERMISSIONS", "RBACEnforcer", "enforce"]

