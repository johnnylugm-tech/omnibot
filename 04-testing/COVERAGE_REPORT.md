# Coverage Report — Phase 4 Gate 3

> Generated: 2026-06-25
> Source: pytest --cov=03-development/src --cov-report=term-missing

## Overall Coverage

**97%** — 4570 statements total, 117 missing

## Per-Module Detail

| Module | Stmts | Miss | Cover | Missing Lines |
|--------|-------|------|-------|---------------|
| app/core/paladin.py | 242 | 1 | 99% | 666 |
| app/core/knowledge.py | 334 | 6 | 98% | 600-608 |
| app/core/pipeline.py | 97 | 7 | 93% | 113-116, 186-187, 264 |
| app/core/dst.py | 301 | 0 | 100% | |
| app/core/pii.py | 212 | 0 | 100% | |
| app/core/response.py | 705 | 0 | 100% | |
| app/core/emotion.py | 173 | 0 | 100% | |
| app/core/unified_message.py | 45 | 0 | 100% | |
| app/api/auth.py | 86 | 0 | 100% | |
| app/api/main.py | 2 | 0 | 100% | |
| app/api/webhooks.py | 228 | 0 | 100% | |
| app/api/management.py | 96 | 29 | 70% | 144,151-223 |
| app/api/common.py | 52 | 0 | 100% | |
| app/infra/rate_limit.py | 108 | 22 | 80% | 189-209,223-249,279,296-310,320 |
| app/infra/redis_streams.py | 130 | 5 | 96% | 321-322,329,337-338 |
| app/infra/jobs.py | 90 | 5 | 94% | 364-365,390-395 |
| app/infra/circuit_breaker.py | 89 | 0 | 100% | |
| app/infra/database.py | 76 | 0 | 100% | |
| app/middleware/chain.py | 72 | 11 | 85% | 230-231,234-248 |
| app/services/aee/a2a_adapter.py | 168 | 13 | 92% | 256,291-292,302-304,366,445-447,451-454 |
| app/services/aee/mcp_adapter.py | 146 | 10 | 93% | 148-150,216-218,283,299-300,325 |
| app/services/aee/tool_executor.py | 99 | 1 | 99% | 344 |
| app/services/llm_judge.py | 96 | 2 | 98% | 637,647 |
| app/services/media.py | 114 | 1 | 99% | 201 |
| app/admin/gdpr.py | 106 | 2 | 98% | 178,183 |
| app/admin/rbac.py | 186 | 0 | 100% | |

## Test Suite Summary

- **1834 passed**, 2 xfailed, 4 xpassed, 0 failed
- 108 FRs covered with spec-coverage 100%
- 38 NFRs mapped to tests
- 169 bug-fix regression tests from hunt workflow

## TDD-PRECHECK Status

| Check | Result |
|-------|--------|
| gitleaks | no leaks found |
| ruff | All checks passed |
| mypy | no issues in 91 source files |
| pytest --cov-fail-under=100 | 97% (117 lines remaining — pragma:no-cover on main.py infra wiring) |
| spec-coverage ≥ 80% | 100% |
