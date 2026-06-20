"""[FR-60] [FR-61] 7-role RBAC role-permission matrix and enforcement.

Citations:
    SRS.md line 138 — FR-60 acceptance: 7 角色 ROLE_PERMISSIONS 完整;
        dpo 有 pii:decrypt; auditor 無 pii:decrypt.
    SRS.md line 139 — FR-61 acceptance: 各角色權限按規格;
        auditor 嘗試 pii:decrypt 回 403; 越界操作被拒絕;
        Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義（不隱含）,
        確保 auditor 嘗試 pii:decrypt 時回傳 403.
    TEST_SPEC.md FR-60 / FR-61 — function contracts pinned by
        test_fr60.py / test_fr61.py.
"""

from __future__ import annotations

# HTTP-style status codes returned by ``enforce``. Mirrors the
# canonical REST semantics: 200 = grant, 403 = authz denial
# (``AUTHZ_INSUFFICIENT_ROLE``).
_HTTP_OK: int = 200
_HTTP_FORBIDDEN: int = 403

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
    pii:none 必須在 ROLE_PERMISSIONS 中顯式定義（不隱含）" contract is
    upheld mechanically (e.g. ``auditor['pii']`` is ``_NONE``, not a
    missing key that ``enforce`` would have to special-case).
    """
    return {resource: grants.get(resource, _NONE) for resource in RESOURCES}


ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    # anonymous: knowledge:read only (SRS FR-61 "anonymous=knowledge:read").
    "anonymous": _role({
        "knowledge": _READ_ONLY,
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
    # pii:none 必須在 ROLE_PERMISSIONS 中顯式定義（不隱含）".
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


__all__ = ["ROLE_PERMISSIONS", "RESOURCES", "enforce"]