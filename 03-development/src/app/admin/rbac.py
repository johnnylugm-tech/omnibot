"""[FR-60] 7-role RBAC role-permission matrix.

Citations:
    SRS.md line 138 — FR-60 acceptance: 7 角色 ROLE_PERMISSIONS 完整；
        dpo 有 pii:decrypt；auditor 無 pii:decrypt.
    TEST_SPEC.md FR-60 — function contract pinned by test_fr60.py.
"""

from __future__ import annotations

# Resource → frozenset-of-actions. Nested encoding is the test's primary
# contract (see test_fr60_dpo_has_pii_decrypt GREEN TODO note). frozenset
# keeps the matrix immutable so callers cannot mutate role grants at
# runtime; the RBAC enforcer treats ROLE_PERMISSIONS as read-only.
ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    # Anonymous: no authenticated identity → no permissions.
    "anonymous": {},

    # Customer: read public knowledge, raise escalations (their own).
    "customer": {
        "knowledge": frozenset({"read"}),
        "escalate": frozenset({"write"}),
        "audit": frozenset(),
        "experiment": frozenset(),
        "system": frozenset(),
        "pii": frozenset(),
    },

    # Agent: handle customer conversations — read/write knowledge and
    # escalate, no delete on customer data.
    "agent": {
        "knowledge": frozenset({"read", "write"}),
        "escalate": frozenset({"read", "write"}),
        "audit": frozenset({"read"}),
        "experiment": frozenset(),
        "system": frozenset(),
        "pii": frozenset(),
    },

    # Editor: curate the knowledge base.
    "editor": {
        "knowledge": frozenset({"read", "write", "delete"}),
        "escalate": frozenset({"read"}),
        "audit": frozenset(),
        "experiment": frozenset({"read"}),
        "system": frozenset(),
        "pii": frozenset(),
    },

    # Admin: full operational control except privacy-sensitive decrypt.
    "admin": {
        "knowledge": frozenset({"read", "write", "delete"}),
        "escalate": frozenset({"read", "write", "delete"}),
        "audit": frozenset({"read", "write"}),
        "experiment": frozenset({"read", "write", "delete"}),
        "system": frozenset({"read", "write", "delete"}),
        "pii": frozenset(),  # admin MUST NOT decrypt; only dpo holds decrypt.
    },

    # Auditor: read audit logs only — MUST NOT decrypt PII (privacy
    # boundary; reinforced by FR-61 explicit pii:none + 403 on
    # pii:decrypt). ``pii`` resource carries zero actions so the
    # test's "decrypt in pii" branch stays False.
    "auditor": {
        "knowledge": frozenset({"read"}),
        "escalate": frozenset(),
        "audit": frozenset({"read"}),
        "experiment": frozenset({"read"}),
        "system": frozenset(),
        "pii": frozenset(),
    },

    # DPO: sole holder of ``pii:decrypt`` (FR-60 acceptance: "dpo 獨有
    # pii:decrypt"). Also gates privacy-sensitive system and audit
    # operations.
    "dpo": {
        "knowledge": frozenset({"read"}),
        "escalate": frozenset(),
        "audit": frozenset({"read", "write"}),
        "experiment": frozenset(),
        "system": frozenset({"read", "write"}),
        "pii": frozenset({"decrypt"}),
    },
}


__all__ = ["ROLE_PERMISSIONS"]
