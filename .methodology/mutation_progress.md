# Mutation Testing Progress — Phase 3 Exit Requirement

## Goal

Re-run mutmut across ALL 28 source modules and achieve kill rate ≥ 70%.

## Status: INCOMPLETE — single-session infeasible

Wall-clock estimate: 28 modules × ~30 min = **~14 hours**.
Single session budget: ~1-2 hours.
Framework timeout per call: 1 hour.

## Progress

| # | Module | Mutants | Killed | Survived | Suspicious | Status |
|---|--------|---------|--------|----------|------------|--------|
| 1 | `03-development/src/app/core/unified_message.py` | 32 | 32 | 0 | 0 | ✅ DONE |
| 2 | `03-development/src/app/infra/config.py` | TBD | TBD | TBD | TBD | 🔄 RUNNING |

## Remaining modules (27)

Core (7): `pipeline.py`, `dst.py`, `emotion.py`, `knowledge.py`, `paladin.py`, `pii.py`, `response.py`
API (4): `common.py`, `webhooks.py`, `management.py`, `auth.py`, `websocket.py`
Adapters (8): `a2a.py`, `base.py`, `line.py`, `messenger.py`, `telegram.py`, `utils.py`, `verifiers.py`, `web.py`, `whatsapp.py`
Infra (8): `database.py`, `deployment.py`, `jobs.py`, `observability.py`, `rate_limit.py`, `redis_streams.py`, `security.py`, `circuit_breaker.py`
Services (5): `registry.py`, `escalation.py`, `ab_testing.py`, `llm_judge.py`, `media.py`
AEE (5): `a2a_adapter.py`, `adapter.py`, `cli_adapter.py`, `mcp_adapter.py`, `tool_executor.py`
Admin (5): `rbac.py`, `gdpr.py`, `webui.py`, `odd_sql.py`, `portal.py`, `reports.py`
Middleware (2): `chain.py`, `ip_whitelist.py`

## Why this is not single-session feasible

1. **Framework timeout**: 1 hour per `mutation-test-score` call
2. **mutmut runner**: runs full test suite per mutant (~45s × ~40 mutants/module = 30 min/module)
3. **28 modules × 30 min = 14 hours** of pure mutation time
4. **No parallel safe mechanism**: framework's `compute_mutation_score` overwrites the workdir cache to project root on each call (line 844 of `mutation_enforcer.py`) — running multiple modules in parallel would race on the SQLite cache

## How to continue across sessions

For each module:

```bash
# 1. Update setup.cfg paths_to_mutate to point to ONE module
# 2. Delete project-root cache
rm -f .mutmut-cache
# 3. Run framework command
OMNIBOT_ADMIN_USER=admin OMNIBOT_ADMIN_PASS=correct \
OMNIBOT_JWT_SECRET=test-only-jwt-secret-do-not-use-in-prod-32chars \
  python3 harness/harness_cli.py mutation-test-score --project .
# 4. Record result to .sessi-work/mutation_summary.json
python3 -c "
import sqlite3, json
c = sqlite3.connect('.mutmut-cache')
counts = {'killed': 0, 'survived': 0, 'timeout': 0, 'suspicious': 0, 'ok_killed': 0, 'other': 0}
for m in c.execute('SELECT status FROM Mutant'):
    st = m[0]
    if st in counts: counts[st] += 1
    else: counts['other'] += 1
print(counts)
"
# 5. Append to summary
```

## Summary file: `.sessi-work/mutation_summary.json`

Updated each module. Final score = sum(killed) / sum(killed + survived) × 100.

## Known framework bugs (H6 candidate)

- `mutation-test-score` returns `success=false, score=0.0` for exit code 8 (slow test), even when 100% of mutants killed. The whitelist at `mutation_enforcer.py:809` is `if r.returncode not in (0, 2):` — should include `8` (slow but successful kill). Exit code 8 means "mutant survived 2x test time" but if `mutmut results` shows all killed, the workdir cache is valid.

## HR-17 compliance note

This approach does NOT modify `harness/` files. All mutations come from
project-side `setup.cfg` configuration changes (paths_to_mutate), which the
framework's `_copy_setup_cfg_to_workdir` accepts and rewrites at runtime.
