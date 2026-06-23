// Bug hunt v3 — Full-codebase CRG-guided adversarial sweep
// Phase 4: 找非測試代碼中所有潛在的 bug
// 排除 test_*.py、tests/、conftest、fixtures
//
// v2 只掃 CLAUDE.md 列的 10 個 high-risk module (22% 檔案覆蓋率);
// v3 改為 8 個 directory-based group 並行,覆蓋全部 58 個 source files。
//
// 策略:
//   Map      → CRG 列全部 non-test 檔案,按 directory 分 8 組
//   Hunt     → 8 個 directory agent 並行掃描,每組 4-lens
//   Verify   → 每 finding 跑 3 票對抗驗證
//   Synth    → 合併所有 confirmed findings 成 md 報告
//
// 排除測試: agent prompt 明令排除 test_*/tests/conftest/fixture/fake/stub/mock。

export const meta = {
  name: 'bug-hunt-full-codebase-v3',
  description: 'CRG-guided adversarial bug hunt across ALL non-test code; 8 directory groups × 4-lens + 3-vote verify + md report',
  phases: [
    { title: 'Map' },
    { title: 'Hunt' },
    { title: 'Verify' },
    { title: 'Synthesize' },
  ],
}

// 8 個 directory groups — 全部 source code 都被分配到一個 group。
// 排序按風險 / 已知問題密度 (high-risk module 集中地先掃)。
const DIRECTORY_GROUPS = [
  { name: 'app/api',                      risk: 'high',   reason: 'HTTP 入口、auth、SSRF 表面' },
  { name: 'app/api/adapters',             risk: 'high',   reason: 'webhook / adapter 注入點' },
  { name: 'app/middleware',               risk: 'high',   reason: 'chain / ipwhitelist 守門邏輯' },
  { name: 'app/admin',                    risk: 'medium', reason: 'admin-only 但仍為攻擊面' },
  { name: 'app/core',                     risk: 'high',   reason: 'paladin/knowledge/dst 已知高密度 bug' },
  { name: 'app/infra',                    risk: 'high',   reason: 'jobs/rate_limit/redis_streams 已知高密度' },
  { name: 'app/services',                 risk: 'high',   reason: 'aee/llm_judge/media 已知高密度' },
  { name: 'app/services/aee',             risk: 'high',   reason: 'a2a/mcp/tool_executor 子模組' },
]

// Hunt prompt — 4-lens, 排除 test
function huntPrompt(group) {
  return `你是 adversarial bug hunter。目標目錄: ${group.name} (risk=${group.risk}, 原因: ${group.reason})

# 工具
使用 CRG MCP 導航:
- mcp__code-review-graph__semantic_search_nodes_tool query=<concept> kind=Function limit=15
- mcp__code-review-graph__query_graph_tool pattern=file_summary target=<file>   列出文件所有節點
- mcp__code-review-graph__query_graph_tool pattern=callers_of target=<func>     找函數被誰調用
- mcp__code-review-graph__query_graph_tool pattern=callees_of target=<func>     找函數調用誰
- mcp__code-review-graph__get_flow_tool flow_name=<name>                        看完整 call chain
- mcp__code-review-graph__list_communities_tool                                看哪些 community 在此目錄
- mcp__code-review-graph__get_community_tool community_name=<kw>                拿 community 細節
需要源碼時直接 Read 對應檔案

# 排除
- 跳過任何 test_*.py、tests/、conftest.py、*_fixture*、*_fake*、*_stub*、*_mock*
- 跳過 .methodology/、harness/、scripts/、node_modules/

# 範圍
此目錄下「所有 .py source files」(非 test)。用 CRG 列舉:
1. semantic_search_nodes_tool query="${group.name.split('/').pop()}" kind=Function
2. file_summary pattern 拿每個檔案節點
3. Read 每個檔案理解業務邏輯

# 4 個 lens (每個都要跑)
1. CORRECTNESS    — 邏輯錯誤、邊界條件、off-by-one、null/None 處理、空集合
2. ERROR_PATH      — 例外被吞、錯誤碼不傳遞、finally/with 漏掉、cleanup 失敗
3. RACE/CONCURRENCY — async/await 死結、共享狀態沒 lock、TOCTOU、原子性破壞
4. RESOURCE_LEAK  — 連線/cursor/handle/transaction 沒釋放、context manager 漏掉
   SECURITY       — SSRF、auth bypass、injection、敏感資料洩漏 (額外重點)
   STATE_MACHINE   — 狀態轉換錯誤、precedence bug、boundary 處理

# 輸出 JSON Schema
{
  "directory": "${group.name}",
  "files_scanned": ["abs/path/to/file1.py", ...],   // 實際看過的 source files
  "findings": [
    {
      "id": "F<index>",
      "file": "<abs path>",
      "line_range": "L120-L145",
      "func_or_class": "<name>",
      "lens": "CORRECTNESS|ERROR_PATH|RACE|RESOURCE_LEAK|SECURITY|STATE_MACHINE",
      "claim": "一句話講清楚 bug 是什麼",
      "evidence": "貼 2-5 行關鍵源碼 (不要全段)",
      "why_buggy": "為什麼這段會壞 — 觸發條件",
      "fix_hint": "最小修法方向 (一句話)",
      "confidence": 0.0-1.0
    }
  ]
}

# 規則
- 每個 finding 必須 confidence ≥ 0.5,否則丟掉
- 同一個 bug 不要從多個 lens 重複報 — 選最準的
- 找不到就回 {"findings": [],"files_scanned": [...]},不要編
- 一個目錄最多 12 個 findings (v2 是 8;全 codebase 提高上限)
- 找 1-2 個高信心 (>0.75) bug 比 10 個模糊猜測有用
- files_scanned 必須列出此目錄下「所有」你實際看過的 source files
- 對目錄下「每個檔案」至少要 Read 一次,不能跳過 (這是 breadth 掃描)`
}

// Verify prompt — 3 票 adversarial vote
function verifyPrompt(finding) {
  return `你是 adversarial verifier。挑戰下面這個 bug claim,預設傾向於 refuted。

# Bug claim
${JSON.stringify(finding, null, 2)}

# 工具
用 CRG MCP 與 Read 確認:
- 該行代碼確實存在且語意如 claim 所述
- claim 描述的觸發條件真的會發生
- 有沒有 caller 已經防禦了這個場景 (callers_of / call chain)
- 有沒有測試覆蓋這個場景 (TESTED_BY edge,CRG 圖可查)

# 排除
不要看測試代碼來判斷 bug 是否存在 — 測試本身可能是錯的或過時的。
但要查「有沒有測試覆蓋」這個客觀事實。

# 輸出 JSON Schema
{
  "finding_id": "${finding.id}",
  "refuted": true|false,
  "refute_reason": "如果 refuted=true,講清楚為什麼 claim 不成立",
  "support_reason": "如果 refuted=false,講最強的支持證據",
  "severity": "low|medium|high|critical",
  "verdict_confidence": 0.0-1.0
}

# 規則
- 不確定時 refuted=true
- 「看起來不太對」不夠格 — 必須能指出確切破壞路徑
- 如果 bug 真存在但被 caller 防禦掉,標 refuted=true 並註明哪個 caller`
}

// Synth prompt — 合併所有 confirmed findings 成 md
function synthPrompt(confirmed) {
  return `把下面已驗證的 bugs 整理成簡潔的 md 報告。

# 已確認 bugs (JSON 陣列)
${JSON.stringify(confirmed, null, 2)}

# 輸出格式
\`\`\`markdown
# Bug Hunt Report (v3 — full codebase) — 2026-06-23

> 掃描範圍: 全部 non-test 檔案 (58 source files, 8 directory groups)
> 總計: <N> confirmed bugs (M 個原始 findings 中確認)

## Summary
| Severity | Count |
|----------|-------|
| critical | N |
| high     | N |
| medium   | N |
| low      | N |

## Per-Directory Distribution
| Directory | Confirmed |
|-----------|-----------|
| app/api   | N |
| app/api/adapters | N |
| app/middleware | N |
| app/admin | N |
| app/core  | N |
| app/infra | N |
| app/services | N |
| app/services/aee | N |

## Findings

### [SEVERITY] finding_id — 一句話標題
- **目錄**: app.x.y
- **檔案**: path/to/file.py:L120-L145
- **函數**: function_name
- **Lens**: CORRECTNESS
- **Bug**: 一句話講清楚
- **證據**: 2-5 行關鍵源碼
- **為何會壞**: 觸發條件
- **修法建議**: 一句話

(每個 finding 一個 block,按 severity 排序)
\`\`\`

# 規則
- 嚴格按 JSON 內容寫,不要補充猜測
- 刪掉 verdict_confidence < 0.6 的 finding
- 如果 confirmed 為空,輸出 "## No bugs found" 並列出掃描過的 8 個 directory
- 同一個 bug 跨多個目錄被報 → dedup by (file, func, claim 開頭 50 chars)`
}

// === Phase 1: Map ===
phase('Map')
log('列全部 non-test 檔案,按 directory 分 8 組...')

const mapResult = await agent(
  `用 CRG 列舉這個 codebase 的「所有 non-test Python source files」,按以下 8 個目錄分組:

${DIRECTORY_GROUPS.map(g => `- ${g.name}`).join('\n')}

工具:
- list_graph_stats_tool — 看總檔案數 (251) 與 non-test 數
- list_communities_tool detail_level=minimal — 拿到所有 community 名稱,推導對應的目錄
- query_graph_tool pattern=file_summary target=app/<path> — 拿每個目錄下的檔案清單
- semantic_search_nodes_tool kind=Function — 用關鍵字掃每個目錄的 function
- 直接 Read src/app/<dir>/*.py 看實際結構

輸出 JSON:
{
  "total_source_files": <int>,
  "groups": [
    {
      "directory": "app/api",
      "files": ["abs/path/to/file1.py", ...],   // 絕對路徑
      "file_count": <int>
    },
    ...
  ]
}

規則:
- 嚴格只列 non-test 檔案 (沒有 test_ 前綴、不在 tests/ 目錄)
- 8 個目錄都要列出,即使 file_count = 0
- 找不到目錄 → 從 CRG community name 推導 (例: "api-token" community → app/api/auth.py 之類)
- 不要編,找不到就空陣列`,
  { label: 'map:full-codebase', phase: 'Map', schema: {
    type: 'object',
    properties: {
      total_source_files: { type: 'number' },
      groups: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            directory: { type: 'string' },
            files: { type: 'array', items: { type: 'string' } },
            file_count: { type: 'number' },
          },
          required: ['directory', 'files', 'file_count'],
        },
      },
    },
    required: ['total_source_files', 'groups'],
  }}
)

const validGroups = (mapResult?.groups || []).filter(g => g.files && g.files.length > 0)
log(`Map 完成: ${validGroups.length}/${DIRECTORY_GROUPS.length} 個目錄有 source files (共 ${mapResult?.total_source_files || 0} 個檔案)`)

// Merge DIRECTORY_GROUPS metadata (risk / reason) with the file list
// returned by the Map agent — the map result only carries
// (directory, files, file_count), but huntPrompt also needs the
// risk / reason from the static DIRECTORY_GROUPS config.
const huntGroups = DIRECTORY_GROUPS
  .map(g => {
    const matched = validGroups.find(x => x.directory === g.name)
    return {
      name: g.name,
      risk: g.risk,
      reason: g.reason,
      files: matched?.files || [],
    }
  })
  .filter(g => g.files.length > 0)

// === Phase 2: Hunt ===
phase('Hunt')
log(`Hunt 階段: ${huntGroups.length} 個目錄並行掃描 (4-lens + 2 bonus)...`)

const huntResults = await parallel(huntGroups.map(g => () =>
  agent(huntPrompt(g),
    { label: `hunt:${g.directory}`, phase: 'Hunt', schema: {
      type: 'object',
      properties: {
        directory: { type: 'string' },
        files_scanned: { type: 'array', items: { type: 'string' } },
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
      required: ['directory', 'findings'],
    }}
  )
))

const allFindings = huntResults.filter(Boolean).flatMap(r => r.findings || [])
log(`Hunt 完成: ${huntResults.length} 目錄掃描,${allFindings.length} 個原始 findings`)

// === Phase 3: Verify ===
phase('Verify')
log(`Verify 階段: ${allFindings.length} 個 findings 各跑 3 個對抗 verifier...`)

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
    const survived = (validVotes.length - refutedCount) >= 2
    if (!survived) return null
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
  total_source_files: mapResult?.total_source_files || 0,
  directories_scanned: huntGroups.length,
  raw_findings: allFindings.length,
  confirmed_findings: confirmed.length,
  per_directory: huntGroups.map(g => ({
    directory: g.name,
    file_count: g.files.length,
    confirmed: confirmed.filter(c => c.file && c.file.includes(g.name)).length,
  })),
  report: finalReport,
}
