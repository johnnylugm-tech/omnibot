"""TDD-RED: failing tests for FR-97 — 備份策略 pg_basebackup+WAL / Redis RDB
(DR <5min).

Spec source: 02-architecture/TEST_SPEC.md (FR-97)
SRS source : SRS.md FR-97 (Module 22: Deployment / Module 27: DR)

Acceptance criteria (from SRS FR-97):
    PostgreSQL pg_basebackup + WAL archiving (每日全備 + 持續 WAL, 保留 30 天);
    Redis RDB (每小時) + AOF (每秒), 保留 7 天;
    配置 Git 版控;
    備份排程存在且可執行;
    災備復原時間 < 5 分鐘 (DR <5min).

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr97_pg_basebackup_restore_under_5min
         Inputs: backup_type="pg_basebackup"; restore_time_minutes="5"
         Type  : happy_path
    2. test_fr97_redis_rdb_restore_works
         Inputs: backup_type="rdb"; expected_restored="true"
         Type  : happy_path
    3. test_fr97_backup_failure_triggers_alert
         Inputs: backup_type="pg_basebackup"; status="failed";
                 expected_alert="true"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr97-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``BackupStrategy`` is intentionally NOT YET exported by
# ``app.infra.backup_strategy``. The import below is unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/backup_strategy.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these names
# and behaviours are observable):
#
#   - Canonical configuration constants
#       BACKUP_TYPE_PG_BASEBACKUP = "pg_basebackup"
#       BACKUP_TYPE_REDIS_RDB     = "rdb"
#       DR_RESTORE_TARGET_MINUTES = 5       # SRS FR-97 DR <5min
#       PG_RETENTION_DAYS         = 30
#       REDIS_RETENTION_DAYS      = 7
#
#   - BackupStrategy
#       In-memory abstraction for the FR-97 backup & restore contract so
#       unit tests can exercise every guarantee without a live Postgres /
#       Redis cluster. Required attributes / methods:
#
#           __init__(...) -> None
#               Construct with FR-97 defaults (pg_basebackup + WAL,
#               pg_retention_days=30, redis RDB hourly + AOF per-second,
#               redis_retention_days=7, dr_target_minutes=5).
#           run_backup(backup_type: str) -> BackupResult
#               Execute a backup of the given type. Returns a
#               ``BackupResult`` whose ``status`` is "success" in the
#               happy path; ``run_backup`` MUST also accept an injected
#               clock / target so tests can simulate elapsed restore time
#               deterministically (no real subprocess / pg_basebackup /
#               redis-cli I/O).
#           restore(backup_type: str) -> BackupResult
#               Execute a restore of the given type. Returns a
#               ``BackupResult`` whose ``restore_time_minutes`` is the
#               elapsed restore duration. The contract for FR-97 is that
#               restore_time_minutes < DR_RESTORE_TARGET_MINUTES (5).
#           has_schedule(backup_type: str) -> bool
#               Returns True iff a scheduled job exists for the given
#               backup type (SRS FR-97: "備份排程存在且可執行").
#           triggers_alert_on_failure() -> bool
#               Returns True iff a failed backup will surface an alert
#               (the FR's "expected_alert=true" guarantee).
#
#   - BackupResult
#       Result of a backup / restore operation. Required attributes /
#       methods:
#           status: str
#               One of "success" / "failed".
#           restored: bool
#               True iff a restore completed successfully.
#           restore_time_minutes: float
#               Elapsed restore duration in minutes (used by the DR <5min
#               guarantee in test 1).
#           alert_triggered: bool
#               True iff an alert was emitted for this result (used by
#               test 3).
#
# The tests below intentionally avoid any real pg_basebackup / psql / WAL /
# redis-cli / subprocess I/O — they exercise the BackupStrategy abstraction
# in isolation, which is the canonical unit-test shape for FR-97.
# ---------------------------------------------------------------------------
# Re-export the constants so the tests can assert against the same values
# the production code uses (and so the harness sees the same names in
# the import surface as the green implementation must expose).
from app.infra.deployment import (  # noqa: F401
    BACKUP_TYPE_PG_BASEBACKUP,
    BACKUP_TYPE_REDIS_RDB,
    DR_RESTORE_TARGET_MINUTES,
    PG_RETENTION_DAYS,
    REDIS_RETENTION_DAYS,
    BackupResult,
    BackupStrategy,
)


# ---------------------------------------------------------------------------
# 1. A pg_basebackup + WAL restore completes in under 5 minutes (happy_path).
#
# Spec input: backup_type="pg_basebackup"; restore_time_minutes="5".
# SRS FR-97: "災備復原時間 < 5 分鐘".
# A regression that produced a restore_time_minutes >= 5 would violate the
# DR SLA — the literal hard ceiling written into the SRS and the TEST_SPEC
# (restore_time_minutes="5"). A regression that returned a non-finite /
# negative / None restore_time_minutes would mask the SLA breach and make
# the DR drill unmeasurable.
# ---------------------------------------------------------------------------
def test_fr97_pg_basebackup_restore_under_5min():
    # Spec input literals — also used as trigger values for the fr97-ok
    # sub-assertion guard.
    backup_type = "pg_basebackup"
    restore_time_minutes = "5"  # spec string sentinel: the SLA ceiling

    # GREEN TODO: ``DR_RESTORE_TARGET_MINUTES`` MUST be exported from
    # ``app.infra.backup_strategy`` and MUST equal 5 (the SRS FR-97
    # hard ceiling for DR restore).
    assert DR_RESTORE_TARGET_MINUTES == 5, (
        f"FR-97 DR_RESTORE_TARGET_MINUTES must be 5; got "
        f"{DR_RESTORE_TARGET_MINUTES!r}"
    )

    # GREEN TODO: ``BACKUP_TYPE_PG_BASEBACKUP`` MUST be exported and
    # MUST equal "pg_basebackup" — the canonical Postgres backup
    # identifier mandated by FR-97.
    assert BACKUP_TYPE_PG_BASEBACKUP == "pg_basebackup", (
        f"FR-97 BACKUP_TYPE_PG_BASEBACKUP must be 'pg_basebackup'; "
        f"got {BACKUP_TYPE_PG_BASEBACKUP!r}"
    )

    # Companion invariant for the SRS FR-97 Postgres leg:
    # "PostgreSQL pg_basebackup + WAL archiving (... 保留 30 天)".
    # A GREEN that picked 7 here would silently cut retention in
    # half and break the historical-recoverability guarantee.
    assert PG_RETENTION_DAYS == 30, (
        f"FR-97 PG_RETENTION_DAYS must be 30; got {PG_RETENTION_DAYS!r}"
    )

    # GREEN TODO: ``BackupStrategy()`` constructed with no arguments MUST
    # surface the FR-97 defaults via the public methods. GREEN may spell
    # the accessors however it likes so long as the values returned
    # match the spec.
    strategy = BackupStrategy()
    result = strategy.restore(backup_type)  # bind for the fr97-ok predicate

    # Spec fr97-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input literal
    # (backup_type="pg_basebackup"). The harness parser requires a single
    # VAR == c literal in the trigger block — compound conditions are
    # not matched. So we wrap the predicate in a narrow guard on the
    # spec's first case-1 trigger variable.
    if backup_type == "pg_basebackup":
        assert result is not None, (
            "fr97-ok predicate: result must not be None"
        )

    # Public surface contract: ``BackupResult`` MUST expose
    # ``restore_time_minutes`` so the DR drill harness can read the
    # observed restore duration. GREEN may spell it as an attribute
    # or accessor; both forms are checked below.
    if restore_time_minutes == "5":
        observed = (
            result.restore_time_minutes()
            if callable(getattr(result, "restore_time_minutes", None))
            else result.restore_time_minutes
        )
        assert observed is not None, (
            "FR-97 BackupResult.restore_time_minutes must not be None"
        )

        # The restore_time_minutes MUST be a finite, non-negative number.
        # A regression that returned a string sentinel here would break
        # every downstream SLA comparison.
        assert isinstance(observed, (int, float)), (
            f"FR-97 restore_time_minutes must be a number; got "
            f"{type(observed).__name__}"
        )

        # The DR SLA MUST hold: restore_time_minutes < 5. The SRS
        # explicitly mandates "災備復原時間 < 5 分鐘"; equality at
        # the ceiling is a regression because the FR's "<" is strict.
        assert observed < DR_RESTORE_TARGET_MINUTES, (
            f"FR-97 pg_basebackup restore_time_minutes must be < "
            f"{DR_RESTORE_TARGET_MINUTES}; got {observed}"
        )


# ---------------------------------------------------------------------------
# 2. A Redis RDB restore completes successfully (happy_path).
#
# Spec input: backup_type="rdb"; expected_restored="true".
# SRS FR-97: "Redis RDB (每小時) + AOF (每秒), 保留 7 天".
# A regression that returned restored=False for a healthy RDB restore
# would force every DR drill to fail and block the runbook; a regression
# that silently swallowed the Redis backup type and routed everything
# through the Postgres path would lose hourly snapshots on every Redis
# restart.
# ---------------------------------------------------------------------------
def test_fr97_redis_rdb_restore_works():
    # Spec input literals.
    backup_type = "rdb"
    expected_restored = "true"  # spec string sentinel

    # GREEN TODO: ``BACKUP_TYPE_REDIS_RDB`` MUST be exported and MUST
    # equal "rdb" — the canonical Redis snapshot identifier mandated
    # by FR-97.
    assert BACKUP_TYPE_REDIS_RDB == "rdb", (
        f"FR-97 BACKUP_TYPE_REDIS_RDB must be 'rdb'; got "
        f"{BACKUP_TYPE_REDIS_RDB!r}"
    )

    # GREEN TODO: ``REDIS_RETENTION_DAYS`` MUST equal 7 — the SRS
    # explicit "保留 7 天" for the Redis RDB + AOF pair.
    assert REDIS_RETENTION_DAYS == 7, (
        f"FR-97 REDIS_RETENTION_DAYS must be 7; got "
        f"{REDIS_RETENTION_DAYS!r}"
    )

    strategy = BackupStrategy()

    # The strategy MUST accept the Redis backup type on restore() —
    # a regression that hard-coded only the Postgres path would
    # silently break FR-97's Redis leg.
    if backup_type == "rdb":
        result = strategy.restore(backup_type)

        # Public surface contract: ``BackupResult`` MUST expose
        # ``restored`` so the DR drill harness can read the boolean
        # outcome. GREEN may spell it as an attribute or accessor;
        # both forms are checked below.
        assert hasattr(result, "restored"), (
            "FR-97 BackupResult must expose ``restored``"
        )
        observed_restored = (
            result.restored()
            if callable(getattr(result, "restored", None))
            else result.restored
        )

        # The restore MUST report success — the FR's "expected_restored=
        # true" guarantee.
        if expected_restored == "true":
            assert observed_restored is True, (
                f"FR-97 rdb restore must return restored=True; got "
                f"{observed_restored!r}"
            )

        # The restore MUST also report status="success" so observability
        # dashboards can distinguish success from the failed-state branch
        # exercised in test 3.
        observed_status = (
            result.status()
            if callable(getattr(result, "status", None))
            else result.status
        )
        assert observed_status == "success", (
            f"FR-97 rdb restore must return status='success'; got "
            f"{observed_status!r}"
        )


# ---------------------------------------------------------------------------
# 3. A failed backup emits an alert (validation).
#
# Spec input: backup_type="pg_basebackup"; status="failed";
#             expected_alert="true".
# SRS FR-97: any backup failure MUST be surfaced so on-call can react
# before the next scheduled run; a regression that silently swallowed
# the failure would let the DR SLA drift undetected.
# ---------------------------------------------------------------------------
def test_fr97_backup_failure_triggers_alert():
    # Spec input literals.
    backup_type = "pg_basebackup"
    status = "failed"  # spec string sentinel
    expected_alert = "true"  # spec string sentinel

    strategy = BackupStrategy()

    # GREEN TODO: ``BackupStrategy`` MUST expose a way to simulate /
    # observe a failed backup outcome. GREEN may choose ``run_backup``
    # with a fault-injection hook, a ``simulate_failure`` knob, or
    # any equivalent contract that lets the test observe the failed
    # state without touching real Postgres / Redis. The contract here
    # is: after a backup of ``backup_type`` is reported as ``status``,
    # ``alert_triggered`` on the resulting ``BackupResult`` MUST be
    # True.
    assert hasattr(strategy, "run_backup") and callable(strategy.run_backup), (
        "FR-97 BackupStrategy must expose ``run_backup(backup_type: str) "
        "-> BackupResult``"
    )

    result = strategy.run_backup(backup_type)

    # Public surface contract: ``BackupResult`` MUST expose
    # ``alert_triggered`` so the alerting layer can read whether an
    # alert should fire. GREEN may spell it as an attribute or
    # accessor; both forms are checked below.
    assert hasattr(result, "alert_triggered"), (
        "FR-97 BackupResult must expose ``alert_triggered``"
    )

    # Force the failed status so we can exercise the alerting branch.
    # GREEN may instead accept ``status`` as a constructor argument or
    # provide a dedicated ``fail()`` hook — the assertion below holds
    # regardless so long as the test can drive the result into
    # status="failed".
    observed_status = (
        result.status()
        if callable(getattr(result, "status", None))
        else result.status
    )
    if status == "failed":
        # The result MUST reflect the failed status. A GREEN that
        # forced status="success" here would silently mask the
        # alerting branch and break the FR's "expected_alert=true"
        # guarantee.
        assert observed_status == "failed", (
            f"FR-97 failed backup must report status='failed'; got "
            f"{observed_status!r}"
        )

    if expected_alert == "true":
        observed_alert = (
            result.alert_triggered()
            if callable(getattr(result, "alert_triggered", None))
            else result.alert_triggered
        )
        assert observed_alert is True, (
            f"FR-97 backup failure must trigger an alert "
            f"(alert_triggered=True); got {observed_alert!r}"
        )



# NFR coverage: NFR-14 (DR recovery<5min), NFR-32 (unit>=70% integration>=20% e2e>=10%)
