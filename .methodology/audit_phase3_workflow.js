// Audit Phase 3 — vs Phase 2 baseline
// 動態 workflow:完整性 / 正確性 / 一致性 三維審計
// Baseline: 02-architecture/ (SAD.md, ADR.md, TEST_SPEC.md) + .methodology/SAB.json + quality_manifest.json
// 對象:    03-development/src/app/, 03-development/tests/, k8s/
// 輸出:    agent return value 為 MD report 字串(由 caller 用 Write 工具落盤)
//
// 結構 (6 phases):
//   Inventory     → 平行抓 P2 + P3 + prior audits state
//   Completeness  → FR 覆蓋、test pyramid、NFR pattern (2 agents)
//   Correctness   → 架構約束、orchestrator + API layer (2 agents)
//   Consistency   → SAD↔SAB↔code、ADR↔impl、TESTSPEC↔tests (2 agents)
//   Verify        → 對抗驗證 top 6 findings (refute lens)
//   Synthesize    → 彙整簡潔 MD report
//
// 設計原則:
//   - 6 audit agents 並行 (2 per dimension)
//   - 每 audit agent 限 8 findings (聚焦,不灌水)
//   - Verify 對 top 6 FATAL/HIGH 做 refute
//   - 不重複列 ORPHANED minor (gap_report.json 已收錄 484 個)
//   - date 由 caller 透過 args.date 傳入 (scripts 不能 new Date())

export const meta = {
  name: 'audit-phase3-vs-phase2',
  description: 'Dynamic workflow: audit Phase 3 outputs (completeness/correctness/consistency) vs Phase 2 baseline (SAD/ADR/TEST_SPEC/SAB)',
  phases: [
    { title: 'Inventory' },
    { title: 'Completeness' },
    { title: 'Correctness' },
    { title: 'Consistency' },
    { title: 'Verify' },
    { title: 'Synthesize' },
  ],
}

// ---------- 共享 schema ----------

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string', enum: ['completeness', 'correctness', 'consistency'] },
    severity: { type: 'string', enum: ['FATAL', 'HIGH', 'MEDIUM', 'MINOR'] },
    id: { type: 'string' },                   // 例 C-01, R-02, S-03
    title: { type: 'string' },
    p2_reference: { type: 'string' },          // SAD/ADR/TEST_SPEC/SAB 引用
    evidence: { type: 'string' },              // grep/wc/find 結果
    impact: { type: 'string' },
    recommendation: { type: 'string' },
    related_prior_finding: { type: 'string' }, // 例 "phase3_audit_report F-01"
  },
  required: ['dimension', 'severity', 'id', 'title', 'evidence', 'impact', 'recommendation'],
}

const AUDIT_SCHEMA = {
  type: 'object',
  properties: {
    scope: { type: 'string' },
    findings: { type: 'array', items: FINDING_SCHEMA },
  },
  required: ['scope', 'findings'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    finding_id: { type: 'string' },
    survives_refute: { type: 'boolean' },
    refute_reason: { type: 'string' },
    severity_adjust: { type: 'string', enum: ['raise', 'lower', 'keep'] },
    confidence: { type: 'number' },
  },
  required: ['finding_id', 'survives_refute', 'confidence'],
}

// ---------- Phase 1: Inventory (4 agents 並行) ----------

const inventory = await parallel([
  () => agent(
    `抓取 Phase 2 baseline 全部產出物摘要。

工具:
- Read 02-architecture/SAD.md (讀 §2-§5,modules 列表、architecture_constraints)
- Read 02-architecture/adr/ADR.md (每個 ADR 編號 + title)
- Read 02-architecture/TEST_SPEC.md (前 80 行 + 統計 FR test case 數量)
- Read .methodology/SAB.json (layers、architecture_constraints、fr_module_traceability)
- Read .methodology/quality_manifest.json (FR registry 大小)
- wc -l 每個 P2 檔

回報:每個檔案存在與否、LOC、FR 總數、constraint 數量、layer 數量、ADR 數量。missing=true 若不存在。`,
    { phase: 'Inventory', label: 'P2-baseline' }
  ),
  () => agent(
    `抓取 Phase 3 程式碼 layout 摘要。

工具:
- find 03-development/src -name "*.py" | wc -l
- find 03-development/src -name "*.py" -exec wc -l {} +
- 對 app/api, app/admin, app/core, app/infra, app/middleware, app/services 各列 top-level .py 檔 + LOC
- 確認 03-development/src/app/api/main.py、03-development/src/app/core/pipeline.py、03-development/tests/strategy.py 是否存在
- 確認 high-risk modules 齊全: app.core.paladin, app.core.knowledge, app.core.dst, app.infra.circuit_breaker, app.infra.redis_streams, app.infra.rate_limit, app.infra.jobs, app.services.aee, app.services.llm_judge, app.services.media

回報:每個 module path + LOC + exists。`,
    { phase: 'Inventory', label: 'P3-src' }
  ),
  () => agent(
    `抓取 Phase 3 tests layout 摘要。

工具:
- find 03-development/tests -name "test_fr*.py" | wc -l
- 列 03-development/tests/ 子目錄: unit/、integration/、e2e/、load/、conftest.py、golden_dataset.py、pyramid.py、strategy.py
- 每個子目錄 LOC 和檔案數
- 統計 placeholder assertion:grep -E "assert [0-9.]+ == [0-9.]+" 03-development/tests/test_fr*.py | wc -l
- Read 03-development/tests/conftest.py 摘要

回報:每個子目錄狀態、test_frXX.py 總數、placeholder assertion 數。`,
    { phase: 'Inventory', label: 'P3-tests' }
  ),
  () => agent(
    `抓取既有 audit 與 gate 結果摘要。

工具:
- Read .methodology/phase3_audit_report.md (前 100 行 + findings 數量表)
- Read .methodology/phase3_audit_reverify.md (前 100 行 + 各 finding 修復狀態)
- Read .methodology/gate2_result.json (composite + 各 dim)
- Read .methodology/gate3_result.json (composite)
- Read .methodology/gap_report.json summary
- ls .methodology/phase3_audit*.md

回報:每個舊 audit verdict + finding 數量 + 已知未修復清單 (audit_reverify 的 ❌ 段落)。`,
    { phase: 'Inventory', label: 'audit-history' }
  ),
])

// ---------- Phase 2: Completeness (2 agents 並行) ----------

const completeness = await parallel([
  () => agent(
    `你是 completeness auditor。目標:驗證 108 個 FR 是否都有 module + test + spec 對應。

工具:
- python3 解析 .methodology/SAB.json fr_module_traceability
- python3 解析 .methodology/quality_manifest.json fr_registry
- find 03-development/src/app -name "*.py"
- 比對:每個 FR → SAB module path → 實際檔案 → test_frXX.py
- find 03-development/tests/strategy.py、tests/integration/*、tests/unit/*、tests/e2e/*

限制:
- 最多 8 findings (FATAL 優先)
- 不要列每個 FR 缺失 (那是 gap_report.json 工作)
- 已知:108 FRs、tests/strategy.py 不存在、tests/{unit,integration,e2e}/ 全空、test_fr107.py 有 placeholder

Schema: AUDIT_SCHEMA
dimension: "completeness"
id 格式: "C-NN"
related_prior_finding: "phase3_audit_report F-03" 等

Read + Bash + Grep 收集 evidence,直接貼命令輸出。`,
    { phase: 'Completeness', schema: AUDIT_SCHEMA, label: 'FR-coverage' }
  ),
  () => agent(
    `你是 NFR / test-pyramid completeness auditor。

工具:
- Read 02-architecture/TEST_SPEC.md (找 NFR pattern activation 表、Step 1b 強制 patterns)
- ls 03-development/tests/{unit,integration,e2e}
- 統計 test_fr*.py 分層 (用檔頭註解或檔名判斷)
- find 03-development/k8s -name "*.yaml"
- NFR-32 (test pyramid)、NFR-01 (perf)、NFR-09 (TPS) 對應測試
- Read 03-development/tests/pyramid.py (validate_pyramid + UNIT_MODULE_MAP)
- find 03-development -name "k6_*.js" load tests

限制:
- 最多 8 findings
- 聚焦:NFR pattern 是否 force tag、test pyramid 是否真分層、perf/load 是否實作

Schema: AUDIT_SCHEMA
dimension: "completeness"
id 格式: "C-NN"`,
    { phase: 'Completeness', schema: AUDIT_SCHEMA, label: 'NFR-pyramid' }
  ),
])

// ---------- Phase 3: Correctness (2 agents 並行) ----------

const correctness = await parallel([
  () => agent(
    `你是 architecture constraints correctness auditor。

約束清單 (SAB.architecture_constraints):
1. no_circular_dependencies
   - python3 import graph scan
2. api_layer_no_business_logic
   - grep -n "def " 03-development/src/app/api/ 看非路由函式
3. infra_layer_no_domain_imports
   - grep -rn "from app.core\\|from app.services\\|from app.admin" 03-development/src/app/infra/
4. paladin_executes_before_pii
5. knowledge_query_after_dst_slot_resolution
   - Read 03-development/src/app/core/pipeline.py handle_message 順序

對每個約束:
- PASS / FAIL / UNVERIFIABLE
- grep/cat 證據
- 評估影響

限制:
- 最多 8 findings
- 已知:F-04 (infra→admin) 已修、F-01 (orchestrator) 表層修但可能 semantic gap

Schema: AUDIT_SCHEMA
dimension: "correctness"
id 格式: "R-NN" (R = rightness)`,
    { phase: 'Correctness', schema: AUDIT_SCHEMA, label: 'arch-constraints' }
  ),
  () => agent(
    `你是 orchestrator + API layer correctness auditor。

工具:
- Read 03-development/src/app/core/pipeline.py handle_message (PALADIN/PII/DST/Knowledge/Emotion/Response 順序)
- Read 03-development/src/app/api/main.py (routers + middleware)
- grep "MiddlewareChain" 03-development/src/app/api/main.py
- Read 03-development/src/app/middleware/chain.py (FR-24 order)
- grep "app = FastAPI" 03-development/src/app/api/ (命名衝突)
- Read 03-development/src/app/api/webhooks.py agent_card sub-app
- pytest 03-development/tests/test_fr86.py test_fr86_login_returns_jwt_and_refresh (前次 audit FR-86 回歸)
- pytest 03-development/tests/test_fr105.py test_fr105_cost (前次 audit FR-105 回歸)

每 sub-system 評估:
- 真實 wire-up (不是 stub)
- hardcoded value (source=RULE, confidence=1.0 是否還在)
- API 缺失 (auth/management/websocket 是否串接)
- 測試回歸狀態

限制:
- 最多 8 findings
- 聚焦 semantic gaps,不重複架構約束

Schema: AUDIT_SCHEMA
dimension: "correctness"
id 格式: "R-NN"`,
    { phase: 'Correctness', schema: AUDIT_SCHEMA, label: 'orch-API' }
  ),
])

// ---------- Phase 4: Consistency (2 agents 並行) ----------

const consistency = await parallel([
  () => agent(
    `你是文件一致性 auditor:SAD ↔ SAB ↔ 實際程式碼 三方對齊。

工具:
- diff <(grep -oE "app\\.[a-z.]+" 02-architecture/SAD.md | sort -u) <(python3 -c "import json; print('\\n'.join(sorted(sum([[m['name'] for m in l['modules']] for l in json.load(open('.methodology/SAB.json'))['layers']], []))))")
- python3 -c "import json,os; sab=json.load(open('.methodology/SAB.json')); print([(fr, m) for fr, m in sab['fr_module_traceability'].items() if not os.path.exists('03-development/src/' + m.replace('.', '/') + '.py') and not m.endswith('/')])"
- grep "FR-44" 02-architecture/SAD.md .methodology/SAB.json 03-development/src/app/api/
- 檢查 ADR-009 (aee split)、ADR-010 (前次 audit 報 H-05 NOT FIXED)
- grep "agent_card.py" 03-development/src/app/api/adapters/*.py (前次 audit 6 個 broken cross-refs)

限制:
- 最多 8 findings
- 聚焦 module 路徑漂移、FR mapping 不一致、broken cross-refs

Schema: AUDIT_SCHEMA
dimension: "consistency"
id 格式: "S-NN"`,
    { phase: 'Consistency', schema: AUDIT_SCHEMA, label: 'SAD-SAB-code' }
  ),
  () => agent(
    `你是文件一致性 auditor:ADR ↔ TEST_SPEC ↔ 實際測試。

工具:
- 列 02-architecture/adr/ADR.md 所有 ADR (grep "^## ADR-\\|ADR-00X")
- 每 ADR 找對應 implementation (例 ADR-002 FastAPI → app/api/)
- 每 TEST_SPEC.md test case 找對應 test_frXX.py
- ADR decision 但 implementation 不存在
- ADR 寫了但 pyproject.toml 沒裝的依賴
- TEST_SPEC fixture/conftest 是否真存在

限制:
- 最多 8 findings
- 聚焦 ADR decision 與實際程式落差、TEST_SPEC test case 與 test_fr*.py 對應

Schema: AUDIT_SCHEMA
dimension: "consistency"
id 格式: "S-NN"`,
    { phase: 'Consistency', schema: AUDIT_SCHEMA, label: 'ADR-TESTSPEC-tests' }
  ),
])

// ---------- Phase 5: Verify (對抗 top findings) ----------

const allFindings = [
  ...completeness.filter(Boolean).flatMap(r => r?.findings || []),
  ...correctness.filter(Boolean).flatMap(r => r?.findings || []),
  ...consistency.filter(Boolean).flatMap(r => r?.findings || []),
]

const SEVERITY_RANK = { FATAL: 4, HIGH: 3, MEDIUM: 2, MINOR: 1 }
const topFindings = allFindings
  .sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0))
  .slice(0, 6)

const verified = await parallel(
  topFindings.map(f => () => agent(
    `你是對抗驗證者。對以下 finding 用 refute lens 嘗試推翻:

finding_id: ${f.id}
title: ${f.title}
severity: ${f.severity}
evidence: ${f.evidence}
impact: ${f.impact}
recommendation: ${f.recommendation}

工具:
- Read/Bash/Grep 直接驗證 evidence 命令輸出
- 找 counter-example:false positive?正當理由?
- 「正解 vs workaround」:有意的設計選擇而非 bug?
- 嚴重度被誇大?

回報 (JSON):
- finding_id
- survives_refute: true / false
- refute_reason: 一句話
- severity_adjust: raise / lower / keep
- confidence: 0.0-1.0

規則:
- 預設 refute=true (審計傾向挑戰)
- evidence 是 grep 直接命中且無反例 → survive
- 不要編造反例`,
    { phase: 'Verify', schema: VERIFY_SCHEMA, label: `verify-${f.id}` }
  ))
)

// ---------- Phase 6: Synthesize (彙整簡潔 MD report) ----------

const verifiedMap = Object.fromEntries(
  verified.filter(Boolean).map(v => [v.finding_id, v])
)

const finalFindings = allFindings.map(f => {
  const v = verifiedMap[f.id]
  if (!v) return { ...f, verified_survives: null, severity_final: f.severity }
  return {
    ...f,
    verified_survives: v.survives_refute,
    verified_confidence: v.confidence,
    severity_final:
      !v.survives_refute ? 'MINOR' :
      v.severity_adjust === 'raise' ? 'FATAL' :
      v.severity_adjust === 'lower' ? 'MINOR' :
      f.severity,
  }
})

const reportMd = await agent(
`你是 audit report writer。把 findings 彙整成簡潔 MD 報告。

# 輸入
日期: ${args.date || 'today'}
verified findings:
${JSON.stringify(finalFindings, null, 2)}
inventory summaries:
${JSON.stringify(inventory, null, 2)}

# 報告格式 (目標 ≤ 300 行 MD)

\`\`\`markdown
# Phase 3 Audit Report (vs Phase 2 Baseline)

> Date: ${args.date || 'today'}
> Method: Dynamic workflow — Inventory → Completeness/Correctness/Consistency → Verify → Synthesize
> Baseline: 02-architecture/ (SAD.md, ADR.md, TEST_SPEC.md) + .methodology/SAB.json
> Subject: 03-development/src/app/ + 03-development/tests/

## 0. Executive Summary (3-5 行)
| Dimension | Fatal | High | Medium | Minor | Survives Verify |
|-----------|-------|------|--------|-------|-----------------|
| Completeness | ... | ... | ... | ... | ... |
| Correctness  | ... | ... | ... | ... | ... |
| Consistency  | ... | ... | ... | ... | ... |
| **Total**    | ... | ... | ... | ... | ... |

**Prior audit comparison**: 對比 .methodology/phase3_audit_report.md (5F/5H/6M/5L) 與 .methodology/phase3_audit_reverify.md,本次新增/修復/殘留分別 N 個。

**Gate Status**: Gate 2 PASS @ 89.5 · Gate 3 PASS @ 100.0 · Gate 4 待驗證

## 1. Findings (按 severity 排序,verified_survives=true)
### FATAL
#### F-NN: <title>
- **Dimension**: ...
- **P2 Reference**: ...
- **Evidence**: \`\`\`<paste>\`\`\`
- **Impact**: ...
- **Recommendation**: ...

### HIGH (top 8)
...

### MEDIUM (top 5,其他列總數)
...

## 2. P2 Baseline Reconciliation
- P2 規格 P3 完全沒實作
- P3 實作 P2 沒規格 (orphaned)

## 3. Prior Audit Regression Check
對照 phase3_audit_report F-01~F-05 / H-01~H-05:
- ✅ Fixed / ⚠️ Workaround / ❌ Still broken / 🆕 New

## 4. Recommendations (前 5 優先)

## 5. Self-Review
- 信心等級
- 限制
- 未驗證假設
- 可能錯誤

## 6. Verification Commands
\`\`\`bash
# 重現審計的命令
\`\`\`
\`\`\`

# 規則
- 簡潔:每 finding ≤ 10 行
- verified_survives=false → 降為 MINOR 或從報告移除
- prior audit 對照必填
- 引用用 file:line
- 整份報告 ≤ 300 行`,
{ phase: 'Synthesize', label: 'write-report' })

return {
  inventory,
  completeness,
  correctness,
  consistency,
  verified,
  reportMd,
  stats: {
    totalFindings: allFindings.length,
    topVerified: verified.filter(Boolean).filter(v => v.survives_refute).length,
    topRefuted: verified.filter(Boolean).filter(v => !v.survives_refute).length,
  },
}