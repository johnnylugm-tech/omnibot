# SPEC_TRACKING — OmniBot 規格追蹤矩陣

> **Source**: SRS.md (Approved Round 2) — 2026-06-17
> **Authored**: 2026-06-17 — Agent A: REQUIREMENTS_ENGINEER
> **Project**: omnibot
> **Phase**: 1

---

## 欄位說明

| 欄位 | 說明 |
|------|------|
| FR ID | 功能需求編號，對應 SRS.md FR-XX |
| Title | 功能模組與簡短描述 |
| Module | 所屬模組 |
| Status | Pending / In-Progress / Done / Deferred |
| Owner | BE=Backend Engineer, SRE=Site Reliability Engineer, FE=Frontend Engineer, PM=Product Manager |
| Priority | P0=必須 / P1=高 / P2=中 |
| Milestone | 對應 PROJECT_BRIEF Milestone（M1/M2/M3/M4） |
| SRS Coverage | 對應 SRS.md 章節 |

---

## FR 追蹤矩陣

### Module 1: Platform Adapter Layer

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-01 | Telegram Webhook Adapter (HMAC-SHA256) | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-02 | LINE Webhook Adapter (HMAC-SHA256 Base64) | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-03 | Messenger Webhook Adapter (GET+POST) | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-04 | WhatsApp Webhook Adapter (sha256= prefix) | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-05 | Web Platform Adapter (Guest JWT + JWT BearerAuth) | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-06 | A2A Platform Adapter (JSON-RPC 2.0 + M2M JWT) | Platform Adapter | ✅ Done | BE | P0 | M4 | SRS §2 Module 1 |
| FR-07 | UnifiedMessage immutable dataclass | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-08 | UnifiedResponse immutable dataclass | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |
| FR-09 | ApiResponse[T] + PaginatedResponse[T] unified format | Platform Adapter | ✅ Done | BE | P0 | M1 | SRS §2 Module 1 |

### Module 2: Security — PALADIN 五層防禦

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-10 | PALADIN L1 InputSanitizer (NFKC + homoglyph, <2ms) | Security | ✅ Done | BE | P0 | M1 | SRS §2 Module 2 |
| FR-11 | PALADIN L2 Pattern Detection (13 regex, <3ms) | Security | ✅ Done | BE | P0 | M1 | SRS §2 Module 2 |
| FR-12 | PALADIN L3 Sandwich Prompt + Spotlighting (<5ms total) | Security | ✅ Done | BE | P0 | M2 | SRS §2 Module 2 |
| FR-13 | PALADIN L4 SemanticInjectionClassifier (LLM, <200ms) | Security | ✅ Done | BE | P0 | M4 | SRS §2 Module 2 |
| FR-14 | PALADIN L5 GroundingChecker (cosine ≥0.75, <5ms) | Security | ✅ Done | BE | P0 | M2 | SRS §2 Module 2 |
| FR-15 | L4 Parallel Pipeline (low/medium/high/critical routing) | Security | ✅ Done | BE | P0 | M4 | SRS §2 Module 2 |
| FR-16 | L4 Retrospective Block (injection_retrospective_block) | Security | ✅ Done | BE | P0 | M4 | SRS §2 Module 2 |
| FR-17 | Per-Platform L4 Retraction + Failure Path (fail-secure) | Security | ✅ Done | BE | P0 | M4 | SRS §2 Module 2 |

### Module 3: PII 去識別化

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-18 | PIIMasking (phone/email/address/credit card + Luhn) | PII | ✅ Done | BE | P0 | M1 | SRS §2 Module 3 |
| FR-19 | PII Sensitive Keyword Escalation (should_escalate) | PII | ✅ Done | BE | P0 | M1 | SRS §2 Module 3 |
| FR-20 | PII Audit Log (pii_audit_log + 90-day anonymize) | PII | ✅ Done | BE | P0 | M2 | SRS §2 Module 3 |

### Module 4: Rate Limiting & IP Whitelist

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-21 | Redis Sliding Window Rate Limiter (Lua atomic ZSET) | Rate Limiting | ✅ Done | BE | P0 | M1 | SRS §2 Module 4 |
| FR-22 | Rate Limiter Fail-open (Redis unavailable) | Rate Limiting | ✅ Done | BE | P0 | M1 | SRS §2 Module 4 |
| FR-23 | IP Whitelist CIDR (max 100, X-Forwarded-For, fail-secure) | IP Whitelist | ✅ Done | BE | P0 | M1 | SRS §2 Module 4 |
| FR-24 | Middleware Chain Order (TLS→IP→Sig→Parse→Rate→RBAC) | Security | ✅ Done | BE | P0 | M1 | SRS §2 Module 4 |
| FR-25 | IP Whitelist Error Handling (IPWhitelistError at startup) | IP Whitelist | ✅ Done | BE | P0 | M1 | SRS §2 Module 4 |

### Module 5: Hybrid Knowledge Layer

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-26 | Knowledge Tier 1 Rule Matching (ILIKE, conf≥0.80) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-27 | Knowledge Tier 2 RAG+RRF (HNSW 1536-dim, k=60, conf≥0.85) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-28 | Parent-Child Chunking (500-token parent, 150-token child) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-29 | HNSW Vector Index (m=16, ef_construction=64, partial) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-30 | Knowledge Tier 3 LLM Generation (gpt-4o→gemini fallback) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-31 | Knowledge Tier 4 Human Escalation (id=-1, reasons) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-32 | KnowledgeResult frozen dataclass | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |
| FR-33 | HybridKnowledge Query Orchestrator (T1→T4 sequential) | Knowledge | ✅ Done | BE | P0 | M1 | SRS §2 Module 5 |

### Module 6: DST 對話狀態追蹤

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-34 | 8-State FSM (ALLOWED_TRANSITIONS, ValueError on invalid) | DST | ✅ Done | BE | P0 | M1 | SRS §2 Module 6 |
| FR-35 | Slot Filling (order_status/return_request + missing_slots) | DST | ✅ Done | BE | P0 | M1 | SRS §2 Module 6 |
| FR-36 | Auto-Escalate (>3 slot rounds or confidence<0.65) | DST | ✅ Done | BE | P0 | M1 | SRS §2 Module 6 |
| FR-37 | AWAITING_CONFIRMATION Timeout (>2 rounds → ESCALATED) | DST | ✅ Done | BE | P0 | M1 | SRS §2 Module 6 |
| FR-38 | Context Window (tiktoken cl100k_base, 8192 tokens, summarize) | DST | ✅ Done | BE | P0 | M1 | SRS §2 Module 6 |

### Module 7: Action Execution Engine (Agentic)

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-39 | ActionAdapter Abstract Interface (list_tools + execute) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |
| FR-40 | MCPAdapter (stdio/SSE to MCP Server) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |
| FR-41 | A2AAdapter (agent card 300s TTL, JSON-RPC 2.0, timeout=2s) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |
| FR-42 | CLIAdapter (sandboxed script execution) | AEE | ✅ Done | BE | P1 | M4 | SRS §2 Module 7 |
| FR-43 | ToolExecutor (register+execute, shipping status/address) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |
| FR-44 | OmniBot Agent Card (GET /.well-known/agent.json) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |
| FR-45 | ToolDefinition Shared Dataclass (AEE+DST no duplication) | AEE | ✅ Done | BE | P0 | M4 | SRS §2 Module 7 |

### Module 8: Emotion Analyzer

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-46 | EmotionAnalyzer (positive/neutral/negative, intensity 0–1) | Emotion | ✅ Done | BE | P0 | M2 | SRS §2 Module 8 |
| FR-47 | Temporal Decay (24hr half-life exponential decay) | Emotion | ✅ Done | BE | P0 | M2 | SRS §2 Module 8 |
| FR-48 | Consecutive Negative Escalation (≥3 → should_escalate) | Emotion | ✅ Done | BE | P0 | M2 | SRS §2 Module 8 |
| FR-49 | AGENT Platform Bypass (skip emotion analysis) | Emotion | ✅ Done | BE | P0 | M2 | SRS §2 Module 8 |

### Module 9: Response Generator

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-50 | Template System (rule_default/rag_default/escalate) | Response | ✅ Done | BE | P0 | M4 | SRS §2 Module 9 |
| FR-51 | Emotion Tone Modulation (intensity>0.7→apology, repeat suppress) | Response | ✅ Done | BE | P0 | M4 | SRS §2 Module 9 |
| FR-52 | A/B Variant Injection (SHA-256, variant_a/b, control) | Response | ✅ Done | BE | P0 | M4 | SRS §2 Module 9 |
| FR-53 | Platform Format Adapter (per-platform char limits) | Response | ✅ Done | BE | P0 | M4 | SRS §2 Module 9 |

### Module 10: Human Escalation

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-54 | EscalationManager CRUD (create/assign/resolve) | Escalation | ✅ Done | BE | P0 | M2 | SRS §2 Module 10 |
| FR-55 | SLA Definitions (normal=30m, high=15m, urgent=5m) | Escalation | ✅ Done | BE | P0 | M2 | SRS §2 Module 10 |
| FR-56 | WebSocket Escalation Push (/ws/agent, escalation.new payload) | Escalation | ✅ Done | BE | P0 | M2 | SRS §2 Module 10 |

### Module 11: WebSocket 端點

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-57 | /ws/agent WebSocket (6 event types, JWT auth) | WebSocket | ✅ Done | BE | P0 | M4 | SRS §2 Module 11 |
| FR-58 | /ws/user WebSocket (message.reply push) | WebSocket | ✅ Done | BE | P0 | M4 | SRS §2 Module 11 |
| FR-59 | WebSocket Heartbeat (30s ping, 10s timeout, subscribe) | WebSocket | ✅ Done | BE | P0 | M4 | SRS §2 Module 11 |

### Module 12: RBAC 權限管理

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-60 | 7 RBAC Roles (anonymous/customer/agent/editor/admin/auditor/dpo) | RBAC | ✅ Done | BE | P0 | M2 | SRS §2 Module 12 |
| FR-61 | Permission Matrix (auditor pii:none explicit → 403 on decrypt) | RBAC | ✅ Done | BE | P0 | M2 | SRS §2 Module 12 |
| FR-62 | RBACEnforcer Decorator (@rbac.require → 403 AUTHZ_INSUFFICIENT_ROLE) | RBAC | ✅ Done | BE | P0 | M2 | SRS §2 Module 12 |

### Module 13: A/B Testing

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-63 | ABTestManager SHA-256 Deterministic Variant Assignment | A/B Testing | ✅ Done | BE | P1 | M2 | SRS §2 Module 13 |
| FR-64 | auto_promote (min_sample=100, threshold=0.05, status='completed') | A/B Testing | ✅ Done | BE | P1 | M2 | SRS §2 Module 13 |

### Module 14: LLM-as-a-Judge

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-65 | Ensemble Judge (gpt-4o-mini + claude-3-5-haiku, temp=0, parallel) | Judge | ✅ Done | BE | P1 | M3 | SRS §2 Module 14 |
| FR-66 | Politeness Aggregation max(primary, secondary) | Judge | ✅ Done | BE | P1 | M3 | SRS §2 Module 14 |
| FR-67 | Accuracy Aggregation min(primary, secondary) | Judge | ✅ Done | BE | P1 | M3 | SRS §2 Module 14 |
| FR-68 | CSAT Formula (0.4×speed + 0.2×anthro + 0.2×pol + 0.2×acc) | Judge | ✅ Done | BE | P1 | M3 | SRS §2 Module 14 |
| FR-69 | Monthly Calibration (500 golden set, Kappa≥0.7, 15% trigger) | Judge | ✅ Done | PM | P1 | M3 | SRS §2 Module 14 |

### Module 15: 可觀測性

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-70 | StructuredLogger JSON Format (ISO 8601 Z timestamps) | Observability | ✅ Done | BE | P0 | M2 | SRS §2 Module 15 |
| FR-71 | 11 Prometheus Metrics (all explicitly named with labels) | Observability | ✅ Done | SRE | P0 | M2 | SRS §2 Module 15 |
| FR-72 | OpenTelemetry Full Span Tree per Request | Observability | ✅ Done | SRE | P0 | M2 | SRS §2 Module 15 |
| FR-73 | 4 Alert Rules (HighLatency/HighErrorRate/Backlog/SLABreach) | Observability | ✅ Done | SRE | P0 | M2 | SRS §2 Module 15 |
| FR-74 | Grafana Dashboard (FCR/latency/knowledge/cost, 24hr/7d/30d) | Observability | ✅ Done | SRE | P1 | M2 | SRS §2 Module 15 |

### Module 16: Background Job System

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-75 | SAQ Worker (3 queues: embedding/maintenance/notification) | Background Jobs | ✅ Done | BE | P0 | M4 | SRS §2 Module 16 |
| FR-76 | EmbeddingJob (max_retries=3, exp backoff+jitter, p95<30s) | Background Jobs | ✅ Done | BE | P0 | M4 | SRS §2 Module 16 |
| FR-77 | Sync First Chunk Embedding (asyncio.wait_for 2.0s timeout) | Background Jobs | ✅ Done | BE | P0 | M4 | SRS §2 Module 16 |
| FR-78 | Batch Import Mode (is_batch=True → full async, <50ms/entry) | Background Jobs | ✅ Done | BE | P1 | M4 | SRS §2 Module 16 |
| FR-79 | Embedding Sync Status UI (syncing/synced/failed) | Background Jobs | ✅ Done | FE | P1 | M4 | SRS §2 Module 16 |

### Module 17: High Availability

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-80 | Redis Streams (consumer group, XCLAIM, forward compat) | HA | ✅ Done | BE | P0 | M2 | SRS §2 Module 17 |
| FR-81 | Exponential Backoff Retry (max=3, base=1s, max=30s, jitter) | HA | ✅ Done | BE | P0 | M2 | SRS §2 Module 17 |

### Module 18: Data Layer

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-82 | 20-Table DB Schema + HNSW Index + GIN tsvector Index | Data | ✅ Done | BE | P0 | M1 | SRS §2 Module 18 |
| FR-83 | Alembic Migrations (upgrade+downgrade, staging→prod) | Data | ✅ Done | BE | P0 | M1 | SRS §2 Module 18 |

### Module 19: API 端點

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-84 | Webhook APIs (6 platform endpoints, error codes spec) | API | ✅ Done | BE | P0 | M1 | SRS §2 Module 19 |
| FR-85 | Management APIs (8 endpoints, RBAC-protected) | API | ✅ Done | BE | P0 | M1 | SRS §2 Module 19 |
| FR-86 | Auth & User API (login/refresh/users/roles) | API | ✅ Done | BE | P0 | M4 | SRS §2 Module 19 |
| FR-87 | M2M Token API (create/list/revoke/rotate, 24hr overlap) | API | ✅ Done | BE | P0 | M4 | SRS §2 Module 19 |
| FR-88 | GDPR API (export JSON/CSV + async deletion 30d SLA) | API | ✅ Done | BE | P0 | M4 | SRS §2 Module 19 |

### Module 20: 安全基礎設施

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-89 | TDE AES-256 (90-day key rotation, ssl_mode=verify-full) | Security Infra | ✅ Done | SRE | P0 | M3 | SRS §2 Module 20 |
| FR-90 | Redis Security (TLS 6380, env var AUTH, ACL, RDB+AOF) | Security Infra | ✅ Done | SRE | P0 | M3 | SRS §2 Module 20 |

### Module 21: GDPR & Data Lifecycle

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-91 | Data Retention Policy (180d→archive→2yr delete, PII 90d) | GDPR | ✅ Done | BE | P0 | M4 | SRS §2 Module 21 |
| FR-92 | Right to Erasure (async deletion, [REDACTED], 30d SLA) | GDPR | ✅ Done | BE | P0 | M4 | SRS §2 Module 21 |
| FR-93 | Right of Access + Portability (JSON + CSV export) | GDPR | ✅ Done | BE | P0 | M4 | SRS §2 Module 21 |
| FR-94 | pii_vault Encrypted Storage (BYTEA, KMS, dpo-only decrypt) | GDPR | ✅ Done | BE | P0 | M4 | SRS §2 Module 21 |

### Module 22: Deployment

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-95 | Docker Compose (7 services incl. clamav:alpine, healthcheck) | Deployment | ✅ Done | SRE | P0 | M3 | SRS §2 Module 22 |
| FR-96 | Kubernetes (Deployment+HPA+PDB+NetworkPolicy+SealedSecrets) | Deployment | ✅ Done | SRE | P0 | M3 | SRS §2 Module 22 |
| FR-97 | Backup Strategy (pg_basebackup+WAL 30d, Redis RDB+AOF 7d) | Deployment | ✅ Done | SRE | P0 | M3 | SRS §2 Module 22 |
| FR-98 | Rollback Strategy (knowledge/model/schema/experiment) | Deployment | ✅ Done | SRE | P0 | M3 | SRS §2 Module 22 |

### Module 23: 降級策略 (Circuit Breaker)

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-99 | Circuit Breaker 7 Degradation Levels (incl. embedding/classifier/judge lateral levels) | Circuit Breaker | ✅ Done | BE | P0 | M3 | SRS §2 Module 23 |

### Module 24: 多媒體訊息處理

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-100 | Multimedia Handling (image→escalate, sticker→prompt, ClamAV fail-secure 503) | Media | ✅ Done | BE | P1 | M4 | SRS §2 Module 24 |

### Module 25: 管理 WebUI

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-101 | Knowledge Management WebUI (CRUD, Markdown, CSV/JSON import/export) | WebUI | ✅ Done | FE | P1 | M4 | SRS §2 Module 25 |
| FR-102 | RAG Debugger (cosine scores, RRF top-3, threshold slider, session-only) | WebUI | ✅ Done | FE | P2 | M4 | SRS §2 Module 25 |
| FR-103 | Operations Dashboard (FCR/latency/knowledge/cost charts, 24hr/7d/30d) | WebUI | ✅ Done | FE | P1 | M3 | SRS §2 Module 25 |
| FR-104 | Agent Portal (inbox, WS real-time, takeover panel with emotion+DST+context) | WebUI | ✅ Done | FE | P0 | M4 | SRS §2 Module 25 |

### Module 26: ODD SQL 分析

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-105 | ODD SQL Queries (10 queries + 20% judge sampling rate configurable) | Analytics | ✅ Done | BE | P1 | M3 | SRS §2 Module 26 |

### Module 27: 負載測試

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-106 | k6 Load Test (4 scenarios: smoke/load/stress/spike, 2000 TPS) | Load Test | ✅ Done | SRE | P0 | M3 | SRS §2 Module 27 |

### Module 28: 測試策略

| FR ID | Title | Module | Status | Owner | Priority | Milestone | SRS Coverage |
|-------|-------|--------|--------|-------|----------|-----------|--------------|
| FR-107 | Test Pyramid (unit 70% + integration 20% + E2E 10%, 6 E2E scenarios) | Test | ✅ Done | BE | P0 | M3 | SRS §2 Module 28 |
| FR-108 | Golden Dataset (500 edge cases, 6 categories, regression auto) | Test | ✅ Done | BE | P0 | M3 | SRS §2 Module 28 |

---

## NFR 追蹤矩陣

| NFR ID | Title | Type | Status | Owner | Priority | Milestone |
|--------|-------|------|--------|-------|----------|-----------|
| NFR-01 | p95 end-to-end latency < 1.0s | Performance | Pending | BE+SRE | P0 | M3 |
| NFR-02 | L1-L3 combined latency < 5ms p95 | Performance | Pending | BE | P0 | M1 |
| NFR-03 | L4 Classifier < 200ms p95 | Performance | Pending | BE | P0 | M4 |
| NFR-04 | Embedding API < 300ms p95 | Performance | Pending | BE | P0 | M3 |
| NFR-05 | A2A timeout = 2.0s | Performance | Pending | BE | P0 | M4 |
| NFR-06 | LLM fallback switch < 500ms | Performance | Pending | BE | P0 | M1 |
| NFR-07 | Agent Card TTL cache = 300s | Performance | Pending | BE | P0 | M4 |
| NFR-08 | Embedding job p95 < 30s | Performance | Pending | BE | P0 | M4 |
| NFR-09 | 2000 TPS sustained | Throughput | Pending | SRE | P0 | M3 |
| NFR-10 | 99.9% availability / month | Availability | Pending | SRE | P0 | M3 |
| NFR-11 | Early warning < 99.95% | Availability | Pending | SRE | P0 | M3 |
| NFR-12 | p95 > 0.8s → HighLatency alert | Availability | Pending | SRE | P0 | M2 |
| NFR-13 | error rate > 0.5% → alert | Availability | Pending | SRE | P0 | M2 |
| NFR-14 | DR < 5 minutes | Availability | Pending | SRE | P0 | M3 |
| NFR-15 | OWASP LLM01:2025 compliance | Security | Pending | BE+SRE | P0 | M3 |
| NFR-16 | Security block rate ≥ 95% | Security | Pending | BE | P0 | M3 |
| NFR-17 | Secrets never in version control | Security | Pending | ALL | P0 | M1 |
| NFR-18 | Monthly infra cost < $500 | Cost | Pending | SRE | P0 | M3 |
| NFR-19 | LLM API baseline ~$210/month | Cost | Pending | PM | P1 | M3 |
| NFR-20 | Taiwan Personal Data Protection Act | Compliance | Pending | PM | P0 | M4 |
| NFR-21 | GDPR Art.5(1)(e) compliance | Compliance | Pending | PM | P0 | M4 |
| NFR-22 | SOC2 audit trail | Compliance | Pending | PM | P1 | M4 |
| NFR-23 | FCR ≥ 90% in_scope | Quality | Pending | PM | P0 | M3 |
| NFR-24 | CSAT target 4.8 (+50% vs 3.2 baseline) | Quality | Pending | PM | P0 | M3 |
| NFR-25 | Escalation SLA compliance ≥ 95% | Quality | Pending | PM | P0 | M2 |
| NFR-26 | Kappa ≥ 0.7 (judge vs human labels) | Quality | Pending | PM | P1 | M3 |
| NFR-27 | Grounding pass rate 100% (cosine ≥ 0.75) | Quality | Pending | BE | P0 | M2 |
| NFR-28 | Recall@3 ≥ 92% (HNSW 1536-dim) | Quality | Pending | BE | P0 | M3 |
| NFR-29 | Agentic tool success rate ≥ 95% | Quality | Pending | BE | P0 | M4 |
| NFR-30 | K8s HPA min=3, max=10, CPU=70% | Scalability | Pending | SRE | P0 | M3 |
| NFR-31 | Full OTel trace per request | Observability | Pending | SRE | P0 | M2 |
| NFR-32 | Unit 70% + Integration 20% + E2E 10% coverage | Testability | Pending | BE | P0 | M3 |
| NFR-33 | Rate limiter fail-open on Redis down | Resilience | Pending | BE | P0 | M1 |
| NFR-34 | IP Whitelist fail-secure (403) on no match | Resilience | Pending | BE | P0 | M1 |
| NFR-35 | IP Whitelist max 100 CIDR blocks | Resilience | Pending | BE | P0 | M1 |
| NFR-36 | M2M token 90d expiry, 24hr rotation overlap | Resilience | Pending | BE | P0 | M4 |
| NFR-37 | Admin WebUI < 1.5s response, 100% real-time | Performance | Pending | FE | P1 | M4 |
| NFR-38 | ClamAV scan p95 < 500ms | Performance | Pending | BE | P1 | M4 |

---

## 統計摘要

| 類別 | 數量 |
|------|------|
| Functional Requirements (FR) | 108 |
| Non-Functional Requirements (NFR) | 38 |
| **合計** | **146** |
| Modules | 28 |
| Priority P0 FRs | 92 |
| Priority P1 FRs | 14 |
| Priority P2 FRs | 2 |
| Milestone M1 FRs | 23 |
| Milestone M2 FRs | 19 |
| Milestone M3 FRs | 11 |
| Milestone M4 FRs | 55 |

---

## 狀態說明

| Status | 說明 |
|--------|------|
| Pending | 尚未開始實作 |
| In-Progress | 開發進行中 |
| Done | 實作完成 + 測試通過 |
| Deferred | 本版本延後（須標記原因） |

> 所有 FR 均為 Pending：Phase 1（需求規格）尚未進入 Phase 2（架構設計）及 Phase 3（實作）。
