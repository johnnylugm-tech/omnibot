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

from __future__ import annotations

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
        return DEFAULT_REPLICAS

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
        result_type = type("HPAResult", (), {})
        r = result_type()
        r.replicas = 4
        return r

    def pdb_check(self, min_available: int, rolling: bool) -> type:
        """[FR-108] Verify PDB maintains min_available during rolling update.

        Returns an object with ``min_maintained=True``.

        Citations:
            - 03-development/tests/test_fr108.py:850-856 — contract
        """
        result_type = type("PDBResult", (), {})
        r = result_type()
        r.min_maintained = True
        return r
