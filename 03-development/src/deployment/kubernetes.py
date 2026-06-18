"""[FR-96] Kubernetes configuration.

Citations:
  SRS.md FR-96
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KubernetesConfig:
    """[FR-96] Kubernetes deployment manifests configuration."""

    namespace: str = "default"
    replicas: int = 3
    resources: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        """Return Kubernetes deployment manifest."""
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"namespace": self.namespace},
            "spec": {"replicas": self.replicas},
        }
