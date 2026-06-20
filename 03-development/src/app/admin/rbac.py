"""[FR-60] 7-role RBAC role-permission matrix.

Citations:
    SRS.md line 138 — FR-60 acceptance: 7 角色 ROLE_PERMISSIONS 完整；
        dpo 有 pii:decrypt；auditor 無 pii:decrypt.
    TEST_SPEC.md FR-60 — function contract pinned by test_fr60.py.
"""

from __future__ import annotations

# Full resource surface — every role entry MUST enumerate all resources
# so the RBAC enforcer can dispatch ``matrix[role][resource]`` without
# raising ``KeyError``. The nested ``resource -> frozenset-of-actions``
# encoding is the test's primary contract (see test_fr60 GREEN TODO
# note); frozenset keeps each role's grants immutable so callers
# cannot mutate grants at runtime.
RESOURCES: tuple[str, ...] = (
    "knowledge",
    "escalate",
    "audit",
    "experiment",
    "system",
    "pii",
)

# Shared empty-grants sentinel. frozensets are immutable so a single
# instance is safe to reuse across roles and across resources.
_NONE: frozenset[str] = frozenset()


def _role(grants: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Merge ``grants`` over the full ``RESOURCES`` surface, filling
    every undeclared resource with the empty sentinel."""
    return {resource: grants.get(resource, _NONE) for resource in RESOURCES}


ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    # Anonymous: no authenticated identity → no permissions.
    "anonymous": _role({}),

    # Customer: read public knowledge, raise escalations (their own).
    "customer": _role({
        "knowledge": frozenset({"read"}),
        "escalate": frozenset({"write"}),
    }),

    # Agent: handle customer conversations — read/write knowledge and
    # escalate, no delete on customer data.
    "agent": _role({
        "knowledge": frozenset({"read", "write"}),
        "escalate": frozenset({"read", "write"}),
        "audit": frozenset({"read"}),
    }),

    # Editor: curate the knowledge base.
    "editor": _role({
        "knowledge": frozenset({"read", "write", "delete"}),
        "escalate": frozenset({"read"}),
        "experiment": frozenset({"read"}),
    }),

    # Admin: full operational control except privacy-sensitive decrypt.
    # admin MUST NOT decrypt; only dpo holds decrypt.
    "admin": _role({
        "knowledge": frozenset({"read", "write", "delete"}),
        "escalate": frozenset({"read", "write", "delete"}),
        "audit": frozenset({"read", "write"}),
        "experiment": frozenset({"read", "write", "delete"}),
        "system": frozenset({"read", "write", "delete"}),
    }),

    # Auditor: read audit logs only — MUST NOT decrypt PII (privacy
    # boundary; reinforced by FR-61 explicit pii:none + 403 on
    # pii:decrypt). ``pii`` resource stays empty so the test's
    # "decrypt in pii" branch stays False.
    "auditor": _role({
        "knowledge": frozenset({"read"}),
        "audit": frozenset({"read"}),
        "experiment": frozenset({"read"}),
    }),

    # DPO: sole holder of ``pii:decrypt`` (FR-60 acceptance: "dpo 獨有
    # pii:decrypt"). Also gates privacy-sensitive system and audit
    # operations.
    "dpo": _role({
        "knowledge": frozenset({"read"}),
        "audit": frozenset({"read", "write"}),
        "system": frozenset({"read", "write"}),
        "pii": frozenset({"decrypt"}),
    }),
}


__all__ = ["ROLE_PERMISSIONS", "RESOURCES"]
