from __future__ import annotations
"""TDD-RED: failing tests for FR-106 — k6 load tests (smoke/load/stress/spike).

Spec source: 02-architecture/TEST_SPEC.md (FR-106)
SRS source : SRS.md Module 27 (負載測試)
SAD mapping: tests.load — "k6 load tests (FR-106)"

Acceptance criteria (from SRS FR-106 / TEST_SPEC.md):
    - Smoke: 10 VUs, 1m baseline
    - Load: 200 VUs, 10m, p95 < 1000ms, error rate < 1%
    - Stress: 500→2000→3000→0 VUs phased, no crash
    - Spike: 10s spike to 3000 VUs, recovery normal
    - Test case weights: FAQ(40%), semantic(40%), complex(10%), emotion(10%)
    - Target: 2000 TPS sustained

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-106 resides in ``tests.load`` per SAD.md §2.2 line 854.
#
# The GREEN contract pinned by this spec:
#
#   ``K6Runner`` — orchestrates k6 load test scenarios programmatically.
#     - __init__(k6_binary: str = "k6", work_dir: str | None = None)
#     - run_smoke(*, vus: int, duration_sec: int) -> dict
#         Returns {"passed": bool, "baseline_p95_ms": float, ...}
#     - run_load(*, vus: int, duration_sec: int,
#           p95_limit_ms: int, error_rate_limit: float) -> dict
#         Returns {"passed": bool, "p95_ms": float, "error_rate": float, ...}
#     - run_stress(*, stages: list[dict]) -> dict
#         stages = [{"vus": N, "duration_sec": S}, ...]
#         Returns {"passed": bool, "crashed": bool, "max_tps": float, ...}
#     - run_spike(*, spike_vus: int, spike_duration_sec: int,
#           recovery_threshold_ms: int) -> dict
#         Returns {"passed": bool, "recovered": bool,
#                  "recovery_time_ms": float, ...}
#
#   ``K6Config`` — immutable configuration for a k6 scenario.
#     - Fields: vus, duration_sec, thresholds, test_case_weights
#     - test_case_weights MUST sum to 1.0
#
#   ``DEFAULT_TEST_WEIGHTS`` — module-level constant:
#     {"faq": 0.40, "semantic": 0.40, "complex": 0.10, "emotion": 0.10}
#
#   ``STRESS_STAGES`` — module-level constant for the standard stress profile:
#     [{"vus": 500, "duration_sec": 120},
#      {"vus": 2000, "duration_sec": 120},
#      {"vus": 3000, "duration_sec": 120},
#      {"vus": 0, "duration_sec": 60}]
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because
# ``tests.load`` does not exist yet — that is the valid RED signal.
# ---------------------------------------------------------------------------
from tests.load import (  # noqa: F401 -- RED: GREEN owns the names
    DEFAULT_TEST_WEIGHTS,
    STRESS_STAGES,
    K6Config,
    K6Runner,
)

# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================


def test_fr106_smoke_10vu_baseline():
    """Smoke test: 10 VUs for 1 minute establishes a baseline.

    Inputs (from TEST_SPEC): vus="10"; duration="1m"
    Type: happy_path (Q1)
    """
    runner = K6Runner()

    result = runner.run_smoke(vus=10, duration_sec=60)

    # Must return a result dictionary
    assert result is not None, "run_smoke() must return a result dict"
    assert isinstance(result, dict), "result must be a dict"

    # Baseline must be captured
    assert "passed" in result, "result must contain 'passed' field"
    assert "baseline_p95_ms" in result, (
        "result must contain 'baseline_p95_ms' baseline metric"
    )

    # Smoke test with valid config should pass
    assert result["passed"] is True, (
        f"Smoke test must pass with 10 VUs, got passed={result.get('passed')}"
    )
    assert result["baseline_p95_ms"] >= 0, (
        "Baseline p95 must be non-negative"
    )


def test_fr106_load_p95_under_1000ms():
    """Load test: 200 VUs, 10 min, p95 latency must stay under 1000 ms.

    Inputs (from TEST_SPEC): vus="200"; duration="10m"; p95_limit="1000ms"
    Type: nfr_pattern (Q6/NP-06)
    """
    runner = K6Runner()

    result = runner.run_load(
        vus=200,
        duration_sec=600,
        p95_limit_ms=1000,
        error_rate_limit=0.01,
    )

    assert result is not None, "run_load() must return a result dict"
    assert isinstance(result, dict), "result must be a dict"

    # p95 must be reported
    assert "p95_ms" in result, "result must contain 'p95_ms'"
    assert isinstance(result["p95_ms"], (int, float)), (
        "p95_ms must be numeric"
    )

    # Under threshold, load test must pass
    if result["p95_ms"] < 1000:
        assert result["passed"] is True, (
            f"p95={result['p95_ms']}ms < 1000ms → load test must pass"
        )
    else:
        # p95 at or above threshold → must fail
        assert result["passed"] is False, (
            f"p95={result['p95_ms']}ms >= 1000ms → load test must fail"
        )

    # NP-06 latency SLA check
    assert result["p95_ms"] < 1000, (
        f"NP-06 SLA breach: p95={result['p95_ms']}ms >= 1000ms threshold"
    )


def test_fr106_load_error_rate_below_1pct():
    """Load test: error rate must stay below 1%.

    Inputs (from TEST_SPEC): vus="200"; expected_error_rate="<1%"
    Type: nfr_pattern (Q6/NP-06)
    """
    runner = K6Runner()

    result = runner.run_load(
        vus=200,
        duration_sec=600,
        p95_limit_ms=1000,
        error_rate_limit=0.01,
    )

    assert result is not None, "run_load() must return a result dict"
    assert "error_rate" in result, "result must contain 'error_rate'"

    error_rate = result["error_rate"]
    assert isinstance(error_rate, (int, float)), (
        "error_rate must be numeric"
    )
    assert 0.0 <= error_rate <= 1.0, (
        f"error_rate must be in [0, 1], got {error_rate}"
    )

    # Error rate must be below 1% (0.01)
    assert error_rate < 0.01, (
        f"Error rate {error_rate:.4f} ({error_rate*100:.2f}%) "
        f"must be < 1% (0.01)"
    )

    # Load test must pass when error rate is under threshold
    assert result["passed"] is True, (
        f"Load test must pass when error_rate={error_rate:.4f} < 0.01"
    )


def test_fr106_stress_2000tps_no_crash():
    """Stress test: phased 500→2000→3000→0 VUs, must NOT crash.

    Inputs (from TEST_SPEC): vus_peak="3000"; expected_crash="false"
    Type: nfr_pattern (Q6/NP-06)
    Target: 2000 TPS sustained
    """
    runner = K6Runner()

    result = runner.run_stress(stages=STRESS_STAGES)

    assert result is not None, "run_stress() must return a result dict"
    assert isinstance(result, dict), "result must be a dict"

    # Must NOT crash
    assert "crashed" in result, "result must contain 'crashed' field"
    assert result["crashed"] is False, (
        "Stress test must NOT crash: 500→2000→3000→0 VUs phased ramp"
    )

    # Stress test must pass (system stays up under peak load)
    assert result["passed"] is True, (
        "Stress test must pass: system must survive peak 3000 VUs"
    )

    # Throughput check — must sustain >= 2000 TPS
    assert "max_tps" in result, "result must contain 'max_tps'"
    assert result["max_tps"] >= 2000, (
        f"SRS throughput requirement: max_tps={result['max_tps']} "
        f"must be >= 2000 TPS"
    )


def test_fr106_spike_recovery_normal():
    """Spike test: 10s spike to 3000 VUs, system recovers to normal.

    Inputs (from TEST_SPEC): spike_vus="3000"; spike_duration="10s";
        expected_recovery="true"
    Type: fault_injection (Q5)
    """
    runner = K6Runner()

    result = runner.run_spike(
        spike_vus=3000,
        spike_duration_sec=10,
        recovery_threshold_ms=30000,  # 30s recovery window
    )

    assert result is not None, "run_spike() must return a result dict"
    assert isinstance(result, dict), "result must be a dict"

    # Must report recovery status
    assert "recovered" in result, "result must contain 'recovered' field"
    assert result["recovered"] is True, (
        "System must recover after 10s spike to 3000 VUs"
    )

    # Recovery time must be reported
    assert "recovery_time_ms" in result, (
        "result must contain 'recovery_time_ms'"
    )
    assert isinstance(result["recovery_time_ms"], (int, float)), (
        "recovery_time_ms must be numeric"
    )
    assert result["recovery_time_ms"] >= 0, (
        "recovery_time_ms must be non-negative"
    )

    # Spike test must pass
    assert result["passed"] is True, (
        "Spike recovery test must pass: system recovered to normal"
    )

    # Recovery must be within threshold
    assert result["recovery_time_ms"] <= 30000, (
        f"Recovery time {result['recovery_time_ms']}ms "
        f"exceeds 30s recovery threshold"
    )
