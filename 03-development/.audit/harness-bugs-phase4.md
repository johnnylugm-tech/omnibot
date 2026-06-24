# Harness Bugs Found During Phase 4 Execution

> Generated: 2026-06-25
> Context: Phase 4 (Testing) → Gate 3 → advance to Phase 5

## H-BUG-01: Phase Truth `check_pytest` — parent env pollution breaks tests

**Severity**: High
**File**: `harness/core/quality_gate/phase_truth_verifier.py:161-167`
**Symptom**: `check_pytest` spawns `pytest` subprocess via `subprocess.run` with default `env=None`, inheriting the parent process environment. When `OMNIBOT_JWT_SECRET` is set in the parent (e.g. from a prior `conftest.py` load), `conftest.setdefault()` is bypassed. The hardcoded JWT in `test_fr58_user_ws_jwt_verified` fails verification → 2 FAILED → Phase Truth drops to 76%.

**Root cause**: `subprocess.run` inherits `os.environ` from parent. The Phase Truth verifier runs after other harness operations that may have loaded Python modules that set env vars via `setdefault`.

**Workaround**: Made `test_fr58_user_ws_jwt_verified` hermetic by adding `monkeypatch.setenv("OMNIBOT_JWT_SECRET", ...)` in the test function signature.

**Status**: Worked around. Harness should either clear known env vars before pytest subprocess, or document that tests must be env-hermetic.

## H-BUG-02: Phase Truth `check_pytest` — XPASS causes exit≠0 → false failure

**Severity**: Medium
**File**: `harness/core/quality_gate/phase_truth_verifier.py:169`
**Symptom**: When tests marked `@pytest.mark.xfail` unexpectedly pass (XPASS), pytest returns exit code 1. `check_pytest` treats any non-zero exit code as failure: `passed = result.returncode == 0`. The `_parse_failure_count` regex correctly counts only `^FAILED\s+` lines (0), but the exit code check overrides — result: "pytest has 0 failure(s)" but score=0.

**Root cause**: Pytest exit code 1 covers both real failures AND XPASS. The harness only checks exit code, not the failure count.

**Workaround**: Removed `@pytest.mark.xfail` from 4 timing-sensitive tests that now pass reliably on Python 3.11+.

**Status**: Worked around. Harness should check `_parse_failure_count > 0` for failure detection, or use `--strict-markers` with `filterwarnings`.

## H-BUG-03: CRG `get_hub_nodes_func` — unexpected keyword arg `min_fan_in`

**Severity**: Low
**File**: `harness/harness_bridge.py` (CRG enrichment path)
**Symptom**: Every `finalize-gate` call prints:
```
[CRG] get_hub_nodes_func unavailable via subprocess: crg_tool_runner get_hub_nodes_func failed (rc=5):
get_hub_nodes_func failed: get_hub_nodes_func() got an unexpected keyword argument 'min_fan_in'
CRG enrichment failed; test_coverage hub-penalty fabrication signal may be dropped.
```

**Root cause**: `crg_tool_runner` passes a `min_fan_in` kwarg that the CRG backend doesn't support.

**Status**: Non-blocking (harness falls back gracefully). Should fix the CRG bridge to match the backend API.

## H-BUG-04: `_update_quality_manifest` — missing `project_root` argument

**Severity**: Low
**File**: `harness/harness_cli.py`
**Symptom**: Every `finalize-gate` call prints:
```
_update_quality_manifest called without project_root; falling back to CWD (...).
Pass project_root explicitly to avoid CWD-rel hazards.
```

**Root cause**: Internal call path doesn't pass `project_root` to `_update_quality_manifest`.

**Status**: Non-blocking (CWD fallback works). Should add explicit `project_root` parameter.

## H-BUG-05: Traceability scanner `FR_TAG_PATTERN` — doesn't handle comma-separated multi-FR

**Severity**: Medium
**File**: `harness/core/traceability/scanner.py:32`
**Symptom**: FR-54, FR-63, FR-93 appeared as "uncoded" in ASPICE traceability check (code_coverage=97.2%, blocking push). Source files contained `[FR-54, FR-55, FR-56]` in module docstrings but the scanner regex `\[FR-(\d+)\]` only matches one FR per bracket pair.

**Root cause**: `FR_TAG_PATTERN = re.compile(r'\[FR-(\d+)\]')` treats brackets as single-match. Multi-FR annotations like `[FR-52, FR-63, FR-64]` produce zero matches because the bracket content is `52, FR-63, FR-64` which doesn't match `\d+`.

**Workaround**: Added standalone `# [FR-54] [FR-55] [FR-56]` comment lines in each source file.

**Proposed fix**: Extend pattern to `\[FR-(\d+)(?:,\s*FR-(\d+))*\]` or add a second pattern `FR-(\d+)` to also match FR tags in comments/docstrings without requiring single-FR-per-bracket.

**Status**: Worked around. Scanner should support the multi-FR format commonly used in module docstrings.

## H-BUG-06: `build-trace-attestation --write` silently overwrites manual edits

**Severity**: Low
**File**: `harness/scripts/build_trace_attestation.py`
**Symptom**: Manual additions to `attestation.json` (e.g., adding FR→code links) are silently overwritten by `build-trace-attestation --write`. The command re-derives the full matrix from source code scanning.

**Root cause**: By design — attestation is meant to be source-derived. But there's no warning when overwriting a file that has manual edits.

**Status**: By design. Should add a `--dry-run` or diff warning when the existing attestation differs from the re-derived matrix.

---

## Non-Bugs (Documented Behavior)

| Item | Explanation |
|------|-------------|
| Gitleaks JWT false positive | `test_fr58.py` hardcoded JWT is a test fixture. Allowlisted via `.gitleaks.toml`. |
| Python 3.9 vs 3.14 `asyncio.TimeoutError` | macOS `python3` is 3.9. Harness correctly uses `sys.executable` (3.14). Manual simulation with wrong Python caused false alarm. |
| `ruff --fix` import reordering | Standard ruff behavior. Configurable via `lint.isort` settings. |
| `audit-phase` score 74% / 57% | Audit checks include C5 (document content depth) and C6 (commit timeline). The scoring weights are conservative by design. |
