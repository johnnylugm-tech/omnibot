# SRS — OmniBot 軟體需求規格書

> **Source**: SPEC.md v8.1 (2026-06-06) — INGESTION MODE (100% transcription)
> **Authored**: 2026-06-17 — Agent A: REQUIREMENTS_ENGINEER
> **Project**: omnibot
> **Phase**: 1
> **Changelog**:
> - 2026-06-17: 修正規格不一致問題 (FR-73, FR-87, FR-01~04, NFR Table, 等)

---

## 1. Requirements Overview

OmniBot 是多平台企業級客服聊天機器人，同時服務 Telegram、LINE、Messenger、WhatsApp、Web、A2A 六個管道（註：SPEC 中 KPI 表格標示 4 個平台為過時資訊，以此處 6 個管道為準）。核心目標：FCR ≥ 90%、p95 < 1.0s、可用性 99.9%、PALADIN 五層安全防禦。

---

## 2. Functional Requirements

### Module 1: Platform Adapter Layer

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-01 | Telegram Webhook Adapter：接收 POST /api/v1/webhook/telegram，驗證 X-Telegram-Bot-Api-Secret-Token（HMAC-SHA256），解析 update_id + message，映射為 UnifiedMessage | 合法請求回 200；簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}；rate limit 超出回 429 | `TelegramWebhookVerifier.verify()`, platform adapter |
| FR-02 | LINE Webhook Adapter：接收 POST /api/v1/webhook/line，驗證 x-line-signature（HMAC-SHA256 Base64），解析 events 陣列，映射為 UnifiedMessage | 合法請求回 200；簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}；rate limit 超出回 429 | `LineWebhookVerifier.verify()`, platform adapter |
| FR-03 | Messenger Webhook Adapter：GET 驗證（hub.mode, hub.verify_token, hub.challenge 回傳）+ POST HMAC-SHA256 簽名驗證，映射為 UnifiedMessage | GET 回傳 hub.challenge 字串；POST 合法回 200；簽名失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"} | `MessengerWebhookVerifier.verify()`, platform adapter |
| FR-04 | WhatsApp Webhook Adapter：GET 驗證（hub.challenge）+ POST HMAC-SHA256 簽名驗證（sha256= prefix），映射為 UnifiedMessage | GET 回傳 hub.challenge；POST 合法回 200；簽名失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"} | `WhatsAppWebhookVerifier.verify()`, platform adapter |
| FR-05 | Web Platform Adapter：POST /api/v1/web/guest-session 初始化匿名連線回傳 Guest JWT；POST /api/v1/web/message 使用 JWT BearerAuth 傳訊 | guest-session 回 200 含 JWT；JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED；rate limit 超出回 429 | `WebAdapter`, JWT middleware |
| FR-06 | A2A Platform Adapter：POST /api/v1/a2a/rpc 接收 JSON-RPC 2.0（method: ask_customer_service / escalate_to_human），使用 M2M OAuth2/JWT BearerAuth 驗證，映射為 UnifiedMessage | 合法 M2M token 回 200 JSON-RPC 2.0 回應；token 驗證失敗回 401 | `A2AAdapter`, M2M auth middleware |
| FR-07 | UnifiedMessage 資料結構：immutable dataclass，欄位含 platform(Platform enum), platform_user_id, unified_user_id(Optional), message_type(MessageType enum), content, raw_payload, received_at, reply_token(LINE 特有) | 所有平台訊息皆可建立合法 UnifiedMessage 實例；frozen=True 確保不可變 | `UnifiedMessage` dataclass |
| FR-08 | UnifiedResponse 資料結構：immutable dataclass，欄位含 content, source(rule\|rag\|wiki\|escalate), confidence, knowledge_id(Optional), emotion_adjustment(Optional), quick_replies | 所有知識層輸出皆可轉換為 UnifiedResponse；source 欄位限定四個合法值 | `UnifiedResponse` dataclass |
| FR-09 | 統一回應格式：ApiResponse[T]（success, data, error, error_code）+ PaginatedResponse[T]（total, page, limit, has_next）；所有管理 API 端點回應包裝於 ApiResponse 外層 | 所有管理 API 回應符合 ApiResponse schema；PaginatedResponse 包含正確分頁欄位 | `ApiResponse`, `PaginatedResponse` |

### Module 2: Security — PALADIN 五層防禦

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-10 | PALADIN L1 — InputSanitizer：NFKC 正規化 + homoglyph 替換（Cyrillic/Greek → ASCII）+ 控制字元移除；延遲 < 2ms p95 | 西里爾/希臘同形字被正確替換；NFKC 正規化通過 unicode 標準測試；延遲 < 2ms | `InputSanitizer.sanitize()` |
| FR-11 | PALADIN L2 — Pattern Detection：13 個 SUSPICIOUS_PATTERNS regex（ignore previous instructions, system:, pretend you, act as, forget everything 等）+ Unicode 變體偵測；延遲 < 3ms p95 | 所有已知 pattern 測試案例命中；正常用戶訊息不誤判；延遲 < 3ms | `PromptInjectionDefense.check_input()` |
| FR-12 | PALADIN L3 — Instruction Hierarchy：Sandwich Prompt 建構，系統指令標記 PRIORITY: HIGHEST，用戶訊息標記 UNTRUSTED DATA BOUNDARY，使用 Spotlighting delimiters（ICLR 2025）；L1-L3 合計延遲 < 5ms | Sandwich prompt 結構正確包含三個標記區塊；SYSTEM/UNTRUSTED 邊界清晰 | `PromptInjectionDefense.build_sandwich_prompt()` |
| FR-13 | PALADIN L4 — SemanticInjectionClassifier：LLM-based（gpt-4o-mini 預設），回傳 `{is_injection, confidence, injection_type: direct_prompt_injection\|indirect_injection\|jailbreak\|none}`；p95 < 200ms；classifier 超時 → 放行並標記 "unverified" | 分類器回傳合法 JSON；超時不阻斷主流程；injection_type 限定四個合法值 | `SemanticInjectionClassifier.classify()` |
| FR-14 | PALADIN L5 — GroundingChecker：計算 LLM 輸出與 source_texts 之間 cosine similarity（text-embedding-3-small 1536維），閾值 0.75；延遲 < 5ms（本地計算） | cosine score < 0.75 → grounded=False；cosine score ≥ 0.75 → grounded=True；無 source_texts → grounded=False | `GroundingChecker.check()` |
| FR-15 | PALADIN L4 平行化執行策略：low risk → 跳過 L4 直接 L3；medium risk → L4 與 L3 平行（L3 不等待 L4）；high/critical → 同步 L4 阻擋（不呼叫 L3）；L4 觸發率 < 5% 總流量 | low risk 請求不呼叫 L4；medium risk L4 與 L3 並發執行；high/critical 直接安全攔截不呼叫 L3 LLM | `PALADINPipeline.process()` |
| FR-16 | L4 事後攔截：medium risk 若 L4 在 L3 完成後才判定 injection → 撤回 L3 結果，發送安全回應，記錄 injection_retrospective_block 至 security_logs | injection_retrospective_block 事件正確寫入 security_logs；撤回回應替換原回覆 | `PALADINPipeline.process()` |
| FR-17 | 各平台 L4 事後撤回策略：Telegram deleteMessage（48hr 內）；LINE 不支援刪除 → 補發道歉訊息；Messenger DELETE（10 分鐘內）；WhatsApp 受限 → 補發更正；Web WebSocket 直接替換；A2A 回傳 revoked: true；**撤回失敗路徑**：Telegram 48hr 視窗過期或 API 拒絕 → 補發道歉訊息 + 記錄 retraction_failed 至 security_logs；Messenger 10min 視窗過期 → 同 Telegram 補發道歉；所有撤回失敗均 fail-secure（不重試，補發更正，記錄日誌） | 各平台按策略執行撤回或補發；撤回失敗時補發道歉並記錄 retraction_failed；Web 端 WebSocket 替換正確 | platform-specific retraction handlers |

### Module 3: PII 去識別化

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-18 | PIIMasking：偵測並遮蔽電話（台灣格式 \d{10,11}）、Email、台灣地址（市縣路街巷弄號樓正則）、信用卡（16 位 + Luhn 校驗）；遮蔽格式 `[{pii_type}_masked]` | 所有四類 PII 正確遮蔽；信用卡 Luhn 校驗失敗者不遮蔽；mask_count 正確回傳 | `PIIMasking.mask()` |
| FR-19 | PII 敏感關鍵字觸發轉接：偵測 密碼/銀行帳戶/信用卡號/提款卡 關鍵字 → should_escalate() 回傳 True | 四個敏感關鍵字觸發 should_escalate()=True；其他關鍵字不誤判 | `PIIMasking.should_escalate()` |
| FR-20 | PII 稽核日誌：每次遮蔽事件寫入 pii_audit_log（conversation_id, mask_count, pii_types, action, performed_by）；保留 90 天後自動匿名化 | pii_audit_log 寫入成功；90 天到期後 PII 欄位自動清除 | `pii_audit_log` table + scheduled job |

### Module 4: Rate Limiting & IP Whitelist

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-21 | Redis 滑動視窗速率限制（Lua atomic ZSET）：Telegram/LINE/Messenger/WhatsApp 30 req/s；Web 10 req/s；Agent 100 req/s；超限回 429 RATE_LIMIT_EXCEEDED | 各平台超出限制回 429；未超限回 200；Lua script 原子性保證無競態 | `RateLimiter.allow()` |
| FR-22 | Rate Limiter Fail-open：Redis 不可用時（ConnectionError/TimeoutError）放行請求 + 記錄 Warning log | Redis 斷線時請求通過；warning 日誌正確記錄；不拋例外 | `RateLimiter.allow()` |
| FR-23 | IP 白名單：CIDR 格式（最多 100 個），從 `IP_WHITELIST_CIDRS` 環境變數載入（逗號分隔）；優先讀取 X-Forwarded-For 最左側 IP，fallback request.client.host；無匹配 → 403 Forbidden（空 body） | 合法 IP 通過；非白名單 IP 回 403；空 body；白名單空或無 IP header 回 400 + warning log | `IPWhitelist.is_allowed()` |
| FR-24 | 攔截鏈順序：TLS → IP Whitelist → Webhook Signature Validation → Platform Adapter Parse → Rate Limiting → RBAC | 各層按順序執行；IP 攔截在 signature 驗證前；Rate Limiting 在 Platform Adapter 解析 user_id 後 | middleware chain |
| FR-25 | IP 白名單錯誤處理：無效 CIDR 格式 → 啟動時拋出 IPWhitelistError；無效 IP 格式（is_allowed 呼叫時）→ 回 False（fail-secure，不拋例外） | 非法 CIDR 啟動時即失敗；非法 IP 不拋例外回 False | `IPWhitelist.__init__()`, `IPWhitelist.is_allowed()` |

### Module 5: Hybrid Knowledge Layer

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-26 | Knowledge Tier 1 — 規則匹配：PostgreSQL ILIKE + keywords 精確比對；confidence ≥ 0.80 時直接回傳（exact match 0.95，partial 0.7）；LIMIT 5 | confidence ≥ 0.80 命中直接回傳 source="rule"；未達閾值繼續 Tier 2 | `HybridKnowledge._rule_match()` |
| FR-27 | Knowledge Tier 2 — RAG + RRF：pgvector HNSW（1536維 text-embedding-3-small），Child Chunk 向量搜尋，Top-10 去重取 Top-5 Parent；RRF k=60 融合 Tier 1 + Tier 2 結果；confidence ≥ 0.85 回傳 source="rag" | RRF 排名正確融合；confidence ≥ 0.85 回傳 rag；Parent-Child 追索邏輯正確 | `HybridKnowledge._rag_search()`, `_reciprocal_rank_fusion()` |
| FR-28 | Parent-Child Chunking：Parent = 500 tokens（100 token overlap），Child = 150 tokens；僅 Child Chunks 建向量索引；向量命中 Child → 追索對應 Parent 送 LLM | Parent/Child 尺寸符合規格；向量搜尋命中 Child 後正確追索 Parent | chunking module, `knowledge_chunks` table |
| FR-29 | HNSW 向量索引：knowledge_chunks 表建 HNSW 索引（vector_cosine_ops，m=16，ef_construction=64）；Partial Index（WHERE embeddings IS NOT NULL） | HNSW 索引建立成功；Partial Index 只索引非 NULL 向量；Recall@3 ≥ 92% | `CREATE INDEX ... USING hnsw` |
| FR-30 | Knowledge Tier 3 — LLM 生成：gpt-4o 主要 → gemini-1.5-flash fallback；使用 Sandwich Prompt（L3）；L5 Grounding Check ≥ 0.75；grounding 失敗 → None（觸發 Tier 4）；LLM fallback 切換 < 500ms | gpt-4o 失敗自動降級 gemini；grounding < 0.75 → escalate；source="wiki" | `HybridKnowledge._llm_generate()`, `_call_llm_api()` |
| FR-31 | Knowledge Tier 4 — 人工轉接：所有 Tier 1/2/3 無法處理時 escalate；reason 含 no_rule_match/out_of_scope/low_confidence/emotion_trigger；source="escalate"，id=-1 | Tier 1-3 均無結果時觸發 Tier 4；KnowledgeResult.id=-1 標識非知識庫來源 | `HybridKnowledge._escalate()` |
| FR-32 | KnowledgeResult 資料結構：immutable frozen dataclass（id, content, confidence, source, knowledge_id(Optional)）；id=-1 代表非知識庫來源 | KnowledgeResult 建構成功；source 限定 rule\|rag\|wiki\|escalate | `KnowledgeResult` dataclass |
| FR-33 | HybridKnowledge 查詢協調器：按 Tier 1 → Tier 2 → Tier 3 → Tier 4 順序執行；各 Tier 有明確置信度門檻；EMBEDDING_MODEL = text-embedding-3-small, EMBEDDING_DIM = 1536 | 查詢路徑按 Tier 順序；置信度門檻正確攔截；更換模型時 EMBEDDING_DIM 同步變更 | `HybridKnowledge.query()` |

### Module 6: DST 對話狀態追蹤

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-34 | 8 狀態 FSM：IDLE → INTENT_DETECTED → SLOT_FILLING → AWAITING_CONFIRMATION → PROCESSING → TOOL_CALLING → RESOLVED / ESCALATED；ALLOWED_TRANSITIONS 嚴格執行非法轉移 → ValueError | 所有合法轉移成功；非法轉移拋 ValueError；轉移後 turn_count +1 | `DialogueState.transition()`, `ALLOWED_TRANSITIONS` |
| FR-35 | Slot Filling：order_status 需要 order_id；return_request 需要 order_id + reason；missing_slots() 回傳缺失的必填 slot 清單 | order_status / return_request 缺 slot 時 missing_slots() 正確回傳；slot 填完後進入 AWAITING_CONFIRMATION | `DialogueSlot`, `INTENT_TO_SLOTS`, `DialogueState.missing_slots()` |
| FR-36 | 自動轉接觸發條件：SLOT_FILLING 超過 3 輪未完成 → ESCALATED；意圖置信度 < INTENT_CONFIDENCE_THRESHOLD (0.65) → ESCALATED；PROCESSING 置信度 < 0.65 → ESCALATED | 超過 3 輪 slot filling 觸發轉接；confidence < 0.65 觸發轉接 | DST state machine transitions |
| FR-37 | AWAITING_CONFIRMATION 超時：超過 2 輪未確認 → ESCALATED；用戶確認 → PROCESSING；用戶否認 → SLOT_FILLING | 2 輪未確認觸發 ESCALATED；確認/否認狀態轉移正確 | DST transitions |
| FR-38 | 對話 Context Window 管理：sliding_window_with_summarization 策略；max_tokens=8192，system_reserved=512，knowledge_max=2048，history_budget=5632；溢出時前 1/3 messages 摘要替換；**Token 計算使用 tiktoken cl100k_base（適用 gpt-4o）；gemini fallback 亦使用相同 cl100k_base 計算以維持 budget 一致性（保守估算，不因 tokenizer 差異導致 context overflow）** | token 計算正確（cl100k_base）；超出 budget 觸發摘要；保留最近 1/3 messages；gemini fallback 時 budget 計算不變 | `ContextWindowManager.manage()` |

### Module 7: Action Execution Engine (Agentic)

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-39 | ActionAdapter 抽象介面：list_tools() → List[ToolDefinition]；execute(tool_name, arguments) → ToolExecutionResult；ToolDefinition 欄位含 name, description, parameters_schema, protocol, handler_ref | 所有 Adapter 子類實作 list_tools + execute；ToolExecutionResult 包含 success, output, error_message | `ActionAdapter`, `ToolDefinition`, `ToolExecutionResult` |
| FR-40 | MCPAdapter：透過 stdio 或 SSE 連線至外部 MCP Server；list_tools 回傳 MCP server 宣告的工具清單；execute 呼叫 MCP 工具回傳 ToolExecutionResult | MCPAdapter 連線至 MCP Server 成功；工具呼叫回傳正確結果 | `MCPAdapter` |
| FR-41 | A2AAdapter：GET /.well-known/agent.json 發現 Agent Card（300s TTL cache）；execute 透過 JSON-RPC 2.0 呼叫（Authorization: Bearer）；timeout=2.0s；agent.json 不可達 → 回傳空工具清單（降級） | Agent Card Discovery 成功；JSON-RPC 2.0 請求格式正確；timeout 2.0s 回傳 error；不可達不拋例外 | `A2AAdapter._discover_agent_card()`, `A2AAdapter.execute()` |
| FR-42 | CLIAdapter：在 sandboxed 容器內執行本地 Python/Bash 腳本；回傳 ToolExecutionResult | CLIAdapter 執行成功回 success=True；執行失敗回 success=False + error_message | `CLIAdapter` |
| FR-43 | ToolExecutor：register(tool, handler) 綁定工具定義與 handler；execute(tool_name, arguments_json) 回傳 ToolExecutionResult；預設工具：get_shipping_status（查詢物流）、update_shipping_address（更新配送地址，出貨前才允許） | 預設工具可正常執行；工具不存在回 success=False；update_shipping_address 在 shipped/delivered 狀態拒絕修改 | `ToolExecutor`, `_get_shipping_status()`, `_update_shipping_address()` |
| FR-44 | OmniBot Agent Card：GET /.well-known/agent.json 回傳 Agent Card JSON（name, description, url, version, capabilities, methods, auth_schemes）；methods: [ask_customer_service, escalate_to_human] | Agent Card 端點回 200 合法 JSON；methods 清單正確 | `/.well-known/agent.json` endpoint |
| FR-45 | ToolDefinition 統一定義：AEE（Action Execution Engine）與 DST 模組共用同一 ToolDefinition dataclass（name, description, parameters_schema, protocol, handler_ref），避免重複定義 | AEE 和 DST 使用同一 ToolDefinition 類別；無重複定義 | `ToolDefinition` shared dataclass |

### Module 8: Emotion Analyzer

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-46 | EmotionAnalyzer：分類情緒為 positive/neutral/negative，強度 intensity 範圍 0.0–1.0，每次分析建立 EmotionScore 記錄 | 情緒分類結果限定三個合法值；intensity 範圍 [0.0, 1.0] | `EmotionScore`, emotion classification |
| FR-47 | 時序衰減：EmotionTracker 以 24hr half-life 指數衰減（decay = exp(-0.693 * hours_ago / 24.0)）計算 current_weighted_score()；近期情緒權重更高 | 衰減計算公式正確；half_life=24hr；24hr 後權重降至 50% | `EmotionTracker.current_weighted_score()` |
| FR-48 | 連續負面觸發轉接：consecutive_negative_count() ≥ 3 → should_escalate()=True；計算從最近往回的連續負面次數 | 連續 3 次負面觸發；中間有非負面打斷重計；should_escalate() 正確 | `EmotionTracker.should_escalate()` |
| FR-49 | AGENT 平台 Bypass：platform == AGENT 時跳過情緒分析模組 | AGENT 平台請求不執行情緒分析；不觸發情緒轉接 | platform check in pipeline |

### Module 9: Response Generator

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-50 | Template System：ResponseTemplate（name, platform, emotion_tone, template）；預設模板：rule_default（{answer}）、rag_default（附「📌 此回覆根據相關知識庫內容生成」）、escalate（附案件編號） | 三個預設模板存在且格式正確；variable interpolation 正確 | `ResponseGenerator.DEFAULT_TEMPLATES` |
| FR-51 | Emotion Tone Modulation：negative + intensity > 0.7 → 前綴「非常抱歉造成您的困擾。」；positive → 前綴「太好了！」；repeat_count > 0 且 negative → 抑制重複道歉 | 情緒調整規則按閾值正確觸發；重複道歉抑制生效 | `ResponseGenerator._apply_emotion_tone()` |
| FR-52 | A/B Variant Injection：SHA-256 確定性分配（非 Python hash()）；variant_a → 結尾 "還有其他問題嗎？"；variant_b → 結尾 "需要進一步說明嗎？"；control → 不注入 | SHA-256 分配跨進程一致；variant 注入正確；control 無注入 | `ResponseGenerator._apply_ab_variant()`, `ABTestManager.get_variant()` |
| FR-53 | Platform Format Adapter：各平台訊息限制（Telegram 4096 字元/HTML MarkdownV2；LINE 5000 字元/Quick Reply；Messenger 2000 字元/截斷+link；WhatsApp 4096 字元；Web 無限制/完整 Markdown；Agent 無限制/純 JSON） | 各平台輸出格式符合限制；長訊息正確截斷或分段 | platform format adapters |

### Module 10: Human Escalation

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-54 | EscalationManager：create(EscalationRequest) → 插入 escalation_queue（conversation_id, reason, priority, sla_deadline）→ 回傳 escalation_id；assign(escalation_id, agent_id)；resolve(escalation_id) | 建立轉接記錄成功；assign 更新 assigned_agent + picked_at；resolve 更新 resolved_at | `EscalationManager.create()`, `.assign()`, `.resolve()` |
| FR-55 | SLA 定義：normal(priority=0) 30 分鐘；high(priority=1) 15 分鐘；urgent(priority=2) 5 分鐘（emotion_trigger）；get_sla_breaches() 查詢超 SLA 未解決案件 | sla_deadline = queued_at + SLA 分鐘；breach = resolved_at IS NULL AND sla_deadline < NOW() | `EscalationManager.SLA_BY_PRIORITY`, `get_sla_breaches()` |
| FR-56 | WebSocket 轉接推送：建立轉接後透過 /ws/agent 推送 escalation.new 事件（payload: escalation_id, conversation_id, priority, reason, platform, queued_at, preview{user_message, emotion}） | 轉接建立後 WebSocket 即時推送；payload 欄位完整 | `EscalationManager` + WebSocket push |

### Module 11: WebSocket 端點

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-57 | /ws/agent WebSocket：客服工作台；Server→Client 事件：escalation.new, escalation.claimed, escalation.resolved, conversation.message；Client→Server 事件：agent.typing, agent.takeover；JWT Bearer 驗證（query param 或 initial message） | 事件格式正確；JWT 驗證失敗拒絕連線；各事件 payload 欄位完整 | `/ws/agent` WebSocket handler |
| FR-58 | /ws/user WebSocket：Web 前端用戶；Server→Client：message.reply（message_id, content, source, timestamp）；JWT BearerAuth | message.reply 即時推送；JWT 驗證；避免輪詢 | `/ws/user` WebSocket handler |
| FR-59 | WebSocket 心跳：Server 每 30s 發送 ping；Client 10s 內未回 pong → Server 發送 disconnect(reason: timeout)；支援 subscribe/subscribed channel 訂閱流程 | 30s ping；10s timeout disconnect；channel 訂閱回 subscribed | WebSocket lifecycle |

### Module 12: RBAC 權限管理

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-60 | 7 角色定義：anonymous, customer, agent, editor, admin, auditor, dpo；每角色對 knowledge/escalate/audit/experiment/system/pii 資源各有不同權限（read/write/delete）；dpo 獨有 pii:decrypt | 7 角色 ROLE_PERMISSIONS 完整；dpo 有 pii:decrypt；auditor 無 pii:decrypt | `ROLE_PERMISSIONS` |
| FR-61 | 權限矩陣（完整）：anonymous=knowledge:read；customer=knowledge:read + escalate:write；agent=knowledge:read + escalate:write；editor=knowledge:read+write + escalate:read + experiment:read；admin=全資源 read+write+delete；auditor=knowledge/escalate/audit/experiment/system:read **+ pii:none（無 pii 任何權限）**；dpo=同 auditor + pii:decrypt；**Explicit pii:none 必須在 ROLE_PERMISSIONS 中顯式定義（不隱含），確保 auditor 嘗試 pii:decrypt 時回傳 403** | 各角色權限按規格；auditor 嘗試 pii:decrypt 回 403；越界操作被拒絕 | `ROLE_PERMISSIONS` |
| FR-62 | RBACEnforcer 裝飾器 Middleware：@rbac.require(resource, action) 套用於管理 API endpoint；user_role 從 request 取得；無權限拋 PermissionError → HTTP 403 AUTHZ_INSUFFICIENT_ROLE | 無權限請求回 403；有權限請求通過；裝飾器正確注入 | `RBACEnforcer.require()`, `check()` |

### Module 13: A/B Testing

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-63 | ABTestManager：get_variant(user_id, experiment_id) 使用 SHA-256（hashlib.sha256，非 Python hash()）確定性分配 variant；run_experiment() 呼叫對應 variant prompt；analyze_results() 查詢實驗指標 | 同 user_id + experiment_id 跨進程回傳相同 variant；SHA-256 hash 計算正確 | `ABTestManager.get_variant()`, `run_experiment()` |
| FR-64 | auto_promote：最小樣本量 100；metric 差異 ≥ 0.05（threshold）→ 最佳 variant 勝出，實驗 status 設 'completed'；樣本量不足 → 回傳 None | 樣本 < 100 不判定勝負；差異 ≥ 0.05 且樣本足夠時自動結束實驗 | `ABTestManager.auto_promote()` |

### Module 14: LLM-as-a-Judge 評測

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-65 | Ensemble Judge：primary=gpt-4o-mini (temp=0) + secondary=claude-3-5-haiku (temp=0)；平行呼叫兩個 judge；各 judge 分別評測 politeness + accuracy | 兩個 judge 並行呼叫；temperature=0 確保確定性；各 judge 回傳 JudgeResult | `LLMJudge.evaluate()` |
| FR-66 | Politeness 聚合：max(primary_score, secondary_score)（寬鬆評分，情感支持寧可寬容）；Score 1-5 評分標準：1=Rude, 2=Cold, 3=Professional, 4=Warm, 5=Exceptional | politeness = max(two scores)；中文語氣標記：正面（請問/協助/啦）、負面（吼/咧/嘛）正確識別 | `LLMJudge.evaluate()` aggregation |
| FR-67 | Accuracy 聚合：min(primary_score, secondary_score)（保守評分，幻覺不可接受）；Score 1-5：1=False, 2=Incomplete, 3=Partially Correct, 4=Correct, 5=Excellent | accuracy = min(two scores)；任一 judge 低分即拉低整體 | `LLMJudge.evaluate()` aggregation |
| FR-68 | CSAT 公式：CSAT = 0.4×速度 + 0.2×擬人化 + 0.2×禮貌度 + 0.2×準確度；aggregate_csat 以正規化公式計算；目標 CSAT 4.8（2025Q4 基準 3.2，+50%） | CSAT 公式計算正確；score 正規化至 0-5 範圍 | `LLMJudge.evaluate()` |
| FR-69 | 月度校準：golden set 500 筆；Cohen's Kappa ≥ 0.7（judge vs 人工標注）；觸發條件：CSAT 人工回饋與 judge 評分絕對偏差 > 15% | Kappa ≥ 0.7；偏差 > 15% 觸發緊急 recalibration | calibration pipeline |

### Module 15: 可觀測性

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-70 | StructuredLogger：JSON 格式，欄位含 timestamp(ISO 8601 Z), level, service, message 及任意 kwargs；支援 DEBUG/INFO/WARN/ERROR/CRITICAL；CRITICAL 用於安全事件 | JSON 日誌格式正確；各 level 正確路由至 Python logging | `StructuredLogger.log()` |
| FR-71 | Prometheus Metrics（9 種，全部顯式列出）：1. response_duration_seconds(histogram)；2. requests_total(counter)；3. fcr_total(counter)；4. knowledge_hit_total(counter, labels: tier)；5. pii_masked_total(counter)；6. escalation_queue_size(gauge)；7. emotion_escalation_total(counter)；8. escalation_sla_breach_total(counter)；9. llm_tokens_total(counter, labels: model) | 所有 9 個 metric 名稱正確定義；各 metric 類型（histogram/counter/gauge）正確；label 完整；Prometheus 抓取端點回傳所有 9 個 metric | Prometheus metrics definitions |
| FR-72 | OpenTelemetry Tracing：每請求完整 span tree（handle_message → emotion_analysis → knowledge_query → response_generation）；span attributes 含 platform, user_id, emotion, knowledge_source, confidence, trace_id | Span 樹正確；attributes 完整；trace_id 透過 HTTP header 跨服務傳遞 | `setup_tracing()`, tracer spans |
| FR-73 | 告警規則（4 條）：HighLatency（p95 > 0.8s for 5m, warning; p95 > 1.0s for 5m, critical）；HighErrorRate（error rate > 0.5% for 3m, critical）；EscalationQueueBacklog（queue > 50 for 10m, warning）；SLABreach（轉接 SLA 遵守率 < 90%, critical, for=0m） | 4 條告警規則正確定義；閾值符合規格；SLABreach for=0m 立即觸發 | Prometheus alert rules |
| FR-74 | Grafana Dashboard：連結 Prometheus + ODD SQL 指標；提供 FCR 折線圖、p95 延遲儀表、知識來源圓餅圖、成本時序圖；刷新頻率支援 24hr/7d/30d | Dashboard 面板存在；指標即時連動；<99.95% 可用性顯示早期警報 | Grafana dashboard config |

### Module 16: Background Job System

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-75 | SAQ Worker：queues=embedding(high, concurrency=3, timeout=30s) + maintenance(low, concurrency=1, timeout=60s) + notification(high, concurrency=5, timeout=10s)；stop_grace_period=30s（SIGTERM 緩衝） | Worker 正確訂閱各 queue；SIGTERM 後等待 30s 完成當前任務 | SAQ worker configuration |
| FR-76 | EmbeddingJob：欄位含 chunk_id, knowledge_id, content, model, retry_count, max_retries=3；失敗後指數退避 + jitter re-enqueue；p95 完成時間 < 30s | max_retries=3 後停止重試；指數退避含 jitter；p95 < 30s | `EmbeddingJob`, `process_embedding_job()` |
| FR-77 | 同步首 Chunk Embedding：單筆知識新增時，第一個 chunk 同步生成 embedding（asyncio.wait_for timeout=2.0s）；超時 → 記錄 warning，fallback 全部走非同步 | 單筆新增後 Tier 2 在 < 2.5s 內可搜尋到首 chunk；超時不阻斷主流程 | `create_knowledge_with_chunks()` |
| FR-78 | 批次匯入模式（> 10 筆）：is_batch=True → 所有 chunks 全部非同步排入 SAQ（不等待同步首 chunk）；per entry 延遲 < 50ms | 批次模式不等待首 chunk 同步；每筆插入 < 50ms | `batch_import_knowledge()` |
| FR-79 | Embedding 同步狀態 UI：知識庫列表顯示 🟡同步中（x/n chunks 完成）/🟢已同步/🔴失敗；embedding_synced_at 欄位標記全部完成時間 | UI 狀態標示正確；embedding_synced_at 在所有 chunks 完成後更新 | `knowledge_base.embedding_synced_at`, WebUI |

### Module 17: High Availability

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-80 | Redis Streams 異步處理：consumer group "omnibot"；XREADGROUP block=5000；XACK 確認處理；XPENDING/XCLAIM 處理 crash 消費者遺留的 pending 訊息；未知欄位寬容處理（forward compatibility） | Consumer group 建立成功；BUSYGROUP 錯誤靜默忽略；pending 訊息被 XCLAIM 後繼續處理 | `AsyncMessageProcessor` |
| FR-81 | 指數退避重試：max_retries=3, base_delay=1.0s, max_delay=30.0s, jitter=True；delay = min(base * 2^attempt, max) * (0.5 + random()) | 第 3 次後停止重試；delay 上限 30s；jitter 避免 thundering herd | `RetryStrategy.execute_with_retry()` |

### Module 18: Data Layer

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-82 | 完整資料庫 Schema（20 張表）：users, conversations, messages, knowledge_base, knowledge_chunks, platform_configs, escalation_queue, user_feedback, security_logs, emotion_history, edge_cases, pii_vault, roles, role_assignments, pii_audit_log, experiments, experiment_results, retry_log, encryption_config, schema_migrations；含 Index 定義；**必須包含 knowledge_chunks 的 GIN tsvector 全文搜尋索引（`CREATE INDEX ... USING gin(to_tsvector('simple', content))`，供 FR-99 level_embedding_down 降級使用）** | 20 張表可成功建立；所有 FK 約束正確；HNSW 索引 + GIN tsvector 索引均建立成功；level_embedding_down 可執行全文搜尋 | SQL DDL, Alembic migrations |
| FR-83 | Alembic Schema 遷移：每個 migration 含 upgrade() + downgrade()；staging 驗證通過再 production 執行；production 執行前建立快照 | migration 雙向測試通過；downgrade() 正確回退 | Alembic migration files |

### Module 19: API 端點

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-84 | Webhook API 端點（6 個）：POST /api/v1/webhook/telegram, /line, /messenger(GET+POST), /whatsapp(GET+POST), POST /api/v1/web/guest-session, /web/message, /a2a/rpc；各端點錯誤碼規範（AUTH_INVALID_SIGNATURE/RATE_LIMIT_EXCEEDED/VALIDATION_ERROR/INTERNAL_ERROR/LLM_TIMEOUT/AUTH_TOKEN_EXPIRED/AUTHZ_INSUFFICIENT_ROLE） | 各端點存在且回傳正確 HTTP status；錯誤碼規範一致 | FastAPI routers |
| FR-85 | 管理 API（8 個端點）：GET/POST /api/v1/knowledge；PUT/DELETE /api/v1/knowledge/{id}；POST /api/v1/knowledge/bulk；GET /api/v1/conversations；POST /api/v1/experiments；GET /api/v1/health | 各端點 RBAC 保護正確；分頁回應格式符合 PaginatedResponse；health 回傳 status/postgres/redis/uptime_seconds | FastAPI management routes |
| FR-86 | Auth & User API：POST /api/v1/auth/login（回傳 JWT access + refresh token）；POST /api/v1/auth/refresh；GET/POST /api/v1/users；POST/DELETE /api/v1/users/{user_id}/roles（admin 限定） | login 失敗回 401；role 管理需 system:write 權限；refresh token 正常換發 | auth module |
| FR-87 | M2M Token API：POST /api/v1/m2m/tokens（admin 限定，client_name, scopes, expires_in_days=90）→ 回傳 token 僅顯示一次；GET /api/v1/m2m/tokens（不顯示 token 值）；POST /api/v1/m2m/tokens/{client_id}/revoke；Token 格式：m2m_ prefix + 32 bytes random hex，儲存 SHA-256 hash | Token 建立僅回傳一次；儲存 hash 不存明文；90 天到期；revoke 成功後 token 立即失效 | M2M token management |
| FR-88 | GDPR API：GET /api/v1/users/{user_id}/data（匯出 JSON/CSV）；DELETE /api/v1/users/{user_id}/data（觸發異步刪除，30 天內完成，含 PII 欄位清除 + messages 內容 [REDACTED] + 稽核日誌） | data export 回傳合法 JSON/CSV；deletion 記錄 pii_audit_log 並異步執行；30 天 SLA | GDPR compliance module |

### Module 20: 安全基礎設施

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-89 | TDE 加密：PostgreSQL AES-256 加密，金鑰輪換週期 90 天，ssl_mode=verify-full；pii_vault 僅透過應用層解密（DBA 無法直接讀取），需 pii:decrypt 權限 | TDE 啟用；90 天輪換計畫存在；pii_vault 無法裸讀 | PostgreSQL TDE config |
| FR-90 | Redis 安全：TLS 啟用（tls-port 6380）；requirepass 環境變數注入（不 hard-code）；ACL 啟用，default_user 停用；RDB + AOF 雙備份 | Redis 拒絕明文連線；密碼從環境變數讀取；default user 已停用 | Redis security config |

### Module 21: GDPR & Data Lifecycle

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-91 | 資料保留政策：conversations(messages) 180 天 → 封存 cold storage(Parquet/S3)；封存後 2 年永久刪除；PII 稽核日誌 90 天 → 自動匿名化；情緒歷史 90 天 → 刪除；安全日誌 1 年 → 封存後 2 年刪除；用戶回饋永久保留（已去識別化） | 排程任務按保留期限正確執行；匿名化保留統計不保留 PII；封存格式為 Parquet/S3 | data retention scheduled jobs |
| FR-92 | 刪除權（Right to Erasure）：DELETE /api/v1/users/{user_id}/data 觸發異步刪除：users.profile=NULL + platform_user_id='DELETED'；messages.content='[REDACTED]'；pii_audit_log 記錄 gdpr_deletion 事件；30 天內完成 | 刪除後用戶 PII 欄位清除；messages 內容標記 REDACTED；稽核日誌存在；30 天 SLA | `execute_data_deletion()` |
| FR-93 | 查閱權（Right of Access）+ 可攜權：GET /api/v1/users/{user_id}/data 回傳結構化 JSON（含所有個人資料）；支援 CSV 格式 | 回傳完整個人資料；格式符合 JSON；CSV 可下載 | data export endpoint |
| FR-94 | pii_vault：original_text_encrypted(BYTEA), masked_text_encrypted(BYTEA) 均應用層加密儲存（拒絕明文）；category（PHONE/ADDRESS/SSN 等）；encryption_key_id 關聯外部 KMS；僅 dpo 角色透過應用層 API 解密 | 明文不落地；KMS key_id 正確關聯；dpo 可解密；其他角色解密失敗 | `pii_vault` table, KMS integration |

### Module 22: Deployment

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-95 | Docker Compose 開發環境：services 含 omnibot-api, postgres(pgvector/pgvector:pg16), redis(redis:7-alpine, TLS), otel-collector, prometheus, grafana；healthcheck 配置；pgdata volume | docker compose up 後所有 services healthy；health 端點回 200 | docker-compose.yml |
| FR-96 | Kubernetes 部署：Deployment（replicas=3, RollingUpdate maxUnavailable=1）+ HPA（min=3, max=10, CPU utilization=70%）+ PDB（minAvailable=2）+ NetworkPolicy（限制 ingress 來源）+ Service（LoadBalancer port=80）；secrets 透過 SealedSecrets/External Secrets 注入（不用明文 ConfigMap）；requests{cpu:500m,mem:512Mi} limits{cpu:2000m,mem:2Gi} | K8s 資源建立成功；HPA 在負載時自動擴縮；PDB 確保滾動更新不斷服務；Secrets 不明文 | K8s manifests |
| FR-97 | 備份策略：PostgreSQL pg_basebackup + WAL archiving（每日全備 + 持續 WAL，保留 30 天）；Redis RDB（每小時）+ AOF（每秒），保留 7 天；配置 Git 版控 | 備份排程存在且可執行；災備復原時間 < 5 分鐘 | backup scripts |
| FR-98 | Rollback 策略：knowledge_update（version + is_active 軟刪除）；model_switch（A/B Testing 漸進 10%→50%→100%，指標下降 > 5% 自動回退）；schema_migration（Alembic downgrade()）；experiment_abort（status='aborted'，流量回 control） | 各 rollback 路徑可執行；schema rollback 不丟失資料 | rollback procedures |

### Module 23: 降級策略（Circuit Breaker）

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-99 | 階梯式降級策略（**9 級（6 主級 + 3 橫向）**）：level_0=全功能；level_1=輕度延遲啟用快取（LLM p95>800ms for 2m）；level_2=關閉 Tier3 僅 Tier1+2（LLM p95>1.5s for 2m）；level_3=熔斷 LLM 僅 Tier1（連續失敗≥5次）；level_4=DB 降級啟用 Redis 快取（DB p95>2s for 1m）；level_embedding_down=Tier2 降級為 tsvector 全文搜尋（Embedding API 失敗≥3次或p95>5s for 2m）；level_classifier_down=Bypass L4（Classifier 失敗≥3次）；level_judge_down=暫停 Judge 改規則式（雙 Judge 失敗≥3次）；level_5=全面癱瘓靜態維護頁 | 各觸發條件正確觸發降級；恢復條件（連續成功次數）後自動回升；降級期間不影響已上線功能的基礎可用性 | circuit breaker implementation |

### Module 24: 多媒體訊息處理

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-100 | 多媒體處理路徑：Image → auto_escalate（不支援圖片理解）；Sticker → ignore + 固定回覆「請用文字描述您的問題」+ log sticker 頻率；Location → 解析經緯度，附帶於 conversation context；File → malware scan（ClamAV）+ size_limit 10MB + allowed_types[pdf,docx,xlsx,csv,txt] → auto_escalate（不支援解析）；ClamAV 失敗模式 = fail-secure（拒絕文件上傳 + 回傳 503 FILE_SCAN_UNAVAILABLE）；ClamAV 掃描 p95 延遲 < 500ms** | Image/File 自動觸發人工轉接；Sticker 回覆固定文字；Location 座標正確提取；File 超過 10MB 拒絕；ClamAV 不可用時回 503 FILE_SCAN_UNAVAILABLE（不放行） | media handling pipeline, ClamAV service |

### Module 25: 管理 WebUI

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-101 | Knowledge 管理 WebUI：條目 CRUD 列表；Markdown 知識編輯器；Keywords 標籤管理；批次 CSV/JSON 匯入/匯出；Embedding 同步狀態顯示（已同步/同步中）；UI 響應時間 < 1.5s | CRUD 操作正確；CSV/JSON 匯入成功；同步狀態即時更新 | WebUI frontend (React) |
| FR-102 | RAG Debugger：管理員輸入測試提問 → 展示 ILIKE 匹配結果+置信度、Child Chunk 餘弦相似度分數、Parent Chunk 內容、RRF k=60 Top-3 評分；相似度閾值滑桿（預設 0.75，沙盒調整不寫入 platform_configs） | Debugger 正確展示 Tier 1+2 決策流程；滑桿調整即時反映搜尋結果；沙盒調整不持久化 | RAG Debugger UI |
| FR-103 | Operations Dashboard：FCR 折線圖（< 90% 觸發黃色警報）；p95 延遲儀表（< 1.0s 綠色/> 1.0s 紅色）；知識來源圓餅圖（Tier 1/2/3/4 分布）；成本累計時序圖（月度上限 $500）；24hr/7d/30d 時序切換 | 各圖表正確顯示；KPI 告警觸發正確；時序切換正常 | Operations Dashboard UI |
| FR-104 | Agent Portal：轉接收件匣（Unassigned/My Chats/Resolved）+ WebSocket 即時連動；優先級色彩（urgent=紅/high=橙/normal=藍）；智慧接管面板（情緒歷史軌跡、對話時間軸、DST Slot 側邊欄、Grounding 知識背景高亮）；1 秒掌握背景 | 佇列 WebSocket 即時更新；優先級色彩正確；接管面板數據完整 | Agent Portal UI |

### Module 26: ODD SQL 分析

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-105 | ODD SQL 查詢集（10 個）：FCR 首問解決率（scope_type='in_scope' + 30天）；p95 回應延遲（含 platform 分組）；知識層命中分布（含百分比）；CSAT 分數；用戶回饋分析；轉接 SLA 遵守率；情緒觸發統計；安全阻擋率；成本效益分析；月度成本報告（Tier 1=$0/Tier 2=$0.003/Tier 3=$0.009）；PII 稽核摘要；RBAC 權限審計；A/B 實驗效果；**Judge Evaluation 成本：LLM-as-a-Judge 預設採 20% Sampling Rate（每 5 筆回應評估 1 筆），以控制 judge 成本在預估的 $9/月 範圍內（總 LLM API 成本控制在 $210 內）；sampling_rate 存入 experiments 表，可透過管理 API 動態調整（valid range 0.01–1.0）；成本 SQL 須含 judge_sample_rate 欄位** | 各 SQL 可正確執行；FCR 計算僅含 in_scope + 非 NULL；成本計算按 Tier 定價；judge sampling 預設 20%；成本報告含 judge_sample_rate | ODD SQL scripts, judge sampling config |

### Module 27: 負載測試

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-106 | k6 負載測試（4 場景）：smoke（10 VUs, 1m 基線）；load（200 VUs, 10m，p95<1000ms，error<1%）；stress（500→2000→3000→0 VUs 分階段）；spike（10s 衝 3000 VUs）；測試案例：FAQ(40%)、語義查詢(40%)、複雜查詢(10%)、情緒觸發(10%)；目標 2000 TPS | load 場景 p95 < 1000ms；error rate < 1%；stress 場景不崩潰；spike 場景恢復正常 | k6 load test scripts |

### Module 28: 測試策略

| FR ID | Requirement Description | Acceptance Criteria | Implementation Function |
|-------|------------------------|---------------------|------------------------|
| FR-107 | 測試金字塔：Unit 70%（InputSanitizer, PromptInjectionDefense, PIIMasking, DST, EmotionTracker, RateLimiter, RRF, RBAC, ABTestManager）；Integration 20%（Webhook→UnifiedMessage, HybridKnowledge 查詢路徑, ResponseGenerator, EscalationManager→WS, EmbeddingJob→SAQ）；E2E 10%（FAQ精確匹配、語意搜尋、多輪對話DST、情緒觸發轉接、Prompt Injection攔截、Fallback轉接） | unit/integration/e2e 覆蓋率達 70/20/10；6個 E2E 場景通過 | pytest test suite, k6 |
| FR-108 | 黃金數據集：500 筆邊界案例（6 類：語音亂碼/拼寫錯誤/方言簡稱/多意圖/情感爆發/Prompt Injection）；用於回歸測試自動化；edge_cases 表記錄（status: pending/approved/rejected） | 500 筆數量達標；6 類覆蓋；regression 測試可自動執行 | golden dataset + edge_cases table |
| FR-200 | PUT /api/v1/knowledge/{id} — 真正更新 KB row (title/content) 並重 embed 所有 chunks（超時走 enqueue_embedding_job） | RBAC: knowledge:write 通過；知識存在；回傳 200；role 不符 → 403；chunks 已用新向量覆寫；< 2.5s SLO | `app.api.management.update_knowledge` |
| FR-202 | GET /api/v1/conversations — 真正從 Postgres `conversations` 表讀取並回傳 PaginatedResponse (total/page/limit/has_next/items) | RBAC: escalate:read 通過；page/limit ∈ [1,100]；回傳 200 + PaginatedResponse；page 越界 → 空 items + has_next=false；未授權/型別錯 → 403 | `app.api.management.list_conversations` |
| FR-203 | POST /api/v1/experiments — 真正透過 ABTestManager 建實驗（traffic_split 驗證、寫 DB、status='active'、回傳 experiment_id） | RBAC: experiment:write 通過；payload 含 name/traffic_split/model；sum(traffic_split)==1.0；回傳 200；缺欄位/型別錯/role 不符 → 403；DB row 已建立且 status='active' | `app.api.management.create_experiment` |

---

## 3. Non-Functional Requirements (NFR)

| ID | Type | Requirement | Test Method | Related FR |
|----|------|-------------|-------------|------------|
| NFR-01 | Performance | p95 end-to-end latency < 1.0s（全負載） | k6 load test (p(95)<1000) | N/A |
| NFR-02 | Performance | L1-L3 合計延遲 < 5ms p95 | Unit benchmark | N/A |
| NFR-03 | Performance | L4 Semantic Classifier < 200ms p95（async） | L4 unit test with timing | N/A |
| NFR-04 | Performance | Embedding API < 300ms p95 | Integration test with timing | N/A |
| NFR-05 | Performance | A2A timeout = 2.0s | Fault injection test | N/A |
| NFR-06 | Performance | LLM fallback switch < 500ms | Fault injection test (primary LLM down) | N/A |
| NFR-07 | Performance | Agent Card TTL cache = 300s（不重複 discovery） | Unit test cache expiry | N/A |
| NFR-08 | Performance | Embedding job p95 < 30s | SAQ dashboard monitoring | N/A |
| NFR-09 | Throughput | 2000 TPS sustained（k6 load scenario） | k6 stress test | N/A |
| NFR-10 | Availability | 99.9% / month | Prometheus uptime monitor | N/A |
| NFR-11 | Availability | 早期告警閾值 < 99.95%（SLA 前觸發） | Prometheus alert: early-warning | N/A |
| NFR-12 | Availability | p95 > 0.8s → HighLatency 告警 | Prometheus alert rule | N/A |
| NFR-13 | Availability | error rate > 0.5% → 告警（> 1% = SLA breach） | Prometheus alert rule | N/A |
| NFR-14 | Availability | 災備復原時間 < 5 分鐘 | DR drill | N/A |
| NFR-15 | Security | OWASP LLM01:2025 合規（PALADIN 五層覆蓋） | Red-team + OWASP checklist | N/A |
| NFR-16 | Security | 安全阻擋率 ≥ 95% | Red-team test | N/A |
| NFR-17 | Security | 機密資料（secrets）不提交至版控 | git-secrets / pre-commit hook | N/A |
| NFR-18 | Cost | 月費用 < $500（含 GPU 推理、Embedding、備援） | Cost dashboard | N/A |
| NFR-19 | Cost | LLM API 基礎估算 ~$210/月（10 萬對話、Tier 2 覆蓋 40%） | Cost dashboard | N/A |
| NFR-20 | Compliance | 台灣個資法合規 | Legal review | N/A |
| NFR-21 | Compliance | GDPR Art.5(1)(e) 合規（資料最小化） | GDPR audit | N/A |
| NFR-22 | Compliance | SOC2 稽核軌跡 | SOC2 audit trail | N/A |
| NFR-23 | Quality | FCR ≥ 90%（in_scope 對話） | ODD SQL | N/A |
| NFR-24 | Quality | CSAT 目標 4.8（2025Q4 基準 3.2，+50%） | LLM-as-a-Judge monthly | N/A |
| NFR-25 | Quality | Escalation SLA 遵守率 ≥ 95% | ODD SQL | N/A |
| NFR-26 | Quality | LLM-as-a-Judge Cohen's Kappa ≥ 0.7 vs 人工標注 | 500 筆黃金集校準 | N/A |
| NFR-27 | Quality | Grounding check pass rate 100%（cosine ≥ 0.75） | L5 unit tests | N/A |
| NFR-28 | Quality | Recall@3 ≥ 92%（HNSW 1536維） | Golden set regression | N/A |
| NFR-29 | Quality | Agentic tool success rate ≥ 95% | Integration tests | N/A |
| NFR-30 | Scalability | Kubernetes HPA min=3, max=10, CPU target=70% | K8s load test | N/A |
| NFR-31 | Observability | 每請求完整 OpenTelemetry trace | Trace sampling verification | N/A |
| NFR-32 | Testability | Unit 70% + Integration 20% + E2E 10% coverage | pytest-cov | N/A |
| NFR-33 | Resilience | Rate Limiter fail-open on Redis unavailability | Redis failure injection | N/A |
| NFR-34 | Resilience | IP Whitelist fail-secure (403) on no match | Security test | N/A |
| NFR-35 | Resilience | IP Whitelist max 100 CIDR blocks | Config validation test | N/A |
| NFR-36 | Resilience | M2M token 90 天到期 | Token expiry unit test | N/A |
| NFR-37 | Performance | Admin WebUI 響應時間 < 1.5s，100% 資料即時連動 | Lighthouse audit + manual | N/A |
| NFR-38 | Performance | ClamAV 文件掃描 p95 < 500ms | Integration test with timing | N/A |

---

## 4. Constraints

- **語言**：Python 3.11（uv 管理 venv）
- **框架**：FastAPI
- **資料庫**：PostgreSQL 16 + pgvector（HNSW m=16, ef_construction=64）
- **Cache/Queue**：Redis 7（ZSET 速率限制 + Streams 異步）
- **Embedding**：OpenAI text-embedding-3-small 1536 維（更換模型需同步更新 vector(N) 維度 + 重建 HNSW + 更新 EMBEDDING_DIM）
- **Primary LLM**：gpt-4o（環境變數配置，不 hard-code）
- **Fallback LLM**：gemini-1.5-flash（環境變數 FALLBACK_LLM_MODEL，不 hard-code）
- **開發週期**：8-11 週（4 名後端 + 2 名 SRE）
- **Out of Scope（v8.1）**：圖片/視頻理解、檔案內容解析、語音輸入、多語言（僅 zh-TW + English）、自訂 LLM fine-tuning、原生 mobile app

---

## 5. Glossary

| Term | Definition |
|------|------------|
| FCR | First Contact Resolution — 24 小時內未針對同一意圖再次進線即視為解決 |
| CSAT | Customer Satisfaction Score — CSAT = 0.4×速度 + 0.2×擬人化 + 0.2×禮貌度 + 0.2×準確度 |
| PALADIN | 五層 Prompt Injection 防禦架構（L1-L5） |
| DST | Dialogue State Tracking — 8 狀態 FSM |
| RRF | Reciprocal Rank Fusion — k=60 排名融合 |
| RAG | Retrieval-Augmented Generation |
| HNSW | Hierarchical Navigable Small World — pgvector 向量索引算法 |
| Parent-Child | 500-token parent 送 LLM，150-token child 建向量索引 |
| M2M | Machine-to-Machine — 外部 Agent 使用的 OAuth2/JWT 憑證 |
| A2A | Agent-to-Agent Protocol — JSON-RPC 2.0 跨 Agent 通訊 |
| MCP | Model Context Protocol — Anthropic 定義的工具呼叫協議 |
| ODD | Operational Data Dashboard — 以 SQL 計算 KPI |
| SAQ | Simple Async Queue — 輕量 Redis-backed 異步任務佇列 |
| AEE | Action Execution Engine — 管理 MCP/A2A/CLI Adapter 的工具執行層 |
| TDE | Transparent Data Encryption — PostgreSQL AES-256 加密 |
| pii_vault | PII 加密保管庫，僅 dpo 角色可透過應用層解密 |
| Fail-open | Redis 不可用時放行請求（速率限制），避免全面服務中斷 |
| Fail-secure | IP 無匹配時拒絕請求（403），保守安全策略 |
| Sandwich Prompt | 系統指令 + 知識 context + 用戶訊息的分層 Prompt 結構（L3 防注入） |
| Spotlighting | 明確 UNTRUSTED DATA BOUNDARY 分隔符（Hines et al., 2024） |

---

## 6. Cross-Cutting Test Requirements

### API Completeness（每個端點必須有以下四類測試）

- 正常流程 (2xx)
- 認證失敗 (401)
- 速率限制 (429)
- 驗證錯誤 (400/422)

**端點清單**（開發者補充測試名稱）：
- [ ] `test_webhook_telegram_valid_signature_returns_200`
- [ ] `test_webhook_telegram_invalid_signature_returns_401`
- [ ] `test_webhook_telegram_rate_limit_returns_429`
- [ ] `test_webhook_line_valid_signature_returns_200`
- [ ] `test_webhook_line_invalid_signature_returns_401`
- [ ] `test_webhook_messenger_hub_challenge_returns_challenge`
- [ ] `test_webhook_whatsapp_hub_challenge_returns_challenge`
- [ ] `test_web_guest_session_returns_jwt`
- [ ] `test_web_message_invalid_jwt_returns_401`
- [ ] `test_a2a_rpc_valid_m2m_token_returns_200`
- [ ] `test_a2a_rpc_invalid_m2m_token_returns_401`
- [ ] `test_knowledge_create_requires_knowledge_write`
- [ ] `test_knowledge_delete_requires_knowledge_delete`
- [ ] `test_health_endpoint_returns_200`

### Security Red Team

- [ ] `test_redteam_prompt_injection_direct_telegram_payload`
- [ ] `test_redteam_prompt_injection_indirect_knowledge_content`
- [ ] `test_redteam_rate_limit_burst_attack_blocked`
- [ ] `test_redteam_pii_mixed_phone_email_leak_detected`
- [ ] `test_redteam_pii_credit_card_luhn_valid_masked`
- [ ] `test_redteam_homoglyph_cyrillic_normalized`
- [ ] `test_redteam_ip_whitelist_unauthorized_ip_returns_403`

### KPI Gates（對應 ODD SQL + k6）

- [ ] `test_kpi_p95_latency_phase1_under_1s`
- [ ] `test_kpi_fcr_phase1_target_90_percent`
- [ ] `test_kpi_recall_at_3_hnsw_above_92_percent`
- [ ] `test_kpi_grounding_cosine_above_075`
- [ ] `test_kpi_escalation_sla_compliance_above_95_percent`

### Deployment Smoke

- [ ] `test_deploy_docker_compose_all_services_healthy`
- [ ] `test_deploy_health_endpoint_returns_200_after_startup`
- [ ] `test_backup_pg_basebackup_and_restore`

### Version Consistency（Phase 2+ 必填）

- [ ] `test_backward_compat_phase1_tests_pass_in_phase2_env`

---

## 7. FR Block (machine-readable)

<!-- FR:START -->
```json
{
    "version": "1.0",
    "created_at": "2026-06-17",
    "phase": 1,
    "project": "omnibot",
    "functional_requirements": [
        {
            "id": "FR-01",
            "description": "Telegram Webhook Adapter with HMAC-SHA256 signature verification",
            "implementation_functions": [
                "TelegramWebhookVerifier.verify",
                "telegram_adapter"
            ],
            "verification_method": "Unit: valid req -> 200; invalid sig -> 401 {\"error\": \"AUTH_INVALID_SIGNATURE\"}"
        },
        {
            "id": "FR-02",
            "description": "LINE Webhook Adapter with HMAC-SHA256 Base64 signature verification",
            "implementation_functions": [
                "LineWebhookVerifier.verify",
                "line_adapter"
            ],
            "verification_method": "Unit: valid req -> 200; invalid sig -> 401 {\"error\": \"AUTH_INVALID_SIGNATURE\"}"
        },
        {
            "id": "FR-03",
            "description": "Messenger Webhook GET challenge verification + POST HMAC-SHA256",
            "implementation_functions": [
                "MessengerWebhookVerifier.verify",
                "messenger_adapter"
            ],
            "verification_method": "Unit: valid req -> 200; invalid sig -> 401 {\"error\": \"AUTH_INVALID_SIGNATURE\"}"
        },
        {
            "id": "FR-04",
            "description": "WhatsApp Webhook GET challenge + POST sha256= prefix HMAC verification",
            "implementation_functions": [
                "WhatsAppWebhookVerifier.verify",
                "whatsapp_adapter"
            ],
            "verification_method": "Unit: valid req -> 200; invalid sig -> 401 {\"error\": \"AUTH_INVALID_SIGNATURE\"}"
        },
        {
            "id": "FR-05",
            "description": "Web Platform Adapter: guest-session JWT + web message JWT BearerAuth",
            "implementation_functions": [
                "WebAdapter",
                "jwt_middleware"
            ],
            "verification_method": "guest-session→JWT; invalid JWT→401; rate limit→429"
        },
        {
            "id": "FR-06",
            "description": "A2A Platform Adapter JSON-RPC 2.0 with M2M OAuth2/JWT",
            "implementation_functions": [
                "A2AAdapter",
                "m2m_auth_middleware"
            ],
            "verification_method": "valid M2M→200 JSON-RPC; invalid→401"
        },
        {
            "id": "FR-07",
            "description": "UnifiedMessage immutable dataclass (platform, user_id, message_type, content, raw_payload, received_at, reply_token)",
            "implementation_functions": [
                "UnifiedMessage"
            ],
            "verification_method": "Unit: all platforms create valid instance; frozen=True"
        },
        {
            "id": "FR-08",
            "description": "UnifiedResponse immutable dataclass (content, source, confidence, knowledge_id, emotion_adjustment, quick_replies)",
            "implementation_functions": [
                "UnifiedResponse"
            ],
            "verification_method": "Unit: source limited to rule|rag|wiki|escalate"
        },
        {
            "id": "FR-09",
            "description": "ApiResponse[T] + PaginatedResponse[T] unified response format",
            "implementation_functions": [
                "ApiResponse",
                "PaginatedResponse"
            ],
            "verification_method": "All management API responses wrap ApiResponse"
        },
        {
            "id": "FR-10",
            "description": "PALADIN L1 InputSanitizer: NFKC + homoglyph substitution + control char removal, <2ms",
            "implementation_functions": [
                "InputSanitizer.sanitize"
            ],
            "verification_method": "Unit: Cyrillic/Greek chars normalized; latency <2ms"
        },
        {
            "id": "FR-11",
            "description": "PALADIN L2 Pattern Detection: 13 SUSPICIOUS_PATTERNS regex + Unicode variant, <3ms",
            "implementation_functions": [
                "PromptInjectionDefense.check_input"
            ],
            "verification_method": "Unit: all 13 patterns hit; normal messages no false positive; latency <3ms"
        },
        {
            "id": "FR-12",
            "description": "PALADIN L3 Instruction Hierarchy: Sandwich Prompt with UNTRUSTED DATA BOUNDARY, L1-L3 <5ms total",
            "implementation_functions": [
                "PromptInjectionDefense.build_sandwich_prompt"
            ],
            "verification_method": "Unit: 3 boundary markers present; total L1-L3 <5ms"
        },
        {
            "id": "FR-13",
            "description": "PALADIN L4 SemanticInjectionClassifier: LLM-based, <200ms p95, timeout→pass with 'unverified'",
            "implementation_functions": [
                "SemanticInjectionClassifier.classify"
            ],
            "verification_method": "Unit: valid JSON response; timeout doesn't block; injection_type 4 values"
        },
        {
            "id": "FR-14",
            "description": "PALADIN L5 GroundingChecker: cosine similarity ≥0.75 threshold, 1536-dim, <5ms",
            "implementation_functions": [
                "GroundingChecker.check"
            ],
            "verification_method": "Unit: score<0.75→False; score≥0.75→True; no source→False; <5ms"
        },
        {
            "id": "FR-15",
            "description": "PALADIN L4 parallel pipeline: low→skip L4; medium→parallel L3+L4; high→sync block no L3",
            "implementation_functions": [
                "PALADINPipeline.process"
            ],
            "verification_method": "Unit: low risk no L4 call; medium parallel; high sync block"
        },
        {
            "id": "FR-16",
            "description": "L4 retrospective blocking: injection_retrospective_block logged to security_logs",
            "implementation_functions": [
                "PALADINPipeline.process"
            ],
            "verification_method": "Integration: retrospective block event in security_logs"
        },
        {
            "id": "FR-17",
            "description": "Per-platform L4 retraction strategy (Telegram deleteMessage; LINE apology; Messenger DELETE; WhatsApp apology; Web WS replace; A2A revoked:true)",
            "implementation_functions": [
                "platform_retraction_handlers"
            ],
            "verification_method": "Integration: each platform retraction path tested"
        },
        {
            "id": "FR-18",
            "description": "PIIMasking: phone/email/Taiwan address/credit card (Luhn) detection and masking",
            "implementation_functions": [
                "PIIMasking.mask"
            ],
            "verification_method": "Unit: 4 PII types masked; Luhn invalid→not masked; mask_count correct"
        },
        {
            "id": "FR-19",
            "description": "PII sensitive keyword escalation: 密碼/銀行帳戶/信用卡號/提款卡 → should_escalate()=True",
            "implementation_functions": [
                "PIIMasking.should_escalate"
            ],
            "verification_method": "Unit: 4 keywords trigger True; others False"
        },
        {
            "id": "FR-20",
            "description": "PII audit log: pii_audit_log write on each mask event, 90-day retention then anonymize",
            "implementation_functions": [
                "pii_audit_log table",
                "retention_job"
            ],
            "verification_method": "Integration: audit log created; scheduled job anonymizes after 90d"
        },
        {
            "id": "FR-21",
            "description": "Redis sliding window rate limiter (Lua atomic ZSET): Telegram/LINE/Messenger/WhatsApp 30/s, Web 10/s, Agent 100/s",
            "implementation_functions": [
                "RateLimiter.allow"
            ],
            "verification_method": "Unit: over limit→429; under limit→pass; Lua atomic correctness"
        },
        {
            "id": "FR-22",
            "description": "Rate Limiter fail-open on Redis unavailability: allow + log warning, no exception",
            "implementation_functions": [
                "RateLimiter.allow"
            ],
            "verification_method": "Unit: ConnectionError→True + warning log; no exception raised"
        },
        {
            "id": "FR-23",
            "description": "IP Whitelist CIDR-based (max 100), X-Forwarded-For leftmost IP, no match→403 empty body; empty WL or bad IP header→400+warning",
            "implementation_functions": [
                "IPWhitelist.is_allowed"
            ],
            "verification_method": "Unit: valid IP pass; invalid→403; empty WL→400; bad header→400"
        },
        {
            "id": "FR-24",
            "description": "Middleware chain order: TLS→IP Whitelist→Webhook Signature→Platform Adapter→Rate Limit→RBAC",
            "implementation_functions": [
                "middleware chain"
            ],
            "verification_method": "Integration: chain order verified via request tracing"
        },
        {
            "id": "FR-25",
            "description": "IPWhitelist error handling: invalid CIDR→IPWhitelistError at startup; invalid IP in is_allowed→False (no exception)",
            "implementation_functions": [
                "IPWhitelist.__init__",
                "IPWhitelist.is_allowed"
            ],
            "verification_method": "Unit: bad CIDR raises at init; bad IP returns False"
        },
        {
            "id": "FR-26",
            "description": "Knowledge Tier 1 rule matching: PostgreSQL ILIKE + keywords, confidence≥0.80 direct return, LIMIT 5",
            "implementation_functions": [
                "HybridKnowledge._rule_match"
            ],
            "verification_method": "Unit: confidence≥0.80 returns rule; <0.80 falls through to T2"
        },
        {
            "id": "FR-27",
            "description": "Knowledge Tier 2 RAG+RRF k=60: pgvector HNSW 1536-dim, Child→Parent, Top-10 dedup to Top-5, confidence≥0.85",
            "implementation_functions": [
                "HybridKnowledge._rag_search",
                "_reciprocal_rank_fusion"
            ],
            "verification_method": "Unit: RRF ranking correct; confidence≥0.85 returns rag; Parent-Child lookup correct"
        },
        {
            "id": "FR-28",
            "description": "Parent-Child chunking: 500-token parent (100-token overlap), 150-token child; child indexed, parent sent to LLM",
            "implementation_functions": [
                "chunking module",
                "knowledge_chunks table"
            ],
            "verification_method": "Unit: chunk sizes correct; vector search hits child→parent lookup succeeds"
        },
        {
            "id": "FR-29",
            "description": "HNSW index: vector_cosine_ops, m=16, ef_construction=64, partial WHERE embeddings IS NOT NULL; Recall@3≥92%",
            "implementation_functions": [
                "CREATE INDEX USING hnsw"
            ],
            "verification_method": "Schema test: index created; golden set Recall@3≥92%"
        },
        {
            "id": "FR-30",
            "description": "Knowledge Tier 3 LLM generation: gpt-4o→gemini fallback, Sandwich Prompt, L5 grounding≥0.75, fallback <500ms",
            "implementation_functions": [
                "HybridKnowledge._llm_generate",
                "_call_llm_api"
            ],
            "verification_method": "Integration: primary failure→fallback; grounding<0.75→escalate; fallback<500ms"
        },
        {
            "id": "FR-31",
            "description": "Knowledge Tier 4 human escalation: all tiers fail→escalate; source=escalate, id=-1",
            "implementation_functions": [
                "HybridKnowledge._escalate"
            ],
            "verification_method": "Integration: T1-T3 no match→escalate with id=-1"
        },
        {
            "id": "FR-32",
            "description": "KnowledgeResult frozen dataclass (id, content, confidence, source, knowledge_id); id=-1 for non-KB",
            "implementation_functions": [
                "KnowledgeResult"
            ],
            "verification_method": "Unit: source limited to 4 values; id=-1 recognized as non-KB"
        },
        {
            "id": "FR-33",
            "description": "HybridKnowledge query orchestrator: T1→T2→T3→T4 sequential; EMBEDDING_DIM=1536",
            "implementation_functions": [
                "HybridKnowledge.query"
            ],
            "verification_method": "Unit: query path follows T1→T4 order; EMBEDDING_DIM constant=1536"
        },
        {
            "id": "FR-34",
            "description": "8-state FSM: ALLOWED_TRANSITIONS enforced; invalid transition raises ValueError; turn_count+1 per transition",
            "implementation_functions": [
                "DialogueState.transition",
                "ALLOWED_TRANSITIONS"
            ],
            "verification_method": "Unit: all legal transitions succeed; illegal→ValueError; turn_count increments"
        },
        {
            "id": "FR-35",
            "description": "Slot filling: order_status needs order_id; return_request needs order_id+reason; missing_slots() correct",
            "implementation_functions": [
                "DialogueSlot",
                "INTENT_TO_SLOTS",
                "DialogueState.missing_slots"
            ],
            "verification_method": "Unit: missing required slots returned; filled slots not in missing"
        },
        {
            "id": "FR-36",
            "description": "Auto-escalate: slot_filling>3 rounds→ESCALATED; confidence<0.65→ESCALATED",
            "implementation_functions": [
                "DST state machine transitions"
            ],
            "verification_method": "Unit: 3 rounds trigger escalation; confidence<0.65 triggers escalation"
        },
        {
            "id": "FR-37",
            "description": "AWAITING_CONFIRMATION timeout: >2 rounds unconfirmed→ESCALATED; confirm→PROCESSING; deny→SLOT_FILLING",
            "implementation_functions": [
                "DST transitions"
            ],
            "verification_method": "Unit: 2 rounds unconfirmed→ESCALATED; confirm/deny transitions correct"
        },
        {
            "id": "FR-38",
            "description": "Context Window Management: sliding_window_with_summarization, max_tokens=8192, overflow→LLM summary of earliest 1/3",
            "implementation_functions": [
                "ContextWindowManager.manage"
            ],
            "verification_method": "Unit: token count correct; overflow triggers summary; recent 1/3 preserved"
        },
        {
            "id": "FR-39",
            "description": "ActionAdapter abstract: list_tools()→List[ToolDefinition]; execute(name, args)→ToolExecutionResult",
            "implementation_functions": [
                "ActionAdapter",
                "ToolDefinition",
                "ToolExecutionResult"
            ],
            "verification_method": "Unit: all adapters implement interface; ToolExecutionResult has success/output/error_message"
        },
        {
            "id": "FR-40",
            "description": "MCPAdapter: stdio/SSE to external MCP Server; list_tools from MCP capabilities",
            "implementation_functions": [
                "MCPAdapter"
            ],
            "verification_method": "Integration: connects to MCP Server; tool call returns result"
        },
        {
            "id": "FR-41",
            "description": "A2AAdapter: agent card discovery (/.well-known/agent.json, 300s TTL); JSON-RPC 2.0, timeout=2.0s; unreachable→empty tools",
            "implementation_functions": [
                "A2AAdapter._discover_agent_card",
                "A2AAdapter.execute"
            ],
            "verification_method": "Unit: cache TTL correct; timeout→ToolExecutionResult(success=False); unreachable→empty list no exception"
        },
        {
            "id": "FR-42",
            "description": "CLIAdapter: sandboxed script execution→ToolExecutionResult",
            "implementation_functions": [
                "CLIAdapter"
            ],
            "verification_method": "Unit: success→True; failure→False+error_message"
        },
        {
            "id": "FR-43",
            "description": "ToolExecutor: register+execute; default tools: get_shipping_status, update_shipping_address (blocked if shipped/delivered)",
            "implementation_functions": [
                "ToolExecutor",
                "_get_shipping_status",
                "_update_shipping_address"
            ],
            "verification_method": "Unit: unknown tool→success=False; update blocked in shipped/delivered state"
        },
        {
            "id": "FR-44",
            "description": "OmniBot Agent Card: GET /.well-known/agent.json returns valid agent card JSON",
            "implementation_functions": [
                "agent_card endpoint"
            ],
            "verification_method": "Integration: endpoint returns 200 with name/url/methods/auth_schemes"
        },
        {
            "id": "FR-45",
            "description": "ToolDefinition shared dataclass: AEE and DST use same class, no duplication",
            "implementation_functions": [
                "ToolDefinition shared"
            ],
            "verification_method": "Code review: single ToolDefinition import path"
        },
        {
            "id": "FR-46",
            "description": "EmotionAnalyzer: classify positive/neutral/negative, intensity 0.0-1.0",
            "implementation_functions": [
                "EmotionScore",
                "emotion_classify"
            ],
            "verification_method": "Unit: category limited to 3 values; intensity in [0.0, 1.0]"
        },
        {
            "id": "FR-47",
            "description": "Temporal decay: 24hr half-life exponential decay in current_weighted_score()",
            "implementation_functions": [
                "EmotionTracker.current_weighted_score"
            ],
            "verification_method": "Unit: 24hr ago score=50% of current; decay formula correct"
        },
        {
            "id": "FR-48",
            "description": "Escalation trigger: consecutive_negative_count()≥3→should_escalate()=True",
            "implementation_functions": [
                "EmotionTracker.should_escalate"
            ],
            "verification_method": "Unit: 3 consecutive negative→True; non-negative interrupts count"
        },
        {
            "id": "FR-49",
            "description": "AGENT platform bypass: skip emotion analysis for platform==AGENT",
            "implementation_functions": [
                "platform check in pipeline"
            ],
            "verification_method": "Unit: AGENT platform messages skip emotion module"
        },
        {
            "id": "FR-50",
            "description": "Template system: rule_default, rag_default (with 📌 suffix), escalate (with case number)",
            "implementation_functions": [
                "ResponseGenerator.DEFAULT_TEMPLATES"
            ],
            "verification_method": "Unit: 3 templates exist; variable interpolation correct"
        },
        {
            "id": "FR-51",
            "description": "Emotion tone: negative+intensity>0.7→apology prefix; positive→positive prefix; repeat_count>0→suppress repeat apology",
            "implementation_functions": [
                "ResponseGenerator._apply_emotion_tone"
            ],
            "verification_method": "Unit: tone rules trigger at correct thresholds; suppression works"
        },
        {
            "id": "FR-52",
            "description": "A/B variant injection: SHA-256 deterministic; variant_a/b suffix injection; control→no injection",
            "implementation_functions": [
                "ResponseGenerator._apply_ab_variant",
                "ABTestManager.get_variant"
            ],
            "verification_method": "Unit: same input→same variant cross-process; control unchanged"
        },
        {
            "id": "FR-53",
            "description": "Platform format adapter: per-platform character limits and formatting",
            "implementation_functions": [
                "platform format adapters"
            ],
            "verification_method": "Unit: Telegram 4096, LINE 5000, Messenger 2000 truncation; Agent pure JSON"
        },
        {
            "id": "FR-54",
            "description": "EscalationManager: create/assign/resolve escalation_queue records",
            "implementation_functions": [
                "EscalationManager.create",
                ".assign",
                ".resolve"
            ],
            "verification_method": "Integration: create→record in DB; assign→assigned_agent updated; resolve→resolved_at set"
        },
        {
            "id": "FR-55",
            "description": "Escalation SLA: normal=30min, high=15min, urgent=5min; breach detection via get_sla_breaches()",
            "implementation_functions": [
                "EscalationManager.SLA_BY_PRIORITY",
                "get_sla_breaches"
            ],
            "verification_method": "Unit: sla_deadline correct for each priority; breach query accurate"
        },
        {
            "id": "FR-56",
            "description": "WebSocket push on escalation.new: push to /ws/agent with full payload",
            "implementation_functions": [
                "EscalationManager + WebSocket push"
            ],
            "verification_method": "Integration: escalation created→WS message received within 1s"
        },
        {
            "id": "FR-57",
            "description": "/ws/agent WebSocket: 6 event types; JWT auth",
            "implementation_functions": [
                "/ws/agent handler"
            ],
            "verification_method": "Integration: all 6 event types sent/received correctly; invalid JWT rejected"
        },
        {
            "id": "FR-58",
            "description": "/ws/user WebSocket: message.reply push; JWT auth",
            "implementation_functions": [
                "/ws/user handler"
            ],
            "verification_method": "Integration: message.reply received by Web client; JWT verified"
        },
        {
            "id": "FR-59",
            "description": "WebSocket heartbeat: 30s ping; 10s timeout disconnect; subscribe/subscribed flow",
            "implementation_functions": [
                "WebSocket lifecycle"
            ],
            "verification_method": "Integration: 10s no pong→disconnect event sent; subscribe returns subscribed"
        },
        {
            "id": "FR-60",
            "description": "7 RBAC roles: anonymous/customer/agent/editor/admin/auditor/dpo with permissions matrix",
            "implementation_functions": [
                "ROLE_PERMISSIONS"
            ],
            "verification_method": "Unit: 7 roles defined; dpo has pii:decrypt; auditor does not"
        },
        {
            "id": "FR-61",
            "description": "Complete permission matrix: resource/action per role as specified",
            "implementation_functions": [
                "ROLE_PERMISSIONS"
            ],
            "verification_method": "Unit: all role×resource×action combinations match spec"
        },
        {
            "id": "FR-62",
            "description": "RBACEnforcer decorator: @rbac.require(resource, action); no permission→403 AUTHZ_INSUFFICIENT_ROLE",
            "implementation_functions": [
                "RBACEnforcer.require",
                "check"
            ],
            "verification_method": "Unit: unauthorized→PermissionError→403; authorized→pass"
        },
        {
            "id": "FR-63",
            "description": "ABTestManager SHA-256 deterministic variant assignment; run_experiment with variant prompt",
            "implementation_functions": [
                "ABTestManager.get_variant",
                "run_experiment"
            ],
            "verification_method": "Unit: same user+experiment→same variant cross-process; hashlib.sha256 used"
        },
        {
            "id": "FR-64",
            "description": "auto_promote: min_sample=100; diff≥0.05→promote best variant, status='completed'",
            "implementation_functions": [
                "ABTestManager.auto_promote"
            ],
            "verification_method": "Unit: sample<100→None; diff≥0.05 with sufficient sample→promote"
        },
        {
            "id": "FR-65",
            "description": "Ensemble Judge: gpt-4o-mini + claude-3-5-haiku, temp=0, parallel calls",
            "implementation_functions": [
                "LLMJudge.evaluate"
            ],
            "verification_method": "Unit: 2 judges called in parallel; temperature=0 in config"
        },
        {
            "id": "FR-66",
            "description": "Politeness aggregation: max(primary, secondary)",
            "implementation_functions": [
                "LLMJudge.evaluate aggregation"
            ],
            "verification_method": "Unit: politeness=max(scores)"
        },
        {
            "id": "FR-67",
            "description": "Accuracy aggregation: min(primary, secondary)",
            "implementation_functions": [
                "LLMJudge.evaluate aggregation"
            ],
            "verification_method": "Unit: accuracy=min(scores)"
        },
        {
            "id": "FR-68",
            "description": "CSAT formula: 0.4*speed + 0.2*anthropomorphism + 0.2*politeness + 0.2*accuracy; normalize to 0-5",
            "implementation_functions": [
                "LLMJudge.evaluate"
            ],
            "verification_method": "Unit: CSAT formula correct; output in [0, 5]"
        },
        {
            "id": "FR-69",
            "description": "Monthly calibration: 500 golden set, Kappa≥0.7; recalibrate if CSAT deviation>15%",
            "implementation_functions": [
                "calibration pipeline"
            ],
            "verification_method": "Monthly: Kappa computed and compared; trigger at >15% deviation"
        },
        {
            "id": "FR-70",
            "description": "StructuredLogger: JSON format, timestamp+level+service+message fields",
            "implementation_functions": [
                "StructuredLogger.log"
            ],
            "verification_method": "Unit: JSON parseable; all required fields present"
        },
        {
            "id": "FR-71",
            "description": "Prometheus metrics: 9 metric definitions with correct types and labels",
            "implementation_functions": [
                "Prometheus metrics definitions"
            ],
            "verification_method": "Integration: all metrics scraped; label cardinality correct"
        },
        {
            "id": "FR-72",
            "description": "OpenTelemetry tracing: full span tree per request; trace_id in response header",
            "implementation_functions": [
                "setup_tracing",
                "tracer spans"
            ],
            "verification_method": "Integration: spans created for all pipeline stages; trace_id propagated"
        },
        {
            "id": "FR-73",
            "description": "Alert rules: HighLatency (warning/critical), HighErrorRate, EscalationQueueBacklog, SLABreach (for=0m)",
            "implementation_functions": [
                "Prometheus alert rules"
            ],
            "verification_method": "Config test: 4 alert rules defined with correct thresholds"
        },
        {
            "id": "FR-74",
            "description": "Grafana dashboard: 4 panels connected to metrics and ODD SQL",
            "implementation_functions": [
                "Grafana dashboard config"
            ],
            "verification_method": "Manual: all 4 panels render; data updates correctly"
        },
        {
            "id": "FR-75",
            "description": "SAQ Worker: 3 queues (embedding/maintenance/notification), concurrency+timeout per queue, 30s grace period",
            "implementation_functions": [
                "SAQ worker configuration"
            ],
            "verification_method": "Integration: workers consume from correct queues; SIGTERM waits 30s"
        },
        {
            "id": "FR-76",
            "description": "EmbeddingJob: max_retries=3, exponential backoff+jitter, p95<30s",
            "implementation_functions": [
                "EmbeddingJob",
                "process_embedding_job"
            ],
            "verification_method": "Integration: 3 retries with backoff; p95<30s on golden set"
        },
        {
            "id": "FR-77",
            "description": "Sync first chunk embedding: single insert→first chunk sync within 2.0s timeout; timeout→async fallback",
            "implementation_functions": [
                "create_knowledge_with_chunks"
            ],
            "verification_method": "Integration: T2 searchable within 2.5s of insert; timeout doesn't block"
        },
        {
            "id": "FR-78",
            "description": "Batch import mode: is_batch=True→all chunks async, per-entry<50ms",
            "implementation_functions": [
                "batch_import_knowledge"
            ],
            "verification_method": "Performance: batch insert<50ms per entry; no sync waiting"
        },
        {
            "id": "FR-79",
            "description": "Embedding sync status UI: 🟡syncing/🟢synced/🔴failed display; embedding_synced_at column",
            "implementation_functions": [
                "knowledge_base.embedding_synced_at",
                "WebUI"
            ],
            "verification_method": "Manual: UI status updates correctly; embedding_synced_at set after all chunks done"
        },
        {
            "id": "FR-80",
            "description": "Redis Streams: consumer group; XACK; XCLAIM for crashed consumers; unknown fields ignored",
            "implementation_functions": [
                "AsyncMessageProcessor"
            ],
            "verification_method": "Integration: pending messages reclaimed; unknown fields don't cause errors"
        },
        {
            "id": "FR-81",
            "description": "Retry strategy: max=3, base=1.0s, max=30.0s, jitter=True",
            "implementation_functions": [
                "RetryStrategy.execute_with_retry"
            ],
            "verification_method": "Unit: 3 retries; delay<30s; jitter applied"
        },
        {
            "id": "FR-82",
            "description": "Complete DB schema: 20 tables with indexes and FK constraints",
            "implementation_functions": [
                "SQL DDL",
                "Alembic migrations"
            ],
            "verification_method": "Schema test: all 20 tables created; all FK and indexes valid"
        },
        {
            "id": "FR-83",
            "description": "Alembic migrations: upgrade()+downgrade() per migration; staging before prod",
            "implementation_functions": [
                "Alembic migration files"
            ],
            "verification_method": "Test: upgrade+downgrade roundtrip on staging; no data loss"
        },
        {
            "id": "FR-84",
            "description": "6 webhook + 2 web + 1 A2A API endpoints with standard error codes",
            "implementation_functions": [
                "FastAPI routers"
            ],
            "verification_method": "API test: all endpoints exist; error codes per spec"
        },
        {
            "id": "FR-85",
            "description": "8 management API endpoints with RBAC protection",
            "implementation_functions": [
                "FastAPI management routes"
            ],
            "verification_method": "Integration: RBAC enforcement on all endpoints; paginated responses correct"
        },
        {
            "id": "FR-86",
            "description": "Auth + User API: login/refresh/users/roles management",
            "implementation_functions": [
                "auth module"
            ],
            "verification_method": "Integration: login→JWT; refresh works; role management requires system:write"
        },
        {
            "id": "FR-87",
            "description": "M2M Token API: create/list/revoke; token format m2m_+32hex; stored as SHA-256",
            "implementation_functions": [
                "M2M token management"
            ],
            "verification_method": "Unit: format m2m_+64hex(SHA256); list hides token value"
        },
        {
            "id": "FR-88",
            "description": "GDPR API: data export (JSON/CSV) + data deletion (async, 30d SLA, PII cleared, audit logged)",
            "implementation_functions": [
                "GDPR compliance module"
            ],
            "verification_method": "Integration: export returns all personal data; deletion clears PII and logs gdpr_deletion"
        },
        {
            "id": "FR-89",
            "description": "TDE: AES-256, 90-day key rotation, ssl_mode=verify-full; pii_vault app-layer decrypt only",
            "implementation_functions": [
                "PostgreSQL TDE config"
            ],
            "verification_method": "Config: TDE enabled; key rotation scheduled; pii_vault direct read blocked for DBA"
        },
        {
            "id": "FR-90",
            "description": "Redis security: TLS tls-port 6380; AUTH from env var; ACL; default_user disabled",
            "implementation_functions": [
                "Redis security config"
            ],
            "verification_method": "Config: plaintext port blocked; env var used; default user disabled"
        },
        {
            "id": "FR-91",
            "description": "Data retention policy: messages 180d→archive; archive 2yr→delete; PII audit 90d→anonymize; emotion 90d→delete; security 1yr→archive→2yr delete",
            "implementation_functions": [
                "data retention scheduled jobs"
            ],
            "verification_method": "Integration: scheduled jobs execute at correct intervals; anonymization verified"
        },
        {
            "id": "FR-92",
            "description": "GDPR right to erasure: async deletion within 30d; profile=NULL; messages=[REDACTED]; pii_audit_log gdpr_deletion",
            "implementation_functions": [
                "execute_data_deletion"
            ],
            "verification_method": "Integration: post-deletion PII fields null; messages redacted; audit log entry exists"
        },
        {
            "id": "FR-93",
            "description": "Right of access + portability: GET /users/{id}/data returns JSON with all personal data; CSV export",
            "implementation_functions": [
                "data export endpoint"
            ],
            "verification_method": "Integration: export contains all user data; JSON and CSV formats valid"
        },
        {
            "id": "FR-94",
            "description": "pii_vault: encrypted BYTEA storage; KMS key_id; dpo-only decrypt; no plaintext storage",
            "implementation_functions": [
                "pii_vault table",
                "KMS integration"
            ],
            "verification_method": "Security test: plaintext not in DB; non-dpo decrypt fails; KMS key_id present"
        },
        {
            "id": "FR-95",
            "description": "Docker Compose: 7 services with healthchecks; pgvector/pgvector:pg16 image",
            "implementation_functions": [
                "docker-compose.yml"
            ],
            "verification_method": "docker compose up→all services healthy; health endpoint 200"
        },
        {
            "id": "FR-96",
            "description": "K8s: Deployment(3 replicas)+HPA(3-10)+PDB(minAvailable=2)+NetworkPolicy+Service(LoadBalancer); Secrets via SealedSecrets",
            "implementation_functions": [
                "K8s manifests"
            ],
            "verification_method": "K8s apply→resources created; HPA scales correctly; PDB prevents disruption"
        },
        {
            "id": "FR-97",
            "description": "Backup: pg_basebackup+WAL daily, 30d retention; Redis RDB hourly+AOF per-second, 7d retention",
            "implementation_functions": [
                "backup scripts"
            ],
            "verification_method": "DR drill: restore completes in <5 minutes"
        },
        {
            "id": "FR-98",
            "description": "Rollback procedures: knowledge soft-delete, model A/B gradual, Alembic downgrade, experiment abort",
            "implementation_functions": [
                "rollback procedures"
            ],
            "verification_method": "Test each rollback path: data preserved; service continues"
        },
        {
            "id": "FR-99",
            "description": "Circuit breaker degradation: 9 levels (6 main + 3 lateral) with trigger conditions and recovery thresholds",
            "implementation_functions": [
                "circuit breaker implementation"
            ],
            "verification_method": "Integration: inject failures→correct level triggered; recovery after success count"
        },
        {
            "id": "FR-100",
            "description": "Multimedia: image/file→escalate; sticker→ignore+prompt; location→extract coordinates; file size limit 10MB",
            "implementation_functions": [
                "media handling pipeline"
            ],
            "verification_method": "Unit: image→escalation; sticker→fixed reply; location→context with coordinates; file>10MB rejected"
        },
        {
            "id": "FR-101",
            "description": "Knowledge WebUI: CRUD + Markdown editor + keywords + CSV/JSON import/export + embedding status",
            "implementation_functions": [
                "WebUI frontend (React)"
            ],
            "verification_method": "Manual: CRUD works; import succeeds; status updates in real-time; response<1.5s"
        },
        {
            "id": "FR-102",
            "description": "RAG Debugger: search sandbox with cosine scores, Parent Chunk content, RRF top-3, threshold slider (session-only)",
            "implementation_functions": [
                "RAG Debugger UI"
            ],
            "verification_method": "Manual: debugger shows T1+T2 decision flow; slider adjusts results; not persisted to DB"
        },
        {
            "id": "FR-103",
            "description": "Operations Dashboard: FCR chart + p95 gauge + knowledge pie + cost chart, 24hr/7d/30d",
            "implementation_functions": [
                "Operations Dashboard UI"
            ],
            "verification_method": "Manual: all 4 panels render; KPI alerts trigger correctly; time range switching works"
        },
        {
            "id": "FR-104",
            "description": "Agent Portal: escalation inbox (Unassigned/My Chats/Resolved) + WS real-time + takeover panel",
            "implementation_functions": [
                "Agent Portal UI"
            ],
            "verification_method": "Manual: inbox WS updates; priority colors correct; takeover panel shows emotion+DST+context"
        },
        {
            "id": "FR-105",
            "description": "ODD SQL queries: 10+ queries for FCR/latency/knowledge/CSAT/SLA/emotion/security/cost/PII/RBAC/A-B analytics",
            "implementation_functions": [
                "ODD SQL scripts"
            ],
            "verification_method": "Integration: all SQL execute without error on staging DB"
        },
        {
            "id": "FR-106",
            "description": "k6 load test: 4 scenarios (smoke/load/stress/spike), 2000 TPS, 4 test case weights",
            "implementation_functions": [
                "k6 load test scripts"
            ],
            "verification_method": "Performance: load scenario p95<1000ms; error<1%; stress no crash; 2000 TPS sustained"
        },
        {
            "id": "FR-107",
            "description": "Test pyramid: unit 70% + integration 20% + E2E 10%; 6 E2E scenarios defined",
            "implementation_functions": [
                "pytest test suite",
                "k6"
            ],
            "verification_method": "pytest-cov: 70/20/10 coverage; all 6 E2E scenarios pass"
        },
        {
            "id": "FR-108",
            "description": "Golden dataset: 500 edge cases, 6 categories (asr-noise/typo/dialect/multi-intent/emotional/injection)",
            "implementation_functions": [
                "golden dataset",
                "edge_cases table"
            ],
            "verification_method": "Count: edge_cases rows≥500; status=approved≥500; regression test pass rate tracked"
        }
    ],
    "non_functional_requirements": [
        {
            "id": "NFR-01",
            "type": "performance",
            "description": "p95 end-to-end latency < 1.0s（全負載）",
            "test_method": "k6 load test (p(95)<1000)",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-02",
            "type": "performance",
            "description": "L1-L3 合計延遲 < 5ms p95",
            "test_method": "Unit benchmark",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-03",
            "type": "performance",
            "description": "L4 Semantic Classifier < 200ms p95（async）",
            "test_method": "L4 unit test with timing",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-04",
            "type": "performance",
            "description": "Embedding API < 300ms p95",
            "test_method": "Integration test with timing",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-05",
            "type": "performance",
            "description": "A2A timeout = 2.0s",
            "test_method": "Fault injection test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-06",
            "type": "performance",
            "description": "LLM fallback switch < 500ms",
            "test_method": "Fault injection test (primary LLM down)",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-07",
            "type": "performance",
            "description": "Agent Card TTL cache = 300s（不重複 discovery）",
            "test_method": "Unit test cache expiry",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-08",
            "type": "performance",
            "description": "Embedding job p95 < 30s",
            "test_method": "SAQ dashboard monitoring",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-09",
            "type": "throughput",
            "description": "2000 TPS sustained（k6 load scenario）",
            "test_method": "k6 stress test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-10",
            "type": "availability",
            "description": "99.9% / month",
            "test_method": "Prometheus uptime monitor",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-11",
            "type": "availability",
            "description": "早期告警閾值 < 99.95%（SLA 前觸發）",
            "test_method": "Prometheus alert: early-warning",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-12",
            "type": "availability",
            "description": "p95 > 0.8s → HighLatency 告警",
            "test_method": "Prometheus alert rule",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-13",
            "type": "availability",
            "description": "error rate > 0.5% → 告警（> 1% = SLA breach）",
            "test_method": "Prometheus alert rule",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-14",
            "type": "availability",
            "description": "災備復原時間 < 5 分鐘",
            "test_method": "DR drill",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-15",
            "type": "security",
            "description": "OWASP LLM01:2025 合規（PALADIN 五層覆蓋）",
            "test_method": "Red-team + OWASP checklist",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-16",
            "type": "security",
            "description": "安全阻擋率 ≥ 95%",
            "test_method": "Red-team test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-17",
            "type": "security",
            "description": "機密資料（secrets）不提交至版控",
            "test_method": "git-secrets / pre-commit hook",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-18",
            "type": "cost",
            "description": "月費用 < $500（含 GPU 推理、Embedding、備援）",
            "test_method": "Cost dashboard",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-19",
            "type": "cost",
            "description": "LLM API 基礎估算 ~$210/月（10 萬對話、Tier 2 覆蓋 40%）",
            "test_method": "Cost dashboard",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-20",
            "type": "compliance",
            "description": "台灣個資法合規",
            "test_method": "Legal review",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-21",
            "type": "compliance",
            "description": "GDPR Art.5(1)(e) 合規（資料最小化）",
            "test_method": "GDPR audit",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-22",
            "type": "compliance",
            "description": "SOC2 稽核軌跡",
            "test_method": "SOC2 audit trail",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-23",
            "type": "quality",
            "description": "FCR ≥ 90%（in_scope 對話）",
            "test_method": "ODD SQL",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-24",
            "type": "quality",
            "description": "CSAT 目標 4.8（2025Q4 基準 3.2，+50%）",
            "test_method": "LLM-as-a-Judge monthly",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-25",
            "type": "quality",
            "description": "Escalation SLA 遵守率 ≥ 95%",
            "test_method": "ODD SQL",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-26",
            "type": "quality",
            "description": "LLM-as-a-Judge Cohen's Kappa ≥ 0.7 vs 人工標注",
            "test_method": "500 筆黃金集校準",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-27",
            "type": "quality",
            "description": "Grounding check pass rate 100%（cosine ≥ 0.75）",
            "test_method": "L5 unit tests",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-28",
            "type": "quality",
            "description": "Recall@3 ≥ 92%（HNSW 1536維）",
            "test_method": "Golden set regression",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-29",
            "type": "quality",
            "description": "Agentic tool success rate ≥ 95%",
            "test_method": "Integration tests",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-30",
            "type": "scalability",
            "description": "Kubernetes HPA min=3, max=10, CPU target=70%",
            "test_method": "K8s load test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-31",
            "type": "observability",
            "description": "每請求完整 OpenTelemetry trace",
            "test_method": "Trace sampling verification",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-32",
            "type": "testability",
            "description": "Unit 70% + Integration 20% + E2E 10% coverage",
            "test_method": "pytest-cov",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-33",
            "type": "resilience",
            "description": "Rate Limiter fail-open on Redis unavailability",
            "test_method": "Redis failure injection",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-34",
            "type": "resilience",
            "description": "IP Whitelist fail-secure (403) on no match",
            "test_method": "Security test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-35",
            "type": "resilience",
            "description": "IP Whitelist max 100 CIDR blocks",
            "test_method": "Config validation test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-36",
            "type": "resilience",
            "description": "M2M token 90 天到期",
            "test_method": "Token expiry unit test",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-37",
            "type": "performance",
            "description": "Admin WebUI 響應時間 < 1.5s，100% 資料即時連動",
            "test_method": "Lighthouse audit + manual",
            "related_fr": "N/A"
        },
        {
            "id": "NFR-38",
            "type": "performance",
            "description": "ClamAV 文件掃描 p95 < 500ms",
            "test_method": "Integration test with timing",
            "related_fr": "N/A"
        }
    ]
}
```
<!-- FR:END -->
