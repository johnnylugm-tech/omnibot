"""[NFR-30] HPA autoscaling — min=3, max=10, CPU target=70%.

Spec source: 04-testing/TEST_PLAN.md §7 NFR mapping table
NFR source: NFR-30 — scalability | app.infra.deployment | HPA min=3 max=10 CPU=70%
"""

from __future__ import annotations

from app.infra.deployment import HPA_CPU_TARGET_PERCENT, HPA_MAX_REPLICAS, HPA_MIN_REPLICAS


def test_nfr30_hpa_constants_must_match_spec() -> None:
    """NFR-30: HPA min=3, max=10, CPU target=70%."""
    assert HPA_MIN_REPLICAS == 3, f"NFR-30 expects HPA min=3, got {HPA_MIN_REPLICAS}"
    assert HPA_MAX_REPLICAS == 10, f"NFR-30 expects HPA max=10, got {HPA_MAX_REPLICAS}"
    assert HPA_CPU_TARGET_PERCENT == 70, f"NFR-30 expects CPU target=70%, got {HPA_CPU_TARGET_PERCENT}"


def test_nfr30_hpa_scale_test_within_bounds() -> None:
    """NFR-30: HPA scale test — replicas must stay within [3, 10]."""
    from app.infra.deployment import K8sManifest

    manifest = K8sManifest()
    r = manifest.hpa_scale_test(HPA_CPU_TARGET_PERCENT - 1)
    assert r.replicas == HPA_MIN_REPLICAS, f"Below target CPU → min replicas, got {r.replicas}"

    r2 = manifest.hpa_scale_test(HPA_CPU_TARGET_PERCENT + 50)
    assert r2.replicas <= HPA_MAX_REPLICAS, f"Above target CPU → must not exceed max={HPA_MAX_REPLICAS}, got {r2.replicas}"
