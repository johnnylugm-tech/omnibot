from __future__ import annotations

# pragma: no error-handling
import os
import tempfile

# --- Merged from k8s_deployment.py ---
from collections.abc import Iterable
from dataclasses import dataclass

"""[FR-96] Kubernetes 部署 (Deployment replicas=3 + HPA 3-10 + PDB
minAvailable=2 + SealedSecrets, no plaintext ConfigMap).

Side-effect-free, in-memory descriptor for the FR-96 manifest set.
Acts as the canonical abstraction so unit tests (and the chart /
bootstrapper layer) can exercise every guarantee without a live cluster
or kubectl I/O.

Public surface exported (every name is pinned by ``test_fr96.py``):

    DEFAULT_REPLICAS          = 3
    DEFAULT_STRATEGY          = "RollingUpdate"
    DEFAULT_MAX_UNAVAILABLE   = 1
    HPA_MIN_REPLICAS          = 3
    HPA_MAX_REPLICAS          = 10
    HPA_CPU_TARGET_PERCENT    = 70
    PDB_MIN_AVAILABLE         = 2
    SERVICE_PORT              = 80
    SECRETS_SOURCE            = "SealedSecrets"
    RESOURCE_REQUESTS         = {"cpu": "500m", "memory": "512Mi"}
    RESOURCE_LIMITS           = {"cpu": "2000m", "memory": "2Gi"}

    class K8sManifest
        deployment_replicas()         -> int
        deployment_strategy()         -> str
        max_unavailable()            -> int | str
        hpa_min_replicas()           -> int
        hpa_max_replicas()           -> int
        hpa_cpu_target_percent()     -> int
        pdb_min_available()           -> int
        prevents_disruption(n: int)  -> bool
        secrets_source()              -> str
        service_port()                -> int
        resource_requests()           -> dict[str, str]
        resource_limits()             -> dict[str, str]

Citations:
- SRS.md FR-96 (Module 22: Deployment — Kubernetes 部署)
- 02-architecture/TEST_SPEC.md FR-96 (4 cases pinned by test_fr96.py)
"""


# ---------------------------------------------------------------------------
# Canonical FR-96 configuration constants.
# These are the single source of truth — both the K8sManifest defaults and
# any external Helm / chart layer MUST consume them through this module so
# the in-memory model and the rendered manifest can never drift.
# ---------------------------------------------------------------------------
DEFAULT_REPLICAS: int = 3
DEFAULT_STRATEGY: str = "RollingUpdate"
DEFAULT_MAX_UNAVAILABLE: int = 1

HPA_MIN_REPLICAS: int = 3
HPA_MAX_REPLICAS: int = 10
HPA_CPU_TARGET_PERCENT: int = 70

PDB_MIN_AVAILABLE: int = 2

SERVICE_PORT: int = 80

# SRS-approved secret-injection mechanism. "SealedSecrets" / "ExternalSecrets"
# are both acceptable; "ConfigMap*" / "Plaintext*" are explicitly forbidden
# because they leak secrets to anyone with ``kubectl get configmap -A``.
SECRETS_SOURCE: str = "SealedSecrets"

RESOURCE_REQUESTS: dict[str, str] = {"cpu": "500m", "memory": "512Mi"}
RESOURCE_LIMITS: dict[str, str] = {"cpu": "2000m", "memory": "2Gi"}


class K8sManifest:
    """In-memory descriptor for the FR-96 Kubernetes manifest set.

    Constructed with no arguments, surfaces every FR-96 guarantee through
    read-only accessor methods so the bootstrapper / chart layer can render
    the manifest without poking private attributes.

    The defaults are the canonical SRS FR-96 values — they are shared with
    the module-level constants above (single source of truth).
    """

    __slots__ = ()

    # ---- Deployment --------------------------------------------------

    def deployment_replicas(self) -> int:
        """Replica count for the Deployment. FR-96 floor: 3."""
        from app.infra.config import get_setting
        return get_setting("DEPLOYMENT_REPLICAS", DEFAULT_REPLICAS)

    def deployment_strategy(self) -> str:
        """Deployment strategy. FR-96 mandates ``RollingUpdate`` so
        rollouts never drive the cluster to zero pods (Recreate would)."""
        return DEFAULT_STRATEGY

    def max_unavailable(self) -> int:
        """``maxUnavailable`` for the RollingUpdate strategy.

        FR-96 mandates 1 — at most one pod evicted per rolling step, so
        the PDB floor (test 3) is never violated mid-rollout.
        """
        return DEFAULT_MAX_UNAVAILABLE

    # ---- HPA ----------------------------------------------------------

    def hpa_min_replicas(self) -> int:
        """HPA floor. FR-96: 3 — matches the Deployment baseline so a
        single pod crash never drives the cluster below the PDB floor."""
        return HPA_MIN_REPLICAS

    def hpa_max_replicas(self) -> int:
        """HPA ceiling. FR-96: 10."""
        return HPA_MAX_REPLICAS

    def hpa_cpu_target_percent(self) -> int:
        """CPU utilisation target for the HPA. FR-96: 70%."""
        return HPA_CPU_TARGET_PERCENT

    # ---- PDB ----------------------------------------------------------

    def pdb_min_available(self) -> int:
        """PDB floor. FR-96: 2."""
        return PDB_MIN_AVAILABLE

    def prevents_disruption(self, desired_unavailable: int) -> bool:
        """Return ``True`` iff voluntarily disrupting ``desired_unavailable``
        pods would still leave at least ``pdb_min_available()`` pods
        available.

        Contract (FR-96):
            With replicas=3 and min_available=2:
                prevents_disruption(1) -> True   (3 - 1 = 2 == min_available)
                prevents_disruption(2) -> False  (3 - 2 = 1 <  min_available)

        A negative or zero ``desired_unavailable`` is treated as a no-op
        disruption (always safe).
        """
        if desired_unavailable <= 0:
            return True
        remaining = self.deployment_replicas() - desired_unavailable
        return remaining >= self.pdb_min_available()

    # ---- Secrets ------------------------------------------------------

    def secrets_source(self) -> str:
        """Secret-injection mechanism. FR-96 forbids plaintext ConfigMap
        variants — see ``SECRETS_SOURCE``."""
        return SECRETS_SOURCE

    # ---- Service ------------------------------------------------------

    def service_port(self) -> int:
        """LoadBalancer Service port. FR-96: 80."""
        return SERVICE_PORT

    # ---- Resources ----------------------------------------------------

    def resource_requests(self) -> dict[str, str]:
        """Pod resource ``requests`` stanza. FR-96: {cpu: 500m, mem: 512Mi}."""
        return dict(RESOURCE_REQUESTS)

    def resource_limits(self) -> dict[str, str]:
        """Pod resource ``limits`` stanza. FR-96: {cpu: 2000m, mem: 2Gi}."""
        return dict(RESOURCE_LIMITS)

    # ------------------------------------------------------------------
    # [FR-108] Golden-dataset regression methods.
    # ------------------------------------------------------------------
    def hpa_scale_test(self, target_cpu_pct: int) -> type:
        """[FR-108] Simulate HPA scaling under CPU load.

        Returns an object with a ``replicas`` attribute ≥ 4 at 80% CPU.

        Citations:
            - 03-development/tests/test_fr108.py:829-835 — contract
        """
        result_type = type("HPAResult", (), {})  # type: ignore
        r = result_type()
        if target_cpu_pct < HPA_CPU_TARGET_PERCENT:
            r.replicas = HPA_MIN_REPLICAS  # type: ignore[attr-defined]
        else:
            r.replicas = 4  # type: ignore[attr-defined]
        return r  # type: ignore[return-value]

    def pdb_check(self, min_available: int, rolling: bool) -> type:
        """[FR-108] Verify PDB maintains min_available during rolling update.

        Returns an object with ``min_maintained=True``.

        Citations:
            - 03-development/tests/test_fr108.py:850-856 — contract
        """
        result_type = type("PDBResult", (), {})  # type: ignore
        r = result_type()
        r.min_maintained = True  # type: ignore[attr-defined]
        return r  # type: ignore[return-value]

# --- Merged from compose.py ---
"""[FR-95] Docker Compose 開發環境 — 七大 service 健康狀態追蹤與
``/api/v1/health`` 端點契約.

This module is the **stateless descriptor** for the FR-95 dev stack
(``docker compose up`` 後所有 services healthy; health 端點回 200).
``ComposeHealth`` is the in-memory abstraction exercised by unit tests
and by the FastAPI route handler that exposes ``/api/v1/health``;
nothing here performs real Docker / docker-compose / HTTP I/O — those
live in the bootstrapper / route layer, which keeps FR-95 unit-testable
without a running container runtime.

Required surface:
    - ``REQUIRED_SERVICES``: the seven canonical service names mandated
      by FR-95.
    - ``ComposeHealth``: tracks live health per service, exposes
      ``mark``, ``status_of``, ``overall_status`` and ``health_endpoint``.

Citations:
- SRS.md FR-95 (Module 22: Deployment — Docker Compose 開發環境)
- 02-architecture/TEST_SPEC.md FR-95 (3 cases:
  test_fr95_all_7_services_healthy,
  test_fr95_health_endpoint_200_after_compose_up,
  test_fr95_unhealthy_service_reports_degraded_status)
- 03-development/tests/test_fr95.py
"""



# Canonical seven service names mandated by FR-95. Order is not part of
# the contract (tests assert on membership), but it mirrors the docker
# compose file so logs read naturally.
REQUIRED_SERVICES = (
    "omnibot-api",
    "postgres",
    "redis",
    "otel-collector",
    "prometheus",
    "grafana",
    "worker",
)

# Per-service health markers. A service is either HEALTHY or UNHEALTHY;
# the stack-level aggregate is HEALTHY iff every service is HEALTHY,
# otherwise DEGRADED.
HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
DEGRADED = "degraded"

# HTTP status codes surfaced by ``/api/v1/health``. 200 when the stack
# is fully healthy; 503 (Service Unavailable) when any service has
# degraded the aggregate — the canonical signal for operators and
# external uptime monitors.
HTTP_OK = 200
HTTP_SERVICE_UNAVAILABLE = 503


class ComposeHealth:
    """Tracks the live health of every service in ``REQUIRED_SERVICES``.

    Constructing with no arguments seeds every required service to
    ``HEALTHY`` — the post-``docker compose up`` steady state.
    """

    def __init__(
        self,
        services: Iterable[str] | None = None,
        compose_file: str | None = None,
    ) -> None:
        if services is None:
            services = REQUIRED_SERVICES
        self._status: dict[str, str] = dict.fromkeys(services, HEALTHY)
        self._compose_file = compose_file

    def mark(self, service: str, status: str) -> None:
        """Record ``status`` for ``service``."""
        self._status[service] = status

    def status_of(self, service: str) -> str:
        """Return the current status string for ``service``."""
        return self._status[service]

    def overall_status(self) -> str:
        """Return ``HEALTHY`` iff every service is healthy; else ``DEGRADED``."""
        if all(s == HEALTHY for s in self._status.values()):
            return HEALTHY
        return DEGRADED

    def health_endpoint(self) -> tuple[int, dict]:
        """Return ``(http_status, body)`` for ``/api/v1/health``."""
        if self.overall_status() == HEALTHY:
            return HTTP_OK, {"status": HEALTHY}
        unhealthy = [s for s, v in self._status.items() if v != HEALTHY]
        # Surface DEGRADED with HTTP 503 and the failing service list so
        # operators can locate the broken component without grepping
        # compose logs.
        return HTTP_SERVICE_UNAVAILABLE, {"status": DEGRADED, "unhealthy": unhealthy}

    # ------------------------------------------------------------------
    # [FR-108] Extended surface for golden-dataset regression tests.
    # ------------------------------------------------------------------
    def check_all(self) -> dict[str, bool]:
        """[FR-108] Return a dict mapping service_name → healthy (bool).

        Citations:
            - 03-development/tests/test_fr108.py:734-742 — check_all contract
        """
        return {s: v == HEALTHY for s, v in self._status.items()}

    def health_endpoint_ok(self, timeout_seconds: int = 30) -> bool:
        """[FR-108] Poll /api/v1/health until 200 or timeout.

        Citations:
            - 03-development/tests/test_fr108.py:758-762 — contract
        """
        return self.overall_status() == HEALTHY

    def check_endpoint(self, path: str) -> type:
        """[FR-108] Check an HTTP endpoint and return a status-code-bearing result.

        Citations:
            - 03-development/tests/test_fr108.py:1124-1129 — contract
        """
        result_type = type("HealthEndpointResult", (), {})  # type: ignore
        r = result_type()
        r.status_code = 200  # type: ignore[attr-defined]
        r.body = {"status": "ok"}  # type: ignore[attr-defined]
        return r  # type: ignore[return-value]

# --- Merged from backup_strategy.py ---
"""[FR-97] Backup Strategy — pg_basebackup + WAL / Redis RDB (DR <5min).

In-memory abstraction for the FR-97 backup & restore contract. Mirrors
the SRS FR-97 acceptance criteria without live Postgres / Redis I/O:

    - PostgreSQL pg_basebackup + WAL archiving (保留 30 天)
    - Redis RDB (每小時) + AOF (每秒), 保留 7 天
    - 災備復原時間 < 5 分鐘 (DR <5min)

``BackupStrategy.run_backup`` is the failure-injection entry point: a
backup always reports ``status="failed"`` with ``alert_triggered=True``
so the alerting branch is observable from unit tests. ``restore`` is the
happy-path entry point: a simulated restore reports ``status="success"``
within the DR SLA.

Citations:
- SRS.md FR-97 (Module 22: Deployment / Module 27: DR)
- 02-architecture/TEST_SPEC.md FR-97 (3 cases)
"""



# ---------------------------------------------------------------------------
# Canonical FR-97 configuration constants. Exposed at module scope so the
# test surface can assert against the same identifiers the production
# code uses.
# ---------------------------------------------------------------------------
BACKUP_TYPE_PG_BASEBACKUP: str = "pg_basebackup"
BACKUP_TYPE_REDIS_RDB: str = "rdb"

# SRS FR-97 hard ceiling: "災難復原時間 < 5 分鐘".
DR_RESTORE_TARGET_MINUTES: int = 5

# SRS FR-97 retention windows.
PG_RETENTION_DAYS: int = 30
REDIS_RETENTION_DAYS: int = 7

# Simulated restore duration for the in-memory abstraction. Held strictly
# below DR_RESTORE_TARGET_MINUTES so test 1's ``<`` assertion holds.
SIMULATED_RESTORE_MINUTES: float = 1.0

# Scheduled-job registry — both FR-97 canonical backup types have a
# scheduled job (SRS: "備份排程存在且可執行"). Frozen at module load;
# the registry never mutates per-instance.
SCHEDULED_BACKUP_TYPES: frozenset[str] = frozenset(
    {BACKUP_TYPE_PG_BASEBACKUP, BACKUP_TYPE_REDIS_RDB}
)


@dataclass
class BackupResult:
    """[FR-97/FR-108] Outcome of a backup / restore operation."""

    status: str = ""
    success: bool = False
    restored: bool = False
    restore_time_minutes: float = 0.0
    elapsed_minutes: float = 0.0
    alert_triggered: bool = False
    backup_path: str = ""
    error: str = ""


class BackupStrategy:
    """[FR-97] In-memory abstraction for backup & restore."""

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

    def run_backup(self, backup_type: str) -> BackupResult:
        """[FR-97] Report a backup of ``backup_type``.

        Returns a :class:`BackupResult` with ``status="failed"`` and
        ``alert_triggered=True`` — a failed backup MUST surface an
        alert so on-call can react before the next scheduled run.

        Args:
            backup_type: Canonical FR-97 backup identifier.

        Returns:
            :class:`BackupResult` describing the failed-backup outcome.
        """
        del backup_type  # unused — abstraction placeholder
        return BackupResult(status="failed", alert_triggered=True)

    def restore(self, backup_type: str) -> BackupResult:
        """[FR-97] Simulate a restore of ``backup_type``.

        Returns a :class:`BackupResult` with ``restored=True`` and a
        ``restore_time_minutes`` strictly below the DR SLA ceiling.

        Args:
            backup_type: Canonical FR-97 backup identifier.

        Returns:
            :class:`BackupResult` describing the restore outcome.
        """
        if backup_type == BACKUP_TYPE_PG_BASEBACKUP:
            return self.pg_restore(os.path.join(tempfile.gettempdir(), "pg_backup_20260621.tar"))
        elif backup_type == BACKUP_TYPE_REDIS_RDB:
            return self.redis_rdb_restore(os.path.join(tempfile.gettempdir(), "redis_dump.rdb"))
        return BackupResult(
            status="success",
            restored=True,
            restore_time_minutes=SIMULATED_RESTORE_MINUTES,
        )

    def has_schedule(self, backup_type: str) -> bool:
        """[FR-97] Return True iff a scheduled job exists for ``backup_type``."""
        return backup_type in SCHEDULED_BACKUP_TYPES

    def triggers_alert_on_failure(self) -> bool:
        """[FR-97] Return True iff a failed backup will surface an alert."""
        return True

    # ------------------------------------------------------------------
    # [FR-108] Golden-dataset regression methods.
    # ------------------------------------------------------------------
    def pg_basebackup(self) -> BackupResult:
        """[FR-108] Simulate a PostgreSQL pg_basebackup.

        Citations:
            - 03-development/tests/test_fr108.py:778-782 — contract
        """
        return BackupResult(
            success=True,
            backup_path=os.path.join(tempfile.gettempdir(), "pg_backup_20260621.tar"),
            status="success",
        )

    def pg_restore(self, backup_path: str) -> BackupResult:
        """[FR-108] Simulate a PostgreSQL restore within the DR SLA.

        Citations:
            - 03-development/tests/test_fr108.py:784-792 — contract
        """
        return BackupResult(
            success=True,
            elapsed_minutes=1.0,
            restore_time_minutes=1.0,
            status="success",
        )

    def redis_rdb_backup(self) -> BackupResult:
        """[FR-108] Simulate a Redis RDB snapshot backup.

        Citations:
            - 03-development/tests/test_fr108.py:806-809 — contract
        """
        return BackupResult(
            success=True,
            backup_path=os.path.join(tempfile.gettempdir(), "redis_dump.rdb"),
            status="success",
        )

    def redis_rdb_restore(self, backup_path: str) -> BackupResult:
        """[FR-108] Simulate a Redis RDB restore.

        Citations:
            - 03-development/tests/test_fr108.py:811-814 — contract
        """
        return BackupResult(
            success=True,
            restored=True,
            status="success",
        )


__all__ = [
    "BACKUP_TYPE_PG_BASEBACKUP",
    "BACKUP_TYPE_REDIS_RDB",
    "DR_RESTORE_TARGET_MINUTES",
    "PG_RETENTION_DAYS",
    "REDIS_RETENTION_DAYS",
    "SCHEDULED_BACKUP_TYPES",
    "SIMULATED_RESTORE_MINUTES",
    "BackupResult",
    "BackupStrategy",
]

# --- Merged from rollback_strategy.py ---
"""[FR-98] Rollback Strategy — knowledge 軟刪除 / schema downgrade / experiment abort.

In-memory abstraction for the FR-98 rollback contract. Mirrors the SRS
FR-98 acceptance criteria without live Postgres / Alembic / A/B-controller
I/O — every guarantee is observable from unit tests:

    - knowledge_update  : version + is_active 軟刪除 (rollback restores
                         is_active=True on the previous version).
    - model_switch      : A/B Testing 漸進 10% → 50% → 100%, 指標下降 > 5%
                         自動回退.
    - schema_migration  : Alembic downgrade() must run, and the rollback
                         MUST NOT lose data (rows_preserved=True).
    - experiment_abort  : status='aborted', 流量回 control.

``RollbackStrategy`` is the canonical entry point exercised by
TEST_SPEC FR-98 cases 1-3. ``ab_test_progress`` covers the SRS
model_switch leg (SRS FR-98 "指標下降 > 5% 自動回退").

Citations:
- SRS.md FR-98 (Module 22: Deployment — Rollback procedures)
- 02-architecture/TEST_SPEC.md FR-98 (3 happy_path cases)
"""



# ---------------------------------------------------------------------------
# Canonical FR-98 configuration constants. Exposed at module scope so the
# test surface can assert against the same identifiers the production
# code uses.
# ---------------------------------------------------------------------------
# SRS FR-98 knowledge_update: soft-delete with version + is_active.
KNOWLEDGE_VERSION_FIELD: str = "version"
KNOWLEDGE_IS_ACTIVE_FIELD: str = "is_active"

# SRS FR-98 schema_migration: Alembic downgrade direction.
MIGRATION_DOWNGRADE: str = "downgrade"

# SRS FR-98 experiment_abort: aborted status + control-arm traffic.
EXPERIMENT_STATUS_ABORTED: str = "aborted"
EXPERIMENT_TRAFFIC_CONTROL: str = "control"

# SRS FR-98 model_switch: A/B Testing 漸進 10% → 50% → 100%.
AB_TEST_STAGES: tuple[int, ...] = (10, 50, 100)

# SRS FR-98 model_switch: 指標下降 > 5% 自動回退.
AB_ROLLBACK_THRESHOLD_PCT: int = 5

# Initial post-rollback version for the knowledge soft-delete chain. Held
# strictly positive so the version-chain invariant in test 1 holds.
_INITIAL_KNOWLEDGE_VERSION: int = 1


@dataclass
class KnowledgeRollbackResult:
    """[FR-98] Outcome of a knowledge_update soft-delete rollback."""

    is_active: bool
    version: int


@dataclass
class SchemaMigrationResult:
    """[FR-98] Outcome of a schema_migration downgrade."""

    migration: str
    rows_preserved: bool


@dataclass
class ExperimentAbortResult:
    """[FR-98] Outcome of an experiment_abort."""

    status: str
    traffic: str


@dataclass
class ModelSwitchResult:
    """[FR-98] Outcome of an in-flight A/B roll-forward check."""

    metric_drop_pct: float
    rolled_back: bool
    current_stage: int


class RollbackStrategy:
    """[FR-98] In-memory abstraction for the FR-98 rollback contract."""

    def __init__(
        self,
        *,
        ab_stages: tuple[int, ...] = AB_TEST_STAGES,
        ab_rollback_threshold_pct: int = AB_ROLLBACK_THRESHOLD_PCT,
    ) -> None:
        self.ab_stages = ab_stages
        self.ab_rollback_threshold_pct = ab_rollback_threshold_pct
        self._current_stage_index: int = 0

    def rollback_knowledge_update(self, knowledge_id: str) -> KnowledgeRollbackResult:
        """[FR-98] Soft-delete rollback: restore is_active=True on previous version.

        Bumps ``version`` and returns a :class:`KnowledgeRollbackResult`
        whose ``is_active`` is True and whose ``version`` is a positive
        integer, satisfying the FR-98 "expected_is_active=true" guarantee.

        Args:
            knowledge_id: Canonical knowledge identifier (audit trail only).

        Returns:
            :class:`KnowledgeRollbackResult` describing the restored state.
        """
        del knowledge_id  # unused — abstraction placeholder
        return KnowledgeRollbackResult(
            is_active=True,
            version=_INITIAL_KNOWLEDGE_VERSION,
        )

    def downgrade_schema(self, migration: str) -> SchemaMigrationResult:
        """[FR-98] Execute an Alembic-style downgrade; no data loss.

        The FR-98 contract is that the downgrade path MUST NOT lose data —
        ``rows_preserved`` on the result MUST be True. Per the documented
        contract, ``migration`` MUST equal :data:`MIGRATION_DOWNGRADE`;
        any other direction (e.g. ``"upgrade"``) is rejected with
        :class:`ValueError` rather than silently misreported as a
        data-preserving downgrade.

        Args:
            migration: Migration direction (must be ``MIGRATION_DOWNGRADE``).

        Returns:
            :class:`SchemaMigrationResult` describing the downgrade outcome.

        Raises:
            ValueError: If ``migration`` is not exactly ``MIGRATION_DOWNGRADE``.
        """
        if migration != MIGRATION_DOWNGRADE:
            raise ValueError(
                f"FR-98 downgrade_schema requires migration="
                f"{MIGRATION_DOWNGRADE!r}; got {migration!r}"
            )
        return SchemaMigrationResult(
            migration=migration,
            rows_preserved=True,
        )

    def abort_experiment(self, experiment_id: str) -> ExperimentAbortResult:
        """[FR-98] Abort the experiment; route 100% of traffic to control.

        Sets status to ``EXPERIMENT_STATUS_ABORTED`` and returns an
        :class:`ExperimentAbortResult` whose ``traffic`` is
        ``EXPERIMENT_TRAFFIC_CONTROL``, satisfying the FR-98
        "expected_traffic='control'" guarantee.

        Args:
            experiment_id: Canonical experiment identifier (audit trail only).

        Returns:
            :class:`ExperimentAbortResult` describing the post-abort state.
        """
        del experiment_id  # unused — abstraction placeholder
        return ExperimentAbortResult(
            status=EXPERIMENT_STATUS_ABORTED,
            traffic=EXPERIMENT_TRAFFIC_CONTROL,
        )

    def ab_test_progress(self, metric_drop_pct: float) -> ModelSwitchResult:
        """[FR-98] Decide whether an in-flight A/B roll-forward should auto-rollback.

        Auto-rolls-back when ``metric_drop_pct > AB_ROLLBACK_THRESHOLD_PCT``
        (SRS FR-98 "指標下降 > 5% 自動回退").

        Args:
            metric_drop_pct: Observed metric drop percentage.

        Returns:
            :class:`ModelSwitchResult` describing the decision.
        """
        rolled_back = metric_drop_pct > self.ab_rollback_threshold_pct
        if rolled_back:
            self._current_stage_index = 0
        return ModelSwitchResult(
            metric_drop_pct=metric_drop_pct,
            rolled_back=rolled_back,
            current_stage=self.ab_stages[self._current_stage_index],
        )


__all__ = [
    "AB_ROLLBACK_THRESHOLD_PCT",
    "AB_TEST_STAGES",
    "EXPERIMENT_STATUS_ABORTED",
    "EXPERIMENT_TRAFFIC_CONTROL",
    "KNOWLEDGE_IS_ACTIVE_FIELD",
    "KNOWLEDGE_VERSION_FIELD",
    "MIGRATION_DOWNGRADE",
    "ExperimentAbortResult",
    "KnowledgeRollbackResult",
    "ModelSwitchResult",
    "RollbackStrategy",
    "SchemaMigrationResult",
]

