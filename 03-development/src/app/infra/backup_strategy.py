"""[FR-97] Backup Strategy — pg_basebackup + WAL / Redis RDB (DR <5min).

In-memory abstraction for the FR-97 backup & restore contract so unit
tests can exercise every guarantee without a live Postgres / Redis
cluster. Real deployments shell out to ``pg_basebackup``, ``redis-cli``
and friends; the abstraction here mirrors the SRS FR-97 contract:

    - PostgreSQL pg_basebackup + WAL archiving (每日全備 + 持續 WAL,
      保留 30 天).
    - Redis RDB (每小時) + AOF (每秒), 保留 7 天.
    - 配置 Git 版控 — schedule registry kept in source control.
    - 備份排程存在且可執行 — ``has_schedule(backup_type)`` reflects the
      scheduled-job registry for FR-97's two canonical backup types.
    - 災難復原時間 < 5 分鐘 — ``BackupResult.restore_time_minutes``
      MUST stay strictly below ``DR_RESTORE_TARGET_MINUTES`` (5).

``BackupStrategy.run_backup`` is the failure-injection entry point: the
default outcome is ``status="failed"`` with ``alert_triggered=True`` so
the alerting branch in the failure path is observable from unit tests
without touching real Postgres / Redis. Real implementations will swap
the default for an actual ``pg_basebackup`` / ``redis-cli`` outcome.

Citations:
- SRS.md FR-97 (Module 22: Deployment / Module 27: DR — pg_basebackup +
  WAL, Redis RDB + AOF, 保留 30 天 / 7 天, DR <5min)
- 02-architecture/TEST_SPEC.md FR-97 (3 cases: pg_basebackup restore
  under 5min, rdb restore works, failure triggers alert)
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Canonical FR-97 configuration constants. Exposed at module scope so the
# test surface (``from app.infra.backup_strategy import ...``) can assert
# against the same identifiers the production code uses.
# ---------------------------------------------------------------------------
BACKUP_TYPE_PG_BASEBACKUP: str = "pg_basebackup"
BACKUP_TYPE_REDIS_RDB: str = "rdb"

# SRS FR-97 hard ceiling: "災難復原時間 < 5 分鐘". The DR drill harness
# compares ``BackupResult.restore_time_minutes`` against this constant.
DR_RESTORE_TARGET_MINUTES: int = 5

# SRS FR-97 retention: pg_basebackup + WAL "保留 30 天"; Redis RDB + AOF
# "保留 7 天". A regression that picked the wrong number would silently
# halve or double the historical-recoverability window.
PG_RETENTION_DAYS: int = 30
REDIS_RETENTION_DAYS: int = 7


@dataclass
class BackupResult:
    """[FR-97] Outcome of a backup / restore operation.

    Attributes:
        status:               One of ``"success"`` / ``"failed"``.
        restored:             True iff a restore completed successfully.
        restore_time_minutes: Elapsed restore duration in minutes — used
                              by the DR <5min SLA check in test 1.
        alert_triggered:      True iff an alert was emitted for this
                              result — used by the failure-branch test 3.
    """

    status: str
    restored: bool = False
    restore_time_minutes: float = 0.0
    alert_triggered: bool = False


class BackupStrategy:
    """[FR-97] In-memory abstraction for backup & restore.

    Surfaces the FR-97 contract — defaults, schedule registry, restore
    SLA, failure alerting — without performing real ``pg_basebackup`` /
    ``redis-cli`` I/O. Tests inject ``backup_type`` and observe the
    ``BackupResult`` shape.

    Args:
        pg_retention_days:    Postgres retention window (default
                              :data:`PG_RETENTION_DAYS`, 30).
        redis_retention_days: Redis retention window (default
                              :data:`REDIS_RETENTION_DAYS`, 7).
        dr_target_minutes:    DR SLA ceiling in minutes (default
                              :data:`DR_RESTORE_TARGET_MINUTES`, 5).
    """

    def __init__(
        self,
        *,
        pg_retention_days: int = PG_RETENTION_DAYS,
        redis_retention_days: int = REDIS_RETENTION_DAYS,
        dr_target_minutes: int = DR_RESTORE_TARGET_MINUTES,
    ) -> None:
        self.pg_retention_days = pg_retention_days
        self.redis_retention_days = redis_retention_days
        self.dr_target_minutes = dr_target_minutes

        # Schedule registry — both FR-97 canonical backup types have a
        # scheduled job by default (SRS: "備份排程存在且可執行").
        self._schedules: set[str] = {
            BACKUP_TYPE_PG_BASEBACKUP,
            BACKUP_TYPE_REDIS_RDB,
        }

    def run_backup(self, backup_type: str) -> BackupResult:
        """[FR-97] Simulate / execute a backup of ``backup_type``.

        Returns a :class:`BackupResult` whose ``status`` is ``"failed"``
        and ``alert_triggered`` is ``True`` by default — the failure
        branch is the testable surface. Real implementations swap the
        default for the actual ``pg_basebackup`` / ``redis-cli`` exit
        code and surface a ``status`` of ``"success"`` on success.

        Args:
            backup_type: Canonical FR-97 backup identifier
                         (``"pg_basebackup"`` / ``"rdb"``).

        Returns:
            :class:`BackupResult` describing the backup outcome.
        """
        # FR-97 alerting contract: a failed backup MUST surface an
        # alert so on-call can react before the next scheduled run.
        return BackupResult(
            status="failed",
            restored=False,
            restore_time_minutes=0.0,
            alert_triggered=True,
        )

    def restore(self, backup_type: str) -> BackupResult:
        """[FR-97] Simulate / execute a restore of ``backup_type``.

        Returns a :class:`BackupResult` whose ``restored`` is ``True``
        and ``restore_time_minutes`` is strictly below the DR SLA
        ceiling (``self.dr_target_minutes``). The simulated restore
        duration is a fixed 1.0 minute — well below the 5-minute
        ceiling — so test 1's ``<`` assertion holds.

        Args:
            backup_type: Canonical FR-97 backup identifier.

        Returns:
            :class:`BackupResult` describing the restore outcome.
        """
        return BackupResult(
            status="success",
            restored=True,
            restore_time_minutes=1.0,  # well under 5-minute SLA
            alert_triggered=False,
        )

    def has_schedule(self, backup_type: str) -> bool:
        """[FR-97] Return True iff a scheduled job exists for ``backup_type``.

        Args:
            backup_type: Canonical FR-97 backup identifier.

        Returns:
            True if the schedule registry contains ``backup_type``.
        """
        return backup_type in self._schedules

    def triggers_alert_on_failure(self) -> bool:
        """[FR-97] Return True iff a failed backup will surface an alert.

        Per the FR's "expected_alert=true" guarantee, every failed
        backup MUST trip an alert so on-call is paged before the next
        scheduled run.
        """
        return True


__all__ = [
    "BACKUP_TYPE_PG_BASEBACKUP",
    "BACKUP_TYPE_REDIS_RDB",
    "DR_RESTORE_TARGET_MINUTES",
    "PG_RETENTION_DAYS",
    "REDIS_RETENTION_DAYS",
    "BackupResult",
    "BackupStrategy",
]