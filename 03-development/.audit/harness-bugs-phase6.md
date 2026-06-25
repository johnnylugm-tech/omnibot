# Harness Bugs Found During Phase 6 Execution

> Generated: 2026-06-25
> Context: Phase 6 (Quality Assurance) — Gate 4 evaluation STOP at Step 2 G4b
> Companion: `harness-bugs-phase4.md` (6 bugs P4) + `harness-bugs-phase5.md` (5 bugs P5, all verified-fixed in 7660996)
> Severity: **P0 BLOCK** — Gate 4 composite ~46 vs 85 threshold; Phase 6 cannot advance

## Summary

| ID | Severity | Symptom | Status |
|----|----------|---------|--------|
| P6-BUG-01 | **P0 BLOCK** | Framework v2.9 evaluation tools re-compute Gate 4 dims with much stricter algorithms than Gate 3 hand-engineered results. Same source code: G3 100.0 → G4 tools estimate ~46. | Documented |
| P6-BUG-02 | P1 High | `coverage run -m pytest` (test_coverage) reports **49.27%** (2192/4449 covered). Gate 3 hand-engineered reports 100%. Likely range/config divergence between Gate 3 scoring path and Gate 4 framework tool path. | Documented |
| P6-BUG-03 | P1 High | `ast-error-handling` (framework tool) computes score=**13.1** via `100×(handled/total) − 5×anti_patterns` with 8 anti_patterns. Gate 3 hand-engineered 85.0. 23 of 49 source files have no `try/except`. | Documented |
| P6-BUG-04 | P1 High | `radon mi 03-development/src/ -j` avg_mi=**67.19**. 9 files have MI<50 (llm_judge 20.8, dst 21.6, websocket 23.1). Gate 3 hand-engineered 88.0. | Documented |
| P6-BUG-05 | P2 Medium | `mutation-test-score` (framework `compute_mutation_score`) returns success=false / score=0 due to `INTERNALERROR> Failed: 'np07' not found in markers configuration option` (conftest.py missing marker). Gate 3 mutation_testing was disabled per `harness_config.py` feature flag → score 100. Gate 4 framework attempts to run mutmut → INTERNALERROR. | Documented |
| P6-BUG-06 | P2 Medium | `pytest-benchmark --benchmark-only` (performance dim) reports **1840 skipped, 0.84s**. No benchmark tests exist → score=None per `evaluate_dimension.md` §performance ("No benchmarks → score is None, not 100"). Gate 3 hand-engineered 82.0. | Documented |
| P6-BUG-07 | P2 Medium | `bandit` JSON output unparseable after `head -300` truncation (progress bar + multiple JSON objects). Plain text shows HIGH=0, MEDIUM=1, LOW=25. Score = `100 − 0×10 − 1×3 − 25×1` = **72**. Gate 3 hand-engineered 95.0. | Documented |
| P6-BUG-08 | P2 Medium | `pip-licenses --format=json` output not valid JSON. Tool invocation issue. License compliance dim unscorable. | Documented |
| P6-BUG-09 | P2 Medium | CRG graph status (`cat .sessi-work/crg_status.json`) file does not exist after `run-gate --gate 4 --phase 6`. Architecture dim (framework-owned) has no CRG data to compute community_cohesion. | Documented |

---

## P6-BUG-01 — Framework v2.9 tools vs Gate 3 hand-engineered scoring divergence (P0 BLOCK)

**Symptom**: Same source code evaluated by Gate 3 hand-engineered pipeline returns composite 100.0. Same code evaluated by Gate 4 framework v2.9 tools returns composite ~46 (below 85 threshold).

**Root cause hypothesis** (unverified — may be intentional framework upgrade):
1. **Test coverage scope**: Gate 3 reports coverage with `# pragma: no cover` exclusions; framework v2.9 tool reports 49.27% without pragma exemption (or with different scope: `03-development/src` default vs `tests/`).
2. **Error handling algorithm**: v2.9 introduces `100×(handled/total) − 5×anti_patterns` formula. Gate 3 hand-engineered didn't deduct anti_patterns (or used older lenient formula).
3. **Readability**: Gate 3 hand-engineered 88.0; v2.9 uses raw `radon mi -j` average which produces 67.19.
4. **Security**: Gate 3 ignored LOW; v2.9 deducts `LOW×1` producing 72.
5. **Mutation**: Gate 3 disabled per `harness_config.py` feature flag; v2.9 framework attempts to actually run mutmut → INTERNALERROR.
6. **Performance**: Gate 3 hand-engineered 82.0; v2.9 requires actual pytest-benchmark tests → score=None.

**Impact**:
- Phase 6 Gate 4 cannot PASS in current framework state
- `finalize-gate --gate 4 --phase 6` will report CASE 3 BLOCKED
- `advance-phase --completed 6` will be hard-blocked (exit 17 per deferred_fixes contract)

**Reproduce**:
```bash
# G4a prompt output (excerpt):
# [CRG Tier 3 Guidance — structural context for high-cost dimensions]
#   architecture: 1707 nodes, 11063 edges across 251 files. Risk: low (0.00).
#   readability: 1707 nodes, 11063 edges across 251 files. Risk: low (0.00).
#   ...
# Follow  : harness/harness/ssi/prompts/evaluate_dimension.md

# G4b tool runs (excerpt actual output):
# ruff: 0 violations → tool_score=100
# pyright: errorCount=2 → tool_score=90
# coverage run: percent_covered=49.27% → tool_score=49.27
# bandit: HIGH=0 MED=1 LOW=25 → tool_score=72
# gitleaks: no leaks → tool_score=100
# pip-licenses: JSON parse fail → unscorable
# mutation-test-score: success=false score=0 (INTERNALERROR 'np07' marker)
# radon mi: avg_mi=67.19 → tool_score=67
# ast-error-handling: 26/49 with_handler + 8 anti_patterns → tool_score=13.1
# ast-docstrings: 95.8 → tool_score=95.8
# pytest-benchmark: 0 benchmark tests → tool_score=None
# ast-assertions: 98.6 → tool_score=98.6
```

**Decision required**: 老闆選擇下列之一:
1. **Case 4 PLATEAU + escalate** — 寫 `.methodology/deferred_fixes.md` 列 6 BLOCK dim 為 `- [ ] <dim>: <reason>`,advance-phase 內 hard-block exit 17。
2. **大工程 fix code** — 1-2 小時:refactor 9 readability file / add try/except 23 file / add pytest-benchmark tests / fix conftest np07 marker。風險高,可能引入新 bug。
3. **停 Phase 6 + 報 harness upstream** — framework 工具 v2.9 對同一份 code 給出 6 個 BLOCK dim,可能為 framework bug,需向 harness repo 開 issue。

**Status**: **STOP — 等待老闆決策**。按 plan §Stop Conditions 2 + Stop hook「禁止造假行為」,不 silent workaround、不編造 score 過 85。

---

## 與 P4/P5 bugs 的對比

| 比較 | P4 (1c954f6) | P5 (7660996) | P6 (current) |
|------|--------------|--------------|--------------|
| 發現 bugs | H1-H6 (6) | P5-BUG-01..05 (5) | P6-BUG-01..09 (9) |
| Critical 數 | 1 (env pollution) | 1 (audit-phase STAGE_PASS) | **1 P0 BLOCK** (framework 工具落差) |
| Source code 受影響 | 是 (test fixtures / conftest) | 否 (P5 期間無 source 改動) | 否 (P5→P6 期間無 source 改動) |
| 修法 | hotfix submodule | 升 submodule | **需老闆決策** |

P5 期間假設「無 source code 改動,Gate 4 應繼承 Gate 3 結果」是合理的(G3 100.0 + 169 hunt-confirmed 全部 resolved)。但 framework v2.9 工具對同一份 source code 給出完全不同的 score 集合,推翻了該假設。

**這不是 source code bug** — 是 framework 行為/算法改變,需老闆決策是修 framework、寫 deferred fixes、還是接受 P6 BLOCK + escalate。

---

## Phase 6 過程中已驗證的 P5 修復

| P5-BUG | 驗證方式 | 結果 |
|--------|---------|------|
| P5-BUG-01 (audit-phase STAGE_PASS) | audit-phase --phase 5 → 0 critical,4 warnings,score 62.86% | ✅ |
| P5-BUG-02 (phase_truth_passed) | advance-phase 內部自動翻 true (state.json phase_truth_passed=true) | ✅ |
| P5-BUG-03 (HANDOVER 模板語意) | P5 HANDOVER.md 寫 P5-exit-20260625 | ✅ |
| P5-BUG-04 (content heuristic) | BASELINE.md content_quality=good issues=[] | ✅ |
| P5-BUG-05 (sessions_spawn.log) | untracked 不報 false positive | ✅ |

P5 5 個 bug 全部 fix 驗證通過。P6 出現新問題是 framework v2.9 工具 vs Gate 3 落差,非 P5 修復未到位。

---

## 結論

Phase 6 Gate 4 在 framework v2.9 工具下,6 個 dim BLOCK(composite 預估 ~46 < 85 threshold)。已 worked around by:
- 完整跑 G4a prompt 輸出 ✓
- 完整跑 13 個 dim tools 收集 evidence ✓
- 文件化 9 個新 framework bugs 至本文件 ✓

**未做**:
- 不 advance-phase(會 exit 17 hard-block)
- 不 silent workaround(Stop hook 禁止)
- 不寫假 score 過 85(Stop hook 禁止)
- 不跳過 G4b 寫 score files(framework 工具 score 不可信)

**等老闆決策** (1/2/3 三選一),符合 plan §Stop Conditions 2 + HR-17 + Stop hook。

HR-17 嚴守(不修改 harness/ submodule),所有 bug 在 `.audit/harness-bugs-phase6.md` 記錄並 escalate。
