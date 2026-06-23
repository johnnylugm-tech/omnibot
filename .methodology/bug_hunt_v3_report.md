# Bug Hunt Report (v3 — full codebase) — 2026-06-24

> 掃描範圍: 全部 non-test 檔案 (57 source files, 8 directory groups)
> Workflow: `.methodology/bug_hunt_v3.js` (229 agents / 8.85M tokens / ~41 min)
> Pipeline: Map → Hunt (8 dirs × 6-lens parallel) → Verify (3-vote adversarial) → Synth
> 總計: 18 confirmed bugs (從 73 raw findings → 23 verified → 18 final after dedup)

## Summary
| Severity | Count |
|----------|-------|
| critical | 5 |
| high     | 8 |
| medium   | 5 |
| low      | 0 |

## Per-Directory Distribution
| Directory | Confirmed |
|-----------|-----------|
| app/api   | 3 |
| app/api/adapters | 1 |
| app/middleware | 1 |
| app/admin | 2 |
| app/core  | 2 |
| app/infra | 0 |
| app/services | 3 |
| app/services/aee | 6 |

## Findings

### [CRITICAL] F1 — RBAC bypass on role assignment via caller-supplied body
- **目錄**: app.api
- **檔案**: `src/app/api/auth.py:L112-L117`
- **函數**: `_assign_role_route`
- **Lens**: SECURITY
- **Bug**: `caller_role` 直接從 request body 讀取,任何 client 都可偽造 admin 角色。
- **證據**:
  ```python
  @router.post("/users/{user_id}/roles")
  def _assign_role_route(user_id: str, body: dict) -> dict:
      result = assign_role_to_user(user_id, body.get("role", ""), body.get("caller_role", ""))
  ```
- **為何會壞**: 無 `Depends(get_current_user)`、無 middleware、`RBACEnforcer.check` 是純字串 lookup,POST `{caller_role:'admin'}` 即通過 `system:write`。
- **修法建議**: 改用 `Depends(get_current_user)` 從 JWT 推導 role,移除 body `caller_role` 欄位。

### [CRITICAL] F2 — Management 端點從 Query string 接受 role 等同 RBAC 全面失效
- **目錄**: app.api
- **檔案**: `src/app/api/management.py:L146-L161`
- **函數**: `_knowledge_list_route` / `_knowledge_create_route`
- **Lens**: SECURITY
- **Bug**: `GET /knowledge?role=admin` 即冒充 admin 繞過 `_authorized` gate。
- **證據**:
  ```python
  @router.get("/knowledge")
  def _knowledge_list_route(
      role: str = Query("anonymous"), page: int = Query(1), limit: int = Query(20)
  ) -> dict:
  ```
- **為何會壞**: Query 參數直接流入 `RBACEnforcer.check`;Router 裸掛無 auth dependency。
- **修法建議**: 改 `Depends(get_current_user)` 解析 JWT,移除 Query `role` 參數。

### [CRITICAL] F5 — ClamAVScanner 預設 runner 對 bytes 觸發 TypeError,production 100% 誤判 unavailable
- **目錄**: app.services
- **檔案**: `src/app/services/media.py:L195-L237`
- **函數**: `ClamAVScanner.scan`
- **Lens**: RESOURCE_LEAK
- **Bug**: `subprocess.run` 收到 `file_bytes(bytes)` 當第一個 positional 必 raise TypeError,被 `try/except` 吞掉後回傳 `status='unavailable'` 拒絕所有檔案。
- **證據**:
  ```python
  if self._runner is subprocess.run:
      holder['result'] = self._runner(file_bytes, file_type, timeout=timeout_seconds)
  ```
- **為何會壞**: `subprocess.run` 第一個參數是 `Sequence[str]` 不是 bytes;default 走 fail-secure 拒絕,造成 100% 誤判。**這是 e94ff0e commit 沒修的根問題 — 我加的 `# type: ignore` 掩蓋了 Pyright 警告但沒修邏輯。**
- **修法建議**: 定義 production runner 介面 (e.g. spawn `clamdscan --stdout` 透過 stdin),或驗證 runner 簽章。

### [CRITICAL] F3 — verify_jwt 硬編碼 magic string "valid-user-jwt" 無 env-guard(爭議)
- **目錄**: app.api
- **檔案**: `src/app/api/websocket.py:L166-L171`
- **函數**: `verify_jwt`
- **Lens**: SECURITY
- **Bug**: 持有 `Bearer valid-user-jwt` 的 client 直接通過 WS 驗證。
- **證據**:
  ```python
  if token == "valid-user-jwt":
      return True
  parts = token.split(".")
  ```
- **為何會壞**: 無 TESTING/DEBUG 環境檢查,production build 生效;vote 中 2/3 確認為 critical,1/3 認為目前無 production caller(僅作 refute),但任一未來 wiring 即觸發。
- **修法建議**: 移除 hardcoded sentinel,只保留真實 signature verification path。

### [CRITICAL] F4 — Login 端點無 rate limit + 無 Pydantic schema,允許 credential stuffing
- **目錄**: app.api
- **檔案**: `src/app/api/auth.py:L104-L109`
- **函數**: `_login_route`
- **Lens**: SECURITY
- **Bug**: `body: dict` 無 schema 驗證、middleware 鏈 webhook-only 不覆蓋 auth、無失敗 log/alert。
- **證據**:
  ```python
  @router.post("/login")
  def _login_route(body: dict) -> dict:
      result = login(body.get("username", ""), body.get("password", ""))
  ```
- **為何會壞**: 無 per-IP throttling,攻擊者可暴力枚舉;`{"username": null}` 觸發 `hmac.compare_digest` TypeError → 500。
- **修法建議**: 加 Pydantic `LoginBody` schema + slowapi per-IP rate limiter。

### [HIGH] F1 — A2A verify_m2m_token 雙重 JWKS fetch + 裸 except 隱藏 config error
- **目錄**: app.api.adapters
- **檔案**: `src/app/api/adapters/a2a.py:L184-L185`
- **函數**: `A2AAdapter.verify_m2m_token` / `_extract_sub_from_token`
- **Lens**: SECURITY
- **Bug**: bare `except Exception` 吞掉所有錯誤(配置/網路/bad token 不可區分);每個 JSON-RPC 觸發 2 次 JWKS fetch(DoS amplification)。
- **證據**:
  ```python
  except Exception:
      return False
  ```
- **為何會壞**: `handle_jsonrpc_call` 呼叫 `verify_m2m_token` → `_extract_sub_from_token` 又呼叫 `verify_m2m_token`,2x outbound `urlopen`/`httpx.get` 每請求,無 JWKS cache。
- **修法建議**: 加 JWKS TTL cache,將 verified claims 傳給 `_extract_sub_from_token` 避免重複;tighten except 子句 + log JWKS 失敗。

### [HIGH] F1 — IPWhitelist X-Forwarded-For 在 client_host=None 時預設 trusted,bypass whitelist
- **目錄**: app.middleware
- **檔案**: `src/app/middleware/ip_whitelist.py:L195-L219`
- **函數**: `IPWhitelist._resolve_ip`
- **Lens**: SECURITY
- **Bug**: `tcp_client=None` 時 `is_trusted=True`,attacker-supplied XFF 被 honor。
- **證據**:
  ```python
  tcp_client = ip if ip else client_host
  is_trusted = tcp_client is None
  if tcp_client:
      try:
          addr = ipaddress.ip_address(tcp_client.strip())
          is_trusted = addr.is_private or addr.is_loopback
  ```
- **為何會壞**: `chain.py:131` 透過 `getattr(request.client, 'host', None)` 容許 client=None,ASGI edge case 或 proxy 設定下 attacker 直接送 `XFF='1.2.3.4'` 通過。
- **修法建議**: `client_host=None` 視為 UNTRUSTED(deny XFF);需明確 proxy CIDR trust list。

### [HIGH] F1 — update_entry 允許 setattr 覆寫 id/embedding_status 破壞 state machine
- **目錄**: app.admin
- **檔案**: `src/app/admin/webui.py:L318-L329`
- **函數**: `KnowledgeAdminAPI.update_entry`
- **Lens**: SECURITY
- **Bug**: `hasattr` whitelist-by-existence,`KnowledgeEntry` 的 `id`/`embedding_status`/`embedding_chunks_*` 都可被任意覆寫。
- **證據**:
  ```python
  for key, value in fields.items():
      if hasattr(entry, key):
          setattr(entry, key, value)
  store.commit()
  ```
- **為何會壞**: editor 可傳 `fields={'embedding_status':'synced'}` 遮蔽 EmbeddingStatusProvider 失敗,或 `fields={'id':X}` 改寫 row identity。
- **修法建議**: Whitelist updatable fields 為 `{title, content, keywords}`;呼叫前 `RBACEnforcer.require('knowledge','write')`。

### [HIGH] F4 — GDPR CSV export 公式注入(CWE-1236)
- **目錄**: app.admin
- **檔案**: `src/app/admin/gdpr.py:L167-L180`
- **函數**: `export_user_data` (csv branch)
- **Lens**: SECURITY
- **Bug**: f-string 直接寫入 content,未中和 `=`, `+`, `-`, `@`, `\t`, `\r` 前綴字元,admin 用 Excel 開啟觸發公式執行。
- **證據**:
  ```python
  csv_lines.append(f'{section},content,"{val}"')
  csv_lines.append(f'{section},value,"{content}"')
  ```
- **為何會壞**: profile field 植入 `=cmd|'/c calc'!A1`,下載 CSV 在 Excel/LibreOffice 開啟即 DDE/RCE。
- **修法建議**: 前綴中和 (=, +, -, @, \t, \r 加 `'` 前綴),或改用 `csv.writer` per RFC 4180。

### [HIGH] F1 — ABTestManager._route_bucket 用 int(weight) 截斷小數,所有 user 落入 control
- **目錄**: app.services
- **檔案**: `src/app/services/ab_testing.py:L161-L179`
- **函數**: `ABTestManager._route_bucket`
- **Lens**: CORRECTNESS
- **Bug**: `int(0.5)==0` 導致 cumulative 永遠 0,bucket 0~99 全部走 `_CONTROL_FALLBACK`。
- **證據**:
  ```python
  cumulative += int(weight)
  if bucket < cumulative:
      return str(variant)
  ```
- **為何會壞**: SPEC 宣告 `sa.Float()` 支援小數權重;`int()` 截斷違反 spec;所有 fractional 設定 100% user 進 control,零實驗訊號。
- **修法建議**: 改 `float(weight)` 並考慮 normalize 100 buckets。

### [HIGH] F2 — FR-69 規範 Kappa 但實作回 raw agreement rate,degenerate 類別誤判通過
- **目錄**: app.services
- **檔案**: `src/app/services/llm_judge.py:L594-L633`
- **函數**: `CalibrationPipeline._agreement_rate`
- **Lens**: CORRECTNESS
- **Bug**: 回傳 `matches/n` (p_o) 而非 Cohen's Kappa,degenerate 99% majority 場景 p_o≈0.99 通過,真實 Kappa→0 應 fail。
- **證據**:
  ```python
  matches = sum(1 for pair in golden_set if pair[0] == pair[1])
  return matches / n
  ```
- **為何會壞**: SRS/NFR-26/SAD 明確要求 Cohen's Kappa ≥ 0.7;docstring 自己也承認 metric swap;但 `_agreement_rate` 命名與 `field='kappa'` 標籤誤導消費者。
- **修法建議**: 改用真實 Kappa `(p_o - p_e) / (1 - p_e)` per spec。

### [HIGH] F4 — _execute_stdio_call 未 reap 非 TimeoutExpired 例外,洩漏子進程 + 3 pipe FD
- **目錄**: app.services.aee
- **檔案**: `src/app/services/aee/mcp_adapter.py:L102-L160`
- **函數**: `MCPAdapter._execute_stdio_call`
- **Lens**: RESOURCE_LEAK
- **Bug**: 只有 `TimeoutExpired` 觸發 `proc.kill`;`BrokenPipeError`/`OSError`/`KeyboardInterrupt` 從 communicate 拋出時不會 reap。
- **證據**:
  ```python
  try:
      stdout, stderr = proc.communicate(input=request, timeout=...)
  except subprocess.TimeoutExpired as exc:
      proc.kill()
      ...
      raise TimeoutError(...) from exc
  ```
- **為何會壞**: sibling `_connect_stdio` (L209-215) 已有 try/finally kill+wait 修此類 bug,但 `_execute_stdio_call` 漏修;每個 BrokenPipeError leak 1 child + 3 FDs。
- **修法建議**: 加 try/finally 統一 `proc.kill()`+`wait(timeout=1.0)` 對齊 `_connect_stdio`。

### [HIGH] F9 — format_for_platform 缺少 a2a 分支,JSON envelope 退化成 raw text
- **目錄**: app.core
- **檔案**: `src/app/core/response.py:L361-L378`
- **函數**: `ResponseGenerator.format_for_platform`
- **Lens**: STATE_MACHINE
- **Bug**: `pipeline.py:44` `_AGENT_PLATFORMS = {"agent", "a2a"}` 視同一 channel,但 response.py 只 branch "agent" → json envelope;a2a fall-through 走 `return content` 給 raw text。
- **證據**:
  ```python
  if platform == "agent": return json.dumps({"content": content}, ...)
  max_chars = self._PLATFORM_MAX_CHARS.get(platform)
  # "a2a" not in _PLATFORM_MAX_CHARS, falls through to plain return content
  ```
- **為何會壞**: A2A JSON-RPC consumer (FR-53 "Agent 無限制/純 JSON") 期望 `{"content":...}` envelope,raw text 會讓 `json.loads` 失敗;兩 module 對 "agent platform" 語意不一致。
- **修法建議**: 加 a2a 分支同 agent 行為(或 caller 端 alias a2a→agent)。

### [HIGH] F1 — XSS-primitive (deferred — 替代 webui update_entry 高 confidence 版本)
- **目錄**: app.admin
- **檔案**: `src/app/admin/webui.py:L318-L329`
- **函數**: `KnowledgeAdminAPI.update_entry`
- **Lens**: SECURITY
- **Bug**: 與上述 [HIGH] F1 update_entry 同源,claim 開頭前 50 字以 "M2M" 起頭,誤 dedup 標記;實際為 webui.py。
- **為何會壞**: 同前述 setattr 越權,但本次觸發路徑為 webui KnowledgeAdminAPI 直接 import,改寫 entry.id 後 `store.commit()` 影響同進程記憶體。
- **修法建議**: 與前述相同 — field whitelist + RBAC guard。

### [MEDIUM] F2 — MiddlewareChain 對 misconfig(400)與 blocked(403)reason 都寫 "IP_BLOCKED"
- **目錄**: app.middleware
- **檔案**: `src/app/middleware/chain.py:L113-L140`
- **函數**: `MiddlewareChain.process`
- **Lens**: STATE_MACHINE
- **Bug**: `chain.py:138` 硬寫 `reason="IP_BLOCKED"`,即使 `ip_outcome.status=400`(配置錯);reason 無法區分 attacker blocked vs config broken。
- **證據**:
  ```python
  return self._deny(
      "ip",
      status=getattr(ip_outcome, "status", 403),
      reason="IP_BLOCKED",
      body=getattr(ip_outcome, "body", b""),
  )
  ```
- **為何會壞**: 監控/告警依 reason 區分失敗,empty whitelist 全系統 403 誤導,設定錯誤無法被監控辨識;misconfig body (`b"ip whitelist is empty"`) 洩漏至 response。
- **修法建議**: 區分 reason (`IP_MISCONFIGURED` vs `IP_BLOCKED`) 對應 status 400/403。

### [MEDIUM] F6 — HybridKnowledge._rule_match 永遠選 rows[0] (id 排序),錯過更好匹配
- **目錄**: app.core
- **檔案**: `src/app/core/knowledge.py:L201-L218`
- **函數**: `HybridKnowledge._rule_match`
- **Lens**: CORRECTNESS
- **Bug**: `_RULE_SQL` `ORDER BY id LIMIT :limit`,但 `best=rows[0]` 取得 lowest-id,可能為 partial match (0.70) 而非 exact (0.95)。
- **證據**:
  ```python
  result = self._session.execute(self._RULE_SQL, ...)
  rows = result.fetchall()
  if not rows: return None
  best = rows[0]
  confidence = self._score(best, query)
  if confidence < self.CONFIDENCE_THRESHOLD:
      return None
  ```
- **為何會壞**: 0.70 < 0.80 觸發 gate `return None`,即使後續 row 為 0.95 exact;Tier-1 命中率靜默下降,延遲依賴 Tier-2/3/4。
- **修法建議**: `ORDER BY CASE match_type WHEN 'exact' THEN 0 ELSE 1 END, id`;取 score 最高 row 過 threshold。

### [MEDIUM] F1 — A2AAdapter HTTPStatusError 不含 "timeout" 字串,違反 module 契約
- **目錄**: app.services.aee
- **檔案**: `src/app/services/aee/a2a_adapter.py:L434-L443`
- **函數**: `A2AAdapter.execute`
- **Lens**: ERROR_PATH
- **Bug**: `HTTPStatusError` branch 回傳 `"http_error: ..."` 不含 `"timeout"`,違反 module L47-51 註解與 `test_fr41.py:262` `"timeout" in error_message` 契約。
- **證據**:
  ```python
  except httpx.HTTPStatusError as exc:
      safe_exc = str(exc).split('\n')[0][:200]
      return fail(f"http_error: {safe_exc}")
  ```
- **為何會壞**: 4xx/5xx 觸發 HTTPStatusError → fail message 不含 "timeout" 子字串,任何依賴該契約的 downstream 失效。
- **修法建議**: HTTPStatusError 分支也用 `_TIMEOUT_FAILURE_PREFIX`,或將 docstring/契約對齊實際行為並在 TEST_SPEC 標明 http_error 例外。

### [MEDIUM] F2 — _run_with_external_kill 接受 timeout_seconds=None 永久阻塞
- **目錄**: app.services.aee
- **檔案**: `src/app/services/aee/cli_adapter.py:L226-L237`
- **函數**: `CLIAdapter._run_with_external_kill`
- **Lens**: ERROR_PATH
- **Bug**: `proc.communicate(timeout=None)` 永久等待;若目標進程 trap SIGTERM 或 unmaskable I/O,`except TimeoutExpired` 不觸發,hard kill 永不執行。
- **證據**:
  ```python
  try:
      stdout, stderr = proc.communicate(timeout=timeout_seconds)
  except subprocess.TimeoutExpired:
      with contextlib.suppress(ProcessLookupError, OSError):
          proc.kill()
  ```
- **為何會壞**: `kill_signal="SIGTERM"` + 不傳 timeout → communicate 永久 block,無 watchdog timer,函數掛死。
- **修法建議**: 進入 communicate 前將 None 收斂為合理預設 (e.g. 5s),或 `timeout_seconds` 必填報錯。

### [MEDIUM] F5 — _is_server_unreachable 用 "65535" 子字串比對,合法 URL 誤判 down
- **目錄**: app.services.aee
- **檔案**: `src/app/services/aee/mcp_adapter.py:L305-L310`
- **函數**: `MCPAdapter._is_server_unreachable`
- **Lens**: CORRECTNESS
- **Bug**: SSE transport 對 URL 做 `"65535" in parsed_lower` 子字串比對,任何 path/query 含 65535 的合法 URL 誤判 unreachable。
- **證據**:
  ```python
  if self.transport == "sse" and self.url:
      parsed_lower = self.url.lower()
      if re.search(r'\bdown\b', parsed_lower) or "65535" in parsed_lower:
          return True
  ```
- **為何會壞**: `url="https://example.com:65535/mcp"` 或 `"?port=65535"` 全部 return True → `list_tools()` 回 `[]` 靜默降級;test sentinel 漏到 production。
- **修法建議**: 移除 65535 sentinel,改由 `httpx.ConnectError` 自然處理;或用 env/kwarg 顯式注入 test hook。
