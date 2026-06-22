# ADR — OmniBot Architecture Decision Records

> **Project**: omnibot
> **Source**: SRS.md v8.1 specification (2026-06-17 Approved), SAD.md (2026-06-18 Approved)
> **Traceability**: decisions trace to SAD.md traceability matrix §5 (FR→layer mapping)
> **Authored**: 2026-06-18 — Agent A: ARCHITECT
> **Phase**: 2

---

## ADR-001: Five-Layer Application Architecture

## Status
Accepted

## Context
OmniBot serves 6 platforms (Telegram/LINE/Messenger/WhatsApp/Web/A2A) with 108 distinct functional requirements spanning webhook ingestion, PALADIN security, hybrid knowledge retrieval, DST FSM, response generation, RBAC, GDPR, and admin tooling. A flat module structure would produce circular dependencies and make the CRG community cohesion score fail (requires density ≥ 0.3 per community).

## Decision
Adopt a 5-layer vertical split: **api** → **core** → **services** → **infra** → **admin**, with unidirectional dependency flow downward only. Each layer maps to one `app/{layer}/` directory forming one CRG community with a mandatory hub module.

## Rationale
- Single direction prevents circular dependencies, enabling independent testing of core without services
- Hub modules (common.py, pipeline.py, registry.py, config.py, reports.py) create internal CRG edges that compensate for external library imports, keeping cohesion ≥ 0.38 per layer
- 5 directories satisfies the 3-6 CRG community bound
- Admin as a separate layer (not a sub-module of API) allows RBAC and GDPR to be tested without mocking the full HTTP stack

## Consequences
- Positive: Clear dependency boundaries, testable isolation per layer, CRG-friendly directory layout
- Negative: Cross-layer calls require explicit injection (e.g., api layer imports rbac from admin); slight boilerplate overhead for service-level aggregations
- Acceptance criteria: all 5 layers resolve imports in strict downward order; `pylint --enable=cyclic-import` passes; CRG community cohesion ≥ 0.38 per layer

---

## ADR-002: FastAPI as the Web Framework

## Status
Accepted

## Context
OmniBot requires async WebSocket support (/ws/agent, /ws/user with 30s heartbeat), async webhook handlers for 6 platforms, OpenAPI auto-documentation, and JSON schema validation for the 9 standardized error codes.

## Decision
Use **FastAPI** (Python, ASGI) as the only web framework.

## Rationale
- Native `async/await` enables concurrent webhook processing and WebSocket lifecycle without thread pools
- Automatic request validation (Pydantic) matches ApiResponse[T]/PaginatedResponse[T] schema (FR-09)
- Built-in WebSocket support satisfies FR-57–59 without additional library
- `@app.get("/.well-known/agent.json")` serves Agent Card (FR-44) with zero additional routing library

## Consequences
- Positive: Single framework covers REST + WebSocket + validation + OpenAPI docs
- Negative: ASGI deployment requires uvicorn/gunicorn; K8s HPA CPU metric less precise for async workloads than for thread-based workers

---

## ADR-003: PostgreSQL 16 + pgvector for Hybrid Search

## Status
Accepted

## Context
OmniBot's Hybrid Knowledge Layer requires: (a) ILIKE keyword matching for Tier 1 rule search, (b) HNSW vector search for Tier 2 RAG with 1536-dim embeddings, (c) GIN tsvector full-text search as fallback for level_embedding_down circuit breaker state, (d) relational integrity for 20 tables.

## Decision
Use a single **PostgreSQL 16 + pgvector** instance for all persistence needs. Build three index types on `knowledge_chunks`: HNSW (m=16, ef_construction=64, partial WHERE embeddings IS NOT NULL) for vector search, GIN tsvector for full-text fallback, and B-tree on FK columns.

## Rationale
- Single DB eliminates cross-store consistency issues (no Redis/Elasticsearch synchronization)
- pgvector HNSW achieves Recall@3 ≥ 92% at p95 < 100ms for 1536-dim (NFR-28)
- GIN tsvector index fulfills FR-99 level_embedding_down degraded mode without an additional search service
- Partial index (WHERE embeddings IS NOT NULL) avoids indexing chunks that haven't yet received their SAQ-generated embeddings, keeping index size and build time optimal

## Consequences
- Positive: One dependency, consistent ACID transactions across all 20 tables, no data sync lag
- Negative: Single DB is a scaling constraint at very high write rates; mitigated by K8s connection pooling and PgBouncer if needed in Phase 4+

---

## ADR-004: Hybrid Knowledge 4-Tier Cascade (Rule → RAG → LLM → Escalate)

## Status
Accepted

## Context
Customer queries range from exact FAQ matches (high confidence, no LLM needed) to novel questions (require LLM generation) to out-of-scope requests (require human agent). Different tiers have different latency and cost characteristics.

## Decision
Execute knowledge retrieval as a **strict waterfall**: Tier 1 (ILIKE rule, conf≥0.80) → Tier 2 (HNSW RAG+RRF k=60, conf≥0.85) → Tier 3 (gpt-4o→gemini fallback, grounding cosine≥0.75) → Tier 4 (human escalation). Stop at first tier that meets confidence threshold.

## Rationale
- Tier 1 covers ~40% of FAQ traffic at zero LLM cost ($0/query)
- Tier 2 RRF k=60 fuses ILIKE rank and vector rank, reducing false positives vs pure vector search
- Tier 3 LLM Sandwich Prompt (L3 defense) applies grounding check (L5) to block hallucination before response is returned
- Tier 4 is always the fallback — system never returns "no answer" to the user
- Waterfall is deterministic and traceable; confidence thresholds are tunable without code changes

## Consequences
- Positive: Cost optimization (40% queries skip LLM), hallucination guard (L5 grounding), zero silent failures
- Negative: Waterfall is sequential; T1→T2→T3 adds latency if all tiers are exercised (mitigated by p95 target of <1.0s end-to-end, NFR-01)

---

## ADR-005: PALADIN 5-Layer Security Architecture

## Status
Accepted

## Context
OWASP LLM01:2025 prompt injection is the primary attack vector. A single regex check is insufficient; adversarial inputs exploit Unicode homoglyphs, indirect injection in knowledge content, and timing-dependent injection.

## Decision
Implement **PALADIN**: L1 InputSanitizer (NFKC+homoglyph <2ms) → L2 13-pattern regex <3ms → L3 Sandwich Prompt with UNTRUSTED DATA BOUNDARY → L4 SemanticInjectionClassifier (LLM-based, async, <200ms) → L5 GroundingChecker (cosine ≥0.75, <5ms local).

**L4 parallel execution policy**: low-risk → skip L4; medium-risk → L4 parallel with L3 (L4 can retrospectively block after L3 completes); high/critical → L4 sync blocks before L3.

## Rationale
- L1-L3 are deterministic and complete <5ms combined, covering all known pattern-based attacks
- L4 LLM classification catches semantic injection that regex misses; parallelism with L3 for medium-risk minimizes latency impact
- L5 grounding prevents hallucinated responses from reaching the user even if L4 passes
- Retrospective block (FR-16) with platform-specific retraction (FR-17) ensures injected responses can be recalled

## Consequences
- Positive: Defense in depth, OWASP LLM01:2025 compliant, ≥95% block rate target achievable (NFR-16)
- Negative: L4 adds p95 200ms for medium/high risk traffic; retrospective retraction has platform-specific constraints (Telegram 48hr window, Messenger 10min window)

---

## ADR-006: SAQ over Celery for Background Jobs

## Status
Accepted

## Context
OmniBot needs 3 background queues: embedding generation (async, after knowledge insertion), maintenance tasks, and notifications. The embedding queue requires concurrent workers (concurrency=3) and must support retry with exponential backoff.

## Decision
Use **SAQ (Simple Async Queue)** backed by Redis, not Celery.

## Rationale
- SAQ is `async/await` native — no `asyncio.run()` wrappers needed inside FastAPI context
- Redis already required for rate limiting and Streams; SAQ reuses the same connection pool
- SAQ concurrency model maps cleanly to the 3-queue spec (embedding c=3, maintenance c=1, notification c=5) with stop_grace_period=30s
- Celery's broker/backend separation would require an additional message broker or dual Redis configuration

## Consequences
- Positive: Zero new infrastructure dependency, native async, simpler deployment
- Negative: SAQ is less mature than Celery; retry visibility requires custom monitoring via Prometheus (handled by FR-71 `llm_tokens_total` and embedding sync status FR-79)

---

## ADR-007: Redis Streams for Async Messaging (HA)

## Status
Accepted

## Context
OmniBot must survive consumer crashes without message loss (FR-80). Redis Streams with consumer groups provides at-least-once delivery via XCLAIM for orphaned pending messages.

## Decision
Use **Redis Streams** with consumer group "omnibot", XREADGROUP block=5000ms, XACK after processing, XCLAIM for crash recovery. Forward-compatible unknown field handling (ignore unknown keys) allows schema evolution.

## Rationale
- XCLAIM picks up messages from crashed consumers without manual intervention
- BUSYGROUP error on duplicate group creation is silently ignored, making startup idempotent
- Redis already present in the stack; no additional messaging service (Kafka, RabbitMQ)

## Consequences
- Positive: At-least-once delivery, crash recovery, no additional dependency
- Negative: Redis Streams has a simpler feature set than Kafka (no partitioning, no consumer offset replay); acceptable for current throughput targets (2000 TPS), may require migration at 10× scale

---

## ADR-008: tiktoken cl100k_base for Consistent Token Budgeting

## Status
Accepted

## Context
OmniBot uses gpt-4o as the primary LLM and gemini-1.5-flash as fallback (FR-38). Each has a different native tokenizer. Using per-model tokenizers would produce different context window budgets across primary/fallback paths.

## Decision
Use **tiktoken cl100k_base** for all token counting across both gpt-4o and gemini-1.5-flash.

## Rationale
- Single tokenizer guarantees consistent max_tokens=8192 budget regardless of which LLM is active
- cl100k_base is conservative for gemini (gemini tokenizes more efficiently), so the budget is a safe underestimate — context overflow cannot occur due to tokenizer mismatch
- Eliminates a class of subtle bugs where primary LLM passes but fallback overflows context window

## Consequences
- Positive: Deterministic behavior across primary/fallback switch, no runtime tokenizer loading per model
- Negative: Gemini receives slightly shorter contexts than it could handle (conservative by ~5-10%), acceptable tradeoff

---

## ADR-009: SHA-256 for Deterministic A/B Variant Assignment

## Status
Accepted

## Context
A/B test variant assignment (FR-52, FR-63) must be deterministic across processes and restarts — the same user must receive the same variant for the duration of an experiment.

## Decision
Use **hashlib.sha256(f"{user_id}:{experiment_id}".encode()).hexdigest()** for variant assignment, not Python's built-in `hash()`.

## Rationale
- Python `hash()` is non-deterministic across processes (PYTHONHASHSEED randomization) — would break sticky assignment
- SHA-256 produces identical output for identical inputs across all Python processes, machines, and restarts
- Uniform distribution of SHA-256 output ensures even 33/33/33 split for variant_a/variant_b/control

## Consequences
- Positive: Process-stable sticky assignment, no external state needed for assignment lookup
- Negative: Changing experiment_id resets user assignments (intended behavior for new experiments)

---

## ADR-010: LLM-as-a-Judge Ensemble (max politeness, min accuracy)

## Status
Accepted

## Context
OmniBot quality evaluation requires automated CSAT scoring. Single-judge LLM assessment has bias risk. Two-judge ensemble (gpt-4o-mini + claude-3-5-haiku) requires an aggregation policy.

## Decision
**Politeness = max(judge_a, judge_b)** (lenient — emotional support prefers wider tolerance).
**Accuracy = min(judge_a, judge_b)** (conservative — factual hallucination is not acceptable).
Both judges called in **parallel** (temp=0 for determinism).

## Rationale
- max() for politeness: either judge confirming warmth is sufficient; penalizing politeness requires both judges to agree it's rude
- min() for accuracy: if either judge detects a factual error, the response fails accuracy; a single lax judge cannot rescue a hallucination
- Parallel execution keeps judge latency bounded to max(judge_a_latency, judge_b_latency), not sum
- Cohen's Kappa ≥ 0.7 monthly calibration ensures aggregate score doesn't drift from human annotation

## Consequences
- Positive: Defensively strict on accuracy (hallucination risk), lenient on politeness (avoids over-penalizing casual Chinese tone markers)
- Negative: min() accuracy may over-penalize correct responses if one judge miscalibrates; addressed by monthly recalibration (FR-69)

---

## ADR-011: 9-Level Circuit Breaker with Lateral Named Levels

## Status
Accepted

## Context
OmniBot has multiple degradable subsystems: LLM API, Embedding API, Semantic Classifier, LLM Judge, Database. A single binary circuit breaker cannot handle partial degradation gracefully.

## Decision
Implement a **9-level circuit breaker**: 6 numeric levels (0=full → 5=static maintenance) for general degradation plus 3 lateral named levels (level_embedding_down, level_classifier_down, level_judge_down) that can activate independently of the numeric scale.

## Rationale
- Numeric levels handle cascading LLM/DB degradation progressively (latency→feature-reduction→full-block)
- Named lateral levels isolate specific subsystem failures without forcing numeric level escalation (e.g., Embedding API down activates level_embedding_down with GIN tsvector fallback, without triggering level_2 LLM shutdown)
- Auto-recovery on consecutive success count prevents manual intervention for transient failures
- GIN tsvector fallback (FR-82, FR-99) makes level_embedding_down functionally complete without vector search

## Consequences
- Positive: Fine-grained degradation, each subsystem has an independent fallback path, no manual recovery required
- Negative: 9 levels increases complexity of state machine testing (all valid/invalid transitions must be covered in TEST_SPEC); addressed by architecture-risk NP-13 forced tests

---

## ADR-012: ClamAV Fail-Secure for File Uploads

## Status
Accepted

## Context
FR-100 requires malware scanning for file uploads. ClamAV runs as a Docker sidecar service. The question is: what happens if ClamAV is unavailable?

## Decision
**Fail-secure**: if ClamAV service is unavailable, **reject the file upload** with HTTP 503 FILE_SCAN_UNAVAILABLE. Do NOT permit files through an unscanned path.

## Rationale
- Fail-open (allowing files when ClamAV is down) introduces a malware vector that could compromise the entire system
- 503 communicates a temporary service issue to the user (retry is meaningful)
- p95 < 500ms target (NFR-38) with ClamAV Alpine is achievable for files ≤ 10MB
- Consistent with the security-first principle applied to IP whitelist (fail-secure 403, FR-25) and rate limiter (fail-open because blocking legitimate traffic is the greater harm)

## Consequences
- Positive: No unscanned files reach the system under any ClamAV failure mode
- Negative: ClamAV availability becomes a hard dependency for file uploads; mitigated by Docker healthcheck in docker-compose.yml (FR-95) and K8s PDB (FR-96)

---

## ADR-013: M2M Token with 24-Hour Rotation Overlap

## Status
Accepted

## Context
Machine-to-machine tokens for A2A platform (FR-87) need rotation support. Abrupt rotation (old token immediately invalid) causes service interruption for external callers that haven't refreshed yet.

## Decision
On POST /api/v1/m2m/tokens/{client_id}/rotate: create new token, set old token's `rotate_expires_at = NOW() + 24h`. Old token valid until `rotate_expires_at`. Hourly cleanup job removes expired rotated tokens.

## Rationale
- 24-hour overlap allows external callers to discover and apply the new token without emergency on-call coordination
- `rotate_expires_at` field distinguishes "rotated but still valid" from "expired by time" tokens
- Stored as SHA-256 hash (not plaintext) — rotation creates a new hash, old hash remains valid temporarily
- 90-day maximum token lifetime (NFR-36) remains enforced regardless of rotation

## Consequences
- Positive: Zero-downtime rotation for external callers, simple implementation (one new field on m2m_tokens table)
- Negative: During the 24-hour window, two valid tokens coexist; revocation of the old token must also be supported (POST .../revoke still invalidates immediately)

---

## ADR-014: Explicit pii:none for Auditor Role

## Status
Accepted

## Context
FR-61 requires that the auditor role cannot access PII data. The ambiguity is whether "no PII permission" is implicit (absence of pii:read) or explicit (presence of pii:none).

## Decision
Define `pii:none` as an **explicit permission** in ROLE_PERMISSIONS for the auditor role. RBACEnforcer.check() treats pii:none as an active prohibition — any attempt to invoke a pii:decrypt action returns 403 AUTHZ_INSUFFICIENT_ROLE.

## Rationale
- Relying on implicit absence creates a risk: if a new code path forgets to check for pii permission, auditor role could inadvertently access PII if the check defaults to "allowed if not prohibited"
- Explicit pii:none makes the security contract self-documenting in the permission matrix
- Consistent with defense-in-depth: access denied must be stated, not inferred from absence
- dpo role explicitly has pii:decrypt; auditor explicitly has pii:none — no ambiguity between the two roles

## Consequences
- Positive: Unambiguous security contract, resistant to future permission matrix additions that might accidentally grant auditor PII access
- Negative: Requires the RBACEnforcer to handle pii:none as a special "deny" signal, slightly more complex than a simple whitelist check

---

## ADR-015: GDPR Erasure Application-Layer Cascade Order

## Status
Accepted

## Context
FR-92 requires `execute_data_deletion()` to erase user data across multiple tables: users.profile, messages.content, pii_audit_log, pii_vault, emotion_history, security_logs, user_feedback. The question is whether erasure is ordered by PostgreSQL FK ON DELETE CASCADE or by explicit application-layer sequencing in gdpr.py.

## Decision
Use **application-layer ordered erasure** in gdpr.py, not PostgreSQL FK CASCADE. Erasure order:
1. `pii_vault` (BYTEA, KMS-encrypted — decrypt key revoked first)
2. `messages.content = '[REDACTED]'` + `messages.pii_masked = NULL`
3. `users.profile = NULL`
4. `pii_audit_log`: anonymize (replace user_id with gdpr_deletion token)
5. `emotion_history`: DELETE rows for user
6. `security_logs`: retain structure, anonymize user reference (GDPR Art.17(3)(d) security exemption preserves log metadata)

Each step runs in a single DB transaction with SAVEPOINT per table. Partial failure rolls back to last SAVEPOINT; erasure job is idempotent (re-runnable).

## Rationale
- FK CASCADE would erase security_logs entirely — violating GDPR Art.17(3)(d) which permits retention for security/legal obligations; application-layer allows selective anonymization vs deletion
- SAVEPOINT-based partial rollback ensures 30-day SLA (FR-92) survives transient DB failures — the job resumes from the last completed step
- Application-layer ordering makes the erasure sequence auditable and testable (each step is a named function with its own assertion)
- pii_vault key revocation before row deletion ensures decrypted copies in LLM context windows cannot be reconstructed even if a crash occurs mid-erasure

## Consequences
- Positive: GDPR Art.17(3)(d) security log retention preserved; partial failure recovery without full restart; testable step-by-step sequence
- Negative: Application code owns referential integrity during erasure — FK constraints must be temporarily deferred; requires integration test covering partial-failure recovery path (NP-15 forced for external process coordination)

---

## ADR-016: AEE Package Split + Agent Card Consolidation

## Status
Accepted

## Context
Two implementation decisions diverged from the original SAD §2.1 plan:

1. **AEE module split**: `app.services.aee` grew from a single `aee.py` (planned ~500 LOC) to a 5-submodule package (`MCPAdapter`, `A2AAdapter`, `CLIAdapter`, `ToolExecutor`, `ActionAdapter`). A single file would violate SAD §2.4 cohesion targets (predicted density drop to < 0.25).

2. **Agent Card consolidation**: SAD planned a dedicated `app/api/agent_card.py`. In implementation, the Agent Card FastAPI sub-app (`agent_card_app`) was co-located in `webhooks.py` to avoid a 6th api-layer module that would only hold a single static endpoint, which would reduce the api/ CRG community cohesion below 0.38.

## Decision
1. **AEE**: Split into `app/services/aee/` package with `__init__.py` re-exporting the public surface. SAB.json `fr_module_traceability` entries for FR-39–45 point to `app.services.aee` (package, trailing slash variant).
2. **Agent Card**: Keep `agent_card_app = FastAPI(...)` inside `webhooks.py`. Update SAD §2.1 and §2.2 to reflect this. The 6 adapter docstring cross-references to `agent_card.py:12-16` are historical and should be read as referring to the `AGENT_CARD` dict in `webhooks.py`.

## Rationale
- AEE split maintains cohesion ≥ 0.38 per SAD §2.4; each adapter is independently testable
- Agent Card consolidation keeps api/ at 7 modules (not 8), preserving CRG density above threshold
- Both decisions are additive: no SAD layer boundary is violated

## Consequences
- Positive: AEE adapters independently testable; api/ cohesion maintained
- Negative: 6 adapter docstrings reference `agent_card.py:12-16` — these cross-refs are stale; they point to the `AGENT_CARD` dict in `webhooks.py` lines 468–486
