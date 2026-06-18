"""[FR-60] RBAC enforcer.

Citations:
  SRS.md FR-60
"""
from __future__ import annotations



class RBACEnforcer:
    """[FR-60] Role-based access control enforcement."""

    def __init__(self) -> None:
        self._policies: dict[str, set[str]] = {}

    def grant(self, role: str, permission: str) -> None:
        """Grant permission to role."""
        self._policies.setdefault(role, set()).add(permission)

    def is_allowed(self, role: str, action: str) -> bool:
        """Return True if role has permission for action."""
        return action in self._policies.get(role, set())
