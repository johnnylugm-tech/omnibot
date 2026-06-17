# PROJECT_BRIEF — OmniBot

> **Source spec**: SPEC.md v8.1 (2026-06-06)
> **Brief date**: 2026-06-17
> **Language**: Python
> **Delivery window**: 8–11 weeks (4 backend engineers + 2 SRE)

---

## 1. Project Vision

OmniBot is an enterprise-grade multi-platform customer service chatbot that delivers:

- **90% First Contact Resolution (FCR)** via a 4-tier hybrid knowledge layer
- **p95 < 1.0 s** end-to-end response latency under full load
- **99.9% availability** with < 5-minute disaster recovery
- Enterprise security via the PALADIN 5-layer prompt-injection defence architecture

The bot simultaneously serves customers on **Telegram, LINE, Messenger, WhatsApp, Web, and external A2A agents**, presenting a unified interface regardless of channel.

---

## 2. Stakeholders

| Stakeholder | Concern |
|-------------|---------|
| Customer (end-user) | Fast, accurate, polite answers; smooth escalation to human agents |
| Human Agent (customer service rep) | Real-time escalation queue; WebSocket takeover workflow |
| Admin | Knowledge management, RBAC, A/B experiment control |
| Editor | Knowledge CRUD without system-level access |
| Auditor | Read-only access to audit logs and CSAT metrics |
| DPO | PII decrypt rights; GDPR compliance oversight |
| SRE / Ops | Cost ceiling < $500/month; runbooks; disaster recovery |

---

## 3. Business KPIs (Acceptance Criteria)

| KPI | Target | Measurement |
|-----|--------|-------------|
| FCR (First Contact Resolution) | ≥ 90% | ODD SQL (conversations resolved without human) |
| CSAT improvement | +50% vs 2025Q4 baseline (3.2 → 4.8) | LLM-as-a-Judge (Politeness + Accuracy) |
| p95 end-to-end latency | < 1.0 s | k6 load test |
| Platform support | 4 messaging platforms | Functional test |
| System availability | 99.9% / month | Prometheus uptime |
| Security block rate | ≥ 95% | Red-team + OWASP LLM01 checklist |
| Escalation SLA compliance | ≥ 95% | ODD SQL |
| LLM-as-a-Judge agreement | Cohen's Kappa ≥ 0.7 vs human labels | 500-sample golden set calibration |
| Grounding check pass rate | 100% (cosine similarity ≥ 0.75) | L5 unit tests |
| Embedding Recall@3 | ≥ 92% | Golden set regression |
| Disaster recovery time | < 5 minutes | DR drill |
| Monthly cost ceiling | < $500 | Cost dashboard |
| Agentic tool success rate | ≥ 95% | Integration tests |
| LLM fallback switch time | < 500 ms | Fault injection tests |

---

## 4. Functional Scope

### 4.1 Platform Adapter Layer
Normalise messages from 6 channels into `UnifiedMessage`. Verify HMAC-SHA256 webhook signatures per platform (Telegram, LINE, Messenger, WhatsApp). Web uses JWT Bearer; A2A uses M2M OAuth2/JWT.

### 4.2 Security — PALADIN 5 Layers
| Layer | Component | Latency budget |
|-------|-----------|----------------|
| L1 | Input sanitization: NFKC normalization + homoglyph substitution | < 2 ms |
| L2 | Pattern detection: regex SUSPICIOUS_PATTERNS + Unicode variant | < 3 ms |
| L3 | Instruction Hierarchy (Sandwich Prompt, Spotlighting) | < 5 ms total L1–L3 |
| L4 | Semantic Injection Classifier (LLM-based, parallel for medium risk) | < 200 ms, async |
| L5 | Grounding Check: cosine similarity ≥ 0.75 against retrieved context | < 5 ms |

L4 triggers only for medium/high/critical risk or conversation-first message (< 5% of traffic).

### 4.3 PII Masking
Detect and mask phone, email, Taiwan address, credit card (Luhn-validated). Trigger escalation on sensitive keyword match (密碼, 信用卡號, etc.).

### 4.4 Rate Limiting
Redis-backed sliding window (Lua atomic script). Per-platform limits: Telegram/LINE/Messenger/WhatsApp 30 req/s; Web 10 req/s; Agent 100 req/s. Fail-open when Redis is unavailable.

### 4.5 IP Whitelist
CIDR-based (up to 100 blocks). Enforce before signature validation. Fail-secure (403) on no match; fail with 400 + warning log if whitelist is empty or IP header is malformed.

### 4.6 Emotion Analyzer
Classify emotion (positive/neutral/negative) with intensity (0–1) and 24-hour half-life temporal decay. Trigger escalation after 3 consecutive negative turns. Bypass for AGENT platform.

### 4.7 Intent Router + DST (Dialogue State Tracking)
8-state FSM: IDLE → INTENT_DETECTED → SLOT_FILLING → AWAITING_CONFIRMATION → PROCESSING → TOOL_CALLING → RESOLVED / ESCALATED. Slot filling per intent (e.g. `order_status` needs `order_id`). Auto-escalate after 3 unfilled rounds or confidence < 0.65.

### 4.8 Hybrid Knowledge Layer (4 Tiers)
| Tier | Technology | Coverage | Confidence threshold |
|------|-----------|----------|---------------------|
| T1 Rule Matching | PostgreSQL ILIKE + keyword | 40% | ≥ 0.80 |
| T2 RAG + RRF | pgvector HNSW (1536-dim) + Reciprocal Rank Fusion k=60 | 40% | ≥ 0.85 |
| T3 LLM Generation | gpt-4o primary → gemini-1.5-flash fallback | 10% | grounding ≥ 0.75 |
| T4 Escalation | Human queue with SLA | 10% | n/a |

RAG uses Parent-Child chunking: index 150-token child chunks, retrieve 500-token parent for LLM context.

### 4.9 Action Execution Engine (Agentic)
Plugin registry with 3 adapter types: **MCPAdapter** (stdio/SSE to external MCP server), **A2AAdapter** (JSON-RPC 2.0 to peer agents with Agent Card discovery + 300 s TTL cache), **CLIAdapter** (sandboxed local scripts). All return `ToolExecutionResult`. A2A timeout 2.0 s.

### 4.10 Response Generator
Template-based + emotion tone adjustment. Platform-specific formatting (quick replies, etc.). A/B variant selection via deterministic SHA-256 hash split.

### 4.11 RBAC
7 roles: `anonymous`, `customer`, `agent`, `editor`, `admin`, `auditor`, `dpo`. Permission matrix enforced via decorator middleware on all management API endpoints.

### 4.12 Human Escalation
SLA by priority: urgent (emotion trigger) 5 min, high 15 min, normal 30 min. WebSocket push to agent workstation (`/ws/agent`). Real-time conversation sync (`/ws/user`).

### 4.13 LLM-as-a-Judge Evaluation
Ensemble: `gpt-4o-mini` (primary) + `claude-3-5-haiku` (secondary), temp 0. Politeness: `max(primary, secondary)`; Accuracy: `min(primary, secondary)`. CSAT = 0.4×speed + 0.2×anthropomorphism + 0.2×politeness + 0.2×accuracy. Monthly recalibration on 500-sample golden set (Kappa ≥ 0.7).

### 4.14 Observability
Structured JSON logging, Prometheus metrics, OpenTelemetry tracing, Grafana dashboards. Alert thresholds: availability < 99.95% (early warning), p95 > 0.8 s, error rate > 0.5%.

### 4.15 Background Job System
SAQ (Simple Async Queue) worker for embedding generation. Embedding job p95 < 30 s. Synchronous first-chunk embedding on knowledge insert to eliminate search dark period.

### 4.16 GDPR / Data Lifecycle
| Data type | Retention | Expiry action |
|-----------|-----------|---------------|
| Conversation messages | 180 days | Archive to cold storage (Parquet/S3) |
| Archived messages | 2 years | Permanent deletion |
| PII audit logs | 90 days | Auto-anonymize |
| Emotion history | 90 days | Delete |
| Security logs | 1 year | Archive → delete after 2 years |

GDPR rights: data export (`GET /users/{id}/data`), deletion within 30 days (`DELETE /users/{id}/data`).

### 4.17 Deployment
Docker Compose (dev). Kubernetes (prod): Deployment + Service + HPA. Database: TDE encryption. Redis: TLS + AUTH + ACL. Backup: `pg_basebackup` + WAL + Redis RDB/AOF. Rollback strategy defined.

### 4.18 Multi-platform Message Handling
Text: full pipeline. Image/File: auto-escalate. Sticker: ignore + prompt reply. Location: extract coordinates + attach to context.

---

## 5. Non-Functional Requirements (NFRs)

| Category | Requirement |
|----------|-------------|
| Latency | p95 < 1.0 s; L1–L3 < 5 ms; L4 classifier < 200 ms (async); embedding API < 100 ms |
| Throughput | 2000 TPS sustained (k6 load test, 4 scenarios) |
| Availability | 99.9% monthly; degraded mode supported (Redis fail-open, LLM fallback) |
| Cost | LLM API ≈ $210/month baseline; total infra < $500/month |
| Security | OWASP LLM01:2025 compliance; PALADIN 5-layer; secrets never committed |
| Compliance | Taiwan Personal Data Protection Act, GDPR Art.5(1)(e), SOC2 audit trail |
| Scalability | Kubernetes HPA; Redis cluster-ready; pgvector HNSW index |
| Observability | Full OpenTelemetry trace per request; Grafana alerting |
| Testability | Unit 70% + Integration 20% + E2E 10% coverage; golden dataset 500 samples |

---

## 6. Technical Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.11 (uv-managed venv) |
| Web framework | FastAPI |
| Database | PostgreSQL + pgvector (HNSW m=16, ef=64) |
| Cache / Queue | Redis (Streams for async, ZSET for rate limiting) |
| Embedding | OpenAI text-embedding-3-small (1536-dim) |
| Primary LLM | gpt-4o (Tier 3 generation) |
| Fallback LLM | gemini-1.5-flash |
| Judge LLMs | gpt-4o-mini + claude-3-5-haiku |
| Background jobs | SAQ worker |
| Deployment | Docker Compose (dev), Kubernetes (prod) |
| Observability | Prometheus + Grafana + OpenTelemetry |
| Load testing | k6 |
| Schema migration | Alembic |

---

## 7. Delivery Milestones

| Milestone | Key deliverables |
|-----------|-----------------|
| **M1** (weeks 1–3) | Platform adapters (4), webhook signature verification, UnifiedMessage/UnifiedResponse, PII masking, rate limiter, IP whitelist, Knowledge Tier 1–3, DST |
| **M2** (weeks 4–6) | Emotion module, PALADIN L3–L5, escalation + SLA, RBAC + enforcement, A/B testing, full observability stack, Redis Streams async |
| **M3** (weeks 6–8) | TDE + Redis hardening, Docker Compose + Kubernetes, backup/rollback, k6 load tests, LLM-as-a-Judge, golden dataset |
| **M4** (weeks 8–11) | SAQ background jobs, WebSocket endpoints, M2M token management, user management API, GDPR lifecycle, Response Generator, E2E test strategy, A2A bidirectional, PALADIN L4 parallel pipeline |

---

## 8. Known Constraints & Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM API latency exceeds 800 ms p95 | Medium | L3 LLM may breach 1.0 s SLA | L4 parallel execution; gemini fallback < 500 ms switch |
| pgvector HNSW recall degrades at scale | Low | FCR drops below 90% | Parent-Child chunking; periodic HNSW reindex |
| LLM-as-a-Judge bias drift | Medium | CSAT score unreliable | Monthly recalibration (Kappa ≥ 0.7 trigger) |
| L4 false positives blocking legitimate users | Low | Degraded UX | L4 triggers only < 5% of traffic; fail-open on timeout |
| Redis unavailability causing rate-limiter failure | Low | Traffic spike risk | Fail-open by design; log warning; Redis sentinel |
| LINE/WhatsApp API rate limits | Medium | Delayed message delivery | Exponential backoff retry; Redis Streams async queue |
| Cost overrun | Low | Budget breach > $500/month | Cost dashboard; per-tier capping; 20% sampling for judge |

---

## 9. Out of Scope (v8.1)

- Image/video understanding (auto-escalate for now; future: GPT-4V / Claude Vision)
- File content parsing (auto-escalate; future: document AI)
- Voice / audio input
- Multi-language beyond zh-TW + English
- Custom LLM fine-tuning
- Native mobile apps (Telegram/LINE/WhatsApp native SDKs handle client UI)
