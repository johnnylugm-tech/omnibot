# OmniBot Test Plan -- Phase 4

> Generated 2026-06-24 by Phase 4 orchestrator from 
> Source: SRS.md acceptance criteria (table format)
> Coverage scope: 108 functional requirements (FR-01 ... FR-108)
> Context file: `.sessi-work/phase4_ctx.json`

## 1. Scope and Tiers

Each FR has at least one automated test under `03-development/tests/`.
Tests are organised in three tiers:

| Tier | Directory | Purpose |
|------|-----------|---------|
| Unit | `tests/unit/` | Pure-function checks, contracts, mutation-kill tests |
| Integration | `tests/integration/` | Cross-module flows, FR-level end-to-end coverage |
| E2E | `tests/e2e/` | API contract, performance, security scenarios |

## 2. Coverage Matrix

| FR-ID | Title (excerpt) | Acceptance (excerpt) | Unit | Integration | E2E |
|-------|-----------------|----------------------|------|-------------|-----|
| FR-01 | Telegram Webhook Adapter：接收 POST /api/v1/webhook/telegram，驗證 | 合法請求回 200；簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}；ra | - | Y | - |
| FR-02 | LINE Webhook Adapter：接收 POST /api/v1/webhook/line，驗證 x-line- | 合法請求回 200；簽名驗證失敗回 401 {"error": "AUTH_INVALID_SIGNATURE"}；ra | - | Y | - |
| FR-03 | Messenger Webhook Adapter：GET 驗證（hub.mode, hub.verify_token, | GET 回傳 hub.challenge 字串；POST 合法回 200；簽名失敗回 401 {"error": "AU | - | Y | - |
| FR-04 | WhatsApp Webhook Adapter：GET 驗證（hub.challenge）+ POST HMAC-SH | GET 回傳 hub.challenge；POST 合法回 200；簽名失敗回 401 {"error": "AUTH_ | - | Y | - |
| FR-05 | Web Platform Adapter：POST /api/v1/web/guest-session 初始化匿名連線回 | guest-session 回 200 含 JWT；JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED；r | - | Y | - |
| FR-06 | A2A Platform Adapter：POST /api/v1/a2a/rpc 接收 JSON-RPC 2.0（me | 合法 M2M token 回 200 JSON-RPC 2.0 回應；token 驗證失敗回 401 | - | Y | - |
| FR-07 | UnifiedMessage 資料結構：immutable dataclass，欄位含 platform(Platfor | 所有平台訊息皆可建立合法 UnifiedMessage 實例；frozen=True 確保不可變 | Y | - | - |
| FR-08 | UnifiedResponse 資料結構：immutable dataclass，欄位含 content, source | rag\ | Y | - | - |
| FR-09 | 統一回應格式：ApiResponse[T]（success, data, error, error_code）+ Pag | 所有管理 API 回應符合 ApiResponse schema；PaginatedResponse 包含正確分頁欄位 | Y | - | - |
| FR-10 | PALADIN L1 — InputSanitizer：NFKC 正規化 + homoglyph 替換（Cyrillic | 西里爾/希臘同形字被正確替換；NFKC 正規化通過 unicode 標準測試；延遲 < 2ms | - | Y | - |
| FR-11 | PALADIN L2 — Pattern Detection：13 個 SUSPICIOUS_PATTERNS rege | 所有已知 pattern 測試案例命中；正常用戶訊息不誤判；延遲 < 3ms | - | Y | - |
| FR-12 | PALADIN L3 — Instruction Hierarchy：Sandwich Prompt 建構，系統指令標記 | Sandwich prompt 結構正確包含三個標記區塊；SYSTEM/UNTRUSTED 邊界清晰 | - | Y | - |
| FR-13 | PALADIN L4 — SemanticInjectionClassifier：LLM-based（gpt-4o-mi | indirect_injection\ | - | Y | - |
| FR-14 | PALADIN L5 — GroundingChecker：計算 LLM 輸出與 source_texts 之間 cos | cosine score < 0.75 → grounded=False；cosine score ≥ 0.75 → g | - | Y | - |
| FR-15 | PALADIN L4 平行化執行策略：low risk → 跳過 L4 直接 L3；medium risk → L4 與 | low risk 請求不呼叫 L4；medium risk L4 與 L3 並發執行；high/critical 直接安 | - | Y | - |
| FR-16 | L4 事後攔截：medium risk 若 L4 在 L3 完成後才判定 injection → 撤回 L3 結果，發送 | injection_retrospective_block 事件正確寫入 security_logs；撤回回應替換原回覆 | - | Y | - |
| FR-17 | 各平台 L4 事後撤回策略：Telegram deleteMessage（48hr 內）；LINE 不支援刪除 → 補發 | 各平台按策略執行撤回或補發；撤回失敗時補發道歉並記錄 retraction_failed；Web 端 WebSocket | - | Y | - |
| FR-18 | PIIMasking：偵測並遮蔽電話（台灣格式 \d{10,11}）、Email、台灣地址（市縣路街巷弄號樓正則）、信用 | 所有四類 PII 正確遮蔽；信用卡 Luhn 校驗失敗者不遮蔽；mask_count 正確回傳 | Y | - | - |
| FR-19 | PII 敏感關鍵字觸發轉接：偵測 密碼/銀行帳戶/信用卡號/提款卡 關鍵字 → should_escalate() 回傳 | 四個敏感關鍵字觸發 should_escalate()=True；其他關鍵字不誤判 | Y | - | - |
| FR-20 | PII 稽核日誌：每次遮蔽事件寫入 pii_audit_log（conversation_id, mask_count, | pii_audit_log 寫入成功；90 天到期後 PII 欄位自動清除 | Y | - | - |
| FR-21 | Redis 滑動視窗速率限制（Lua atomic ZSET）：Telegram/LINE/Messenger/What | 各平台超出限制回 429；未超限回 200；Lua script 原子性保證無競態 | - | Y | - |
| FR-22 | Rate Limiter Fail-open：Redis 不可用時（ConnectionError/TimeoutErr | Redis 斷線時請求通過；warning 日誌正確記錄；不拋例外 | - | Y | - |
| FR-23 | IP 白名單：CIDR 格式（最多 100 個），從 `IP_WHITELIST_CIDRS` 環境變數載入（逗號分隔） | 合法 IP 通過；非白名單 IP 回 403；空 body；白名單空或無 IP header 回 400 + warni | - | Y | - |
| FR-24 | 攔截鏈順序：TLS → IP Whitelist → Webhook Signature Validation → Pl | 各層按順序執行；IP 攔截在 signature 驗證前；Rate Limiting 在 Platform Adapte | - | Y | - |
| FR-25 | IP 白名單錯誤處理：無效 CIDR 格式 → 啟動時拋出 IPWhitelistError；無效 IP 格式（is_a | 非法 CIDR 啟動時即失敗；非法 IP 不拋例外回 False | - | Y | - |
| FR-26 | Knowledge Tier 1 — 規則匹配：PostgreSQL ILIKE + keywords 精確比對；con | confidence ≥ 0.80 命中直接回傳 source="rule"；未達閾值繼續 Tier 2 | - | Y | - |
| FR-27 | Knowledge Tier 2 — RAG + RRF：pgvector HNSW（1536維 text-embedd | RRF 排名正確融合；confidence ≥ 0.85 回傳 rag；Parent-Child 追索邏輯正確 | - | Y | - |
| FR-28 | Parent-Child Chunking：Parent = 500 tokens（100 token overlap） | Parent/Child 尺寸符合規格；向量搜尋命中 Child 後正確追索 Parent | - | Y | - |
| FR-29 | HNSW 向量索引：knowledge_chunks 表建 HNSW 索引（vector_cosine_ops，m=16 | HNSW 索引建立成功；Partial Index 只索引非 NULL 向量；Recall@3 ≥ 92% | - | Y | - |
| FR-30 | Knowledge Tier 3 — LLM 生成：gpt-4o 主要 → gemini-1.5-flash fallb | gpt-4o 失敗自動降級 gemini；grounding < 0.75 → escalate；source="wik | - | Y | - |
| FR-31 | Knowledge Tier 4 — 人工轉接：所有 Tier 1/2/3 無法處理時 escalate；reason  | Tier 1-3 均無結果時觸發 Tier 4；KnowledgeResult.id=-1 標識非知識庫來源 | - | Y | - |
| FR-32 | KnowledgeResult 資料結構：immutable frozen dataclass（id, content, | KnowledgeResult 建構成功；source 限定 rule\ | - | Y | - |
| FR-33 | HybridKnowledge 查詢協調器：按 Tier 1 → Tier 2 → Tier 3 → Tier 4 順序 | 查詢路徑按 Tier 順序；置信度門檻正確攔截；更換模型時 EMBEDDING_DIM 同步變更 | - | Y | - |
| FR-34 | 8 狀態 FSM：IDLE → INTENT_DETECTED → SLOT_FILLING → AWAITING_CO | 所有合法轉移成功；非法轉移拋 ValueError；轉移後 turn_count +1 | Y | - | - |
| FR-35 | Slot Filling：order_status 需要 order_id；return_request 需要 orde | order_status / return_request 缺 slot 時 missing_slots() 正確回傳； | Y | - | - |
| FR-36 | 自動轉接觸發條件：SLOT_FILLING 超過 3 輪未完成 → ESCALATED；意圖置信度 < INTENT_C | 超過 3 輪 slot filling 觸發轉接；confidence < 0.65 觸發轉接 | Y | - | - |
| FR-37 | AWAITING_CONFIRMATION 超時：超過 2 輪未確認 → ESCALATED；用戶確認 → PROCES | 2 輪未確認觸發 ESCALATED；確認/否認狀態轉移正確 | Y | - | - |
| FR-38 | 對話 Context Window 管理：sliding_window_with_summarization 策略；ma | token 計算正確（cl100k_base）；超出 budget 觸發摘要；保留最近 1/3 messages；gem | Y | - | - |
| FR-39 | ActionAdapter 抽象介面：list_tools() → List[ToolDefinition]；execu | 所有 Adapter 子類實作 list_tools + execute；ToolExecutionResult 包含  | Y | - | - |
| FR-40 | MCPAdapter：透過 stdio 或 SSE 連線至外部 MCP Server；list_tools 回傳 MCP | MCPAdapter 連線至 MCP Server 成功；工具呼叫回傳正確結果 | Y | - | - |
| FR-41 | A2AAdapter：GET /.well-known/agent.json 發現 Agent Card（300s TT | Agent Card Discovery 成功；JSON-RPC 2.0 請求格式正確；timeout 2.0s 回傳  | Y | - | - |
| FR-42 | CLIAdapter：在 sandboxed 容器內執行本地 Python/Bash 腳本；回傳 ToolExecuti | CLIAdapter 執行成功回 success=True；執行失敗回 success=False + error_me | Y | - | - |
| FR-43 | ToolExecutor：register(tool, handler) 綁定工具定義與 handler；execute | 預設工具可正常執行；工具不存在回 success=False；update_shipping_address 在 shi | Y | - | - |
| FR-44 | OmniBot Agent Card：GET /.well-known/agent.json 回傳 Agent Card | Agent Card 端點回 200 合法 JSON；methods 清單正確 | Y | - | - |
| FR-45 | ToolDefinition 統一定義：AEE（Action Execution Engine）與 DST 模組共用同一 | AEE 和 DST 使用同一 ToolDefinition 類別；無重複定義 | Y | - | - |
| FR-46 | EmotionAnalyzer：分類情緒為 positive/neutral/negative，強度 intensity | 情緒分類結果限定三個合法值；intensity 範圍 [0.0, 1.0] | Y | - | - |
| FR-47 | 時序衰減：EmotionTracker 以 24hr half-life 指數衰減（decay = exp(-0.693 | 衰減計算公式正確；half_life=24hr；24hr 後權重降至 50% | Y | - | - |
| FR-48 | 連續負面觸發轉接：consecutive_negative_count() ≥ 3 → should_escalate( | 連續 3 次負面觸發；中間有非負面打斷重計；should_escalate() 正確 | Y | - | - |
| FR-49 | AGENT 平台 Bypass：platform == AGENT 時跳過情緒分析模組 | AGENT 平台請求不執行情緒分析；不觸發情緒轉接 | Y | - | - |
| FR-50 | Template System：ResponseTemplate（name, platform, emotion_ton | 三個預設模板存在且格式正確；variable interpolation 正確 | Y | - | - |
| FR-51 | Emotion Tone Modulation：negative + intensity > 0.7 → 前綴「非常抱歉 | 情緒調整規則按閾值正確觸發；重複道歉抑制生效 | Y | - | - |
| FR-52 | A/B Variant Injection：SHA-256 確定性分配（非 Python hash()）；variant | SHA-256 分配跨進程一致；variant 注入正確；control 無注入 | Y | - | - |
| FR-53 | Platform Format Adapter：各平台訊息限制（Telegram 4096 字元/HTML Markdo | 各平台輸出格式符合限制；長訊息正確截斷或分段 | Y | - | - |
| FR-54 | EscalationManager：create(EscalationRequest) → 插入 escalation_ | 建立轉接記錄成功；assign 更新 assigned_agent + picked_at；resolve 更新 res | - | Y | - |
| FR-55 | SLA 定義：normal(priority=0) 30 分鐘；high(priority=1) 15 分鐘；urgen | sla_deadline = queued_at + SLA 分鐘；breach = resolved_at IS NU | - | Y | - |
| FR-56 | WebSocket 轉接推送：建立轉接後透過 /ws/agent 推送 escalation.new 事件（payloa | 轉接建立後 WebSocket 即時推送；payload 欄位完整 | - | Y | - |
| FR-57 | /ws/agent WebSocket：客服工作台；Server→Client 事件：escalation.new, e | 事件格式正確；JWT 驗證失敗拒絕連線；各事件 payload 欄位完整 | - | Y | - |
| FR-58 | /ws/user WebSocket：Web 前端用戶；Server→Client：message.reply（mess | message.reply 即時推送；JWT 驗證；避免輪詢 | - | Y | - |
| FR-59 | WebSocket 心跳：Server 每 30s 發送 ping；Client 10s 內未回 pong → Serv | 30s ping；10s timeout disconnect；channel 訂閱回 subscribed | - | Y | - |
| FR-60 | 7 角色定義：anonymous, customer, agent, editor, admin, auditor, d | 7 角色 ROLE_PERMISSIONS 完整；dpo 有 pii:decrypt；auditor 無 pii:dec | Y | - | - |
| FR-61 | 權限矩陣（完整）：anonymous=knowledge:read；customer=knowledge:read +  | 各角色權限按規格；auditor 嘗試 pii:decrypt 回 403；越界操作被拒絕 | Y | - | - |
| FR-62 | RBACEnforcer 裝飾器 Middleware：@rbac.require(resource, action)  | 無權限請求回 403；有權限請求通過；裝飾器正確注入 | Y | - | - |
| FR-63 | ABTestManager：get_variant(user_id, experiment_id) 使用 SHA-256 | 同 user_id + experiment_id 跨進程回傳相同 variant；SHA-256 hash 計算正確 | Y | - | - |
| FR-64 | auto_promote：最小樣本量 100；metric 差異 ≥ 0.05（threshold）→ 最佳 varia | 樣本 < 100 不判定勝負；差異 ≥ 0.05 且樣本足夠時自動結束實驗 | Y | - | - |
| FR-65 | Ensemble Judge：primary=gpt-4o-mini (temp=0) + secondary=clau | 兩個 judge 並行呼叫；temperature=0 確保確定性；各 judge 回傳 JudgeResult | - | Y | - |
| FR-66 | Politeness 聚合：max(primary_score, secondary_score)（寬鬆評分，情感支持寧 | politeness = max(two scores)；中文語氣標記：正面（請問/協助/啦）、負面（吼/咧/嘛）正確識 | - | Y | - |
| FR-67 | Accuracy 聚合：min(primary_score, secondary_score)（保守評分，幻覺不可接受） | accuracy = min(two scores)；任一 judge 低分即拉低整體 | - | Y | - |
| FR-68 | CSAT 公式：CSAT = 0.4×速度 + 0.2×擬人化 + 0.2×禮貌度 + 0.2×準確度；aggregat | CSAT 公式計算正確；score 正規化至 0-5 範圍 | - | Y | - |
| FR-69 | 月度校準：golden set 500 筆；Cohen's Kappa ≥ 0.7（judge vs 人工標注）；觸發條 | Kappa ≥ 0.7；偏差 > 15% 觸發緊急 recalibration | - | Y | - |
| FR-70 | StructuredLogger：JSON 格式，欄位含 timestamp(ISO 8601 Z), level, s | JSON 日誌格式正確；各 level 正確路由至 Python logging | - | Y | - |
| FR-71 | Prometheus Metrics（9 種，全部顯式列出）：1. response_duration_seconds( | 所有 9 個 metric 名稱正確定義；各 metric 類型（histogram/counter/gauge）正確； | - | Y | - |
| FR-72 | OpenTelemetry Tracing：每請求完整 span tree（handle_message → emoti | Span 樹正確；attributes 完整；trace_id 透過 HTTP header 跨服務傳遞 | - | Y | - |
| FR-73 | 告警規則（4 條）：HighLatency（p95 > 0.8s for 5m, warning; p95 > 1.0s | 4 條告警規則正確定義；閾值符合規格；SLABreach for=0m 立即觸發 | - | Y | - |
| FR-74 | Grafana Dashboard：連結 Prometheus + ODD SQL 指標；提供 FCR 折線圖、p95  | Dashboard 面板存在；指標即時連動；<99.95% 可用性顯示早期警報 | - | Y | - |
| FR-75 | SAQ Worker：queues=embedding(high, concurrency=3, timeout=30s | Worker 正確訂閱各 queue；SIGTERM 後等待 30s 完成當前任務 | - | Y | - |
| FR-76 | EmbeddingJob：欄位含 chunk_id, knowledge_id, content, model, ret | max_retries=3 後停止重試；指數退避含 jitter；p95 < 30s | - | Y | - |
| FR-77 | 同步首 Chunk Embedding：單筆知識新增時，第一個 chunk 同步生成 embedding（asyncio | 單筆新增後 Tier 2 在 < 2.5s 內可搜尋到首 chunk；超時不阻斷主流程 | - | Y | - |
| FR-78 | 批次匯入模式（> 10 筆）：is_batch=True → 所有 chunks 全部非同步排入 SAQ（不等待同步首  | 批次模式不等待首 chunk 同步；每筆插入 < 50ms | - | Y | - |
| FR-79 | Embedding 同步狀態 UI：知識庫列表顯示 🟡同步中（x/n chunks 完成）/🟢已同步/🔴失敗；embed | UI 狀態標示正確；embedding_synced_at 在所有 chunks 完成後更新 | - | Y | - |
| FR-80 | Redis Streams 異步處理：consumer group "omnibot"；XREADGROUP block | Consumer group 建立成功；BUSYGROUP 錯誤靜默忽略；pending 訊息被 XCLAIM 後繼續處 | - | Y | - |
| FR-81 | 指數退避重試：max_retries=3, base_delay=1.0s, max_delay=30.0s, jitt | 第 3 次後停止重試；delay 上限 30s；jitter 避免 thundering herd | - | Y | - |
| FR-82 | 完整資料庫 Schema（20 張表）：users, conversations, messages, knowledg | 20 張表可成功建立；所有 FK 約束正確；HNSW 索引 + GIN tsvector 索引均建立成功；level_e | - | Y | - |
| FR-83 | Alembic Schema 遷移：每個 migration 含 upgrade() + downgrade()；sta | migration 雙向測試通過；downgrade() 正確回退 | - | Y | - |
| FR-84 | Webhook API 端點（6 個）：POST /api/v1/webhook/telegram, /line, /m | 各端點存在且回傳正確 HTTP status；錯誤碼規範一致 | - | Y | - |
| FR-85 | 管理 API（8 個端點）：GET/POST /api/v1/knowledge；PUT/DELETE /api/v1/ | 各端點 RBAC 保護正確；分頁回應格式符合 PaginatedResponse；health 回傳 status/po | - | Y | - |
| FR-86 | Auth & User API：POST /api/v1/auth/login（回傳 JWT access + refr | login 失敗回 401；role 管理需 system:write 權限；refresh token 正常換發 | - | Y | - |
| FR-87 | M2M Token API：POST /api/v1/m2m/tokens（admin 限定，client_name,  | Token 建立僅回傳一次；儲存 hash 不存明文；90 天到期；revoke 成功後 token 立即失效 | - | Y | - |
| FR-88 | GDPR API：GET /api/v1/users/{user_id}/data（匯出 JSON/CSV）；DELET | data export 回傳合法 JSON/CSV；deletion 記錄 pii_audit_log 並異步執行；30 | - | Y | - |
| FR-89 | TDE 加密：PostgreSQL AES-256 加密，金鑰輪換週期 90 天，ssl_mode=verify-ful | TDE 啟用；90 天輪換計畫存在；pii_vault 無法裸讀 | - | - | Y |
| FR-90 | Redis 安全：TLS 啟用（tls-port 6380）；requirepass 環境變數注入（不 hard-cod | Redis 拒絕明文連線；密碼從環境變數讀取；default user 已停用 | - | - | Y |
| FR-91 | 資料保留政策：conversations(messages) 180 天 → 封存 cold storage(Parqu | 排程任務按保留期限正確執行；匿名化保留統計不保留 PII；封存格式為 Parquet/S3 | - | - | Y |
| FR-92 | 刪除權（Right to Erasure）：DELETE /api/v1/users/{user_id}/data 觸發 | 刪除後用戶 PII 欄位清除；messages 內容標記 REDACTED；稽核日誌存在；30 天 SLA | - | - | Y |
| FR-93 | 查閱權（Right of Access）+ 可攜權：GET /api/v1/users/{user_id}/data 回 | 回傳完整個人資料；格式符合 JSON；CSV 可下載 | - | - | Y |
| FR-94 | pii_vault：original_text_encrypted(BYTEA), masked_text_encryp | 明文不落地；KMS key_id 正確關聯；dpo 可解密；其他角色解密失敗 | - | - | Y |
| FR-95 | Docker Compose 開發環境：services 含 omnibot-api, postgres(pgvecto | docker compose up 後所有 services healthy；health 端點回 200 | - | - | Y |
| FR-96 | Kubernetes 部署：Deployment（replicas=3, RollingUpdate maxUnavai | K8s 資源建立成功；HPA 在負載時自動擴縮；PDB 確保滾動更新不斷服務；Secrets 不明文 | - | - | Y |
| FR-97 | 備份策略：PostgreSQL pg_basebackup + WAL archiving（每日全備 + 持續 WAL， | 備份排程存在且可執行；災備復原時間 < 5 分鐘 | - | - | Y |
| FR-98 | Rollback 策略：knowledge_update（version + is_active 軟刪除）；model_ | 各 rollback 路徑可執行；schema rollback 不丟失資料 | - | - | Y |
| FR-99 | 階梯式降級策略（**9 級（6 主級 + 3 橫向）**）：level_0=全功能；level_1=輕度延遲啟用快取（L | 各觸發條件正確觸發降級；恢復條件（連續成功次數）後自動回升；降級期間不影響已上線功能的基礎可用性 | - | - | Y |
| FR-100 | 多媒體處理路徑：Image → auto_escalate（不支援圖片理解）；Sticker → ignore + 固定 | Image/File 自動觸發人工轉接；Sticker 回覆固定文字；Location 座標正確提取；File 超過 1 | - | - | Y |
| FR-101 | Knowledge 管理 WebUI：條目 CRUD 列表；Markdown 知識編輯器；Keywords 標籤管理；批 | CRUD 操作正確；CSV/JSON 匯入成功；同步狀態即時更新 | - | - | Y |
| FR-102 | RAG Debugger：管理員輸入測試提問 → 展示 ILIKE 匹配結果+置信度、Child Chunk 餘弦相似度 | Debugger 正確展示 Tier 1+2 決策流程；滑桿調整即時反映搜尋結果；沙盒調整不持久化 | - | - | Y |
| FR-103 | Operations Dashboard：FCR 折線圖（< 90% 觸發黃色警報）；p95 延遲儀表（< 1.0s 綠 | 各圖表正確顯示；KPI 告警觸發正確；時序切換正常 | - | - | Y |
| FR-104 | Agent Portal：轉接收件匣（Unassigned/My Chats/Resolved）+ WebSocket  | 佇列 WebSocket 即時更新；優先級色彩正確；接管面板數據完整 | - | - | Y |
| FR-105 | ODD SQL 查詢集（10 個）：FCR 首問解決率（scope_type='in_scope' + 30天）；p95 | 各 SQL 可正確執行；FCR 計算僅含 in_scope + 非 NULL；成本計算按 Tier 定價；judge s | - | - | Y |
| FR-106 | k6 負載測試（4 場景）：smoke（10 VUs, 1m 基線）；load（200 VUs, 10m，p95<100 | load 場景 p95 < 1000ms；error rate < 1%；stress 場景不崩潰；spike 場景恢復 | - | - | Y |
| FR-107 | 測試金字塔：Unit 70%（InputSanitizer, PromptInjectionDefense, PIIMa | unit/integration/e2e 覆蓋率達 70/20/10；6個 E2E 場景通過 | - | - | Y |
| FR-108 | 黃金數據集：500 筆邊界案例（6 類：語音亂碼/拼寫錯誤/方言簡稱/多意圖/情感爆發/Prompt Injection | 500 筆數量達標；6 類覆蓋；regression 測試可自動執行 | - | - | Y |

Legend: Y = test_frNN.py present in tier; - = not in tier.

## 3. Tier Distribution

- Unit tier: 31 FRs
- Integration tier: 57 FRs
- E2E tier: 20 FRs
- Total covered (union): 108/108
- Uncovered: 0/108

## 4. Test Categories (per FR)

For each FR the test set exercises:
- **Positive**: valid input -> expected success path / response shape
- **Negative**: invalid input (bad signature, malformed payload, missing field) -> expected 4xx/5xx with documented error code
- **Boundary**: limit values (rate-limit threshold, max payload, empty body, timeouts)
- **Edge**: race conditions, retries, idempotency, concurrent access

## 5. Specialised Test Files

| File | Purpose |
|------|---------|
| `tests/test_constraints.py` | Cross-FR architectural constraints (no circular deps, API layer purity) |
| `tests/test_coverage_supplementary.py` | Fill remaining line/branch coverage gaps (batch 1) |
| `tests/test_coverage_supplementary2.py` | Fill remaining line/branch coverage gaps (batch 2) |
| `tests/unit/test_aee_adapter_mutation_kills.py` | AEE mutation killing (unit tier) |
| `tests/integration/test_paladin_mutation_kills.py` | PALADIN mutation-killing tests |
| `tests/integration/test_aee_adapter_mutation_kills.py` | AEE mutation-killing tests |
| `tests/integration/test_jobs_mutation_kills.py` | Jobs mutation-killing tests |
| `tests/integration/test_rate_limit_mutation_kills.py` | Rate-limit mutation-killing tests |
| `tests/integration/test_redis_streams_mutation_kills.py` | Redis Streams mutation-killing tests |
| `tests/integration/test_pipeline_h04_source_confidence.py` | High-risk pattern H-04: source confidence |
| `tests/integration/test_pipeline_h08_dst_before_knowledge.py` | High-risk pattern H-08: DST before knowledge |
| `tests/e2e/` | End-to-end FR scenarios (FR-89 ... FR-108) |
| `tests/strategy.py`, `tests/pyramid.py`, `tests/golden_dataset.py`, `tests/load/` | Test infrastructure |

## 6. NFR Coverage (informational)

NFR dimensions are covered indirectly by per-FR tests (e.g. NFR-01 performance via latency assertions in e2e tests).
Direct NFR-09 (load) is exercised by `tests/load/`.

## 7. NFR Coverage Matrix

Each NFR from `02-architecture/SAD.md` §NFR Traceability is mapped to a quality-gate dimension
(`harness/constitution/CONSTITUTION.md` §2.2) and the test artefact that measures it.

| NFR | Dimension | Target | Module | Test Artefact |
|-----|-----------|--------|--------|---------------|
| NFR-01 | performance | API p95 latency | (core pipeline) | `tests/e2e/test_perf.py`, `tests/integration/test_*.py` benchmark markers |
| NFR-02 | performance | Query p95 latency | (pipeline) | `tests/e2e/test_perf.py`, `tests/integration/test_pipeline_*.py` |
| NFR-03 | performance | Knowledge recall p95 | `app.core.knowledge` | `tests/integration/test_knowledge_*.py` |
| NFR-04 | performance | Embedding generation p95 | `app.core.knowledge` | `tests/integration/test_knowledge_*.py` |
| NFR-05 | performance | AEE adapter p95 | `app.services.aee` | `tests/integration/test_aee_*.py`, `tests/unit/test_aee_adapter_mutation_kills.py` |
| NFR-06 | performance | HNSW index search p95 | `app.core.knowledge` | `tests/integration/test_knowledge_*.py` |
| NFR-07 | performance | A2A envelope p95 | `app.api.a2a` | `tests/integration/test_a2a_*.py` |
| NFR-08 | performance | LLM judge p95 | `app.services.llm_judge` | `tests/integration/test_llm_judge_*.py` |
| NFR-09 | performance | Load profile (10x burst) | (whole system) | `tests/load/k6_*.js`, `tests/load/` |
| NFR-10 | error_handling | 5xx rate < 0.1% | (all API) | `tests/integration/test_error_*.py` |
| NFR-11 | error_handling | Circuit breaker opens at 50% | `app.infra.circuit_breaker` | `tests/integration/test_circuit_breaker_*.py` |
| NFR-12 | error_handling | Retry-After honour | `app.infra.rate_limit` | `tests/integration/test_rate_limit_*.py` |
| NFR-13 | error_handling | Timeout < 30s all async | (all async) | `tests/integration/test_*_timeout.py` |
| NFR-14 | error_handling | DLQ on consumer failure | `app.infra.jobs` | `tests/integration/test_jobs_*.py`, `tests/integration/test_jobs_mutation_kills.py` |
| NFR-15 | security | All inputs sanitised | `app.core.pii` | `tests/integration/test_pii_*.py` |
| NFR-16 | security | TLS 1.2+ enforced | `app.infra.observability` | `tests/integration/test_tls_*.py` |
| NFR-17 | security | RBAC per role enforced | `app.api.auth` | `tests/integration/test_auth_*.py` |
| NFR-18 | reliability | FERNET key rotation | `app.admin.gdpr` | `tests/integration/test_fr93.py` |
| NFR-19 | reliability | PII encrypted at rest | `app.admin.gdpr` | `tests/integration/test_fr93.py` |
| NFR-20 | reliability | Right-to-erasure within 30d | `app.admin.gdpr` | `tests/integration/test_fr93.py` |
| NFR-21 | deployability | GDPR Art.5(1)(e) minimisation | `app.admin.gdpr` | `tests/integration/test_fr93.py` |
| NFR-22 | deployability | SOC2 audit trail | `app.infra.observability` | `tests/integration/test_observability_*.py` |
| NFR-23 | testability | FCR ≥90% | `app.admin.odd_sql` | `tests/integration/test_odd_sql_*.py` |
| NFR-24 | testability | CSAT ≥4.8 | `app.services.llm_judge` | `tests/integration/test_llm_judge_*.py` |
| NFR-25 | testability | Escalation SLA ≥95% | `app.services.escalation` | `tests/integration/test_escalation_*.py` |
| NFR-26 | testability | Cohen's Kappa ≥0.7 | `app.services.llm_judge` | `tests/integration/test_llm_judge_*.py` |
| NFR-27 | testability | Grounding ≥100% (cos≥0.75) | `app.core.paladin` | `tests/integration/test_paladin_*.py`, `tests/integration/test_paladin_mutation_kills.py` |
| NFR-28 | testability | Recall@3 ≥92% HNSW 1536d | `app.core.knowledge` | `tests/integration/test_knowledge_*.py` |
| NFR-29 | testability | Agentic tool success ≥95% | `app.services.aee` | `tests/integration/test_aee_*.py`, `tests/unit/test_aee_adapter_mutation_kills.py` |
| NFR-30 | scalability | HPA min=3 max=10 CPU=70% | `app.infra.deployment` | `k8s/hpa.yaml`, validated in deployment |
| NFR-31 | maintainability | 100% OTel trace coverage | `app.infra.observability` | `tests/integration/test_observability_*.py` |
| NFR-32 | testability | unit≥70% integration≥20% e2e≥10% | `tests.strategy` | `tests/strategy.py`, `tests/pyramid.py` |
| NFR-33 | reliability | rate_limit fail-open on Redis unavailable | `app.infra.rate_limit` | `tests/integration/test_rate_limit_*.py` |
| NFR-34 | reliability | IP whitelist fail-secure 403 | `app.infra.rate_limit` | `tests/integration/test_ip_whitelist_*.py` |
| NFR-35 | reliability | Max 100 CIDR blocks | `app.infra.rate_limit` | `tests/integration/test_ip_whitelist_*.py` |
| NFR-36 | security | M2M 90-day expiry; revoke instant | `app.api.auth` | `tests/integration/test_auth_*.py` |
| NFR-37 | performance | WebUI p95 < 1500ms | `app.admin.webui` | `tests/e2e/test_perf.py` |
| NFR-38 | performance | ClamAV scan p95 < 500ms | `app.services.media` | `tests/integration/test_media_*.py` |

> Note: `mutation_testing` is **disabled** via the harness feature-flag mechanism (`harness/core/harness_config.py`, default `mutation_testing=false` when `.methodology/harness_config.json` is absent — currently the case). Existing mutation-killing tests under `tests/integration/test_*_mutation_kills.py` remain on disk as defence-in-depth but are not a Gate 3 scoring input.

## 8. Acceptance

- [x] All 108 FRs have at least one test_frNN.py file
- [x] Test tier distribution: unit, integration, e2e
- [x] Mutation-kill tests for high-risk modules (paladin, aee, jobs, rate_limit, redis_streams)
- [x] Pipeline invariant tests (H-04, H-08)
- [x] NFR-01..NFR-38 mapped to quality-gate dimensions and test artefacts (§7)

## 9. Representative Test Cases

| TC-ID | Description | Module | Test File | Status |
|-------|------------|--------|-----------|--------|
| TC-01 | JWT login returns access + refresh tokens on valid credentials | `app.api.auth` | `tests/unit/test_auth_jwt_and_routes.py` | ✅ PASS |
| TC-02 | PALADIN injection classifier blocks SQL injection payloads | `app.core.paladin` | `tests/test_fr10.py` | ✅ PASS |
| TC-03 | PII masking redacts credit card numbers (with dash separators) | `app.core.pii` | `tests/test_batch_2_bugs.py` | ✅ PASS |
| TC-04 | A2A adapter DNS pinning lock prevents concurrent monkey-patch pollution | `app.services.aee.a2a_adapter` | `tests/test_a2a_adapter_bugs.py` | ✅ PASS |
| TC-05 | Rate limiter fails open when Redis is unavailable (NFR-33) | `app.infra.rate_limit` | `tests/integration/test_fr22.py` | ✅ PASS |
| TC-06 | HPA scaling constants match NFR-30 spec (min=3, max=10, CPU=70%) | `app.infra.deployment` | `tests/unit/test_nfr30_hpa_scaling.py` | ✅ PASS |

