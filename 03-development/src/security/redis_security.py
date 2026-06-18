"""[FR-90] Redis security configuration.

Citations:
  SRS.md FR-90
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RedisSecurityConfig:
    """[FR-90] TLS and auth configuration for Redis connections."""

    host: str
    port: int = 6379
    tls_enabled: bool = True
    password: str = ""
    db: int = 0

    def to_url(self) -> str:
        """Return Redis connection URL."""
        scheme = "rediss" if self.tls_enabled else "redis"
        return f"{scheme}://:{self.password}@{self.host}:{self.port}/{self.db}"
