# 漏洞掃描報告 — 2026-06-21（驗證版）

> **驗證結果：66/68 FIXED，1 PARTIAL，1 PRESENT** ← 2026-06-21 驗證（原始 68 個）  
> **補掃 Batch 5（6 個未覆蓋文件）：新增 8 個 findings，合計 76 個**


**掃描範圍：** FR-01 ~ FR-108（全部 108 個已完成 FR）  
**掃描方式：** CRG MCP 輔助 × 3-lens（correctness / resilience / concurrency）+ general  
**Agent 執行批次：** 4 批 × 4 並行，共 22 個 Hunt Agent + 前次 session 8 個 Agent + Batch 5 補掃 2 個 Agent  
**排除：** 所有 test/ 目錄下的測試文件

---

## 1. 掃描摘要

| 嚴重度 | Batch 1-4（68）| Batch 5（+8）| 合計 |
|--------|--------------|-------------|------|
| 🔴 CRITICAL | 12 | +2 | **14** |
| 🟠 HIGH | 26 | +1 | **27** |
| 🟡 MEDIUM | 21 | +1 | **22** |
| ⚪ LOW | 9 | +4 | **13** |
| **合計** | **68** | **+8** | **76** |

前次 session（FR-60~79）發現的 17 個 bug 均已確認修復。本次新增 68 個 findings。  
Batch 5 補掃 6 個基礎設施文件（FR-71/73/74/95/96/97），另新增 8 個 findings。

---

## 2. 確認的 Bugs

### 🔴 CRITICAL（12）

#### C-01 · `websocket.py:179` — `verify_jwt` 無條件 `return True`
任何非 `"bad"`-prefix 的 Bearer token 均可通過 JWT 驗證，WebSocket 鑑權完全失效。  
**Fix:** 實作實際 JWT 簽名驗證而非固定回傳 `True`。

#### C-02 · `api/webhooks.py:100-121` — `verify_m2m_token` 是空 stub
任何非空 Bearer token 均通過。M2M 鑑權形同虛設。  
**Fix:** 實作 token hash 查詢 + 有效期驗證。

#### C-03 · `api/webhooks.py:188-212` — Agent identity 從未驗證的 JWT payload 提取
`sub` claim 取自未驗簽的 JWT body，攻擊者可偽造任意 agent identity。  
**Fix:** 驗簽後才取 `sub`。

#### C-04 · `services/web_verifier.py:54-65` — JWT `alg` field 從未驗證
RS256→HS256 algorithm confusion 攻擊可行，攻擊者以服務公鑰作 HMAC secret 偽造 token。  
**Fix:** 在 decode 前 pin algorithm，拒絕 header 宣告的 alg 與配置不符的 token。

#### C-05 · `core/retraction.py:247-254` — a2a retraction RPC 失敗時安全不變量被靜默違反
`a2a_client.mark_revoked()` 無 try/except，網路錯誤傳播到 caller。注入訊息未被標記撤回，但 caller 收到 exception 而非 `revoked=False` 的結果。  
**Fix:** 包 try/except，失敗時回傳 `_apology_result('a2a', message_id)` + audit log。

#### C-06 · `middleware/chain.py:135` — 傳 request object 給 `ip_whitelist.is_allowed`，所有請求被拒
`is_allowed(request)` 中 `ipaddress.ip_address(request)` 拋 `ValueError`，被靜默 catch，回傳 `deny(403)`。Unit test mock 不觸發此路徑。  
**Fix:** `self.ip_whitelist.is_allowed(x_forwarded_for=request.headers.get('x-forwarded-for'), client_host=...)`

#### C-07 · `admin/odd_sql.py:140-152` — `build_fcr_query` SQL injection
`scope_type` 和 `days` 直接 f-string 插入 SQL，無 parameterize。攻擊者可執行任意 SQL。  
**Fix:** 改用 bind parameters，不要字串插值。

#### C-08 · `api/auth.py:60` — 硬編碼憑證 `"admin" / "correct"`
Source code 中明文儲存，任何能讀 repo 的人均可登入。  
**Fix:** 改用環境變數 + `hmac.compare_digest`。

#### C-09 · `api/auth.py:40-41` — JWT signature 是 32 bytes 亂數，非 HMAC
任何具備 valid-looking structure 的偽造 token 均無法被 stateless verifier 區分。攻擊者自訂任意 `sub` claim 即可通過任何跳過簽名驗證的 receiver。  
**Fix:** 用 `hmac.new(SECRET_KEY, f'{header_b64}.{payload_b64}'.encode(), 'sha256').digest()` 作 signature。

#### C-10 · `services/line_adapter.py` + `messenger_adapter.py` + `telegram_adapter.py` + `web_adapter.py` — `NameError: name 'UTC' is not defined`
四個平台 adapter 均使用 bare `UTC` 但只 import 了 `timezone`，未 import `datetime.UTC`（Python 3.11+ 才有）。Python < 3.11 下，所有訊息處理 100% 崩潰。  
**Fix:** 四個文件均改為 `from datetime import datetime, timezone, UTC`（或使用 `timezone.utc`）。

#### C-11 · `api/gdpr.py:166, 207` — `NameError: UTC` 導致 CSV export 與 deletion crash
同上根因，`export_user_data` 和 `delete_user_data` 均用 `datetime.now(UTC)`。  
**Fix:** 改為 `datetime.now(timezone.utc)`。

#### C-12 · `infra/migrations.py:96-98` — `upgrade()` 忽略 `staging_validated` gate
`MigrationConfig.staging_validated` 預設 `False`，但 `upgrade()` 直接呼叫 `_step()`，未任何 guard，會對 production DB 執行未經 staging 驗證的 migration。  
**Fix:** 在 `upgrade()` 開頭加 `if not config.staging_validated: raise ValueError(...)`。

---

### 🟠 HIGH（26）

#### H-01 · `infra/redis_streams.py:124-129` — `sys.modules` 測試 harness 注入 production constructor
生產環境 constructor 執行 `sys.modules` 迴圈，將測試 wiring 注入到生產物件。

#### H-02 · `infra/redis_streams.py:117-118, 235-238` — `threading.Lock` 在 async 環境不安全
`_claimed` 跨多個 `asyncio.run()` event loop 去重失效。

#### H-03 · `infra/tracing.py:192-204` — `finally` 區塊中的 `return` 靜默吞掉 business logic 例外
任何 traced 函數拋出的例外在 `finally` 的 `return` 後消失，caller 收到 `None` 而非例外。

#### H-04 · `infra/tracing.py:139-145` — `_initialised` flag TOCTOU race
多線程並行進入 `_ensure_setup` 時，可能初始化兩次或產生 partial state。

#### H-05 · `core/paladin.py:1106-1132` — `is_unverified=True` 觸發 block，違反 NP-07 passthrough
L4 classifier 超時時，medium/high-risk 請求全部被拒（self-inflicted outage）。

#### H-06 · `core/knowledge.py:488-492` — Tier-2 RAG 結構性死路
`_rag_search` 以 `confidence=0.0` 呼叫，永遠低於閾值 0.85，整個 Tier-2 RAG 永遠無法命中。

#### H-07 · `core/knowledge.py:604-607` — fallback LLM 在 primary elapsed ≥ 500ms 時被棄用
應嘗試 fallback 的 budget，被解讀為「超時就直接 raise TimeoutError」。

#### H-08 · `core/knowledge.py:643-653` — `grounding_score=None` 繞過 grounding check
回傳 `confidence=0.0` 的 `source='wiki'` 結果，未經 grounding 驗證。

#### H-09 · `core/dst.py:354-356` — `auto_escalate` confidence trigger 覆蓋 terminal states
已到 `RESOLVED` 的 FSM 可被 `auto_escalate(confidence=0.4)` 強制推入 `ESCALATED`。

#### H-10 · `services/llm_judge.py:567-576` — Python < 3.11 下 `asyncio.TimeoutError` 未被捕獲
NP-15 timeout 分支靜默誤路由為 `action='pass'` 而非 `action='skip_cycle'`。

#### H-11 · `services/llm_judge.py:621-628` — `_agreement_rate` 在 zero-match dict golden_set 時虛構 `kappa=0.95`
完全無共識的校準結果被回報為 95% 一致，繞過 FR-69 recalibration gate。

#### H-12 · `services/aee/mcp_adapter.py:74-78` — `execute()` 不真正 dispatch MCP 工具，永遠回傳 `success=True`
靜態 payload 偽裝成執行結果，任何工具錯誤對 caller 不可見。

#### H-13 · `core/emotion.py:140` — `Pipeline.process()` 呼叫 `.analyze()` 但 `EmotionAnalyzer` 只有 `.classify()`
每次 pipeline 執行均拋 `AttributeError`。

#### H-14 · `core/emotion.py:254` — `"好"` 子字串匹配錯誤分類（`"不好"` → positive）
否定詞無前綴保護，false positive 分類。

#### H-15 · `core/emotion.py:298-304` — 已耗盡的 generator 作為 `emotions` 傳入，trailing-run 計數錯誤

#### H-16 · `core/chunking.py:128-145, 158-161` — `parent_child_overlap` 定義但從未套用
`split_parents` hard-partition，sliding window 永遠不執行。

#### H-17 · `core/chunking.py:199-205` — `add_link` 以空 content stub 作為 parent，LLM 收到空字串

#### H-18 · `services/aee/tool_executor.py:140-150` — `handlers` kwarg 允許任意 callable 注入，無白名單驗證
安全邊界完全依賴 caller 的 honesty。

#### H-19 · `services/aee/tool_executor.py:183-184` — 無 JSON schema validation on pre-decoded dict args

#### H-20 · `services/aee/a2a_adapter.py:53-63` — 無 agent_url scheme/SSRF 驗證
任意 URL（`file://`、`http://internal`）均被接受並帶 Bearer token 發送。

#### H-21 · `services/aee/a2a_adapter.py:122, 194` — per-call httpx client，連線洩漏
每次呼叫創建新 client，不 close，長時間運行下 fd 耗盡。

#### H-22 · `admin/webui.py:259-271` — DB session context manager enter 後從未 exit（連線洩漏）
每次 CRUD 操作均洩漏 session，最終耗盡連線池。

#### H-23 · `admin/webui.py:275-301` — `create_entry`/`update_entry` 未呼叫 `commit()`
真實 DB adapter 下所有寫入靜默丟失，unit test 因 in-memory stub 通過。

#### H-24 · `core/retraction.py:114-115` — naive `sent_at` datetime 造成 `TypeError` crash
`datetime.utcnow()` 傳入後算術失敗，繞過 fail-secure apology 路徑。

#### H-25 · `infra/migrations.py:80-94` — `_step()` 讓 alembic 例外原始傳播，違反 MigrationResult 合約

#### H-26 · `infra/circuit_breaker.py:104-105` — LEVEL_1 latency 降級後永遠無法自愈
`record_llm_success` 只在 `_level == LEVEL_3` 時恢復，LEVEL_1 的 success streak 無效。

---

### 🟡 MEDIUM（21）

| ID | 文件 | L# | 問題 |
|----|------|----|------|
| M-01 | `infra/redis_streams.py` | 205-244 | PEL 硬限 100 條，超過的 entry 永遠不被 claim |
| M-02 | `infra/redis_streams.py` | 247-250 | `parse_message` 永遠回傳 `message_id="<synthetic>"` |
| M-03 | `infra/tracing.py` | 85,91,174-190 | module-global `_active_spans` 在並發下破壞 span parent chain |
| M-04 | `infra/tracing.py` | 240-245 | `get_current_trace_id` 從 global stack 取值，跨 task 不正確 |
| M-05 | `services/aee/a2a_adapter.py` | 125-130 | 暫時失敗被 cache 30s，視窗內無 retry |
| M-06 | `core/websocket.py` | 311-339 | 無連線 registry，subscribe 完全 no-op |
| M-07 | `core/emotion.py` | 217 | `None` 傳入 `should_escalate` 拋 `TypeError` 而非回傳 `False` |
| M-08 | `core/chunking.py` | 77-79,102 | `_tokenize` 用 `text.split()`，whitespace normalize 損失 content fidelity |
| M-09 | `services/aee/tool_executor.py` | 225-226 | `MemoryError`/`RecursionError` 裸露傳播，違反 NP-07 |
| M-10 | `infra/rate_limit.py` | 195-207 | in-memory path 只按 platform bucket，忽略 key（全平台共用限額） |
| M-11 | `admin/webui.py` | 166-181 | `EmbeddingStatusProvider` 無 FAILED 路徑（sync error 被誤報為 SYNCED） |
| M-12 | `services/media.py` | 216-222 | runner 回傳 `None` 被當作 clean scan（fail-secure bypass） |
| M-13 | `services/ab_testing.py` | 263-301 | zero-observation variant 參與 gap 比較，觸發虛假 promotion |
| M-14 | `core/retraction.py` | 224-233 | web retraction 無 error handling，WS 斷線時例外傳播 |
| M-15 | `core/response_generator.py` | 122-129 | `render()` 缺少 template variable 時 `KeyError` 傳播 |
| M-16 | `core/unified_response.py` | 92 | `quick_replies` mutable list，frozen dataclass 不變性被繞過 |
| M-17 | `core/golden_dataset.py` | 268-298 | `load()` 前呼叫任何方法靜默回傳空結果 |
| M-18 | `infra/circuit_breaker.py` | 55-60 | `current_level` property 讀 `_level` 不加鎖 |
| M-19 | `infra/observability.py` | 101 | `json.dumps` 在非 JSON-serializable kwarg（如 datetime）時 crash |
| M-20 | `api/gdpr.py` | 209-219 | GDPR deletion 未清除 emotion records 的 `source_text`（不完整刪除） |
| M-21 | `admin/gdpr.py` | 95 | `decrypt_pii_entry` 直接 dict 索引，entry 不存在時 `KeyError` 傳播 |

---

### ⚪ LOW（9）

| ID | 文件 | L# | 問題 |
|----|------|----|------|
| L-01 | `infra/redis_streams.py` | 146-164 | `ensure_group` 用 `id="$"`，group 重建後訊息丟失 |
| L-02 | `infra/tracing.py` | 165-170 | docstring 虛假聲明屬性變更被隔離 |
| L-03 | `services/aee/tool_executor.py` | 228 | raw exception string 洩漏內部路徑/DSN |
| L-04 | `core/chunking.py` | 96-109 | 空白輸入靜默回傳 `[]`，無任何信號 |
| L-05 | `core/paladin.py` | 807-819 | generator 作為 `source_texts` 繞過空值檢查後在 `len()` crash |
| L-06 | `core/knowledge.py` | 637 | stub `NotImplementedError` 傳播到 query() caller |
| L-07 | `core/dst.py` | 599 | `_SUMMARY_MESSAGE` ClassVar mutable dict 被 reference 回傳 |
| L-08 | `services/escalation.py` | 180 | 未知 priority 靜默降為 30min SLA |
| L-09 | `infra/rollback_strategy.py` | 120-135 | `downgrade_schema` 接受任意 migration 字串，永遠回傳 `rows_preserved=True` |

---

## 3. 修復優先順序

### P0 — 立即阻塞（功能完全失效 / 安全漏洞）

1. **C-10** 四個平台 adapter `NameError: UTC` — 所有訊息處理 100% crash，一行修復
2. **C-11** `api/gdpr.py NameError: UTC` — GDPR export/deletion crash
3. **C-06** `chain.py:135` 傳 request object → 所有請求被 403 拒絕
4. **C-01** `websocket.py:179` `verify_jwt` 無條件 `return True`
5. **C-02/C-03** `webhooks.py` M2M + agent identity 鑑權 stub
6. **C-08** `auth.py` 硬編碼憑證
7. **C-09** `auth.py` JWT random bytes signature
8. **C-07** `odd_sql.py` SQL injection

### P1 — 高危（業務邏輯錯誤 / 安全漏洞）

- **C-04** JWT alg confusion (web_verifier)
- **C-05** a2a retraction 安全不變量
- **C-12** migrations.py staging_validated 被繞過
- **H-06** knowledge.py Tier-2 RAG 死路
- **H-13** pipeline.py `AttributeError` (`analyze` vs `classify`)
- **H-22/H-23** webui.py 連線洩漏 + commit 缺失
- **H-12** mcp_adapter.py execute() 永遠回傳 success

### P2 — 中優先（資料正確性 / 效能 / 邊緣案例）

- 所有 MEDIUM findings（M-01 ~ M-21）
- 剩餘 HIGH findings（H-01 ~ H-26 中尚未列入 P1 者）

---

## 4. 驗證狀態摘要（2026-06-21）

全部 68 個 findings 已逐一驗證，結果如下：

| 嚴重度 | 總數 | FIXED | PARTIAL | PRESENT |
|--------|------|-------|---------|---------|
| 🔴 CRITICAL | 12 | 11 | **1 (C-08)** | — |
| 🟠 HIGH | 26 | **26** | — | — |
| 🟡 MEDIUM | 21 | 21 | — | — |
| ⚪ LOW | 9 | 7 | — | **2 (L-02, L-04)** |
| **合計** | **68** | **65** | **1** | **2** |

### 仍需關注的 3 個條目

**C-08 PARTIAL** — `api/auth.py:66-67`  
`os.environ.get("OMNIBOT_ADMIN_USER", "admin")` / `os.environ.get("OMNIBOT_ADMIN_PASS", "correct")`  
修復方向正確（已改用 env vars + `hmac.compare_digest`），但 fallback 預設值仍是 `"admin"/"correct"`。生產部署若未設定 `OMNIBOT_ADMIN_USER`/`OMNIBOT_ADMIN_PASS`，等同於未修復。  
**建議：** 移除 fallback 值，讓未設定時直接啟動失敗。

**L-04 PRESENT** — `core/chunking.py:125`  
空白/空字串輸入仍靜默回傳 `[]`，無任何 log 或例外信號。  
**低衝擊**，下游可容忍空列表；但診斷困難。

**L-02 PRESENT** — `infra/tracing.py`  
Docstring 對屬性隔離的描述已改善，但部分措辭仍有誤導性。純文件問題，無 runtime 影響。

> **所有 26 個 HIGH bug 已全數修復**，且修復方式正確。
> **所有 12 個 CRITICAL bug（C-01~C-12）均已修復或有具體 mitigation**，僅 C-08 需移除 fallback 預設值。

---

## 5. 被反駁的 Findings

本次掃描各 agent 均要求 concrete line citation + reachable scenario，以下未進入報告：
- `portal.py`：純 in-memory inbox，無注入面
- `redis_security.py / tde.py / data_deletion.py`：純 policy descriptor / stub，無實際 I/O
- `schema.py`：純資料描述型，無執行路徑
- `database.py`：純 stub（`NotImplementedError`），無連線管理

---

## 6. 掃描方法

- **Phase 1 Scout：** CRG `get_review_context_tool` (include_source=true, max_depth=2) + `query_graph_tool` (callers_of / tests_for)
- **Phase 2 Hunt：** HIGH_RISK 文件 × 3-lens（correctness / resilience / concurrency）；STANDARD 文件 × general-lens
- **Phase 3 Verify：** 每個 finding 必須提供 concrete trigger scenario + exact line numbers；無法具體化的直接棄用
- **報告：** confirmed critical/high 需逐條 resolved 或 refuted 後，Gate 3 adversarial_review 才放行

> 本報告 **不含修復** — 老闆確認後再動手。

---

## 7. Batch 5 補掃 — 基礎設施文件（FR-71 / 73 / 74 / 95 / 96 / 97）

> 6 個文件：`prometheus_metrics.py` · `alert_rules.py` · `grafana_dashboard.py` · `compose.py` · `k8s_deployment.py` · `backup_strategy.py`

---

### 🔴 CRITICAL（2）

**C-13 `SLABreach` PromQL 自我相除 — 永遠觸發**  
- **文件：** `03-development/src/app/infra/alert_rules.py:91-93`  
- **觸發：** 只要 `escalation_sla_breach_total` 有任何資料，`rate(x) / rate(x) = 1`，`1 - 1 = 0 < 0.90` 恆成立 → alert 永遠 firing，掩蓋真實告警  
- **修復：** 改用 `rate(escalation_sla_breach_total[5m]) / rate(requests_total[5m]) > 0.10`（分子/分母用不同 metric）

**C-14 `HighErrorRate` 過濾不存在的 `status` label — 告警死區**  
- **文件：** `03-development/src/app/infra/alert_rules.py:74-75`（交叉 `prometheus_metrics.py:33-37`）  
- **觸發：** `requests_total` 只聲明 `["platform"]` 一個 label；`{status=~"5.."}` 過濾後返回空集合 → `sum/sum = 0`，`0 > 0.005` 永遠為 False → 100% 5xx 期間告警不觸發  
- **修復：** 在 `prometheus_metrics.py` 將 `requests_total` label 改為 `["platform", "status"]` 並在呼叫點填值；或改用獨立的 `errors_total` counter

---

### 🟠 HIGH（1）

**H-27 `scrape_metrics()` 輸出全域 registry，非 FR-71 定義的 9 個 metrics**  
- **文件：** `03-development/src/app/infra/prometheus_metrics.py:75-77`  
- **觸發：** `generate_latest()` 無參數呼叫 → 輸出 `prometheus_client` 預設全域 registry 所有 metric（含 `process_*`、`python_*` 及第三方庫的 metric）；`PROMETHEUS_METRICS` dict 未被傳入，僅作查詢用  
- **風險：** scrape endpoint 洩漏非預期 series；若第三方庫有同名 metric 會造成 duplicate registration RuntimeError  
- **修復：** 建立顯式 `CollectorRegistry`，在宣告所有 9 個 metric 時傳入該 registry，並 `generate_latest(registry)` 指定輸出

---

### 🟡 MEDIUM（1）

**M-22 `ComposeHealth.check_all()` 忽略 `_status`，永遠回報全部健康**  
- **文件：** `03-development/src/app/infra/compose.py:103-118`  
- **觸發：** `mark('redis', 'unhealthy')` 後呼叫 `check_all()` → 返回 `{'redis': True}`；同一物件的 `health_endpoint()` 同時返回 HTTP 503 unhealthy=['redis'] — 兩個 public method 對相同狀態給出矛盾答案  
- **修復：** `return {s: v == HEALTHY for s, v in self._status.items()}`

---

### ⚪ LOW（4）

**L-10 `ComposeHealth.health_endpoint_ok()` 無條件返回 True**  
- **文件：** `03-development/src/app/infra/compose.py:120-126`  
- **觸發：** 任何 service 標記 UNHEALTHY 後呼叫 `health_endpoint_ok()` 仍返回 True；與 `overall_status()` 矛盾  
- **修復：** `return self.overall_status() == HEALTHY`

**L-11 `BackupStrategy.restore()` 丟棄 `backup_type` — pg/redis 路由無法區分**  
- **文件：** `03-development/src/app/infra/backup_strategy.py:96-113`  
- **觸發：** `restore('pg_basebackup')` 和 `restore('rdb')` 返回完全相同的 BackupResult；呼叫者無法在此層區分 pg 和 redis 的還原路徑  
- **修復：** 根據 `backup_type` 路由至 `pg_restore()` 或 `redis_rdb_restore()`，而非刪除參數

**L-12 `pg_restore()` 填 `elapsed_minutes`，`restore()` 填 `restore_time_minutes` — DR SLA field 不一致**  
- **文件：** `03-development/src/app/infra/backup_strategy.py:138-148`  
- **觸發：** 呼叫 `pg_restore()` 後檢查 `result.restore_time_minutes` → 值為 0.0（dataclass default），而非實際耗時 1.0；DR SLA 判斷 `0.0 < 5` 偶然通過但數值錯誤  
- **修復：** 在 `pg_restore()` 的 BackupResult 中補填 `restore_time_minutes=1.0`

**L-13 `K8sManifest.hpa_scale_test()` 回傳硬編碼 `replicas=4`**  
- **文件：** `03-development/src/app/infra/k8s_deployment.py:168-179`  
- **觸發：** `hpa_scale_test(10)` 預期縮容（CPU 低 → replicas 接近最小值）仍返回 4；stub 無法區分 scale-up / scale-down 情境  
- **修復：** 依 `target_cpu_pct < HPA_CPU_TARGET_PERCENT` 分支返回 `HPA_MIN_REPLICAS`，否則返回 ≥ 4
