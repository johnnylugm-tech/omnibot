# Mutation Batch Execution Order (small → large)

Priority: smallest first to maximize count within 1hr framework timeout.

| Order | Module | Lines | Est. mutants | Est. min | Status |
|-------|--------|-------|--------------|----------|--------|
| 1 | core/unified_message.py | 30 | 32 | 30 | ✅ DONE (32K/0S) |
| 2 | infra/config.py | 111 | 14 | 30 | ✅ DONE (9K/5S, 64.3%) |
| 3 | core/pipeline.py | 108 | ? | ? | 🔄 RUNNING |
| 4 | api/adapters/utils.py | 38 | ? | ~10 | pending |
| 5 | api/adapters/base.py | 51 | ? | ~15 | pending |
| 6 | api/common.py | 87 | ? | ~20 | pending |
| 7 | services/registry.py | ? | ? | ~5 | pending |
| 8 | middleware/chain.py | 187 | ? | ~40 | pending |
| 9 | api/adapters/line.py | 106 | ? | ~25 | pending |
| 10 | admin/portal.py | 166 | ? | ~35 | pending |
| 11 | admin/odd_sql.py | 182 | ? | ~40 | pending |
| 12 | api/adapters/messenger.py | 139 | ? | ~30 | pending |
| 13 | api/adapters/whatsapp.py | 162 | ? | ~35 | pending |
| 14 | api/adapters/telegram.py | 88 | ? | ~20 | pending |
| 15 | api/auth.py | 106 | ? | ~25 | pending |
| 16 | api/management.py | 154 | ? | ~35 | pending |
| 17 | api/adapters/web.py | 181 | ? | ~40 | pending |
| 18 | core/pii.py | 422 | ? | ~90 | pending |
| 19 | core/emotion.py | 424 | ? | ~90 | pending |
| 20 | infra/rate_limit.py | 211 | ? | ~45 | pending |
| 21 | middleware/ip_whitelist.py | 226 | ? | ~50 | pending |
| 22 | services/escalation.py | 324 | ? | ~70 | pending |
| 23 | services/ab_testing.py | 329 | ? | ~70 | pending |
| 24 | api/adapters/verifiers.py | 328 | ? | ~70 | pending |
| 25 | infra/circuit_breaker.py | 307 | ? | ~65 | pending |
| 26 | services/aee/cli_adapter.py | 260 | ? | ~55 | pending |
| 27 | services/aee/mcp_adapter.py | 298 | ? | ~65 | pending |
| 28 | services/aee/tool_executor.py | 366 | ? | ~80 | pending |
| 29 | infra/redis_streams.py | 333 | ? | ~70 | pending |
| 30 | infra/database.py | 445 | ? | ~95 | pending |
| 31 | admin/rbac.py | 290 | ? | ~60 | pending |
| 32 | admin/gdpr.py | 293 | ? | ~60 | pending |
| 33 | services/aee/a2a_adapter.py | 400 | ? | ~85 | pending |
| 34 | services/media.py | 380 | ? | ~80 | pending |
| 35 | api/adapters/a2a.py | 375 | ? | ~80 | pending |
| 36 | core/response.py | 796 | ? | ~170 (likely TIMEOUT) | pending |
| 37 | infra/observability.py | 824 | ? | ~175 (likely TIMEOUT) | pending |
| 38 | services/llm_judge.py | 721 | ? | ~155 (likely TIMEOUT) | pending |
| 39 | core/dst.py | 617 | ? | ~130 | pending |
| 40 | api/webhooks.py | 554 | ? | ~120 | pending |
| 41 | api/websocket.py | 585 | ? | ~125 | pending |
| 42 | infra/security.py | 541 | ? | ~115 | pending |
| 43 | admin/webui.py | 613 | ? | ~130 (in paths_to_exclude) | pending |
| 44 | core/paladin.py | 1181 | ? | ~250 (TIMEOUT) | pending |
| 45 | infra/jobs.py | 418 | ? | ~90 | pending |
| 46 | infra/deployment.py | 727 | ? | ~155 (TIMEOUT) | pending |
| 47 | core/knowledge.py | 1416 | ? | ~300 (TIMEOUT) | pending |

## Estimated total wall-clock

- 28 modules × average ~60 min = ~28 hours
- Even small modules take 30+ min due to full test suite per mutant

## Strategy

Run smallest first, accept that >500 line modules will TIMEOUT. Track:
- TIMEOUT modules: marked "deferred - framework 1hr limit" in summary
- Surviving mutants from small modules: add assertion-density tests to kill them in next session
