"""[FR-87] Machine-to-machine token API.

Citations:
  SRS.md FR-87
"""
from __future__ import annotations

from typing import Any


class M2MTokenRouter:
    """[FR-87] M2M service-account token management."""

    def issue(self, client_id: str, client_secret: str, scopes: list[str]) -> dict[str, Any]:
        """Issue M2M access token."""
        return {"access_token": "", "expires_in": 3600, "token_type": "bearer"}

    def revoke(self, token: str) -> bool:
        """Revoke M2M token."""
        return True
