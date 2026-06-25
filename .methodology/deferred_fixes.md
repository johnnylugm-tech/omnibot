# Phase 6 — Deferred Fixes (Gate 4 framework-tool BLOCK)

> Generated: 2026-06-25
> Phase 6 Gate 4 case 3 BLOCKED → advance-phase hard-blocked exit 17
> Per plan §G4b step 7 + §G4c CASE 4 PLATEAU
> All 6 dim items MUST be resolved (mark `- [x]`) before advance-phase can succeed.

## Hard-Blocked Items

- [ ] **test_coverage** (tool=49.27%, threshold=80): framework `coverage run -m pytest` reports 2192/4449 covered (49.27%) for `03-development/src`. Gate 3 hand-engineered reported 100% (with `# pragma: no cover` exemptions). Reason: framework v2.9 tool scope differs from Gate 3 scoring path (likely pragma exemption not applied, or scope is `03-development/src` default rather than `tests/`). Remediation options: (a) add `# pragma: no cover` to genuinely untestable lines and verify coverage reruns ≥80%; (b) re-baseline Gate 3 vs Gate 4 framework tools to identify scope divergence; (c) escalate to harness upstream if framework tool divergence is the root cause.

- [ ] **readability** (tool=67.19 avg_mi, threshold=80): `radon mi 03-development/src/ -j` avg_mi=67.19. 9 files have MI<50: `app/services/llm_judge.py` (20.8), `app/core/dst.py` (21.6), `app/api/websocket.py` (23.1), `app/services/ab_testing.py` (28.3), `app/core/knowledge.py` (30.5), `app/infra/security.py` (31.8), `app/core/paladin.py` (37.1), `app/core/emotion.py` (40.9), `app/infra/jobs.py` (46.7), `app/admin/webui.py` (47.0). Gate 3 hand-engineered reported 88.0. Remediation: refactor 9 low-MI files (split large functions, reduce cyclomatic complexity, extract helpers).

- [ ] **error_handling** (tool=13.1, threshold=80 / NFR floor 99.95): framework `ast-error-handling` reports 26/49 source files with `try/except` and 8 anti_patterns (`except BaseException` × 5 + `broad_swallow` × 3 inferred from `100×(26/49) − 5×8 = 13.1`). Gate 3 hand-engineered reported 85.0. Remediation: (a) add `# pragma: no error-handling` to 23 data-model / no-I/O files (eligible for denominator exemption per `evaluate_dimension.md`); (b) replace `except BaseException:` and `except Exception: pass` with narrow typed exceptions; (c) investigate why 8 anti_patterns detected by framework tool.

- [ ] **mutation_testing** (tool=0 INTERNALERROR, threshold=70): framework `mutation-test-score` returns `{"success": false, "score": 0.0}` due to `INTERNALERROR> Failed: 'np07' not found in markers configuration option` (in `03-development/tests/conftest.py:147`). Gate 3 mutation_testing was disabled per `harness_config.py` feature flag → auto-passed at 100. Remediation: (a) add `np07` to `pytest` markers config in `pyproject.toml` or `conftest.py`; (b) re-enable mutation feature flag if intentionally disabled, or (c) escalate as framework tool incompatibility.

- [ ] **security** (tool=72, threshold=80): `bandit -r 03-development/src/` reports HIGH=0, MEDIUM=1, LOW=25 (mostly `B404: subprocess` import warnings). Score = `100 − 0×10 − 1×3 − 25×1 = 72`. Gate 3 hand-engineered reported 95.0. Remediation: (a) add `# nosec BXXX` comments to legitimate LOW findings (e.g., subprocess imports in `app/services/media.py`); (b) investigate 1 MEDIUM finding; (c) escalate if framework tool v2.9 deducts LOW in a way that breaks projects legitimately using subprocess/requests.

- [ ] **performance** (tool=None, threshold=75): `pytest --benchmark-only` reports `1840 skipped, 1 warning in 0.84s` — no benchmark tests exist. `evaluate_dimension.md` §performance: "No benchmarks → score is None, not 100". Gate 3 hand-engineered reported 82.0. Remediation: (a) add `pytest-benchmark` micro-benchmarks to `03-development/tests/test_perf.py` for high-risk modules (NFR-01..09 mapping); (b) target latencies from `quality_manifest.json::nfr_traceability` (NFR-01 p95<1000ms, NFR-02 p95<5ms, etc.).

- [ ] **license_compliance** (tool=fail, threshold=100): `pip-licenses --format=json` output not valid JSON (likely output format flag mismatch). Remediation: (a) verify `pip-licenses` invocation in venv (`pip-licenses --format=json` should work, or use `--format=json-license-finder` alternative); (b) use `scancode-toolkit` per `evaluate_dimension.md` as alternative.

- [ ] **architecture** (framework-owned, not run): `.sessi-work/crg_status.json` does not exist after `run-gate --gate 4 --phase 6`. Architecture dim requires CRG graph (1707 nodes / 11063 edges from Gate 3 cache) for `community_cohesion` computation. Remediation: (a) rebuild CRG graph via `code-review-graph build` MCP tool; (b) verify `crg-arch-check` is the correct CLI command (replaces non-existent `crg-status`).

## Framework Tool Divergence — P6-BUG-01 (P0)

Same source code, Gate 3 hand-engineered 100.0 → Gate 4 framework tools ~46. Root cause unclear without harness upstream diagnosis. **Recommend escalation to harness-methodology repo** for v2.9 → v2.12 (or current) tool scoring parity check. See `.audit/harness-bugs-phase6.md` for full analysis.

## How to Resolve

1. Mark each `- [ ]` to `- [x]` after fix is verified by re-running the relevant tool.
2. Re-run `.venv/bin/python harness_cli.py spec-coverage-check --project . --threshold 90.0` to confirm all overrides.
3. Re-run `.venv/bin/python harness_cli.py finalize-gate --gate 4 --phase 6 --project .` — should produce CASE 1 PASS instead of CASE 3 BLOCKED.
4. Re-run `.venv/bin/python harness_cli.py advance-phase --completed 6 --project .` — should succeed (no exit 17).

**Until all checkboxes are `- [x]`, advance-phase will hard-block with exit 17.**
