"""[FR-85] Management API router.

Citations:
  SRS.md FR-85
"""
from __future__ import annotations

from typing import Any


class ManagementRouter:
    """[FR-85] Admin management API endpoints."""

    def list_users(self, page: int = 1, limit: int = 20) -> dict[str, Any]:
        """Return paginated user list."""
        return {"data": [], "total": 0, "page": page, "limit": limit, "has_next": False}

    def get_stats(self) -> dict[str, Any]:
        """Return system statistics."""
        return {}
