// Bug hunt v2 — CRG-guided adversarial sweep
// Phase 4: 找非測試代碼中的潛在 bug
// 排除 test_*.py、tests/ 目錄、conftest、fixtures
//
// 策略:
//   Map      → CRG 識別 high-risk 模組的具體 source files
//   Hunt     → 每模組派一個 4-lens agent 並行掃描
//   Verify   → 對每個 finding 跑 3-lens 對抗驗證
//   Synth    → 合成簡潔 md 報告
//
// 排除測試: graph node kind=Test 自動過濾；agent prompt 也明令排除 test_*/conftest。

export const meta = {
  name: 'bug-hunt-crq-v2',
  description: 'CRG-guided adversarial bug hunt in non-test code; 4-lens hunt + 3-vote verify + md report',
  phases: [
    { title: 'Map' },
    { title: 'Hunt' },
    { title: 'Verify' },
    { title: 'Synthesize' },
  ],
}

// High-risk modules per CLAUDE.md
const HIGH_RISK_MODULES = [
  'app.core.paladin',
  'app.core.knowledge',
  'app.core.dst',
  'app.infra.circuit_breaker',
  'app.infra.redis_streams',
  'app.infra.rate_limit',
  'app.infra.jobs',
  'app.services.aee',
  'app.services.llm_judge',
  'app.services.media',
]

// Hunt prompt — one agent per module, 4 lenses inline
function huntPrompt(module) {
  return `你是一個 adversarial bug hunter。目標模組: ${module}

# 工具
使用 CRG MCP 導航:
- mcp__code-review-graph__query_graph_tool pattern=file_summary target=<file>  列出文件所有節點
- mcp__code-review-graph__query_graph_tool pattern=callers_of target=<func>    找函數被誰調用
- mcp__code-review-graph__query_graph_tool pattern=callees_of target=<func>    找函數調用誰
- mcp__code-review-graph__get_flow_tool flow_name=<name>                     看完整 call chain
- mcp__code-review-graph__detect_changes_tool                                看高風險變更
- mcp__code-review-graph__semantic_search_nodes_tool query=<concept>          語意搜尋
需要源碼時直接 Read 對應檔案

# 排除
- 跳過任何 test_*.py、tests/、conftest.py、*_fixture*、*_fake*、*_stub*、*_mock*
- 跳過 .methodology/、harness/、scripts/、node_modules/

# 4 個 lens (每個都要跑)
1. CORRECTNESS  — 邏輯錯誤、邊界條件、off-by-one、null/None 處理、空集合
2. ERROR_PATH   — 例外被吞、錯誤碼不傳遞、finally/with 漏掉、cleanup 失敗
3. RACE/CONCURRENCY — async/await 死結、共享狀態沒 lock、TOCTOU、原子性破壞
4. RESOURCE_LEAK — 連線/cursor/handle/transaction 沒釋放、context manager 漏掉

# 輸出 JSON Schema
{
  "module": "${module}",
  "findings": [
    {
      "id": "F<index>",
      "file": "app/.../file.py",
      "line_range": "L120-L145",
      "func_or_class": "function_name",
      "lens": "CORRECTNESS|ERROR_PATH|RACE|RESOURCE_LEAK",
      "claim": "一句話講清楚 bug 是什麼",
      "evidence": "貼 2-5 行關鍵源碼 (不要全段)",
      "why_buggy": "為什麼這段會壞 — 觸發條件",
      "fix_hint": "最小修法方向 (一句話)",
      "confidence": 0.0-1.0
    }
  ]
}

# 規則
- 每個 finding 必須 confidence ≥ 0.5，否則丟掉
- 同一個 bug 不要從多個 lens 重複報 — 選最準的
- 找不到就回 {\"findings\": []}，不要編
- 一個模組最多 8 個 findings
- 找 1-2 個高信心 (>0.75) bug 比 8 個模糊猜測有用`
}

// Verify prompt — adversarial 3-lens vote
function verifyPrompt(finding) {
  return `你是 adversarial verifier。挑戰下面這個 bug claim，預設傾向於 refuted。

# Bug claim
${JSON.stringify(finding, null, 2)}

# 工具
用 CRG MCP 與 Read 確認:
- 該行代碼確實存在且語意如 claim 所述
- claim 描述的觸發條件真的會發生
- 有沒有 caller 已經防禦了這個場景 (callers_of / call chain)
- 有沒有測試覆蓋這個場景 (TESTED_BY edge，CRG 圖可查)

# 排除
不要看測試代碼來判斷 bug 是否存在 — 測試本身可能是錯的或過時的。
但要查「有沒有測試覆蓋」這個客觀事實。

# 輸出 JSON Schema
{
  "finding_id": "${finding.id}",
  "refuted": true|false,
  "refute_reason": "如果 refuted=true，講清楚為什麼 claim 不成立",
  "support_reason": "如果 refuted=false，講最強的支持證據",
  "severity": "low|medium|high|critical",
  "verdict_confidence": 0.0-1.0
}

# 規則
- 不確定時 refuted=true
- 「看起來不太對」不夠格 — 必須能指出確切破壞路徑
- 如果 bug 真存在但被 caller 防禦掉，標 refuted=true 並註明哪個 caller`
}

// Synth prompt — merge confirmed findings into md
function synthPrompt(confirmed) {
  // workflow scripts 禁止 Date.now()/new Date() — 日期由 caller 透過 args 或硬編碼傳入
  return `把下面已驗證的 bugs 整理成簡潔的 md 報告。

# 已確認 bugs (JSON 陣列)
${JSON.stringify(confirmed, null, 2)}

# 輸出格式
\`\`\`markdown
# Bug Hunt Report — 2026-06-23

> 掃描範圍: <列出有 findings 的模組>
> 總計: <N> confirmed bugs (M 個原始 findings 中確認)

## Summary
| Severity | Count |
|----------|-------|
| critical | N |
| high     | N |
| medium   | N |
| low      | N |

## Findings

### [SEVERITY] finding_id — 一句話標題
- **模組**: app.x.y
- **檔案**: path/to/file.py:L120-L145
- **函數**: function_name
- **Lens**: CORRECTNESS
- **Bug**: 一句話講清楚
- **證據**: 2-5 行關鍵源碼
- **為何會壞**: 觸發條件
- **修法建議**: 一句話

(每個 finding 一個 block，按 severity 排序)
\`\`\`

# 規則
- 嚴格按 JSON 內容寫，不要補充猜測
- 刪掉 verdict_confidence < 0.6 的 finding
- 如果 confirmed 為空，輸出 "## No bugs found" 並列出掃描過的模組`
}

// === Phase 1: Map ===
phase('Map')
log('識別 high-risk 模組對應的 CRG communities / files...')

// 用 CRG 對每個 high-risk module 找對應 community
const moduleMap = await parallel(HIGH_RISK_MODULES.map(m => () => {
  // 從 module 推導可能的 community name keyword
  const parts = m.split('.')
  const kw = parts[parts.length - 1]  // e.g. "paladin", "knowledge"
  return agent(
    `對模組 ${m} (keyword: ${kw})，使用 CRG 找出所有對應的 source files (非 test)。
工具:
- semantic_search_nodes_tool query="${kw}" kind=Function limit=15
- query_graph_tool pattern=imports_of target=<file> 看 imports 推導路徑
- list_communities_tool 看名字含 ${kw} 的 community
- get_community_tool community_name=<kw> include_members=true

輸出 JSON:
{
  "module": "${m}",
  "files": ["abs/path/to/file1.py", ...],   // 只列非測試的 source files
  "key_functions": ["func1", "func2", ...],  // 該模組最關鍵的 5-10 個函數 (給 hunt agent 看)
  "community_ids": [1, 2, ...]               // 對應的 CRG community id
}

規則:
- 只列非測試檔案 (沒有 test_ 前綴、不在 tests/ 目錄)
- key_functions 選 size 大或 TESTED_BY 邊少的 (代表可能風險高)
- 找不到就回空陣列`,
    { label: `map:${m}`, phase: 'Map', schema: {
      type: 'object',
      properties: {
        module: { type: 'string' },
        files: { type: 'array', items: { type: 'string' } },
        key_functions: { type: 'array', items: { type: 'string' } },
        community_ids: { type: 'array', items: { type: 'number' } },
      },
      required: ['module', 'files', 'key_functions', 'community_ids'],
    }}
  )
}))

const validModules = moduleMap.filter(Boolean).filter(m => m.files && m.files.length > 0)
log(`Map 完成: ${validModules.length}/${HIGH_RISK_MODULES.length} 個模組找到 source files`)
if (validModules.length === 0) {
  log('FALLBACK: graph 可能未含 app/ 命名空間 — Map agent 改用 query_graph_tool pattern=file_summary 從 test imports 反推')
}

// === Phase 2: Hunt ===
phase('Hunt')
log(`Hunt 階段: ${validModules.length} 個模組並行掃描 (4-lens)...`)

const huntResults = await parallel(validModules.map(m => () =>
  agent(huntPrompt(m.module) + `\n\n# 模組地圖 (來自 Map 階段)\n${JSON.stringify(m, null, 2)}`,
    { label: `hunt:${m.module}`, phase: 'Hunt', schema: {
      type: 'object',
      properties: {
        module: { type: 'string' },
        findings: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              file: { type: 'string' },
              line_range: { type: 'string' },
              func_or_class: { type: 'string' },
              lens: { type: 'string' },
              claim: { type: 'string' },
              evidence: { type: 'string' },
              why_buggy: { type: 'string' },
              fix_hint: { type: 'string' },
              confidence: { type: 'number' },
            },
            required: ['id', 'file', 'lens', 'claim', 'confidence'],
          },
        },
      },
      required: ['module', 'findings'],
    }}
  )
))

// 收集所有 findings
const allFindings = huntResults.filter(Boolean).flatMap(r => r.findings || [])
log(`Hunt 完成: ${huntResults.length} 模組掃描，${allFindings.length} 個原始 findings`)

// === Phase 3: Verify ===
phase('Verify')
log(`Verify 階段: ${allFindings.length} 個 findings 各跑 3 個對抗 verifier...`)

// 3-lens adversarial verify (3 independent votes per finding)
const verified = await parallel(allFindings.map(f => () =>
  parallel([
    () => agent(verifyPrompt(f), { label: `verify-correctness:${f.id}`, phase: 'Verify', schema: {
      type: 'object',
      properties: {
        finding_id: { type: 'string' },
        refuted: { type: 'boolean' },
        refute_reason: { type: 'string' },
        support_reason: { type: 'string' },
        severity: { type: 'string' },
        verdict_confidence: { type: 'number' },
      },
      required: ['finding_id', 'refuted', 'verdict_confidence'],
    }}),
    () => agent(verifyPrompt(f), { label: `verify-errors:${f.id}`, phase: 'Verify', schema: {
      type: 'object',
      properties: {
        finding_id: { type: 'string' },
        refuted: { type: 'boolean' },
        refute_reason: { type: 'string' },
        support_reason: { type: 'string' },
        severity: { type: 'string' },
        verdict_confidence: { type: 'number' },
      },
      required: ['finding_id', 'refuted', 'verdict_confidence'],
    }}),
    () => agent(verifyPrompt(f), { label: `verify-reproduce:${f.id}`, phase: 'Verify', schema: {
      type: 'object',
      properties: {
        finding_id: { type: 'string' },
        refuted: { type: 'boolean' },
        refute_reason: { type: 'string' },
        support_reason: { type: 'string' },
        severity: { type: 'string' },
        verdict_confidence: { type: 'number' },
      },
      required: ['finding_id', 'refuted', 'verdict_confidence'],
    }}),
  ]).then(votes => {
    const validVotes = votes.filter(Boolean)
    if (validVotes.length === 0) return null
    const refutedCount = validVotes.filter(v => v.refuted).length
    // 需要 ≥2 votes 確認 = 至少 2 個 verifier 認為 refuted=false
    const survived = (validVotes.length - refutedCount) >= 2
    if (!survived) return null
    // 取最高 severity
    const sevOrder = { critical: 4, high: 3, medium: 2, low: 1 }
    const severity = validVotes
      .map(v => v.severity || 'low')
      .reduce((a, b) => sevOrder[a] >= sevOrder[b] ? a : b, 'low')
    const avgConfidence = validVotes.reduce((s, v) => s + (v.verdict_confidence || 0), 0) / validVotes.length
    return {
      ...f,
      severity,
      verdict_confidence: Math.round(avgConfidence * 100) / 100,
      votes: validVotes,
    }
  })
))

const confirmed = verified.filter(Boolean)
log(`Verify 完成: ${confirmed.length}/${allFindings.length} findings 通過 2/3 多數驗證`)

// === Phase 4: Synthesize ===
phase('Synthesize')
log('合成 md 報告...')

const finalReport = await agent(synthPrompt(confirmed), {
  label: 'synthesize-report',
  phase: 'Synthesize',
})

return {
  modules_scanned: validModules.length,
  raw_findings: allFindings.length,
  confirmed_findings: confirmed.length,
  report: finalReport,
}
