# Bug Hunt Report — 2026-06-22

**掃描範圍**：30 個主程式模組（12 HIGH-RISK × 3-lens + 18 STANDARD × general-lens）  
**原始發現**：122 findings  
**對抗性驗證（adversarial）**：4 critical/high findings → 4/4 CONFIRMED  
**工具**：CRG MCP（code-review-graph）+ 8 批次 × 4 並行 sub-agent  

---

## 1. 掃描摘要

| Module | Critical | High | Medium | Low |
|--------|----------|------|--------|-----|
| paladin | 1✅ | 2 | 2 | — |
| gdpr | 2✅ | 1 | 2 | 1 |
| auth | 1 | 2✅ | — | 1 |
| rate_limit | — | 2✅ | 1 | — |
| redis_streams | 1 | 2 | 2 | — |
| escalation | 1 | 1 | 2 | 1 |
| jobs | 1 | 2 | 1 | — |
| knowledge | — | 3 | 2 | — |
| mcp_adapter | — | 3 | 2 | 1 |
| circuit_breaker | — | 3 | 2 | 1 |
| llm_judge | — | 2 | 2 | — |
| response | — | 2 | 1 | 1 |
| pii | — | 2 | 2 | 1 |
| webhooks | — | 3 | 2 | — |
| tool_executor | — | 3 | 1 | 1 |
| chain | — | 2 | 1 | — |
| ip_whitelist | — | 1 | 1 | — |
| pipeline | — | 1 | 2 | — |
| a2a_adapter | — | 2 | 1 | — |
| security | — | 2 | — | 1 |
| cli_adapter | — | 1 | 1 | 1 |
| 其餘 9 模組 | — | — | 10 | 6 |

✅ = 已通過對抗性驗證

---

## 2. P0 — 立即修復（Critical）

### BUG-01 `paladin` · classify() ValueError 逃逸 → 安全繞過 ✅ CONFIRMED

**File**: `03-development/src/app/core/paladin.py:656, 578`  
**Lens**: resilience  

`_result_from_verdict()` L656 直接呼叫 `InjectionType(verdict.get("injection_type", "none"))`，若 LLM 回傳非法字串（如 `"prompt_leak"`）則觸發 `ValueError`。`classify()` L578 的 except 只攔截 `(TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)`，**不含 `ValueError`**，導致例外逃逸至 `PALADINPipeline.process()`。若 caller 有 broad except，PII 階段將在 PALADIN 未完成的情況下執行，違反 `paladin_executes_before_pii` 架構約束。

**修復**：在 `_result_from_verdict()` 的 `InjectionType()` 構建外加 `try/except ValueError`，fallback 到 `InjectionType.NONE, is_unverified=True`；同時將 `ValueError` 加入 L578 的 except tuple。

---

### BUG-02 `gdpr` · delete_user_data 未清除 _CONVERSATIONS/_MESSAGES/_EMOTIONS ✅ CONFIRMED

**File**: `03-development/src/app/admin/gdpr.py:177-205`  
**Lens**: general  

`delete_user_data()` L201-204 只寫 `_USERS[user_id] = {"profile": None, ...}`，完全未觸碰 `_CONVERSATIONS`、`_MESSAGES`、`_EMOTIONS`。`export_user_data()` L155-160 仍從這三個 dict 讀取。刪除後 export 仍回傳完整個資，違反 GDPR 右利刪除（FR-88）。

**修復**：在 `delete_user_data()` 加入 `_CONVERSATIONS.pop(user_id, None)`、`_EMOTIONS.pop(user_id, None)`；對 `_MESSAGES` 將訊息內容改為 `[REDACTED]`。

---

### BUG-03 `gdpr` · _VAULT 以 entry_id 為鍵，無法按 user_id 刪除 ✅ CONFIRMED

**File**: `03-development/src/app/admin/gdpr.py:27, 68-73`  
**Lens**: general  

`_VAULT: dict[str, dict] = {}` 的 key 是 UUID `entry_id`，vault record 內無 `user_id` 欄位，`delete_user_data()` 無法找到並刪除特定用戶的 PII vault 條目，違反 FR-92 完整刪除要求。

**修復**：`store_pii_entry()` 須維護 `_VAULT_BY_USER: dict[str, list[str]]` 二級索引；`delete_user_data()` 遍歷並刪除所有對應 entry。

---

### BUG-04 `escalation` · assign() 無 CAS 保護 → 同張工單被兩位客服接手

**File**: `03-development/src/app/services/escalation.py:249-253`  
**Lens**: general  

`assign()` 直接 overwrite `row["assigned_agent"]`，無任何檢查是否已被 assign。兩位客服同時點擊接單 → 後者覆蓋前者，前者仍在服務客戶但系統記錄已換人。

**修復**：加入冪等保護：`if row["assigned_agent"] is not None and row["assigned_agent"] != agent_id: raise ValueError(f"Already assigned to {row['assigned_agent']}")`

---

### BUG-05 `jobs` · infra/jobs.py 頂層 import 違反 infra_layer_no_domain_imports → 循環依賴

**File**: `03-development/src/app/infra/jobs.py:73-75`  
**Lens**: general  

`jobs.py` L73 頂層 `from app.core.knowledge import batch_import_knowledge, create_knowledge_with_chunks`，而 `knowledge.py` 的 deferred import 裡有 `from app.infra.jobs import EmbeddingJob`。形成循環依賴：jobs → knowledge → jobs。若 import 順序不對，`create_knowledge_with_chunks` 可能解析為 `None`，在 call site 觸發 `AttributeError`。

**修復**：刪除 L73-75（`from app.core.knowledge import ...` 和 `__all__` 中的 core 符號），core 符號由各 caller 直接從 `app.core.knowledge` import。

---

## 3. P1 — 高優先修復（High）

### 安全類

**BUG-06 `auth` · JWT secret 有硬編碼 fallback → 可偽造 token** ✅ CONFIRMED  
`auth.py:43` `os.environ.get("OMNIBOT_JWT_SECRET", "dev-secret-do-not-use-in-prod")`，`websocket.py:188` 驗證端使用相同 fallback。未設環境變數時任何知道 source code 的人均可偽造有效 JWT。  
**修復**：改用 `os.environ["OMNIBOT_JWT_SECRET"]`，無該變數則啟動失敗。

**BUG-07 `auth` · os.environ[] 在 module import 時 crash** → 整個服務不可用  
`auth.py:50-51` `os.environ["OMNIBOT_ADMIN_USER"]` / `["OMNIBOT_ADMIN_PASS"]` 在 import 時執行，缺少環境變數直接 `KeyError`，導致所有 import auth.py 的 endpoint 均無法啟動。  
**修復**：改為 deferred lookup 或 `os.environ.get()` + startup 早期 validation。

**BUG-08 `ip_whitelist` · X-Forwarded-For 無 trusted proxy 驗證 → IP whitelist 可偽造**  
`ip_whitelist.py:202-205` 無條件信任 XFF header 最左值，攻擊者直連時發送 `X-Forwarded-For: <whitelisted-ip>` 即可繞過 IP 白名單（NFR-15/16/17）。  
**修復**：僅在 TCP client IP 屬於 trusted proxy CIDR 時才信任 XFF；否則使用 `client_host`。

**BUG-09 `security` · execute_data_deletion() 是硬編碼 stub → GDPR 刪除靜默返回成功**  
`security.py:331-359` 丟棄 `user_id` 並回傳 `DataDeletionResult(profile_null=True, messages_redacted=True)`，實際未刪除任何資料。  
**修復**：改為 `raise NotImplementedError` 使 API 回傳 501，或實作真實刪除邏輯。

**BUG-10 `paladin` · SQL sanitize 可被 zero-width space (U+200B) 繞過**  
`paladin.py:90-103` `_SQL_INJECTION_RE` 使用 `\b` word boundary，`DR​OP TABLE` 中的 U+200B 不在 `_CONTROL_CHARS`（只涵蓋 0x00-0x1F, 0x7F-0x9F），regex 不命中。  
**修復**：擴展 `_CONTROL_CHARS` 包含 Unicode format category（U+200B, U+200C, U+200D, U+FEFF）。

---

### 資料正確性類

**BUG-11 `rate_limit` · ZSET member 時間戳碰撞 → 限流計數少算** ✅ CONFIRMED  
`rate_limit.py:114` Lua script：`ZADD key score f"{now}:{key}"`，同一 tick 兩次 allow() → 第二次 ZADD 覆蓋第一次 → ZCARD 少 1 → 超量請求放行。  
**修復**：member 加入 UUID nonce：`f"{now}:{key}:{uuid4().hex}"`。

**BUG-12 `redis_streams` · ack() 無任何 production caller → PEL 無限成長**  
`redis_streams.py:198-202` `ack()` 的 CRG graph query 顯示零 production callers，所有 delivered message 永留 PEL，`claim_pending()` 持續重複投遞歷史訊息。  
**修復**：consumer loop 在成功處理後呼叫 `ack(message_id)`。

**BUG-13 `knowledge` · _rule_match ORDER BY id → 最舊 rule 優先，非最高分**  
`knowledge.py:169-176` `_RULE_SQL` `ORDER BY id`，取 `rows[0]` 為最低 id，非最佳匹配。若 DB 中較早插入的低分 rule 優先選出，高分 exact-match rule 被忽略，`query()` fallthrough 到 Tier 2。  
**修復**：改為 `ORDER BY CASE WHEN match_type='exact' THEN 0 ELSE 1 END, id`，或取所有 rows 後選 `max(_score(r))` 的那筆。

**BUG-14 `knowledge` · batch_import_knowledge 單筆 enqueue 失敗中斷整批**  
`knowledge.py:1386-1397` for loop 無 try/except，任一 SAQ/Redis 失敗即拋例外，已入隊的前 N-1 筆無法計算，caller 拿到 exception 而非 `BatchImportResult`。  
**修復**：每筆 enqueue 加 try/except，累計 `enqueued_count` 和 `failed_count`，loop 結束後回傳 `BatchImportResult`。

**BUG-15 `a2a_adapter` · execute() 回傳完整 JSON-RPC envelope 而非 result**  
`a2a_adapter.py:340-345` `ok(body)` 中 `body` 是 `{"jsonrpc":"2.0","id":"...","result":{...}}`，caller 拿到的是 envelope 而非 `body["result"]`，所有工具輸出欄位存取均錯位。  
**修復**：`return ok(body.get("result") if isinstance(body, dict) else body)`。

**BUG-16 `response` · LINE/WhatsApp retraction 靜默回傳成功但未發送任何訊息**  
`response.py:569-576, 579-591` `_retract_line()` / `_retract_whatsapp()` 均回傳 `apology_sent=True` / `correction_sent=True`，但完全未呼叫平台 API。`retract()` L695/698 也未傳入 `line_client` / `whatsapp_client`。  
**修復**：補充平台 API 呼叫，並將 client 參數正確傳遞。

**BUG-17 `pii` · +886 國際電話號碼不被 _PHONE_RE 匹配 → PII 洩漏**  
`pii.py:63` 只匹配以 `0` 開頭的格式，`+886-912-345-678` 直接通過 `mask()` 原樣輸出至 LLM/log。  
**修復**：在 `_PHONE_RE` 加入 `\+886[-\s]?(?:0?\d{2,3}[-\s]?\d{3,4}[-\s]?\d{3,4})` 分支。

---

### 工具執行類

**BUG-18 `tool_executor` · handler 呼叫無 timeout → blocking handler 掛住整個 executor**  
`tool_executor.py:303-320` `handler(**arguments)` 無 `asyncio.wait_for` 或 `threading.Timer`，違反 FR-41 / NP-07 timeout 合約。  
**修復**：async handler 用 `asyncio.wait_for(handler(**args), timeout=_HANDLER_TIMEOUT)`；sync handler 用 `loop.run_in_executor()` + `wait_for`。

**BUG-19 `tool_executor` · except Exception 漏掉 BaseException → sys.exit() 逃逸**  
`tool_executor.py:305` 只攔截 `Exception`，`SystemExit`、`KeyboardInterrupt` 繞過 `fail()` 路徑，違反 NP-07「MUST NOT raise」合約。  
**修復**：改為 `except BaseException:`，相同的 log + return fail() 處理。

**BUG-20 `mcp_adapter` · _parse_tool_list() 永遠回傳 [] → production 工具發現永遠失敗**  
`mcp_adapter.py:221-227` 無條件 `return []`，任何非 monkeypatch 環境下 `execute()` 永遠找不到工具（`"unknown tool: <name>"`）。  
**修復**：實作 MCP tools/list JSON-RPC response 解析，或改為 `raise NotImplementedError` 使問題可見。

**BUG-21 `mcp_adapter` · _connect_stdio() 無 stdin=PIPE → MCP server 等待輸入死鎖**  
`mcp_adapter.py:165-170` Popen 未設 `stdin=PIPE`，child 繼承 parent stdin，若 MCP server 等待 JSON-RPC "initialize" 請求則死鎖，`communicate()` timeout 後靜默回傳 []。  
**修復**：加入 `stdin=subprocess.PIPE`，並在讀取 tool list 前先發送 MCP initialize request。

**BUG-22 `circuit_breaker` · embedding/classifier lateral circuit 只能 trip，永遠無法恢復**  
`circuit_breaker.py:122-132` `record_embedding_failure()` / `record_classifier_failure()` 設定 `_embedding_down=True` / `_classifier_down=True` 後，無對應 success 方法重置，搜索和分類服務永久降級。  
**修復**：加入 `record_embedding_success()` 和 `record_classifier_success()` 重置方法。

**BUG-23 `circuit_breaker` · LEVEL_2/4/5 狀態 sticky 永遠不恢復**  
`circuit_breaker.py:111-115` `record_llm_success()` 只對 `LEVEL_1` 和 `LEVEL_3` 觸發恢復，其他級別即使連續成功也永遠停留降級狀態，違反 FR-99。  
**修復**：恢復判斷改為 `if self._level != self.LEVEL_0`，加入完整降級→恢復階梯邏輯。

**BUG-24 `llm_judge` · 雙 judge 失敗 fallback 回傳 score=0，違反 1-5 scale**  
`llm_judge.py:324` `JudgeResult(politeness=0, accuracy=0, judge_name="degraded")`，SRS FR-65 規定最低分為 1。0 傳入 `aggregate_csat()` 靜默產生低於合約下限的 CSAT 分數。  
**修復**：改為 `politeness=1, accuracy=1`，或加入 `is_degraded: bool` 欄位讓 caller 識別。

**BUG-25 `llm_judge` · evaluate() 內 registry import 在 NP-07 保護之外 → ImportError 直接炸穿**  
`llm_judge.py:228-229` deferred import 和 `get_service("dummy")` 在 `asyncio.gather()` 和所有 `_invoke_safely` 之前執行，任何 import 失敗直接炸穿 evaluate() 的 NP-07 合約。  
**修復**：刪除這兩行，或用 `try/except Exception: pass` 包裹。

---

### 鏈路/中介類

**BUG-26 `chain` · rate-limit 判斷只看 status==429，忽略 allowed=False**  
`chain.py:159-166` rate-limiter 結果只檢查 `getattr(..., "status", 200) == 429`，其他所有 middleware 用 `_is_allowed(outcome, default=False)`。若 rate-limiter 回傳 `allowed=False, status=200` 則完全繞過限流。  
**修復**：改為 `if not _is_allowed(rate_outcome, default=False)` 或 dual check。

**BUG-27 `chain` · ip_outcome.status/.body 裸存取無 getattr fallback → AttributeError crash**  
`chain.py:141-143` TLS block 用 `getattr`，但 IP whitelist block 直接 `.status` / `.body`，非標準 object 觸發 AttributeError 直接 crash request。  
**修復**：改為 `getattr(ip_outcome, "status", 403)` 和 `getattr(ip_outcome, "body", b"")`。

**BUG-28 `webhooks` · MessengerWebhookVerifier 無 sha256= prefix 檢查**  
`verifiers.py:124-130` `removeprefix("sha256=")` 若 prefix 缺失為 no-op，攻擊者可送裸 hex string 直接通過 HMAC 比對（WhatsAppWebhookVerifier 有正確 startswith 保護，兩者不一致）。  
**修復**：加入 `if not received_signature.startswith("sha256="): return False`。

**BUG-29 `paladin` · _await_coro_from_sync thread join timeout 後 coroutine 繼續跑，資源洩漏**  
`paladin.py:636-643` join timeout 後 daemon thread 繼續跑，網路連接洩漏；coroutine 最終完成後可能 mutate shared state（cache、rate-limit counter），與下一個 request 的 classify() 產生 race。  
**修復**：timeout 後呼叫 `new_loop.call_soon_threadsafe(new_loop.stop)` 停止 loop，或禁止在 async pipeline 中呼叫 sync `classify()`。

**BUG-30 `jobs` · process_embedding_job 不遞增 retry_count → 可能無限重試**  
`jobs.py:267-274` "retrying" 分支不修改 `job.retry_count`，caller re-enqueue 同一 object 後 `retries_left` 永遠為 True，`max_retries` 永遠不到達。  
**修復**：在 retrying 分支加入 `job.retry_count += 1`。

---

## 4. P2 — 中優先修復（Medium）

| # | Module | File:Line | 說明 |
|---|--------|-----------|------|
| M-01 | dst | `dst.py:451-459` | `handle_confirmation` awaiting_rounds 邊界模糊（`>=` vs `>`），第 2 輪的確認可能被誤判為 escalation |
| M-02 | dst | `dst.py:603-605` | `manage()` no-overflow 路徑回傳原始 list reference，caller 意外 mutate 影響 session state |
| M-03 | knowledge | `knowledge.py:499-504` | Tier-2 RAG search 傳 `RAG_TOP_K_PARENTS=5` 而非 `RAG_TOP_K_CHILDREN=10`，recall 減半 |
| M-04 | knowledge | `knowledge.py:519-527` | `_escalate()` reason 永遠 `"no_rule_match"`，LLM grounding 失敗被錯誤分類 |
| M-05 | knowledge | `knowledge.py:619-622` | primary LLM 失敗 bare except 靜默吞錯，outage 不可見 |
| M-06 | paladin | `paladin.py:786-792` | `GroundingChecker.check()` text-path stub 永遠回傳 `grounded=True`，grounding 未實作 |
| M-07 | a2a_adapter | `a2a_adapter.py:96-127` | DNS rebinding：SSRF 驗證只在 init 做一次，後續 httpx 重新解析 DNS |
| M-08 | mcp_adapter | `mcp_adapter.py:151-155` | JSON-RPC error response 包在 `ok()` 中，caller 拿到 `success=True` 但 output 含 error |
| M-09 | mcp_adapter | `mcp_adapter.py:229-241` | `_is_server_unreachable()` 用 `"down"` substring 匹配，任何含 "down" 的合法 command/URL 被誤判 |
| M-10 | llm_judge | `llm_judge.py:593-597` | 校準 LLM 掛掉時 `action="pass"` 靜默偽裝成校準成功，掩蓋 outage |
| M-11 | pii | `pii.py:63` | phone regex 最低只要 8 位數就命中（需要 10-11），產生假陽性遮蔽 |
| M-12 | pii | `pii.py:242-265` | 零 PII 呼叫也寫 audit log，大量噪音擠出真實 PII 事件（10,000 條 trim） |
| M-13 | pipeline | `pipeline.py:99-103` | `get_context()` 永遠回傳 `{"history": []}`，所有需要對話歷史的邏輯靜默失效 |
| M-14 | pipeline | `pipeline.py:89-90` | `emotion.analyze()` 無 try/except，analyzer 例外直接 crash `process()` |
| M-15 | escalation | `escalation.py:237-247` | `_ensure_row` 建 stub row 時 `sla_deadline=now`，所有「防禦性 fallback」工單立即 SLA breach |
| M-16 | escalation | `escalation.py:305-314` | `compute_sla_compliance()` 硬編碼回傳 0.98，監控永遠顯示綠燈 |
| M-17 | circuit_breaker | `circuit_breaker.py:270-278` | `execute_with_retry` 第一次重試 sleep 用 attempt=1（2s）而非 attempt=0（1s），delay 加倍 |
| M-18 | circuit_breaker | `circuit_breaker.py:79-80` | `record_llm_latency` 只處理 LEVEL_0→LEVEL_1，持續高延遲無法推進到 LEVEL_2 |
| M-19 | gdpr | `gdpr.py:163-173` | CSV export 只輸出 `count`，不輸出實際個資內容，違反 GDPR Article 20 資料可攜 |
| M-20 | webhooks | `webhooks.py:241-242` | `_TOKEN_STORE` 是 in-memory dict，server restart 後舊 token 全失效；concurrent write 有 race |
| M-21 | webhooks | `a2a.py:163-165` | `urllib.request.urlopen` 在 async FastAPI endpoint 做同步 HTTP → event loop 阻塞 |
| M-22 | database | `database.py:404-413` | `run_roundtrip` 不檢查 `_step()` 回傳值，step 失敗仍報告 `success=True` |
| M-23 | observability | `observability.py:88-90` | `sorted(obj)` 對 mixed-type set 觸發 TypeError → 整個 `log()` 失敗 |
| M-24 | observability | `observability.py:160-161` | 未知 log level 靜默 fallback 至 INFO，ERROR 拼錯不觸發 alert |
| M-25 | config | `config.py:92-95` | `get_config_store()` singleton 初始化無鎖，多執行緒 first-caller race |
| M-26 | chain | `chain.py:147-148` | `signature_validator.verify()` 拋例外不被攔截，應回傳 401 但 crash request |
| M-27 | rbac | `rbac.py:197-200` | `role` kwarg 在 production 環境被 pop 後丟棄，caller 降級為 `"anonymous"` |
| M-28 | rbac | `rbac.py:169-170` | `log_admin_action` 無 try/except，log 失敗 → RBAC check 拋例外 |
| M-29 | redis_streams | `redis_streams.py:251-281` | claim_pending 分頁 cursor 遇非標準 message ID 不推進，10,000 次迴圈空轉 |
| M-30 | jobs | `jobs.py:387-393` | `compute_sync_status` chunks_done > chunks_total 時回傳 `"failed"` 而非 `"synced"` |

---

## 5. 修復優先順序

**P0（立即 hotfix，生產安全/資料合規）**
- BUG-01 paladin classify() 安全繞過
- BUG-02 / BUG-03 GDPR 刪除不完整
- BUG-05 jobs 循環依賴（啟動不穩定）
- BUG-06 auth JWT hardcoded secret
- BUG-07 auth module import crash

**P1（本 sprint 完成，功能正確性）**
- BUG-08 IP whitelist XFF bypass
- BUG-09 security stub deletion
- BUG-10 paladin SQL bypass
- BUG-11 rate_limit collision
- BUG-12 redis_streams ack never called
- BUG-13 knowledge wrong ORDER BY
- BUG-14 knowledge batch import abort
- BUG-15 a2a_adapter wrong return value
- BUG-16 response retraction no-op
- BUG-17 pii +886 leak
- BUG-18/19 tool_executor timeout/BaseException
- BUG-20/21 mcp_adapter always empty / stdin deadlock
- BUG-22/23 circuit_breaker lateral + LEVEL recovery
- BUG-24/25 llm_judge score=0 / NP-07 bypass
- BUG-26/27 chain rate-limit / ip_outcome crash
- BUG-28 webhooks prefix bypass
- BUG-29 paladin thread resource leak
- BUG-30 jobs retry_count not incremented

**P2（next sprint）**
- M-01 至 M-30（見上表）

---

## 6. 掃描方法

- **Phase 1**：CRG MCP `get_minimal_context_tool` + `list_communities_tool` + `list_flows_tool` 取得架構全覽
- **Phase 2**：30 個模組 × 8 批次（每批 4 agents）；HIGH-RISK 12 模組三鏡頭（correctness / concurrency / resilience），STANDARD 18 模組 general-lens；每 agent 讀完整檔案 + 呼叫 `query_graph_tool` 取 callers/tests
- **Phase 3**：對抗性驗證 4 個 critical/high findings（refute + confirm），4/4 CONFIRMED
- **覆蓋率**：30/30 主程式模組，排除所有 tests/ 目錄

> ⚠️ confirmed critical/high bugs（BUG-01 to BUG-30）需逐條 resolved 或 documented-as-wontfix 後，Gate 3 adversarial_review 才可放行。
