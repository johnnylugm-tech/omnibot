"""[FR-105] OpenDataDiscovery SQL query templates.

Citations:
  SRS.md FR-105
"""
from __future__ import annotations

from typing import Any


class ODDSQLQueries:
    """[FR-105] ODD-compatible SQL queries for data lineage."""

    def get_data_sources(self) -> list[dict[str, Any]]:
        """Return registered data sources."""
        return []

    def trace_lineage(self, table_name: str) -> dict[str, Any]:
        """Return data lineage graph for table."""
        return {"table": table_name, "upstream": [], "downstream": []}

    def generate_manifest(self) -> str:
        """Return ODD manifest YAML."""
        return ""
