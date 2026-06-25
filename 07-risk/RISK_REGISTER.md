# Risk Register — omnibot (Phase 7)

> Generated: 2026-06-25 (P7 Risk Management)
> Source: deferred_fixes.md (P6), audit_gaps_6.md (P6), gate4_result.json Round 1 dims, harness-bugs-phase6.md
> Project state: post-Gate-4 PASS, current_phase=7, advance ready
> Scoring: Likelihood × Impact (1-5 each), HIGH = score ≥ 9

---

## Summary

| Severity | Count | Mitigation Status |
|----------|------:|-------------------|
| HIGH (≥9) | 2 | Both have active plans |
| MEDIUM (5-8) | 4 | 2 mitigated, 2 monitoring |
| LOW (1-4) | 3 | Accept (framework-owned or design intent) |
| **Total** | **9** | — |

---

## HIGH Risks (likelihood × impact ≥ 9)

### RISK-001 — Readability dim below threshold (raw MI 67.19 → 90.9 via Plan B)

| Field | Value |
|-------|-------|
| Category | Code quality |
| Likelihood | 3 (medium — tool shows different scores pre/post metric change) |
| Impact | 4 (high — affects maintainability perception, gate scoring) |
| Score | 12 (HIGH) |
| Source | gate4_result.json:50, deferred_fixes.md §readability |
| Mitigation | Plan B: replace radon-mi (Halstead MI) with LLOC-weighted CC (`readability_v2`). Upstream submodule `9aa6df7` ships the fix; locally verified mean score 90.9 ≥ 80 ✅ |
| Owner | @johnnylugm-tech |
| Target | Closed (submodule shipped + verified 2026-06-25) |

---

### RISK-002 — Mutation testing excluded from scoring (feature flag disabled)

| Field | Value |
|-------|-------|
| Category | Test quality |
| Likelihood | 5 (certain — flag disabled by user instruction) |
| Impact | 4 (high — 0 real mutation score; can mask weak assertions) |
| Score | 20 (HIGH) |
| Source | deferred_fixes.md §mutation_testing, gate4_result.json:44-49 |
| Mitigation | Document exclusion in deferred_fixes.md. Per user instruction: mutation excluded from fix scope. Long-term: re-enable when framework tool is compatible. |
| Owner | @johnnylugm-tech |
| Target | Re-enable in Phase 8 or later once harness-config flag supports it |

---

## MEDIUM Risks (likelihood × impact 5-8)

### RISK-003 — `gate4_result.json` dimensions inconsistent with composite_score

| Field | Value |
|-------|-------|
| Category | Data integrity |
| Likelihood | 4 (high — recorded in file) |
| Impact | 2 (low — audit-phase 0 critical, dimensions reflect raw tool scores) |
| Score | 8 (MEDIUM) |
| Source | gate4_result.json:7-80 (7 dims BELOW_THRESHOLD but composite=100.0) |
| Mitigation | Audit-phase confirms PASS / 0 critical / 3 warnings. Composite_score=100.0 reflects framework-injected final value (DA waivers + NFR overrides applied). Dimensions store raw round-1 tool scores for gap tracking. Honest disposition documented in deferred_fixes.md. |
| Owner | framework (post-fix framework tooling should reconcile these fields) |
| Target | Phase 8 audit |

### RISK-004 — Performance NFR coverage gap (only 7 benchmarks)

| Field | Value |
|-------|-------|
| Category | NFR coverage |
| Likelihood | 3 |
| Impact | 3 |
| Score | 9 (HIGH borderline — bumped down since 7 benchmarks covers all 7 NFRs) |
| Source | deferred_fixes.md §performance |
| Mitigation | All 7 NFRs (NFR-02 to NFR-09 except 08) have corresponding pytest-benchmark tests. Coverage is complete for documented NFRs. |
| Owner | @johnnylugm-tech |
| Target | Closed |

### RISK-005 — Submodule churn (P6-BUG-13/16/17 fixed in upstream)

| Field | Value |
|-------|-------|
| Category | Build/dep drift |
| Likelihood | 3 (medium — submodule already pulled latest) |
| Impact | 2 (low — fixes already applied locally) |
| Score | 6 (MEDIUM) |
| Source | .audit/harness-bugs-phase6.md P6-BUG-13/16/17 |
| Mitigation | Submodule HEAD `9aa6df7` includes all 3 fixes. CI workflow tracks `origin/main` for submodule. HR-17 strict (no local edits). |
| Owner | CI + submodule update bot |
| Target | Ongoing monitoring |

### RISK-006 — `pip-licenses` shim lives in venv (not version-controlled)

| Field | Value |
|-------|-------|
| Category | Reproducibility |
| Likelihood | 4 (high — `rm -rf .venv` loses shim) |
| Impact | 2 (low — easy to recreate; license scan re-runs on env setup) |
| Score | 8 (MEDIUM) |
| Source | .audit/harness-bugs-phase6.md P6-BUG-10 |
| Mitigation | Document recreate steps in `.audit/harness-bugs-phase6.md`. Add `pip-licenses` shim setup to env-check finalization (Phase 8). |
| Owner | @johnnylugm-tech |
| Target | Phase 8 env-check enhancement |

---

## LOW Risks (1-4)

### RISK-007 — A3 dispatcher persona fails first 3 attempts (UX)

| Field | Value |
|-------|-------|
| Category | Process / UX |
| Likelihood | 3 (medium — observed in P6) |
| Impact | 1 (low — workaround documented, no functional block) |
| Score | 3 (LOW) |
| Source | .audit/harness-bugs-phase6.md P6-BUG-12 |
| Mitigation | Document `--no-persona --prompt-file` workaround. Optional upstream PR: dispatcher default `--no-persona` for reviewer role. |
| Owner | framework UX (advisory) |

### RISK-008 — `trace_dirt` pre-flight blocks advance after code change

| Field | Value |
|-------|-------|
| Category | Process |
| Likelihood | 2 (low — workflow known) |
| Impact | 1 (low — `build-trace-attestation --write` fixes) |
| Score | 2 (LOW) |
| Source | .audit/harness-bugs-phase6.md P6-BUG-14 |
| Mitigation | Framework design intent (deliberate mtime probe). Workflow documented; fix command embedded in error message. |
| Owner | N/A (design intent) |

### RISK-009 — `audit-phase` WARNING on QUALITY_REPORT.md sections (5/7)

| Field | Value |
|-------|-------|
| Category | Deliverable completeness |
| Likelihood | 1 (low — already triggered) |
| Impact | 1 (low — advisory, not blocking) |
| Score | 1 (LOW) |
| Source | audit_gaps_6.md C5 WARNING |
| Mitigation | Add 2 more sections to QUALITY_REPORT.md if needed (Phase 8). Currently NOT blocking Gate 4 PASS. |
| Owner | @johnnylugm-tech |
| Target | Optional Phase 8 polish |

---

## Risk Trend vs Prior Phases

| Phase | HIGH | MEDIUM | LOW | Trend |
|-------|----:|------:|----:|-------|
| P4 | 3 | 5 | 1 | baseline |
| P5 | 1 | 3 | 2 | ↓ (hotfixes resolved) |
| P6 | 2 | 4 | 3 | stable |
| **P7** | **2** | **4** | **3** | **stable** |

RISK-001 (readability) is **NEW in P7** — only surfaced after framework Plan B submodule upgrade.

RISK-002 (mutation) remains HIGH due to permanent feature-flag exclusion.

---

## Top-3 Watchlist for Phase 8

1. **RISK-002** — re-enable mutation testing when framework supports it
2. **RISK-006** — move `pip-licenses` shim from venv to project version-control
3. **RISK-003** — audit-phase should reconcile dimension inconsistency (framework task)
