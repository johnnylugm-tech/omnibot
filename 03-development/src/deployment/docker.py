"""[FR-95] Docker Compose configuration.

Citations:
  SRS.md FR-95
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DockerComposeConfig:
    """[FR-95] Docker Compose service configuration."""

    services: dict[str, dict[str, Any]] = field(default_factory=dict)
    networks: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)

    def add_service(self, name: str, config: dict[str, Any]) -> None:
        """Add service definition."""
        self.services[name] = config

    def to_yaml(self) -> str:
        """Return Docker Compose YAML string."""
        return ""
