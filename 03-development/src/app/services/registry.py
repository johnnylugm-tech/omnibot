"""Services Layer Hub module.

Citations: SAD.md L3 Services Hub.
"""
from __future__ import annotations
from typing import Any

_registry: dict[str, Any] = {}

def register_service(name: str, instance: Any) -> None:
    """[Hub] Register a service."""
    _registry[name] = instance

def get_service(name: str) -> Any:
    """[Hub] Retrieve a registered service."""
    return _registry.get(name)
