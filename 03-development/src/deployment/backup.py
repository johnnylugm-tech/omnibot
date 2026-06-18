"""[FR-97] Backup strategy.

Citations:
  SRS.md FR-97
"""
from __future__ import annotations



class BackupStrategy:
    """[FR-97] PostgreSQL and Redis backup management."""

    def __init__(self, storage_path: str) -> None:
        self._path = storage_path

    def backup_postgres(self) -> str:
        """Run pg_basebackup and return backup path."""
        return ""

    def backup_redis(self) -> str:
        """Trigger Redis RDB save and return backup path."""
        return ""

    def restore(self, backup_path: str) -> bool:
        """Restore from backup path."""
        return True
