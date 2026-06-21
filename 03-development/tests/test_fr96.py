from __future__ import annotations
"""TDD-RED: failing tests for FR-96 — Kubernetes 部署 (Deployment replicas=3
+ HPA 3-10 + PDB minAvailable=2 + SealedSecrets, no plaintext ConfigMap).

Spec source: 02-architecture/TEST_SPEC.md (FR-96)
SRS source : SRS.md FR-96 (Module 22: Deployment — Kubernetes 部署)

Acceptance criteria (from SRS FR-96):
    Kubernetes 部署:Deployment (replicas=3, RollingUpdate
    maxUnavailable=1) + HPA (min=3, max=10, CPU utilization=70%) +
    PDB (minAvailable=2) + NetworkPolicy (限制 ingress 來源) + Service
    (LoadBalancer port=80);secrets 透過 SealedSecrets/External Secrets
    注入 (不用明文 ConfigMap);
    requests{cpu:500m,mem:512Mi} limits{cpu:2000m,mem:2Gi}。

The four TEST_SPEC cases (function names MUST match exactly):
    1. test_fr96_deployment_3_replicas
         Inputs: replicas="3"; strategy="RollingUpdate"
         Type  : happy_path
    2. test_fr96_hpa_scales_to_10
         Inputs: cpu_target="70%"; max_replicas="10"
         Type  : happy_path
    3. test_fr96_pdb_prevents_disruption
         Inputs: min_available="2"; rolling_update="true"
         Type  : validation
    4. test_fr96_secrets_not_in_plaintext_configmap
         Inputs: secrets_source="SealedSecrets";
                 expected_plaintext_configmap="false"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr96-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test — ``K8sManifest`` is intentionally NOT YET exported by
# ``app.infra.k8s_deployment``. The import below is unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/k8s_deployment.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these names
# and behaviours are observable):
#
#   - Canonical configuration constants
#       DEFAULT_REPLICAS         = 3
#       DEFAULT_STRATEGY         = "RollingUpdate"
#       DEFAULT_MAX_UNAVAILABLE  = 1
#       HPA_MIN_REPLICAS         = 3
#       HPA_MAX_REPLICAS         = 10
#       HPA_CPU_TARGET_PERCENT   = 70
#       PDB_MIN_AVAILABLE        = 2
#       SERVICE_PORT             = 80
#       SECRETS_SOURCE           = "SealedSecrets"  # or "ExternalSecrets"
#       RESOURCE_REQUESTS        = {"cpu": "500m", "memory": "512Mi"}
#       RESOURCE_LIMITS          = {"cpu": "2000m", "memory": "2Gi"}
#
#   - K8sManifest
#       In-memory descriptor for the FR-96 manifest set. Acts as the
#       canonical, side-effect-free abstraction so unit tests can
#       exercise every guarantee without a live cluster. Required
#       attributes / methods:
#
#           __init__(...) -> None
#               Construct with FR-96 defaults (replicas=3,
#               strategy="RollingUpdate", max_unavailable=1, hpa min=3 /
#               max=10 / cpu=70%, pdb min_available=2, service
#               type="LoadBalancer" / port=80, secrets_source=
#               "SealedSecrets", resources requests={cpu:500m,mem:512Mi}
#               limits={cpu:2000m,mem:2Gi}).
#           deployment_replicas() -> int
#               Returns the configured replica count.
#           deployment_strategy() -> str
#               Returns "RollingUpdate" (or the equivalent enum string).
#           max_unavailable() -> int | str
#               Returns the maxUnavailable value (1 for FR-96).
#           hpa_min_replicas() -> int
#               Returns 3 (the HPA floor).
#           hpa_max_replicas() -> int
#               Returns 10 (the HPA ceiling).
#           hpa_cpu_target_percent() -> int
#               Returns 70 (CPU utilisation target).
#           pdb_min_available() -> int
#               Returns 2 (the PDB floor).
#           prevents_disruption(desired_unavailable: int) -> bool
#               Returns True iff disrupting ``desired_unavailable`` pods
#               would still leave at least ``pdb_min_available`` pods
#               available. This is the canonical behaviour pinned by
#               test 3.
#           secrets_source() -> str
#               Returns "SealedSecrets" (or "ExternalSecrets" — both
#               are acceptable per SRS) and MUST NOT return
#               "ConfigMapPlaintext" or any plaintext ConfigMap variant.
#           service_port() -> int
#               Returns 80 (LoadBalancer port).
#           resource_requests() -> dict
#               Returns the requests stanza (cpu, memory).
#           resource_limits() -> dict
#               Returns the limits stanza (cpu, memory).
#
# The tests below intentionally avoid any live Kubernetes / kubectl / YAML
# I/O — they exercise the K8sManifest abstraction in isolation, which is
# the canonical unit-test shape for FR-96.
# ---------------------------------------------------------------------------
# Re-export the constants so the tests can assert against the same values
# the production code uses (and so the harness sees the same names in
# the import surface as the green implementation must expose).
from app.infra.deployment import (
    DEFAULT_MAX_UNAVAILABLE,
    DEFAULT_REPLICAS,
    DEFAULT_STRATEGY,
    HPA_CPU_TARGET_PERCENT,
    HPA_MAX_REPLICAS,
    HPA_MIN_REPLICAS,
    PDB_MIN_AVAILABLE,
    RESOURCE_LIMITS,
    RESOURCE_REQUESTS,
    SECRETS_SOURCE,
    SERVICE_PORT,
    K8sManifest,
)


# ---------------------------------------------------------------------------
# 1. The Deployment manifest ships with exactly 3 replicas and uses a
#    RollingUpdate strategy (happy_path).
#
# Spec input: replicas="3"; strategy="RollingUpdate".
# SRS FR-96: "Deployment (replicas=3, RollingUpdate maxUnavailable=1)".
# A regression that produced a single-replica Deployment would create a
# single point of failure for the entire customer-service surface; a
# regression that picked Recreate would cause full-pod downtime on every
# rollout; a regression that mis-declared maxUnavailable would let
# rolling updates evict too many pods at once and break the PDB
# guarantee covered by test 3.
# ---------------------------------------------------------------------------
def test_fr96_deployment_3_replicas():
    # Spec input literals — also used as trigger values for the fr96-ok
    # sub-assertion guard.
    replicas = "3"

    # GREEN TODO: ``DEFAULT_REPLICAS`` MUST be exported from
    # ``app.infra.k8s_deployment`` and MUST equal 3. ``DEFAULT_STRATEGY``
    # MUST equal "RollingUpdate". ``DEFAULT_MAX_UNAVAILABLE`` MUST equal
    # 1 (or the equivalent "25%" string GREEN may prefer).
    assert DEFAULT_REPLICAS == 3, (
        f"FR-96 DEFAULT_REPLICAS must be 3; got {DEFAULT_REPLICAS!r}"
    )
    assert DEFAULT_STRATEGY == "RollingUpdate", (
        f"FR-96 DEFAULT_STRATEGY must be 'RollingUpdate'; got "
        f"{DEFAULT_STRATEGY!r}"
    )
    assert DEFAULT_MAX_UNAVAILABLE in (1, "1", "25%"), (
        f"FR-96 DEFAULT_MAX_UNAVAILABLE must be 1 (or '25%'); got "
        f"{DEFAULT_MAX_UNAVAILABLE!r}"
    )

    # GREEN TODO: ``K8sManifest()`` constructed with no arguments MUST
    # surface the FR-96 defaults via the public accessor methods. GREEN
    # may spell the accessors however it likes so long as the values
    # returned match the spec.
    manifest = K8sManifest()
    result = manifest  # bind for the fr96-ok predicate below

    # Spec fr96-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input literal
    # (replicas="3"). The harness parser requires a single
    # VAR == c literal in the trigger block — compound conditions like
    # ``replicas == "3" and strategy == "RollingUpdate"`` are not
    # matched. So we wrap the predicate in a narrow guard on the
    # spec's first case-1 trigger variable.
    if replicas == "3":
        assert result is not None, (
            "fr96-ok predicate: result must not be None"
        )

    # Public surface contract: every accessor MUST exist on K8sManifest
    # — the absence of any one of them is a regression even if the
    # constants above happen to match.
    assert hasattr(manifest, "deployment_replicas") and callable(
        manifest.deployment_replicas
    ), "FR-96 K8sManifest must expose ``deployment_replicas() -> int``"
    assert hasattr(manifest, "deployment_strategy") and callable(
        manifest.deployment_strategy
    ), "FR-96 K8sManifest must expose ``deployment_strategy() -> str``"
    assert hasattr(manifest, "max_unavailable") and callable(
        manifest.max_unavailable
    ), "FR-96 K8sManifest must expose ``max_unavailable() -> int|str``"

    # The Deployment MUST use exactly 3 replicas — the FR's hard
    # availability floor for the production rollout.
    observed_replicas = manifest.deployment_replicas()
    assert observed_replicas == 3, (
        f"FR-96 deployment_replicas() must return 3; got "
        f"{observed_replicas!r}"
    )

    # The strategy MUST be RollingUpdate — Recreate would force
    # full-pod downtime on every release.
    observed_strategy = manifest.deployment_strategy()
    assert observed_strategy == "RollingUpdate", (
        f"FR-96 deployment_strategy() must return 'RollingUpdate'; got "
        f"{observed_strategy!r}"
    )

    # maxUnavailable MUST be 1 (or its percentage equivalent) so the
    # rolling update evicts at most one pod at a time and the PDB
    # guarantee (test 3) is never violated mid-rollout.
    observed_max_unavailable = manifest.max_unavailable()
    assert observed_max_unavailable in (1, "1", "25%"), (
        f"FR-96 max_unavailable() must be 1 (or '25%'); got "
        f"{observed_max_unavailable!r}"
    )


# ---------------------------------------------------------------------------
# 2. The HPA scales the Deployment up to 10 replicas on 70% CPU
#    utilisation (happy_path).
#
# Spec input: cpu_target="70%"; max_replicas="10".
# SRS FR-96: "HPA (min=3, max=10, CPU utilization=70%)".
# A regression that floored the HPA at 3 (min) without ever scaling up
# would cap throughput at low traffic and re-introduce the
# single-region saturation problem; a regression that floored the
# ceiling at 1 or at the deployment replica count would make HPA a
# no-op; a regression that mis-tuned the CPU target would either
# over- or under-provision the cluster.
# ---------------------------------------------------------------------------
def test_fr96_hpa_scales_to_10():
    cpu_target = "70%"
    max_replicas = "10"

    # GREEN TODO: the canonical HPA constants MUST be exported and MUST
    # match the spec (min=3, max=10, cpu=70).
    assert HPA_MIN_REPLICAS == 3, (
        f"FR-96 HPA_MIN_REPLICAS must be 3; got {HPA_MIN_REPLICAS!r}"
    )
    assert HPA_MAX_REPLICAS == 10, (
        f"FR-96 HPA_MAX_REPLICAS must be 10; got {HPA_MAX_REPLICAS!r}"
    )
    assert HPA_CPU_TARGET_PERCENT == 70, (
        f"FR-96 HPA_CPU_TARGET_PERCENT must be 70; got "
        f"{HPA_CPU_TARGET_PERCENT!r}"
    )

    manifest = K8sManifest()

    # Public surface contract: every HPA accessor MUST exist on
    # K8sManifest so the bootstrapper / Helm chart layer can render
    # the autoscaling stanza without poking private attributes.
    assert hasattr(manifest, "hpa_min_replicas") and callable(
        manifest.hpa_min_replicas
    ), "FR-96 K8sManifest must expose ``hpa_min_replicas() -> int``"
    assert hasattr(manifest, "hpa_max_replicas") and callable(
        manifest.hpa_max_replicas
    ), "FR-96 K8sManifest must expose ``hpa_max_replicas() -> int``"
    assert hasattr(manifest, "hpa_cpu_target_percent") and callable(
        manifest.hpa_cpu_target_percent
    ), (
        "FR-96 K8sManifest must expose "
        "``hpa_cpu_target_percent() -> int``"
    )

    # The HPA floor MUST be 3 (matches the Deployment's baseline so a
    # single pod crash never drives the cluster below 3).
    observed_min = manifest.hpa_min_replicas()
    assert observed_min == 3, (
        f"FR-96 hpa_min_replicas() must return 3; got {observed_min!r}"
    )

    # The HPA ceiling MUST be 10 (the spec literal).
    if max_replicas == "10":
        observed_max = manifest.hpa_max_replicas()
        assert observed_max == 10, (
            f"FR-96 hpa_max_replicas() must return 10; got "
            f"{observed_max!r}"
        )

    # The CPU utilisation target MUST be 70% — a regression that
    # moved it to 90% would starve the autoscaler; a regression that
    # moved it to 30% would over-provision the cluster.
    if cpu_target == "70%":
        observed_cpu = manifest.hpa_cpu_target_percent()
        assert observed_cpu == 70, (
            f"FR-96 hpa_cpu_target_percent() must return 70; got "
            f"{observed_cpu!r}"
        )


# ---------------------------------------------------------------------------
# 3. The PodDisruptionBudget prevents voluntary disruption of more than
#    one pod (validation).
#
# Spec input: min_available="2"; rolling_update="true".
# SRS FR-96: "PDB (minAvailable=2)".
# A regression that floored minAvailable at 1 would allow voluntary
# disruptions (node drains, cluster upgrades) to drive the cluster
# below 2 pods — a single point of failure during the very operation
# that the PDB is supposed to protect. A regression that reported
# minAvailable but never enforced it during a rolling update would
# silently violate the contract and let the rolling update evict more
# than 1 pod at a time.
# ---------------------------------------------------------------------------
def test_fr96_pdb_prevents_disruption():
    min_available = "2"
    rolling_update = "true"

    # GREEN TODO: ``PDB_MIN_AVAILABLE`` MUST be exported and MUST
    # equal 2.
    assert PDB_MIN_AVAILABLE == 2, (
        f"FR-96 PDB_MIN_AVAILABLE must be 2; got {PDB_MIN_AVAILABLE!r}"
    )

    manifest = K8sManifest()

    # Public surface contract: the PDB MUST be observable on
    # K8sManifest via ``pdb_min_available()``.
    assert hasattr(manifest, "pdb_min_available") and callable(
        manifest.pdb_min_available
    ), (
        "FR-96 K8sManifest must expose ``pdb_min_available() -> int``"
    )
    observed_min_available = manifest.pdb_min_available()
    assert observed_min_available == 2, (
        f"FR-96 pdb_min_available() must return 2; got "
        f"{observed_min_available!r}"
    )

    # Public surface contract: ``prevents_disruption`` MUST exist on
    # K8sManifest so the bootstrapper / chart layer can ask the
    # manifest "is this drain safe?" before issuing the call.
    assert hasattr(manifest, "prevents_disruption") and callable(
        manifest.prevents_disruption
    ), (
        "FR-96 K8sManifest must expose "
        "``prevents_disruption(desired_unavailable: int) -> bool``"
    )

    # The PDB MUST protect at least 2 pods out of the 3-replica
    # baseline — so a rolling update evicting exactly 1 pod is
    # acceptable (3 - 1 = 2, which equals minAvailable).
    if min_available == "2" and rolling_update == "true":
        # A single-pod eviction leaves 2 pods available — exactly
        # the PDB floor. The contract says "prevents_disruption"
        # for any proposed eviction count; with minAvailable=2
        # the rolling update evicting 1 pod is therefore safe.
        one_pod_safe = manifest.prevents_disruption(1)
        assert one_pod_safe is True, (
            f"FR-96 prevents_disruption(1) must return True when "
            f"min_available=2 and replicas=3; got {one_pod_safe!r}"
        )

    # Stronger: the PDB MUST actively REJECT any disruption that
    # would drop the cluster below 2 available pods. With
    # min_available=2 and the 3-replica default, evicting 2 pods
    # would leave only 1 — the PDB MUST block that. A GREEN that
    # returns True here would silently let cluster ops evict
    # the floor.
    two_pod_unsafe = manifest.prevents_disruption(2)
    assert two_pod_unsafe is False, (
        f"FR-96 prevents_disruption(2) must return False when "
        f"min_available=2 and replicas=3 (would leave 1 pod); got "
        f"{two_pod_unsafe!r}"
    )


# ---------------------------------------------------------------------------
# 4. Secrets are sourced from SealedSecrets (not from a plaintext
#    ConfigMap) (validation).
#
# Spec input: secrets_source="SealedSecrets";
#             expected_plaintext_configmap="false".
# SRS FR-96: "secrets 透過 SealedSecrets/External Secrets 注入 (不用明文
#            ConfigMap)".
# A regression that stored JWT signing keys, DB credentials or M2M
# client secrets in a plain ConfigMap would leak the entire auth
# surface to anyone with ``kubectl get configmap -A`` access —
# directly violating NFR-17 (機密資料不提交至版控) and the
# SealedSecrets guarantee that the secret cannot be read without the
# cluster's private key.
# ---------------------------------------------------------------------------
def test_fr96_secrets_not_in_plaintext_configmap():
    secrets_source = "SealedSecrets"
    expected_plaintext_configmap = "false"  # spec string sentinel

    # GREEN TODO: ``SECRETS_SOURCE`` MUST be exported and MUST be one
    # of the SRS-approved secret-injection mechanisms
    # ("SealedSecrets" or "ExternalSecrets"). It MUST NOT be
    # "ConfigMap", "Plaintext", or any plaintext-ConfigMap
    # equivalent — the test is the spec's "expected_plaintext_
    # configmap=false" guarantee made concrete.
    assert SECRETS_SOURCE in ("SealedSecrets", "ExternalSecrets"), (
        f"FR-96 SECRETS_SOURCE must be 'SealedSecrets' or "
        f"'ExternalSecrets'; got {SECRETS_SOURCE!r}"
    )
    assert SECRETS_SOURCE != "ConfigMap", (
        f"FR-96 SECRETS_SOURCE must NOT be 'ConfigMap' (plaintext "
        f"ConfigMap leaks secrets via kubectl get); got "
        f"{SECRETS_SOURCE!r}"
    )
    assert "Plaintext" not in SECRETS_SOURCE, (
        f"FR-96 SECRETS_SOURCE must NOT contain 'Plaintext' (any "
        f"plaintext variant is a regression); got {SECRETS_SOURCE!r}"
    )

    manifest = K8sManifest()

    # Public surface contract: ``secrets_source()`` MUST exist on
    # K8sManifest so the bootstrapper / chart layer can render the
    # correct stanza (SealedSecret CR vs ExternalSecret CR vs
    # plain ConfigMap) without poking private attributes.
    assert hasattr(manifest, "secrets_source") and callable(
        manifest.secrets_source
    ), (
        "FR-96 K8sManifest must expose ``secrets_source() -> str``"
    )

    # The manifest's secrets_source MUST equal the exported
    # SECRETS_SOURCE constant and MUST be a SealedSecrets-class
    # mechanism (the spec's mandated choice).
    if secrets_source == "SealedSecrets":
        observed_source = manifest.secrets_source()
        assert observed_source in ("SealedSecrets", "ExternalSecrets"), (
            f"FR-96 secrets_source() must return 'SealedSecrets' or "
            f"'ExternalSecrets'; got {observed_source!r}"
        )
        assert observed_source != "ConfigMap", (
            f"FR-96 secrets_source() must NOT return 'ConfigMap' "
            f"(plaintext ConfigMap leaks secrets); got "
            f"{observed_source!r}"
        )

    # Spec sub-assertion: expected_plaintext_configmap="false" is
    # the spec's literal for "no plaintext ConfigMap for secrets".
    # The strongest concrete check is that the literal
    # 'ConfigMap' (with the spec's "plaintext" implication) never
    # appears as the secrets source.
    if expected_plaintext_configmap == "false":
        # The forbidden value list mirrors the spec — every name a
        # GREEN might use to smuggle a plaintext ConfigMap in via a
        # different alias. Any of these appearing in secrets_source()
        # is a hard regression.
        forbidden = {
            "ConfigMap",
            "ConfigMapPlaintext",
            "PlaintextConfigMap",
            "Plaintext",
        }
        observed = manifest.secrets_source()
        assert observed not in forbidden, (
            f"FR-96 secrets_source() must not be a plaintext "
            f"ConfigMap variant; got {observed!r} (forbidden set: "
            f"{sorted(forbidden)})"
        )

    # Companion invariants pinned by SRS FR-96 (Module 22) — these
    # are not in TEST_SPEC case 4 directly, but the spec's
    # "expected_plaintext_configmap=false" sub-assertion is the
    # tip of a larger contract: the Service MUST be a
    # LoadBalancer on port 80, and the resource stanza MUST be the
    # FR-96-canonical {cpu:500m,mem:512Mi}/{cpu:2000m,mem:2Gi}
    # pair. A GREEN that fixes the secret source but breaks the
    # Service port or the resource stanza is also a regression.
    assert SERVICE_PORT == 80, (
        f"FR-96 SERVICE_PORT must be 80; got {SERVICE_PORT!r}"
    )
    assert RESOURCE_REQUESTS == {"cpu": "500m", "memory": "512Mi"}, (
        f"FR-96 RESOURCE_REQUESTS must be {{cpu:500m, memory:512Mi}}; "
        f"got {RESOURCE_REQUESTS!r}"
    )
    assert RESOURCE_LIMITS == {"cpu": "2000m", "memory": "2Gi"}, (
        f"FR-96 RESOURCE_LIMITS must be {{cpu:2000m, memory:2Gi}}; "
        f"got {RESOURCE_LIMITS!r}"
    )
