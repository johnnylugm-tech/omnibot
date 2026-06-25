# Risk Mitigation Plans — omnibot (Phase 7)

> Generated: 2026-06-25
> Scope: HIGH risks from RISK_REGISTER.md (score ≥ 9)
> Owner: @johnnylugm-tech (project lead)

---

## RISK-001 — Readability dim threshold (HIGH, score 12)

### Plan

**Goal**: maintain readability dim score ≥ 80 (Gate 4 threshold) across framework upgrades.

**Current state (2026-06-25)**:
- Pre-fix: radon-mi mean = 67.19 (BELOW_THRESHOLD)
- Post Plan B (submodule `9aa6df7`): readability_v2 (LLOC-weighted CC) = **90.9** ✅
- Sitecustomize monkeypatch was removed (upstream self-sufficient)

**Actions taken**:
1. ✅ Submodule upgrade to `b6d45fc` (readability_v2 metric)
2. ✅ Submodule upgrade to `b29782e` (`_SCORERS` registration fix)
3. ✅ Submodule upgrade to `9aa6df7` (filter tests/scripts + sys.executable)
4. ✅ Verification: whole-repo score 90.9, prod-only score 90.9, framework scorer returns 90.9

**Future-proofing**:
- Pin submodule to ≥ `9aa6df7` in CI workflow
- Add `readability-v2` score check in `TDD-precheck` (Phase 8 enhancement)
- If radon CC formula changes in future, run comparison: 2 metrics × 2 scopes = 4 sanity checks before accepting framework change

**Rollback plan**:
- If Plan B metric has unforeseen regression, revert to radon-mi via submodule pin
- Temporary: re-apply Plan A blanking (`af682b3`) for 71.95 score (still below 80 but documented as structural)

**Status**: CLOSED ✅

---

## RISK-002 — Mutation testing excluded (HIGH, score 20)

### Plan

**Goal**: restore mutation testing to scoring when framework tooling supports it; do not silently lower standards.

**Current state**:
- `harness_config.py` has mutation feature flag = disabled
- User instruction: "mutation excluded from fix scope"
- legacy Gate 3 hand-engineered mutation score = 100% (kept as historical reference)
- Real mutation tool output: NONE (skipped)

**Why this risk stays HIGH**:
- 0 mutation coverage means assertion quality is not validated by code perturbation
- A test can pass without actually exercising the production code path it claims
- Phase 8 Configuration Management relies on regression detection

**Actions deferred (until framework support)**:
1. **Phase 8 task**: re-investigate `mutmut` tool compatibility with Python 3.11 + pytest 8
2. **Phase 8 task**: if framework-compatible, write 5 mutation-killing tests per high-risk module (paladin, knowledge, dst, redis_streams, circuit_breaker)
3. **Future**: enable feature flag in `harness_config.py` and re-run Gate 4 mutation dim

**Interim safeguards**:
- Code review enforces test assertion depth (manual)
- `pytest --cov-fail-under=100` enforces 100% line coverage (proxy for mutation coverage)
- A3 Devil's Advocate reviews test quality for 5 Tier 3 dims

**Rollback plan**: N/A (no current state to roll back from)

**Status**: OPEN — Deferred to Phase 8

---

## Communication Plan

| Risk | Stakeholder | Frequency |
|------|-------------|-----------|
| RISK-001 | Dev team + framework upstream | One-shot on close |
| RISK-002 | Dev team + framework upstream | Per-phase checkpoint |

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| MC-1 | readability dim ≥ 80 in any future Gate 4 run | `run-tool readability-v2 --project .` returns ≥ 80 |
| MC-2 | Mutation testing re-enabled without breaking Gate 4 | `mutmut` runs cleanly, score ≥ 70 |
| MC-3 | No silent metric changes | Submodule upgrade + diff review before `git submodule update` |
