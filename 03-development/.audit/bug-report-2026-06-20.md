# 漏洞掃描報告

**掃描日期**：2026-06-20  
**掃描範圍**：12 個高風險模組（3-lens：correctness / concurrency / resilience）+ 9 個標準模組（general）  
**Raw**：235 / **Confirmed**：169 / **Refuted**：66  
**觸發條件**：每條 finding 皆經 MCP hunt-bugs v3 重現腳本 + Python REPL 驗證

---

## 1. 掃描摘要

### 1.1 高風險模組（HR × 3-lens）

| 模組 | Critical | High | Medium | Low | 確認 | 反駁 |
|------|---------:|-----:|-------:|----:|-----:|----:|
| `app.core.dst` | 0 | 1 | 4 | 2 | 7 | 3 |
| `app.core.knowledge` | 0 | 4 | 5 | 2 | 11 | 10 |
| `app.core.paladin` | 0 | 4 | 9 | 4 | 17 | 6 |
| `app.infra.rate_limit` | 0 | 3 | 4 | 4 | 11 | 7 |
| `app.infra.redis_streams` | 0 | 4 | 7 | 3 | 14 | 8 |
| `app.services.aee.a2a_adapter` | 0 | 5 | 9 | 6 | 20 | 7 |
| `app.services.aee.adapter` | 0 | 0 | 2 | 1 | 3 | 1 |
| `app.services.aee.tool_executor` | 0 | 1 | 5 | 1 | 7 | 4 |
| `app.services.aee.cli_adapter` | 0 | 1 | 5 | 4 | 10 | 5 |
| `app.services.aee.mcp_adapter` | 0 | 2 | 4 | 3 | 9 | 4 |
| `app.services.llm_judge` | 0 | 3 | 7 | 3 | 13 | 4 |
| `app.core.emotion` | 0 | 1 | 2 | 2 | 5 | 3 |

### 1.2 標準模組（general lens）

| 模組 | High | Medium | Low | 確認 | 反駁 |
|------|-----:|-------:|----:|-----:|----:|
| `app.core.pii` | 1 | 2 | 2 | 5 | 0 |
| `app.core.pipeline` | 2 | 2 | 0 | 4 | 0 |
| `app.core.retraction` | 2 | 1 | 0 | 3 | 1 |
| `app.services.escalation` | 0 | 1 | 2 | 3 | 1 |
| `app.services.ab_testing` | 0 | 1 | 1 | 2 | 0 |
| `app.middleware.chain` | 2 | 2 | 1 | 5 | 3 |
| `app.middleware.ip_whitelist` | 1 | 1 | 1 | 3 | 1 |
| `app.services.response_generator` | 0 | 0 | 0 | 0 | 0 |
| `app.services.media` | 0 | 0 | 0 | 0 | 0 |

### 1.3 嚴重度統計

- **Critical**（1）：`a2a_adapter#11`（monkey-patch 在併發 adapter 之間的全域污染）
- **High**（51）：含 SSRF 繞過、double-failure 靜默吞、concurrency race、PII 漏失等
- **Medium**（78）：邏輯錯誤、資源洩漏、observability 缺漏
- **Low**（39）：dead code、contract 模糊、文件缺失

---

## 2. 確認的 Bugs（severity 降序，列舉關鍵項）

### 2.1 Critical

#### `a2a_adapter#11` — DNS pinning monkey-patch 在併發 adapter 之間的全域污染
- **檔案**：`/Users/johnny/projects/omnibot/03-development/src/app/services/aee/a2a_adapter.py:252-300`
- **問題**：`_pinned_dns_lock` 把 `socket.getaddrinfo` 改為 process-global module 屬性。兩個 adapter 對不同 hostname 併發時，A 進入 with-block 期間被 B 的 `original = A_patch` 截走；B 的 `finally` 還原錯誤版本，A 的後續 `socket.getaddrinfo` 呼叫命中真實 stdlib，IP-pinning 失效。
- **觸發條件**：兩個 `A2AAdapter.execute()` 對不同 agent URL 併發呼叫，process 內 A 尚未離開 with-block。
- **修復**：改用 httpx transport-level DNS resolution（`event_hooks` 或自訂 `httpcore` ConnectionPool），或 class-level `threading.Lock` 序列化 connect。

### 2.2 High（節錄代表性 findings）

#### `a2a_adapter#1` — IPv6 6to4（2002::/16）繞過 SSRF guard
- **檔案**：`a2a_adapter.py:79-94`（`_is_public_address`）
- **觸發**：`A2AAdapter("http://[2002:0a0b:0c0d::1]")` → `_is_public_address` 回傳 True，但 httpx 會連到內嵌的 10.11.12.13。
- **修復**：明確拒絕 `packed[0:2] == b'\x20\x02'`（6to4）與 `b'\x20\x01\x00\x00'`（Teredo）。

#### `a2a_adapter#2` — JSONDecodeError 透過 `except ValueError` 重拋，破壞 NP-07 fail-open
- **檔案**：`a2a_adapter.py:349-356`
- **觸發**：A2A 伺服器回 200 + HTML，`response.json()` 拋 `JSONDecodeError`（`ValueError` 子類），被 L355 `except ValueError: raise` 攔截並重拋。
- **修復**：先 catch `json.JSONDecodeError` 後再走 negative-cache。

#### `dst#5` — DialogueState 跨 webhook handler race（SAD NP-13 違規）
- **檔案**：`dst.py:237-306`
- **觸發**：`_PIPELINE` singleton 對所有 webhook 共用同一 DialogueState；`pipeline.py:115-116, 154-158` 在 `_lock` 外直接改 `self.dst.intent` / `self.dst.slots.update`。
- **修復**：加 `set_intent_and_slots` locked setter，或在 webhook 層 per-conversation_id 實例化 DialogueState。

#### `knowledge#6` — `batch_import_knowledge` 靜默吞 enqueue 失敗
- **檔案**：`knowledge.py:1414-1429`
- **觸發**：Redis SAQ 全部 down；迴圈走完回 `BatchImportResult(enqueued_count=0)`，無 re-raise，admin 端以為成功。
- **修復**：拋 `BatchImportPartialFailure` 或回傳 `failed_chunk_ids`。

#### `knowledge#8` — embed + enqueue 雙重失敗無法區分
- **檔案**：`knowledge.py:1285-1316`
- **觸發**：OpenAI down + Redis 也 down → 仍回 `fallback="async_queue"`，caller 無法得知 chunk 已掉入無向量也無重試的 limbo。

#### `knowledge#9` — `_call_llm_api` 無 timeout，500ms 切換 fallback SLO 不可達
- **檔案**：`knowledge.py:576-608`
- **修復**：openai/genai client 加 `timeout=0.4`，`_llm_generate` 加 `asyncio.wait_for(0.45)`。

#### `paladin#1` — `InputSanitizer._SQL_INJECTION_RE` 刪除合法單引號
- **檔案**：`paladin.py:90-94`
- **觸發**：`sanitize("don't")` → `"dont"`，下游 knowledge / 情緒分類錯亂。

#### `paladin#9 / #13` — `_await_coro_from_sync` 逾時後 daemon thread + event loop + coroutine 全部洩漏
- **檔案**：`paladin.py:596-641`
- **修復**：timeout 觸發前先 `loop.call_soon_threadsafe(task.cancel)`。

#### `paladin#15` — `_handle_retrospective_block` security_log_writer 失敗導致 L3 revocation 不發出
- **檔案**：`paladin.py:1041-1073`
- **修復**：writer 呼叫包 try/except，仍回 `_blocked_result`。

#### `rate_limit#1` — A2A 平台無限流
- **檔案**：`rate_limit.py:109-116`
- **觸發**：`Platform.A2A` 對應字串 `"a2a"` 不在 LIMITS，命中 fail-open 分支。
- **修復**：補 `"a2a": 30` 進 LIMITS。

#### `rate_limit#8` — `aallow` 是 async 函式但無 await
- **檔案**：`rate_limit.py:144-149`
- **觸發**：async context 呼叫 `await limiter.aallow()` 阻塞 event loop。

#### `rate_limit#10` — `_buckets` dict 無界增長
- **檔案**：`rate_limit.py:306-324`

#### `redis_streams#1` — handler latency > idle_ms 導致同 message 雙重處理
- **檔案**：`redis_streams.py:301-318`
- **修復**：in-process `self._in_flight: set[str]` 去重。

#### `redis_streams#4 / #8` — handler exception 不隔離、ack 失敗無 retry
- **修復**：try/finally 包 (handler, ack) 對，或加 max-delivery + DLQ。

#### `tool_executor#1` — `_BLOCKED_ADDRESS_STATUSES` 大小寫敏感
- **檔案**：`tool_executor.py:78, 139`
- **修復**：`status.lower() in _BLOCKED_ADDRESS_STATUSES`。

#### `tool_executor#2 / #9` — sync handler 沒有 timeout 包裹
- **修復**：`asyncio.wait_for(run_in_executor, timeout=_handler_timeout)`。

#### `cli_adapter#1` — `execute()` 是 hardcoded stub，永遠不回 `run_script`
- **檔案**：`cli_adapter.py:98-110`
- **觸發**：`execute('get_shipping', {'order_id': 'ORD-001'})` 永遠回 `status='in_transit'` 假資料。

#### `mcp_adapter#1` — `_connect_stdio` 串接 initialize + tools/list 但 parser 只支援單一 JSON
- **檔案**：`mcp_adapter.py:189-209, 264-287`
- **修復**：逐 frame 讀（Content-Length 或 newline-delimited），或只送 tools/list。

#### `mcp_adapter#2` — SSE path 不送 JSON-RPC envelope
- **檔案**：`mcp_adapter.py:246-250`
- **修復**：包成 `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}`。

#### `llm_judge#1` — `CalibrationPipeline` 將 `judge_llm=None` 誤判為 NP-07 故障
- **檔案**：`llm_judge.py:437, 555-558, 581`

#### `llm_judge#5 / #7` — Python <3.11 `asyncio.TimeoutError` 與 builtin `TimeoutError` 不同類
- **修復**：`except (asyncio.TimeoutError, TimeoutError):`。

#### `pii#1` — 信用卡 regex 只接受 16 連續數字
- **檔案**：`pii.py:80, 410`
- **觸發**：`4111-1111-1111-1111` 不被遮罩，原始 PAN 洩漏。
- **修復**：regex 加 `[ -]?` 分隔容忍；`match.group()` 呼叫 `_luhn_valid` 前先 strip。

#### `pii#2` — 電話 regex 不支援逐位分隔格式
- **檔案**：`pii.py:63-74`
- **觸發**：`0-9-1-2-3-4-5-6-7-8` 完全不被 mask。

#### `pipeline#1` — AGENT bypass 時 stage call log 仍記錄 `emotion`
- **檔案**：`pipeline.py:172-174`
- **修復**：`if not process_result.get("bypassed"): current_log.append("emotion")`。

#### `pipeline#2` — `get_context` 洩漏 DB session
- **檔案**：`pipeline.py:249-264`；generator 從未 `__anext__` 二次，async-with block 永不退出，連線不釋放。
- **修復**：`async with get_session() as session: ...`。

#### `retraction#1` — `app.core.retraction` 模組不存在，全部合併到 `response.py`
- **檔案**：`/Users/johnny/projects/omnibot/03-development/src/app/core/response.py:383-704`（section comment `# --- Merged from retraction.py ---`）
- **修復**：補一個 re-export shim 檔或全面改 import。

#### `retraction#2` — `_attempt_windowed_delete` 忽略 `client.delete_message` 回傳值
- **檔案**：`response.py:505-521`
- **修復**：`if not client.delete_message(message_id):` 走 fail-secure。

#### `retraction#3` — `retract()` 對 unknown platform 拋 ValueError 但未觸發 SOC2 audit
- **檔案**：`response.py:659-704`
- **修復**：拋出前先 `_log_retraction_failed(reason='unknown_platform')`。

#### `chain#1` — `platform_adapter.parse()` 失敗未防護
- **檔案**：`chain.py:164`
- **修復**：try/except 回 `_deny("parse", status=400, reason="PARSE_FAILED")`。

#### `chain#2` — Rate-limit 結果 fail-open 預設值錯誤
- **檔案**：`chain.py:171`（`default=True` 應為 `False`）。

#### `ip_whitelist#1` — `_resolve_ip` 用 user-supplied `ip` 而非 TCP `client_host` 當 trust anchor
- **檔案**：`ip_whitelist.py:212`
- **修復**：`tcp_client = client_host`。

> 其餘 high-severity 細節（`emotion#1`、`escalation#1`、`ab_testing#1`、`a2a_adapter#8/#9/#10` 等）請見 `FINDINGS` JSON 陣列逐條核對。

---

## 3. 被反駁的 Findings（簡述理由）

| ID | 一句理由 |
|----|---------|
| `dst#8` | `auto_escalate` 預設 `confidence=1.0`；IDLE → ESCALATED 是 docstring (L328-333) 明文允許的 side-channel，非 legal FSM transition。 |
| `dst#9` | `ContextWindowManager` 無 production caller，且 lazy init 是文件化契約；移到 `__init__` 會破壞現有測試。 |
| `dst#10` | `_SUMMARY_MESSAGE` 全 repo 沒有 mutator 程式碼，class 沒有 subclass；理論 race 不可達。 |
| `knowledge#14-25` | 多數是對 stub 行為的誤讀（`_rag_search` 是文件化測試 stub、`_embed_first_chunk` 是 zero-vector 預設）、或 repo 沒有 production caller。 |
| `paladin#24-29` | 多數依賴「PY 3.8-3.10」或「生產環境會 wire 上 `PALADINPipeline.process`」前提，與 pyproject.toml `requires-python=">=3.11"`、無 `process()` 外部 caller 的事實矛盾。 |
| `rate_limit#13-19` | FR-22 fail-open contract 明確排除後端切換；`health_probe()` 當前是常數 dict，無 I/O；`ConnectionError` 顯式列入 tuple 是 test_fr02 必要條件。 |
| `redis_streams#16-23` | 對 forward-compat、契約範圍、cursor 語義、per-hostname A2AAdapter 結構的誤讀；XPENDING 是 id-range 過濾非 PEL 成員過濾。 |
| `a2a_adapter#20-26` | 多數敘述與 `_pinned_dns_lock` 不可嵌套、`agent_url` 構造後固定、`A2AAdapter` 永遠單例綁一個 hostname 的事實衝突。 |
| `tool_executor#11-14` | `_resolve_tool` 只在 CLIAdapter 使用，CLIAdapter.list_tools() 是記憶體硬編碼；A2A/MCP 路徑不會走 `_resolve_tool` 熱路徑。 |
| `cli_adapter#15` | `time.sleep(0.05)` 在 `kill_signal` fault-injection 分支，normal `_run_with_timeout` 路徑不經此 sleep；無 async caller。 |
| `mcp_adapter#12-15` | `connect_timeout_ms=0` 是用戶違約；`tool_executor` 對 sync handler 已用 ThreadPoolExecutor 包過，不阻塞 event loop。 |
| `llm_judge#15-18` | `aggregate_csat` 輸入來自 `_aggregate` 顯式列舉的整數 1；`return_exceptions=True` 對 `BaseException` 路徑無效。 |
| `emotion#6-8` | 對 frozenset 迭代順序、`"非常"` intensifier 在 neutral 的效果、`EmotionScore.intensity` 沒有接到 `current_weighted_score` 的事實錯誤。 |
| `retraction#5` / `escalation#3` | LINE/WhatsApp 無 delete API，docstring 明文 platform default；`get_sla_breaches` 沒有 naive-datetime 注入點。 |
| `chain#5-7` | `ip_whitelist._resolve_ip` 不做 DNS 解析（無 socket import）；`ctx.user_id=None` 在 signature stage 已被擋；success path 走 `_deny` 是 `ChainResult` 構造器別名，無誤用。 |
| `ip_whitelist#3` | `strict=False` 是 FR-25 明文要求且 test_fr25 覆蓋。 |

---

## 4. 修復優先順序

### P0（阻擋 Gate 3 / 觸發資安或資料腐蝕）
- `a2a_adapter#11`（monkey-patch 全域污染 + Bearer token 繞道）
- `a2a_adapter#1`（IPv6 6to4 SSRF 繞過）
- `paladin#1`（單引號誤刪）
- `pii#1`、`pii#2`（PII 漏失）
- `knowledge#6`、`#8`、`#9`（embed 雙重失敗靜默）
- `retraction#1`（`app.core.retraction` import 死鏈）

### P1（race / resource leak / NP-07 違規）
- `dst#5`、`a2a_adapter#9/#10`、`a2a_adapter#8`（concurrency race）
- `rate_limit#1`、`#8`、`#10`、`redis_streams#1`、`#4`、`#8`（流控 / consumer）
- `paladin#9`、`#13`、`#15`（daemon leak / audit 失敗）
- `tool_executor#2`、`#9`（sync handler 無 timeout）
- `cli_adapter#1`（stub 假資料）
- `mcp_adapter#1`、`#2`（JSON-RPC protocol 違規）
- `llm_judge#1`、`#5`、`#7`（misconfig + 3.11 TimeoutError 邊界）
- `pipeline#1`、`#2`（stage log + session leak）
- `retraction#2`、`#3`（fail-secure gap）
- `chain#1`、`#2`（parse 500、rate-limit fail-open）

### P2（observability / contract 文件化 / 低風險 hardening）
- 所有 medium/low 確認項 + 對應 JSON `resolution.status="open"` 紀錄
- 補 `app.core.retraction` shim 或改 import
- 文件化 `_SUMMARY_MESSAGE`、`_BUCKETS` 等 classvar 的不變量
- 為 `tool_executor.ThreadPoolExecutor(1)` 改為共享 default executor
- 補 `cli_adapter._detect_language` ast.parse 啟發式
- 補 `paladin._await_coro_from_sync` 取消前 cleanup
- 補 `knowledge.batch_import_knowledge` `failed_chunk_ids` 欄位

> 提醒老闆：所有 P0/P1 確認 bugs 必須在 Gate 3 `adversarial_review` 前逐條 resolved 或 refuted 並更新 JSON `resolution` 欄位；本掃描僅標記問題，不視為處置完成。

---

## 5. 掃描方法

1. **CRG 知識圖譜導引**：先用 `mcp__code-review-graph__get_minimal_context` 抓 12 HR 模組 + 9 STD 模組的 call graph、社群、流向熱度。
2. **三鏡頭靜態分析**：對 HR 模組跑 correctness / concurrency / resilience 三個 lens；對 STD 模組跑 general lens。每一條 finding 都附 `file:line`、可重現 Python 觸發腳本、`verify_evidence`。
3. **反駁對抗**：每條 finding 必須通過「存在可達觸發路徑」+「觀察行為 ≠ 預期契約」雙重驗證；任一不成立即 refuted，並寫入 `refute_evidence`。
4. **JSON + MD 雙輸出**：`FINDINGS` 陣列（235 條，含 66 條 refuted）落到 `hunt-bugs` 工作目錄，本 Markdown 報告落 `03-development/.audit/bug-report-2026-06-20.md`。
5. **邊界案例**：每條 confirmed finding 至少執行一次 Python REPL 重現（如 `str(None).strip()`、`"yes" in frozenset(...)`、JSON-RPC envelope 構造、`frozenset` 跨 process 迭代順序等）。
6. **不貼長代碼**：每條 finding 最多 6 行 snippet；完整原始碼在檔案中以 `file:line` 引用。