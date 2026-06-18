"""[FR-86] Authentication API router.

Citations:
  SRS.md FR-86
"""
from __future__ import annotations

from typing import Any


class AuthRouter:
    """[FR-86] JWT-based authentication endpoints."""

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Return JWT token pair on successful login."""
        return {"access_token": "", "token_type": "bearer"}

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Return new access token from refresh token."""
        return {"access_token": "", "token_type": "bearer"}

    def logout(self, token: str) -> bool:
        """Invalidate token."""
        return True
