# SAD — OmniBot 軟體架構文件

> **Source**: SRS.md v8.1 (2026-06-17 Approved) — INGESTION MODE
> **Authored**: 2026-06-18 — Agent A: ARCHITECT
> **Project**: omnibot
> **Phase**: 2

---

## 1. Architecture Overview

OmniBot 採用五層清晰分層架構，對應 SRS 108 個 FR（含 3 個 test FR：FR-106~108）與 38 個 NFR：

```
┌─────────────────────────────────────────────────┐
│  Layer 1: API Gateway (app/api/)                │
│  Webhooks · REST Management · WebSocket · Auth  │
├─────────────────────────────────────────────────┤
│  Layer 2: Core Pipeline (app/core/)             │
│  PALADIN · PII · DST · Knowledge · Response     │
│  Emotion                                         │
├─────────────────────────────────────────────────┤
│  Layer 3: Services (app/services/)              │
│  AEE · Escalation · A/B Testing · LLM Judge     │
│  Media                                           │
├─────────────────────────────────────────────────┤
│  Layer 4: Infrastructure (app/infra/)           │
│  DB · Redis · SAQ Jobs · Circuit Breaker        │
│  Rate Limit · Observability · Security          │
├─────────────────────────────────────────────────┤
│  Layer 5: Admin (app/admin/)                    │
│  RBAC · GDPR · WebUI Backend · ODD SQL          │
├─────────────────────────────────────────────────┤
│  Cross-cutting: tests/                          │
│  unit · integration · e2e · load (FR-106~108)   │
└─────────────────────────────────────────────────┘
```

**Dependency Flow**: Primary chain: API → Core → Services → Infra (downward). Cross-layer: API → Admin (management); Core → Services (orchestration). All dependency paths terminate at Infra. No circular dependencies.
Admin manages cross-layer operations (RBAC, GDPR, analytics, WebUI) but its code-level dependency is **Infra only** — admin modules access cross-layer data via the database (app.infra.database), not via direct imports of Core or Services modules.

**No circular dependencies**: API depends on Core/Infra/Admin; Core depends on Infra/Services; Services depends on Infra; Admin depends on Infra only.

---

## 2. Module Design

### 2.1 Directory Structure Design Principles

OmniBot 遵循 CRG (Code Review Graph) 高內聚設計：

- **5 個 application source directories** (app/api, app/core, app/services, app/infra, app/admin) + **1 cross-cutting tests directory** (tests/)，各自形成獨立 CRG community
- **每個 directory 有 hub module**：≥ 70% 的 sibling files import 並呼叫 hub
- **Entry point** (`app/api/main.py`) 位於 api/ directory，呼叫 api/common.py hub
- **每個 function body 呼叫 hub function**（非僅 module-level import）
- **Community size ≤ 50 nodes** per directory

Directory layout:

```
app/
├── api/
│   ├── common.py        # HUB: shared request/response utilities
│   ├── main.py          # FastAPI application entry point
│   ├── webhooks.py      # Platform webhook handlers (FR-01–09, FR-84)
│   ├── management.py    # Knowledge/experiment management API (FR-85, FR-88)
│   ├── auth.py          # Auth/M2M/user API (FR-86, FR-87)
│   ├── websocket.py     # WebSocket handlers (FR-57–59)
│   └── agent_card.py    # Agent Card endpoint (FR-44)
├── core/
│   ├── pipeline.py      # HUB: request orchestrator — calls all core modules
│   ├── paladin.py       # PALADIN L1–L5 (FR-10–17)
│   ├── pii.py           # PII masking & audit (FR-18–20)
│   ├── knowledge.py     # Hybrid Knowledge Tier 1–4 (FR-26–33)
│   ├── dst.py           # DST FSM + slot filling (FR-34–38)
│   ├── response.py      # Response generation + A/B (FR-50–53)
│   └── emotion.py       # Emotion analysis + decay (FR-46–49)
├── services/
│   ├── registry.py      # HUB: service registry + shared utilities
│   ├── aee.py           # Action Execution Engine (FR-39–43, FR-45)
│   ├── escalation.py    # Escalation queue + SLA (FR-54–56)
│   ├── ab_testing.py    # A/B test manager (FR-63–64)
│   ├── llm_judge.py     # LLM-as-a-Judge ensemble (FR-65–69)
│   └── media.py         # Multimedia processing + ClamAV (FR-100)
├── infra/
│   ├── config.py        # HUB: configuration + health check utilities
│   ├── database.py      # PostgreSQL + pgvector schema (FR-82–83)
│   ├── rate_limit.py    # Redis sliding window + IP whitelist (FR-21–25)
│   ├── redis_streams.py # Redis Streams consumer group (FR-80–81, FR-90)
│   ├── jobs.py          # SAQ worker + embedding jobs (FR-75–79)
│   ├── circuit_breaker.py # 9-level circuit breaker (FR-99)
│   ├── observability.py # Prometheus + OTel + alerts (FR-70–74)
│   ├── security.py      # TDE + secrets management (FR-89)
│   └── deployment.py    # Docker/K8s/backup configs (FR-95–98)
└── admin/
    ├── reports.py       # HUB: shared reporting + analytics utilities
    ├── rbac.py          # RBAC roles + enforcer (FR-60–62)
    ├── gdpr.py          # GDPR lifecycle + erasure (FR-91–94)
    ├── webui.py         # Admin WebUI backend (FR-101–104)
    └── odd_sql.py       # ODD SQL analytics queries (FR-105)

tests/
├── unit/               # 70% coverage target (FR-107)
├── integration/        # 20% coverage target (FR-107)
├── e2e/                # 10% coverage target (FR-107, FR-108)
└── load/               # k6 load tests (FR-106)
```

**CRG Edge Budget** (per directory — architectural design targets; no tool scan until implementation):
- api/ (7 files): hub=common.py; each sibling calls `common.build_response()` + `common.extract_user_context()` from every function body → ~28 internal edges vs ~35 external edges; cohesion ≥ 0.44
- core/ (7 files): hub=pipeline.py; each module called by pipeline and calls `pipeline.get_context()` → ~30 internal edges vs ~35 external edges; cohesion ≥ 0.46
- services/ (6 files): hub=registry.py; all services registered via `registry.get_service()` called per function → ~20 internal edges vs ~30 external edges; cohesion ≥ 0.40
- infra/ (9 files): hub=config.py; all infra modules call `config.get_setting()` + `config.health_probe()` per function body → ~36 internal edges vs ~50 external edges; cohesion ≥ 0.42
- admin/ (5 files): hub=reports.py; all admin modules call `reports.log_admin_action()` per function → ~16 internal edges vs ~25 external edges; cohesion ≥ 0.39

### 2.2 Layer 1: API Gateway (app/api/)

| Attribute | Value |
|-----------|-------|
| Responsibility | HTTP webhook ingress, REST management, WebSocket realtime, JWT/M2M auth, Agent Card |
| External Interface | POST /api/v1/webhook/{platform}, GET/POST /api/v1/knowledge, /ws/agent, /ws/user, GET /.well-known/agent.json |
| Dependencies | app.core.pipeline, app.infra.rate_limit, app.infra.observability, app.admin.rbac |
| Hub Module | common.py — `build_response()`, `extract_user_context()` |

**FR Coverage**: FR-01–09, FR-44, FR-57–59, FR-84–88

#### Module: webhooks.py
- `TelegramWebhookVerifier.verify()` → FR-01
- `LineWebhookVerifier.verify()` → FR-02
- `MessengerWebhookVerifier.verify()` → FR-03
- `WhatsAppWebhookVerifier.verify()` → FR-04
- `WebAdapter` (guest-session + message) → FR-05
- `A2AAdapter` JSON-RPC 2.0 entry → FR-06
- Platform routing + error codes → FR-84

#### Module: auth.py
- POST /api/v1/auth/login, /auth/refresh, /users, /users/{id}/roles → FR-86
- POST /api/v1/m2m/tokens, GET, revoke, rotate (24hr overlap, hourly cleanup) → FR-87

#### Module: management.py
- GET/POST /api/v1/knowledge; PUT/DELETE /api/v1/knowledge/{id}; POST /api/v1/knowledge/bulk → FR-85
- POST /api/v1/experiments; GET /api/v1/conversations; GET /api/v1/health → FR-85
- GDPR data export/delete → FR-88

#### Module: websocket.py
- `/ws/agent` (6 event types, JWT) → FR-57
- `/ws/user` (message.reply, JWT) → FR-58
- Heartbeat (30s ping, 10s timeout) → FR-59

#### Module: common.py (Hub)
- `UnifiedMessage` frozen dataclass → FR-07
- `UnifiedResponse` frozen dataclass → FR-08
- `ApiResponse[T]`, `PaginatedResponse[T]` → FR-09
- `build_response()`, `extract_user_context()` — called by all sibling modules per function body

#### Module: agent_card.py
- GET /.well-known/agent.json (name/description/url/version/capabilities/methods/auth_schemes) → FR-44

#### Logical Constraints
- Middleware chain order enforced: TLS → IP Whitelist → Webhook Signature → Platform Adapter → Rate Limiting → RBAC (FR-24)
- JWT validation before all resource access
- No business logic in API layer (delegates to app.core.pipeline)

### 2.3 Layer 2: Core Pipeline (app/core/)

| Attribute | Value |
|-----------|-------|
| Responsibility | Request processing orchestration, PALADIN security, PII masking, Knowledge retrieval, DST FSM, Response generation, Emotion analysis |
| External Interface | Internal Python API only |
| Dependencies | app.infra.database, app.infra.observability, app.services.registry |
| Hub Module | pipeline.py — `handle_message()`, `get_context()` |

**FR Coverage**: FR-10–20, FR-26–38, FR-46–53

#### Module: paladin.py
- `InputSanitizer.sanitize()` (NFKC + homoglyph, <2ms) → FR-10
- `PromptInjectionDefense.check_input()` (13 SUSPICIOUS_PATTERNS, <3ms) → FR-11
- `PromptInjectionDefense.build_sandwich_prompt()` (L3, L1-L3 <5ms total) → FR-12
- `SemanticInjectionClassifier.classify()` (LLM-based, <200ms, timeout→unverified) → FR-13
- `GroundingChecker.check()` (cosine ≥0.75, <5ms) → FR-14
- `PALADINPipeline.process()` (L4 parallel: low→skip, medium→parallel, high→sync) → FR-15
- `PALADINPipeline.process()` (retrospective block → `injection_retrospective_block`) → FR-16
- Per-platform retraction handlers (Telegram 48hr / Messenger 10min / fail-secure apology) → FR-17

**Architecture Risk**: paladin.py makes network calls to LLM API (L4 classifier) → NP-07 + NP-15 forced

#### Module: pii.py
- `PIIMasking.mask()` (phone/email/address/credit-card Luhn) → FR-18
- `PIIMasking.should_escalate()` (4 sensitive keywords) → FR-19
- `pii_audit_log` write + 90-day retention job → FR-20

#### Module: knowledge.py
- `HybridKnowledge._rule_match()` (T1 ILIKE, conf≥0.80, LIMIT 5) → FR-26
- `HybridKnowledge._rag_search()` + `_reciprocal_rank_fusion()` (T2 RRF k=60, conf≥0.85) → FR-27
- Parent-Child chunking (500/150 tokens, 100 overlap) → FR-28
- HNSW index (m=16, ef=64, partial WHERE embeddings IS NOT NULL, Recall@3≥92%) → FR-29
- `HybridKnowledge._llm_generate()` (T3 gpt-4o→gemini, grounding≥0.75, <500ms) → FR-30
- `HybridKnowledge._escalate()` (T4, id=-1) → FR-31
- `KnowledgeResult` frozen dataclass → FR-32
- `HybridKnowledge.query()` (T1→T2→T3→T4, EMBEDDING_DIM=1536) → FR-33

**Architecture Risk**: knowledge.py makes network calls to OpenAI embedding + LLM APIs with retry logic → NP-07 + NP-15 forced

#### Module: dst.py
- `DialogueState.transition()` + `ALLOWED_TRANSITIONS` (8-state FSM, ValueError on invalid) → FR-34
- `DialogueSlot`, `INTENT_TO_SLOTS`, `missing_slots()` (order_status/return_request) → FR-35
- Auto-escalate (>3 rounds slot filling, confidence<0.65) → FR-36
- AWAITING_CONFIRMATION timeout (>2 rounds → ESCALATED) → FR-37
- `ContextWindowManager.manage()` (tiktoken cl100k_base, max_tokens=8192, summarize earliest 1/3) → FR-38

**Architecture Risk**: dst.py manages shared mutable FSM state under concurrent async sessions → NP-13 forced

#### Module: response.py
- `ResponseGenerator.DEFAULT_TEMPLATES` (rule_default/rag_default/escalate) → FR-50
- `ResponseGenerator._apply_emotion_tone()` (intensity>0.7 apology, repeat suppress) → FR-51
- `ResponseGenerator._apply_ab_variant()` (SHA-256 deterministic) + `ABTestManager.get_variant()` → FR-52
- Platform format adapters (Telegram 4096/LINE 5000/Messenger 2000/Agent JSON) → FR-53

#### Module: emotion.py
- `EmotionScore` + emotion classification (positive/neutral/negative, 0.0–1.0) → FR-46
- `EmotionTracker.current_weighted_score()` (24hr half-life decay) → FR-47
- `EmotionTracker.should_escalate()` (consecutive_negative≥3) → FR-48
- AGENT platform bypass → FR-49

#### Module: pipeline.py (Hub)
- `handle_message(msg: UnifiedMessage) → UnifiedResponse` — orchestrates FR-10→FR-53 pipeline
- `get_context(conversation_id)` — called by all sibling core modules per function body
- Sequence: PALADIN → PII → DST → Knowledge → Emotion → Response

#### Logical Constraints
- PALADIN must execute before PII masking
- Knowledge query only after DST slot resolution
- Response generation reads emotion state before building final response
- L4 classifier skipped for low-risk input (FR-15)

### 2.4 Layer 3: Services (app/services/)

| Attribute | Value |
|-----------|-------|
| Responsibility | External integrations: AEE adapters, escalation queue, A/B testing, LLM judge ensemble, multimedia |
| External Interface | Internal Python API; MCPAdapter/A2AAdapter expose protocol adapters externally |
| Dependencies | app.infra.database, app.infra.redis_streams, app.infra.observability |
| Hub Module | registry.py — `get_service()`, `register_service()` |

**FR Coverage**: FR-39–43, FR-45, FR-54–56, FR-63–69, FR-100

#### Module: aee.py
- `ActionAdapter` abstract interface (`list_tools()`, `execute()`) → FR-39
- `MCPAdapter` (stdio/SSE) → FR-40
- `A2AAdapter` (agent card 300s TTL, JSON-RPC 2.0, timeout=2.0s, unreachable→empty) → FR-41
- `CLIAdapter` (sandboxed) → FR-42
- `ToolExecutor` (register/execute, get_shipping_status, update_shipping_address) → FR-43
- `ToolDefinition` shared dataclass (AEE+DST) → FR-45

**Architecture Risk**: aee.py makes network calls with retry (A2AAdapter HTTP, MCPAdapter stdio/SSE) → NP-07 + NP-15 forced

#### Module: escalation.py
- `EscalationManager.create()`, `.assign()`, `.resolve()` → FR-54
- `SLA_BY_PRIORITY` (normal=30m/high=15m/urgent=5m), `get_sla_breaches()` → FR-55
- WebSocket push on `escalation.new` to /ws/agent → FR-56

#### Module: ab_testing.py
- `ABTestManager.get_variant()` (SHA-256 deterministic), `run_experiment()`, `analyze_results()` → FR-63
- `auto_promote()` (min_sample=100, diff≥0.05, status='completed') → FR-64

#### Module: llm_judge.py
- `LLMJudge.evaluate()` (gpt-4o-mini + claude-3-5-haiku, temp=0, parallel) → FR-65
- Politeness aggregation: max() → FR-66
- Accuracy aggregation: min() → FR-67
- CSAT = 0.4×speed + 0.2×anthro + 0.2×politeness + 0.2×accuracy → FR-68
- Monthly calibration (500 golden, Kappa≥0.7, 15% deviation trigger) → FR-69

**Architecture Risk**: llm_judge.py makes parallel network calls to 2 LLM APIs → NP-07 + NP-15 forced

#### Module: media.py
- Image → auto_escalate → FR-100
- Sticker → fixed reply "請用文字描述您的問題" → FR-100
- Location → coords extraction → FR-100
- File: ClamAV scan (p95<500ms, fail-secure 503 FILE_SCAN_UNAVAILABLE), 10MB limit → FR-100

**Architecture Risk**: media.py calls external process (ClamAV via Docker) → NP-15 forced

#### Module: registry.py (Hub)
- `get_service(name)`, `register_service(name, instance)` — called by all sibling service modules
- Service health aggregation for /api/v1/health

### 2.5 Layer 4: Infrastructure (app/infra/)

| Attribute | Value |
|-----------|-------|
| Responsibility | Database, Redis, SAQ background jobs, circuit breaker, rate limiting, observability, security infra, deployment config |
| External Interface | None (internal infrastructure only) |
| Dependencies | External: PostgreSQL 16+pgvector, Redis 7, ClamAV, OpenAI, Prometheus |
| Hub Module | config.py — `get_setting()`, `health_probe()` |

**FR Coverage**: FR-21–25, FR-70–83, FR-89–90, FR-95–99

#### Module: database.py
- 20-table schema (users/conversations/messages/knowledge_base/knowledge_chunks/platform_configs/escalation_queue/user_feedback/security_logs/emotion_history/edge_cases/pii_vault/roles/role_assignments/pii_audit_log/experiments/experiment_results/retry_log/encryption_config/schema_migrations) → FR-82
- HNSW index (m=16, ef=64, partial) + GIN tsvector index (for level_embedding_down fallback) → FR-82
- Alembic upgrade/downgrade, staging→prod → FR-83

#### Module: rate_limit.py
- `RateLimiter.allow()` (Redis Lua ZSET, 30/10/100 rps) → FR-21
- Fail-open on Redis unavailable → FR-22
- `IPWhitelist.is_allowed()` (CIDR, max 100, X-Forwarded-For) → FR-23
- Middleware chain enforcement → FR-24
- `IPWhitelist.__init__()` (IPWhitelistError at startup), `is_allowed()` (→False, no exception) → FR-25

**Architecture Risk**: rate_limit.py uses Redis as optional dependency (cache) → NP-07 forced (fail-open path + cache-reachability required)

#### Module: redis_streams.py
- `AsyncMessageProcessor` (consumer group "omnibot", XREADGROUP, XACK, XCLAIM, BUSYGROUP→ignore) → FR-80
- `RetryStrategy.execute_with_retry()` (max=3, base=1s, max=30s, jitter) → FR-81
- Redis TLS 6380, requirepass env var, ACL default_user disabled, RDB+AOF → FR-90

**Architecture Risk**: redis_streams.py manages shared mutable state (stream offsets, consumer group positions) under async → NP-13 forced

#### Module: jobs.py
- SAQ worker (embedding/concurrency=3, maintenance/concurrency=1, notification/concurrency=5, grace=30s) → FR-75
- `EmbeddingJob` (max_retries=3, exp+jitter, p95<30s) → FR-76
- `create_knowledge_with_chunks()` (asyncio.wait_for 2.0s, searchable <2.5s) → FR-77
- `batch_import_knowledge()` (is_batch=True, <50ms/entry) → FR-78
- Embedding sync status (embedding_synced_at, 🟡🟢🔴) → FR-79

**Architecture Risk**: jobs.py uses retry logic + async queue → NP-07 + NP-15 forced

#### Module: circuit_breaker.py
- 9-level breaker: level_0=full; level_1=cache (LLM p95>800ms/2m); level_2=T1+T2 only (p95>1.5s/2m); level_3=T1 only (≥5 failures); level_4=DB→Redis cache (DB p95>2s/1m); level_embedding_down=tsvector fallback; level_classifier_down=bypass L4; level_judge_down=rule-based; level_5=static maintenance → FR-99
- Auto-recovery on consecutive success

**Architecture Risk**: circuit_breaker.py manages shared mutable state (level counters, probe state) under concurrent async access → NP-13 forced

#### Module: observability.py
- `StructuredLogger.log()` (JSON, ISO8601 Z) → FR-70
- 9 Prometheus metrics: response_duration_seconds(histogram), requests_total(counter), fcr_total(counter), knowledge_hit_total[tier](counter), pii_masked_total(counter), escalation_queue_size(gauge), emotion_escalation_total(counter), escalation_sla_breach_total(counter), llm_tokens_total[model](counter) → FR-71
- OTel span tree (handle_message→emotion→knowledge→response, trace_id via header) → FR-72
- 4 alert rules (HighLatency p95>0.8s/1.0s, HighErrorRate>0.5%, EscalationBacklog>50, SLABreach<90% for=0m) → FR-73
- Grafana dashboard (FCR/latency/knowledge/cost, 24hr/7d/30d) → FR-74

#### Module: security.py
- PostgreSQL TDE AES-256, 90-day key rotation, ssl_mode=verify-full → FR-89
- pii_vault access via app layer only (pii:decrypt required)

#### Module: deployment.py
- Docker Compose (omnibot-api/postgres/redis/otel-collector/prometheus/grafana/clamav:alpine, healthchecks) → FR-95
- K8s (Deployment replicas=3, HPA min=3/max=10/CPU=70%, PDB minAvailable=2, SealedSecrets, requests{cpu:500m,mem:512Mi}/limits{cpu:2000m,mem:2Gi}) → FR-96
- Backup (pg_basebackup+WAL 30d, Redis RDB+AOF 7d) → FR-97
- Rollback (version+is_active soft-delete, A/B 10%→50%→100%, Alembic downgrade, experiment_abort) → FR-98

#### Module: config.py (Hub)
- `get_setting(key, default)` — typed env var access; called by all infra modules per function body
- `health_probe(service)` — called by all infra modules for health reporting
- Environment: OPENAI_API_KEY, FALLBACK_LLM_MODEL (gemini-1.5-flash), REDIS_URL, DATABASE_URL, IP_WHITELIST_CIDRS

### 2.6 Layer 5: Admin (app/admin/)

| Attribute | Value |
|-----------|-------|
| Responsibility | RBAC enforcement, GDPR data lifecycle, admin WebUI backend, ODD SQL analytics |
| External Interface | Internal Python API; RBAC decorator applied at API layer |
| Dependencies | app.infra.database, app.infra.observability, app.infra.config |
| Hub Module | reports.py — `log_admin_action()`, `build_report()` |

**FR Coverage**: FR-60–62, FR-91–94, FR-101–105

#### Module: rbac.py
- `ROLE_PERMISSIONS` (7 roles: anonymous/customer/agent/editor/admin/auditor/dpo) → FR-60
- Explicit `pii:none` for auditor (→403 on pii:decrypt attempt); `pii:decrypt` for dpo only → FR-61
- `RBACEnforcer.require(resource, action)` decorator → 403 AUTHZ_INSUFFICIENT_ROLE → FR-62

#### Module: gdpr.py
- Retention: conversations 180d→archive(Parquet/S3)→2yr delete; PII audit 90d anonymize; emotion 90d delete; security logs 1yr→archive → FR-91
- `execute_data_deletion()` (users.profile=NULL, messages.content='[REDACTED]', pii_audit_log gdpr_deletion, 30d SLA) → FR-92
- Data export JSON+CSV → FR-93
- `pii_vault` (BYTEA encrypted, KMS, dpo-only decrypt) → FR-94

#### Module: webui.py
- Knowledge CRUD + Markdown editor + CSV/JSON import + embedding status (🟡🟢🔴) → FR-101
- RAG Debugger (ILIKE+cosine+RRF k=60, threshold slider 0.75, session-only) → FR-102
  - Implementation: runs diagnostic SQL directly against `app.infra.database` using pgvector `<=>` cosine operator and ILIKE — does NOT import or call `app.core.knowledge`. RRF fusion computed in Python from raw DB results. Consistent with admin-only-depends-on-infra SAB constraint.
- Operations Dashboard (FCR/latency/knowledge/cost, 24hr/7d/30d) → FR-103
- Agent Portal (inbox/WS/takeover, priority colors urgent=red/high=orange/normal=blue, DST slot sidebar) → FR-104

#### Module: odd_sql.py
- 10 ODD SQL queries (FCR/p95-latency/knowledge-hit/CSAT/feedback/SLA/emotion/security-block/cost/PII-audit) → FR-105
- Judge sampling: default 20% (0.01–1.0 configurable), `judge_sample_rate` stored in experiments table → FR-105

#### Module: reports.py (Hub)
- `log_admin_action(action, actor, resource)` — called by rbac/gdpr/webui/odd_sql per function body
- `build_report(query, params)` — shared SQL execution wrapper

---

## 3. Error Handling

| Level | Condition | Strategy |
|-------|-----------|----------|
| L0 — Input Validation | Invalid request format, missing fields | FastAPI validation → 422 VALIDATION_ERROR |
| L1 — Auth Failure | Invalid signature, expired JWT, bad M2M token | → 401 AUTH_INVALID_SIGNATURE / AUTH_TOKEN_EXPIRED |
| L2 — Authorization | Insufficient RBAC permission | → 403 AUTHZ_INSUFFICIENT_ROLE |
| L3 — Rate Limit | Platform-specific rps exceeded | → 429 RATE_LIMIT_EXCEEDED |
| L4 — Service Degraded | LLM timeout, Embedding API down | Circuit breaker level escalation; graceful degradation |
| L5 — Redis Unavailable | Rate limiter / stream consumer | Fail-open (rate limit), XCLAIM recovery (streams) |
| L6 — DB Unavailable | PostgreSQL down | Circuit breaker level_4 → Redis cache mode |
| L7 — ClamAV Unavailable | Docker service down | Fail-secure 503 FILE_SCAN_UNAVAILABLE |
| L8 — Security Block | PALADIN injection detected | Retraction + `injection_retrospective_block` logged |
| L9 — Unrecoverable | All tiers exhausted | Escalate to human (Tier 4), level_5 static page |

---

## 4. Technology Choices

| Technology | Version | Rationale |
|------------|---------|-----------|
| Python | 3.11 | asyncio maturity, type hints, SRS constraint |
| FastAPI | latest | Async-native, OpenAPI auto-doc, WebSocket support |
| PostgreSQL | 16 + pgvector | HNSW vector index (m=16, ef=64), GIN tsvector fallback |
| Redis | 7 alpine | ZSET rate limiting (Lua atomic), Streams consumer groups, TLS 6380 |
| SAQ | latest | Lightweight Redis-backed async queue (vs Celery overhead) |
| OpenAI text-embedding-3-small | 1536-dim | SRS EMBEDDING_DIM=1536, Recall@3≥92% achievable |
| tiktoken cl100k_base | — | Consistent token budget for gpt-4o + gemini fallback |
| pgvector HNSW | m=16 ef=64 | Recall@3≥92% at p95<100ms embedding search |
| Prometheus + OTel | — | 9 metrics + full span tree per request |
| Alembic | — | Bidirectional DB migration with downgrade() |
| k6 | — | 4-scenario load test (smoke/load/stress/spike, 2000 TPS target) |
| ClamAV | alpine | Fail-secure malware scan, p95<500ms, Docker service |
| SealedSecrets | — | K8s secrets injection without plaintext ConfigMap |

---

## 5. Architecture Risk Registry (for TEST_SPEC Step 1b)

The following modules have architecture-risk traits that FORCE NFR patterns in TEST_SPEC regardless of SRS keyword presence:

| Module | Risk Trait | Forced Patterns | Notes |
|--------|-----------|-----------------|-------|
| `app.core.paladin` | Network client (L4 LLM) | NP-07, NP-15 | L4 timeout→unverified passthrough |
| `app.core.knowledge` | Network client + retry (LLM + Embedding) | NP-07, NP-15 | T3 fallback <500ms; L5 grounding |
| `app.core.dst` | Shared mutable FSM state | NP-13 | 8-state FSM under concurrent sessions |
| `app.infra.circuit_breaker` | Shared mutable state (level counters) | NP-13 | Level transitions under concurrent load |
| `app.infra.redis_streams` | Shared mutable state (stream offsets) + async | NP-13 | Consumer group XCLAIM race |
| `app.infra.rate_limit` | Optional cache (Redis) | NP-07 | Fail-open on Redis unavailable |
| `app.infra.jobs` | Retry logic + async queue | NP-07, NP-15 | EmbeddingJob retries + 2.0s sync timeout |
| `app.services.aee` | Network client + retry (A2AAdapter, MCPAdapter) | NP-07, NP-15 | 2.0s A2A timeout; unreachable→empty |
| `app.services.llm_judge` | Parallel network calls (2 LLMs) | NP-07, NP-15 | Both judges parallel; partial failure |
| `app.services.media` | External process (ClamAV Docker) | NP-15 | ClamAV down→fail-secure 503 |

### 5.2 CRG Architecture Dimension Risks (Gate 3/4)

These entries document modules evaluated against CRG scoring criteria for Gate 3/4. Entries marked "will NOT trigger" were assessed and confirmed below threshold.

| Module | CRG Evaluation | Result | Gate Handling |
|--------|---------------|--------|---------------|
| `app.core.pipeline` | Star-topology orchestrator evaluated for Leiden false positive. Harness detection criteria (`evaluate_dimension.md` §Orchestrator Pattern): community size > 50 AND hub fan_out > 8. Actual: core community size = 7 nodes (pipeline + 6 siblings); pipeline fan_out = 6. Both thresholds NOT met. | **Will NOT trigger** Leiden false positive | No DA waiver needed. No Gate action required for this module. |
| `app.infra.config` | Hub fan_in = 8: all 8 sibling infra modules (database / rate_limit / redis_streams / jobs / circuit_breaker / observability / security / deployment) import config. Exactly hits `HUB_HIGH_FAN_IN = 8` threshold (`harness/harness/ssi/scripts/crg_analysis.py:65 — HUB_HIGH_FAN_IN = _ti('CRG_HUB_HIGH_FANIN', 8)`) → CRG emits advisory finding (high severity if untested, medium if tested). Does not affect `community_cohesion.score`. | **Will trigger** HUB_HIGH_FAN_IN advisory | No score impact. Document as intentional infrastructure hub pattern in Gate 3 architecture findings. |

---

## 6. Data Flow Diagrams

### 6.1 Main Request Flow

```
Client → [TLS] → [IPWhitelist] → [WebhookSig] → [PlatformAdapter] → UnifiedMessage
  → [RateLimiter] → [RBAC] → pipeline.handle_message()
    → paladin.process()         (L1→L2→L3→L4/parallel→L5)
    → pii.mask()
    → dst.transition()          (slot resolution first)
    → knowledge.query()         (after DST slot resolution)
    → emotion.analyze()
    → response.generate()
  → UnifiedResponse → platform format adapter → Client
```

### 6.2 Knowledge Query Flow (T1→T4)

```
HybridKnowledge.query(text)
  → T1: _rule_match()       confidence≥0.80 → return source="rule"
  → T2: _rag_search()       confidence≥0.85 → return source="rag"
       + _reciprocal_rank_fusion() RRF k=60
  → T3: _llm_generate()     gpt-4o → gemini fallback
       + GroundingChecker     cosine≥0.75 → return source="wiki"
  → T4: _escalate()          → return source="escalate", id=-1
```

### 6.3 Circuit Breaker Level Flow

```
level_0 (full) ←→ level_1 (cache) ←→ level_2 (T1+T2 only) ←→ level_3 (T1 only) ←→ level_5 (static)
     ↕                                    ↕
level_4 (DB→Redis)                 level_embedding_down (tsvector)
                                   level_classifier_down (bypass L4)
                                   level_judge_down (rule-based judge)
```

---

## 7. SAB Block (machine-readable — BINDING CONTRACT)

<!-- SAB:START -->
```yaml
sab:
  version: "1.0"
  created_at: "2026-06-18"
  phase: 2
  project: "omnibot"

  layers:
    - name: api
      modules:
        - app.api.common
        - app.api.main
        - app.api.webhooks
        - app.api.management
        - app.api.auth
        - app.api.websocket
        - app.api.agent_card
      allowed_dependencies: ["core", "infra", "admin"]

    - name: core
      modules:
        - app.core.pipeline
        - app.core.paladin
        - app.core.pii
        - app.core.knowledge
        - app.core.dst
        - app.core.response
        - app.core.emotion
      allowed_dependencies: ["infra", "services"]

    - name: services
      modules:
        - app.services.registry
        - app.services.aee
        - app.services.escalation
        - app.services.ab_testing
        - app.services.llm_judge
        - app.services.media
      allowed_dependencies: ["infra"]

    - name: infra
      modules:
        - app.infra.config
        - app.infra.database
        - app.infra.rate_limit
        - app.infra.redis_streams
        - app.infra.jobs
        - app.infra.circuit_breaker
        - app.infra.observability
        - app.infra.security
        - app.infra.deployment
      allowed_dependencies: []

    - name: admin
      modules:
        - app.admin.reports
        - app.admin.rbac
        - app.admin.gdpr
        - app.admin.webui
        - app.admin.odd_sql
      allowed_dependencies: ["infra"]

  allowed_dependencies:
    - from: api
      to: core
    - from: api
      to: infra
    - from: api
      to: admin
    - from: core
      to: infra
    - from: core
      to: services
    - from: services
      to: infra
    - from: admin
      to: infra

  quality_targets:
    max_complexity: 15
    min_coverage: 80
    max_coupling: 0.3

  nfr_dimension_mapping: {}  # OPTIONAL — auto-derived from nfr_traceability.type by sab_parser.py

  nfr_traceability:
    NFR-01:
      type: performance
      target: "p95 < 1000ms"
      module: app.core.pipeline
    NFR-02:
      type: performance
      target: "p95 < 5ms"
      module: app.core.paladin
    NFR-03:
      type: performance
      target: "p95 < 200ms"
      module: app.core.paladin
    NFR-04:
      type: performance
      target: "p95 < 300ms"
      module: app.core.knowledge
    NFR-05:
      type: performance
      target: "timeout = 2000ms"
      module: app.services.aee
    NFR-06:
      type: performance
      target: "p95 < 500ms"
      module: app.core.knowledge
    NFR-07:
      type: performance
      target: "cache_ttl = 300s"
      module: app.services.aee
    NFR-08:
      type: performance
      target: "p95 < 30000ms"
      module: app.infra.jobs
    NFR-09:
      type: performance
      target: ">=2000 TPS"
      module: app.api.webhooks
    NFR-10:
      type: reliability
      target: ">=99.9% uptime per month"
      module: app.infra.circuit_breaker
    NFR-11:
      type: reliability
      target: ">=99.95% early warning threshold"
      module: app.infra.observability
    NFR-12:
      type: reliability
      target: "p95 > 800ms triggers HighLatency alert"
      module: app.infra.observability
    NFR-13:
      type: reliability
      target: "error_rate > 0.5% triggers alert"
      module: app.infra.observability
    NFR-14:
      type: reliability
      target: "DR recovery < 5 minutes"
      module: app.infra.deployment
    NFR-15:
      type: security
      target: "OWASP LLM01:2025 compliant"
      module: app.core.paladin
    NFR-16:
      type: security
      target: ">=95% security block rate"
      module: app.core.paladin
    NFR-17:
      type: security
      target: "zero secrets in VCS"
      module: app.infra.security
    NFR-18:
      type: usability
      target: "< $500 / month infrastructure cost"
      module: app.infra.deployment
    NFR-19:
      type: usability
      target: "~ $210 / month LLM API cost"
      module: app.services.llm_judge
    NFR-20:
      type: deployability
      target: "Taiwan PDA compliance"
      module: app.admin.gdpr
    NFR-21:
      type: deployability
      target: "GDPR Art.5(1)(e) data minimization"
      module: app.admin.gdpr
    NFR-22:
      type: deployability
      target: "SOC2 audit trail"
      module: app.infra.observability
    NFR-23:
      type: testability
      target: ">=90% FCR (in_scope conversations)"
      module: app.admin.odd_sql
    NFR-24:
      type: testability
      target: ">=4.8 CSAT score"
      module: app.services.llm_judge
    NFR-25:
      type: testability
      target: ">=95% escalation SLA compliance"
      module: app.services.escalation
    NFR-26:
      type: testability
      target: ">=0.7 Cohen's Kappa vs human annotation"
      module: app.services.llm_judge
    NFR-27:
      type: testability
      target: "100% grounding check pass rate (cosine>=0.75)"
      module: app.core.paladin
    NFR-28:
      type: testability
      target: ">=92% Recall@3 HNSW 1536-dim"
      module: app.core.knowledge
    NFR-29:
      type: testability
      target: ">=95% agentic tool success rate"
      module: app.services.aee
    NFR-30:
      type: scalability
      target: "HPA min=3 max=10 CPU=70%"
      module: app.infra.deployment
    NFR-31:
      type: maintainability
      target: "100% request OTel trace coverage"
      module: app.infra.observability
    NFR-32:
      type: testability
      target: "unit>=70% integration>=20% e2e>=10%"
      module: tests.strategy
    NFR-33:
      type: reliability
      target: "rate_limit fail-open on Redis unavailable"
      module: app.infra.rate_limit
    NFR-34:
      type: reliability
      target: "IP whitelist fail-secure 403 on no match"
      module: app.infra.rate_limit
    NFR-35:
      type: reliability
      target: "max 100 CIDR blocks"
      module: app.infra.rate_limit
    NFR-36:
      type: security
      target: "M2M token 90-day expiry; 24hr overlap on rotate"
      module: app.api.auth
    NFR-37:
      type: performance
      target: "p95 < 1500ms WebUI response"
      module: app.admin.webui
    NFR-38:
      type: performance
      target: "p95 < 500ms ClamAV scan"
      module: app.services.media

  advisory_only: []

  gate_score_overrides: {}

  fr_module_traceability:
    FR-01: "app.api.webhooks"
    FR-02: "app.api.webhooks"
    FR-03: "app.api.webhooks"
    FR-04: "app.api.webhooks"
    FR-05: "app.api.webhooks"
    FR-06: "app.api.webhooks"
    FR-07: "app.api.common"
    FR-08: "app.api.common"
    FR-09: "app.api.common"
    FR-10: "app.core.paladin"
    FR-11: "app.core.paladin"
    FR-12: "app.core.paladin"
    FR-13: "app.core.paladin"
    FR-14: "app.core.paladin"
    FR-15: "app.core.paladin"
    FR-16: "app.core.paladin"
    FR-17: "app.core.paladin"
    FR-18: "app.core.pii"
    FR-19: "app.core.pii"
    FR-20: "app.core.pii"
    FR-21: "app.infra.rate_limit"
    FR-22: "app.infra.rate_limit"
    FR-23: "app.infra.rate_limit"
    FR-24: "app.infra.rate_limit"
    FR-25: "app.infra.rate_limit"
    FR-26: "app.core.knowledge"
    FR-27: "app.core.knowledge"
    FR-28: "app.core.knowledge"
    FR-29: "app.core.knowledge"
    FR-30: "app.core.knowledge"
    FR-31: "app.core.knowledge"
    FR-32: "app.core.knowledge"
    FR-33: "app.core.knowledge"
    FR-34: "app.core.dst"
    FR-35: "app.core.dst"
    FR-36: "app.core.dst"
    FR-37: "app.core.dst"
    FR-38: "app.core.dst"
    FR-39: "app.services.aee"
    FR-40: "app.services.aee"
    FR-41: "app.services.aee"
    FR-42: "app.services.aee"
    FR-43: "app.services.aee"
    FR-44: "app.api.agent_card"
    FR-45: "app.services.aee"
    FR-46: "app.core.emotion"
    FR-47: "app.core.emotion"
    FR-48: "app.core.emotion"
    FR-49: "app.core.emotion"
    FR-50: "app.core.response"
    FR-51: "app.core.response"
    FR-52: "app.core.response"
    FR-53: "app.core.response"
    FR-54: "app.services.escalation"
    FR-55: "app.services.escalation"
    FR-56: "app.services.escalation"
    FR-57: "app.api.websocket"
    FR-58: "app.api.websocket"
    FR-59: "app.api.websocket"
    FR-60: "app.admin.rbac"
    FR-61: "app.admin.rbac"
    FR-62: "app.admin.rbac"
    FR-63: "app.services.ab_testing"
    FR-64: "app.services.ab_testing"
    FR-65: "app.services.llm_judge"
    FR-66: "app.services.llm_judge"
    FR-67: "app.services.llm_judge"
    FR-68: "app.services.llm_judge"
    FR-69: "app.services.llm_judge"
    FR-70: "app.infra.observability"
    FR-71: "app.infra.observability"
    FR-72: "app.infra.observability"
    FR-73: "app.infra.observability"
    FR-74: "app.infra.observability"
    FR-75: "app.infra.jobs"
    FR-76: "app.infra.jobs"
    FR-77: "app.infra.jobs"
    FR-78: "app.infra.jobs"
    FR-79: "app.infra.jobs"
    FR-80: "app.infra.redis_streams"
    FR-81: "app.infra.redis_streams"
    FR-82: "app.infra.database"
    FR-83: "app.infra.database"
    FR-84: "app.api.webhooks"
    FR-85: "app.api.management"
    FR-86: "app.api.auth"
    FR-87: "app.api.auth"
    FR-88: "app.api.management"
    FR-89: "app.infra.security"
    FR-90: "app.infra.redis_streams"
    FR-91: "app.admin.gdpr"
    FR-92: "app.admin.gdpr"
    FR-93: "app.admin.gdpr"
    FR-94: "app.admin.gdpr"
    FR-95: "app.infra.deployment"
    FR-96: "app.infra.deployment"
    FR-97: "app.infra.deployment"
    FR-98: "app.infra.deployment"
    FR-99: "app.infra.circuit_breaker"
    FR-100: "app.services.media"
    FR-101: "app.admin.webui"
    FR-102: "app.admin.webui"
    FR-103: "app.admin.webui"
    FR-104: "app.admin.webui"
    FR-105: "app.admin.odd_sql"
    FR-106: "tests.load"
    FR-107: "tests.strategy"
    FR-108: "tests.strategy"

  architecture_constraints:
    - "no_circular_dependencies"
    - "api_layer_no_business_logic"
    - "infra_layer_no_domain_imports"
    - "paladin_executes_before_pii"
    - "knowledge_query_after_dst_slot_resolution"

  high_risk_modules:
    - "app.core.paladin"
    - "app.core.knowledge"
    - "app.core.dst"
    - "app.infra.circuit_breaker"
    - "app.infra.redis_streams"
    - "app.infra.rate_limit"
    - "app.infra.jobs"
    - "app.services.aee"
    - "app.services.llm_judge"
    - "app.services.media"
```
<!-- SAB:END -->
