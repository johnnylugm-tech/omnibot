# Phase 3 產出物審計報告 (vs Phase 2 基準)

> **Author**: Hermes (sequential-thinking MCP driven)
> **Date**: 2026-06-22
> **Scope**: Phase 3 deliverables (03-development/) audited against Phase 2 baseline (02-architecture/SAD.md, adr/ADR.md, TEST_SPEC.md, .methodology/SAB.json)
> **Method**: Cross-reference each Phase 2 binding contract → verify Phase 3 implementation existence, correctness, and consistency
> **Dimensions**: Completeness (完整性) · Correctness (正確性) · Consistency (一致性)

---

## 0. Executive Summary

| Dimension | Verdict | Fatal | High | Medium | Minor |
|-----------|---------|-------|------|--------|-------|
| **Completeness** | ❌ FAIL | 3 | 2 | 2 | 1 |
| **Correctness** | ❌ FAIL | 2 | 1 | 1 | 2 |
| **Consistency** | ⚠️ WARN | 0 | 2 | 3 | 2 |
| **Total** | — | **5** | **5** | **6** | **5** |

**Gate 2 verdict (P3 退場)**: PASS @ 89.544/75 — 但審計發現 **Gate 2 通過不等於 P3 真正完整**。多個 fatal findings 直接挑戰 gate 評分依據 (mutation_testing=70 是 proxy 未實際跑 mutmut、integration_coverage=60 是 file-count proxy 非實際 coverage ratio)。

**核心問題 (one-liner)**: Phase 3 實作了 *模組* 但 **沒有實作「系統」**。108 個 FR 各模組獨立存在,但缺少把它們串成可執行應用的 orchestration layer (`app/core/pipeline.py` 是 stub,`app/api/main.py` 完全不存在)。無 main entry point = 無法 uvicorn 啟動 = P3 退場時的 application binary 不存在。

---

## 1. Scope & Inputs

### Phase 2 Baseline (審計基準)
| Artifact | Path | Role |
|----------|------|------|
| SAD | `02-architecture/SAD.md` | 架構契約 (5 layers, FR→module mapping, data flow) |
| ADR | `02-architecture/adr/ADR.md` | 9 個設計決策 (架構、FastAPI、PG、Knowledge cascade、PALADIN、SAQ、Redis Streams、tiktoken、SHA-256) |
| TEST_SPEC | `02-architecture/TEST_SPEC.md` | 108 FR 命名 test cases,15 個 NFR pattern,Step 1b 強制 pattern |
| SAB | `.methodology/SAB.json` | 機器可讀架構 baseline (binding contract) |
| Quality Manifest | `.methodology/quality_manifest.json` | FR registry + SAB data |

### Phase 3 Deliverables (審計對象)
- `03-development/src/app/` — 17,082 LOC across 50+ files
- `03-development/tests/` — 108 test_fr*.py files (324 test functions)
- `03-development/src/app/middleware/` — 未在 SAD 規劃的額外目錄
- Gate 2 result: composite=89.544, 10 dims evaluated
- Gate 3 result: composite=100.0, 16 dims evaluated

---

## 2. Findings by Severity

### 🔴 FATAL (5)

#### F-01: `app/core/pipeline.py` 缺少真正的 orchestration logic
**Dimension**: Correctness, Completeness
**SAD Reference**: §2.3 "Module: pipeline.py (Hub) — `handle_message(msg: UnifiedMessage) → UnifiedResponse` — orchestrates FR-10→FR-53 pipeline"
**SAB Reference**: layers.core.modules 含 `app.core.pipeline`,hub role
**Evidence**:
```
$ wc -l 03-development/src/app/core/pipeline.py
     108 03-development/src/app/core/pipeline.py
$ grep -n "PALADIN\|dst.transition\|knowledge.query\|response.generate\|handle_message" pipeline.py
(empty — only FR-49 emotion bypass logic exists)
```
**Impact**:
- 整個請求處理鏈 PALADIN→PII→DST→Knowledge→Emotion→Response **無從執行**
- 任何 integration test 都無法驗證 E2E flow
- NFR-01 (pipeline p95<1000ms) 無法實測
- 兩個 architecture_constraints (`paladin_executes_before_pii`, `knowledge_query_after_dst_slot_resolution`) **無從驗證**

**修復方向**: pipeline.py 需擴充為完整 orchestrator,呼叫 `paladin.process()` → `pii.mask()` → `dst.transition()` → `knowledge.query()` → `emotion.analyze()` → `response.generate()`,順序強制執行 architecture_constraints。

---

#### F-02: `app/api/main.py` FastAPI entry point 完全不存在
**Dimension**: Completeness, Correctness
**SAD Reference**: §2.1 "Entry point (`app/api/main.py`) 位於 api/ directory,呼叫 api/common.py hub" + §2.2 attribute table
**SAB Reference**: layers.api.modules 含 `app.api.main`
**Evidence**:
```
$ find 03-development -name "main.py" -path "*/app/*"
(empty)
$ grep -rn "^app = FastAPI" 03-development/src/
03-development/src/app/api/webhooks.py:487:app = FastAPI(title="OmniBot Agent Card", version="0.1.0")
(only Agent Card sub-app, NOT the root OmniBot app)
$ pyproject.toml [project.scripts]
(empty — no console_scripts entry)
```
**Impact**:
- 無法 `uvicorn app.main:app` 啟動系統
- ADR-002 "FastAPI as the Web Framework" 決策 **無法落實**
- Phase 4 testing / Phase 5 baseline / Phase 6 release **沒有 application binary 可打包**
- P3 退場時聲稱 "所有 FR 實作完成" 但 application 本身無法運行

**修復方向**: 建立 `03-development/src/app/api/main.py`,組裝所有 routers (webhooks + auth + management + websocket + agent_card),透過 MiddlewareChain 套用 FR-24 攔截鏈,註冊 /api/v1/health endpoint。

---

#### F-03: `tests.strategy` 模組完全缺失 (FR-107, FR-108 無對應 module)
**Dimension**: Completeness
**SAB Reference**: `fr_module_traceability.FR-107 = "tests.strategy"`, `FR-108 = "tests.strategy"`
**Evidence**:
```
$ find 03-development -name "strategy.py" -type f
(empty)
$ ls 03-development/tests/
  conftest.py  e2e/  golden_dataset.py  integration/  load/
  pyramid.py  test_fr*.py (108 files)  unit/
(NO strategy.py)
$ python3 -c "import tests.strategy"
ModuleNotFoundError: No module named 'tests.strategy'
```
**Impact**:
- SAB binding contract 違約 (fr_module_traceability 指向不存在的模組)
- FR-107 (Test Strategy) 與 FR-108 (Test Execution Pipeline) **沒有正式 module**,僅靠 `test_fr107.py` (內含 `assert 0.70 == 0.70` placeholder) 與 `pyramid.py` 部分實作
- `test_fr108.py` 完全沒有對應實作 module
- Gate 1 per-FR sentinel 對 FR-107/108 的 `tests.strategy` 路徑檢查會失敗

**修復方向**: 建立 `03-development/tests/strategy.py`,封裝 NFR-32 pyramid ratio validator + golden dataset runner + FR-108 e2e pipeline orchestrator。

---

#### F-04: Architecture constraint "infra_layer_no_domain_imports" 違反
**Dimension**: Correctness (architecture constraint compliance)
**SAD Reference**: §2.1 "no_circular_dependencies" + §2.5 Layer 4 「Dependencies: External only」(SAB 寫 `allowed_dependencies: []`)
**SAB Reference**: `architecture_constraints: ["infra_layer_no_domain_imports", ...]`
**Evidence**:
```
$ grep -rn "from app.core\|from app.services\|from app.admin" 03-development/src/app/infra/
03-development/src/app/infra/security.py:350:    from app.admin.gdpr import delete_user_data as _gdpr_delete
```
**Impact**:
- Infra layer (Layer 4) 反向依賴 Admin layer (Layer 5) — 違反 SAD §2.1 單向依賴設計
- 觸發潛在 circular dependency (雖然目前 import graph 無 cycle,但若 admin.gdpr 反向引入 infra.security 會立即 deadlock)
- SAB `gate_score_overrides` 假設 architecture_constraints 100% 成立,此違規應觸發 gate 扣分但 Gate 2 仍 PASS

**修復方向**: `infra/security.py` 的 GDPR deletion helper 應改透過 (a) 直接呼叫 `app.infra.database` SQL 操作,或 (b) 從 admin 模組把 deletion 邏輯下沉到 infra (admin 變 thin wrapper),或 (c) 引入 mediator pattern 反轉依賴。

---

#### F-05: Pipeline orchestration 順序約束無從驗證 + 額外架構約束違反
**Dimension**: Correctness (constraints unenforced)
**SAD Reference**: §2.3 "Sequence: PALADIN → PII → DST → Knowledge → Emotion → Response" + §2.1 constraints `paladin_executes_before_pii`, `knowledge_query_after_dst_slot_resolution`
**Evidence**:
```
$ grep -n "PALADIN\|sequence\|order\|step" 03-development/src/app/core/pipeline.py
(empty)
$ python3 -c "import re,os; ... # circular dep scan"
Cycles found: 0
(but pipeline.py is 108-line stub, so trivially acyclic)
```
**Impact**:
- `paladin_executes_before_pii` 約束沒有任何程式碼強制
- `knowledge_query_after_dst_slot_resolution` 同上
- F-01 是根因:沒有 orchestrator → 沒有 sequence → 沒有 constraint enforcement
- 即使寫成順序代碼,如果沒有 integration test 驗證順序,仍可能在 refactor 中漂移

**修復方向**: F-01 修復後,在 `Pipeline.handle_message()` 加入 sequence assertion (asserts + dev-mode runtime check),並加入 integration test 驗證執行順序。

---

### 🟠 HIGH (5)

#### H-01: Pipeline `get_context()` 反向依賴 admin (同 F-04 性質,獨立 finding)
**Dimension**: Correctness, Consistency
**Evidence**:
```python
# 03-development/src/app/core/pipeline.py:92
def get_context(conversation_id: str) -> dict:
    """[HUB] Retrieve conversation context.
    Required by SAD.md for core cohesion.
    """
    from app.admin.gdpr import _MESSAGES  # ← core imports admin!
    return {"conversation_id": conversation_id, "history": _MESSAGES.get(conversation_id, [])}
```
**Impact**: Core (Layer 2) 不應依賴 Admin (Layer 5)。`_MESSAGES` 是 GDPR 模組內部 mock 狀態變數,production 應從 `app.infra.database` query conversation history。

---

#### H-02: SAD ↔ SAB FR-44 mapping 不一致
**Dimension**: Consistency
**Evidence**:
- SAD §2.1 §2.2 寫 `app/api/agent_card.py` 獨立模組 (Hub-caller pattern)
- SAB.json `fr_module_traceability.FR-44 = "app.api.webhooks"`
- 實作:webhooks.py:488 有 `@app.get("/.well-known/agent.json")` 實作 endpoint
**Impact**:
- 兩份 binding contract 不一致 → 後續 tooling (drift detector / constitution check) 可能誤判
- 雖然功能存在 (endpoint 實作),但架構設計意圖 (獨立模組 vs 合併模組) 不一致
- 文件與程式碼解讀歧義

**修復方向**: 兩個選擇 — (a) 把 agent_card endpoint 拆出到獨立 `app/api/agent_card.py` 並更新 SAB,或 (b) 把 SAD §2.1 §2.2 的 agent_card.py 行刪除,接受合併架構。

---

#### H-03: `app/admin/portal.py` 未列入 SAB / SAD 模組清單
**Dimension**: Completeness, Consistency
**Evidence**:
```
$ wc -l 03-development/src/app/admin/portal.py
     166 03-development/src/app/admin/portal.py
$ grep "portal" .methodology/SAB.json
(empty)
$ grep "portal" 02-architecture/SAD.md
(only one mention in §2.6 webui.py reference, not as separate module)
```
**Impact**:
- 166 LOC 的 FR-104 Agent Portal 模組,既不在 SAB.layers.admin.modules,也不在 SAD §2.6 §2.1 模組清單
- Architecture drift:實際多了 1 個 module,但 baseline 文件沒記錄
- traceability gap:PORTAL → FR-104 對應,但無文件化契約

**修復方向**: 把 `app.admin.portal` 加入 SAB layers.admin.modules 並補 SAD §2.6 一行。

---

#### H-04: Tests 子目錄結構 vs SAD 不一致 (unit/integration/e2e 全空)
**Dimension**: Consistency, Completeness
**SAD Reference**: §2.1 `tests/{unit,integration,e2e,load}/` 四個子目錄
**Evidence**:
```
$ ls 03-development/tests/
  conftest.py  e2e/  golden_dataset.py  integration/  load/  pyramid.py
  test_fr*.py (108 files in ROOT)  unit/
$ ls 03-development/tests/integration/ /unit/ /e2e/
(empty)
```
**Impact**:
- 所有 108 個 test_fr*.py 散落在 `tests/` 根目錄,沒有 pyramid 分層
- NFR-32 (unit≥70%/integration≥20%/e2e≥10%) **無法實測驗證**
- Gate 2 integration_coverage=60 的 tool evidence 是 "108 files across integration tests" — 但實際 integration/ 是空的,純粹是 file count proxy 非實際 ratio
- FR-107 test_pyramid validator (`tests/pyramid.py`) 用 hardcoded `assert 0.70 == 0.70`,**非實際比例測量**

**修復方向**: 把現有 test files 按 TEST_SPEC.md 分類標記 (unit/integration/e2e),搬移到對應子目錄,或更新 SAD §2.1 接受扁平結構 + 更新 NFR-32 measurement logic。

---

#### H-05: AEE 模組拆分: SAD 寫 single file,實作為 package,與 SAB trailing slash 標記
**Dimension**: Consistency
**Evidence**:
- SAD §2.1 寫 `app/services/aee.py` (單檔)
- SAB.json `layers.services.modules` 含 `app.services.aee/` (trailing slash = package)
- 實作:`app/services/aee/` package with 5 submodules + `__init__.py` (1416 LOC total)
**Impact**:
- 設計意圖變更 (single → split),但只有 SAB 更新,SAD 沒同步
- 雖然功能存在且更組織化,但文件化契約分裂
- ADR-001 寫 "5-layer vertical split" 但沒記錄 module-level 的 split 決策

**修復方向**: 更新 SAD §2.1 §2.4 反映 AEE package 結構,或寫 ADR-010 記錄這次拆分決策。

---

### 🟡 MEDIUM (6)

#### M-01: `tests/pyramid.py` `UNIT_MODULE_MAP["InputSanitizer"] = "app.core.chunking"` 錯誤
**Evidence**: `app.core.chunking` 模組不存在;InputSanitizer 實作在 `app.core.paladin` (FR-10)
**Impact**: pyramid validator 啟動時 import 失敗,fall back 行為不明

#### M-02: `test_fr107.py` 多個 placeholder assertion (`assert 0.70 == 0.70`)
**Impact**: test 雖然有 assertion (test_assertion_quality = 100),但語意是 placeholder,不是實際驗證 NFR-32 ratio

#### M-03: Mutation testing score = 70 純 proxy 估算,mutmut 未實際執行
**Evidence**: gate2_result.json `tool_evidence: "mutmut not run (proxy); 2515 asserts across 509 tests, 8 zero-assert = high assertion density; mutation survival estimated ≥70% from assertion density"`
**Impact**: 70 分是從 assert count 推估,非實際 mutation kill rate。mutmut cache (`.mutmut-cache.unified_message.full`) 存在但未跑;是否 100% mutation kill 無從驗證

#### M-04: `app/middleware/` 目錄不在 SAD 規劃內
**Evidence**: `app/middleware/{chain.py, ip_whitelist.py}` (413 LOC) 在 SAD §2.1 §2.2 完全沒有此目錄
**Impact**: 雖然是 plan-only evolution (middleware 邏輯本來規劃在 api/common.py 或 webhooks.py),但沒文件化

#### M-05: `app/core/unified_message.py` 位置與 SAD §2.2 不一致
**Evidence**: SAD §2.2 把 `UnifiedMessage` 列在 `app/api/common.py`;實作拆出獨立 `app/core/unified_message.py` (84 LOC)
**Impact**: api/* import 路徑從 `app.api.common.UnifiedMessage` 變 `app.core.unified_message.UnifiedMessage`,所有 adapters 7 個檔案實際 import 後者

#### M-06: API layer import `app.core.unified_message` 雖不違反 constraint,但 convention drift
**Evidence**: 雖然是 dataclass 不是業務邏輯 (`api_layer_no_business_logic` 仍 PASS),但跨層 dataclass 共享沒有在 SAB `architecture_constraints` 顯式規範

---

### 🟢 MINOR (5)

#### L-01: AEE `__init__.py` 只有 5 行,無 re-export — 從外部 import 需深層路徑
**Impact**: e.g. `from app.services.aee.adapter import ActionAdapter` vs 期望的 `from app.services.aee import ActionAdapter`

#### L-02: `chain.py.bak` 殘留備份檔未被清理
**Evidence**: `03-development/src/app/middleware/chain.py.bak` 存在
**Impact**: 污染源碼樹,可能在 CI 編譯時被意外 pick up

#### L-03: webhooks.py 487-554 行定義的 `app = FastAPI(...)` 是 Agent Card sub-app,但命名 `app` 會 shadow import 慣例
**Impact**: 閱讀性差,後續加入 main app 時命名衝突

#### L-04: pyproject.toml 缺少 `[project.scripts]` 區塊
**Impact**: 無 `omnibot-api` 等 CLI command,uvicorn 啟動需手寫 module path

#### L-05: `app/core/pipeline.py:42` `_AGENT_PLATFORMS = frozenset({"agent", "a2a"})` 硬編碼
**Impact**: 若日後新增 A2A 變體(如 "agent-federation"),需改 source code 而非 config

---

## 3. Cross-Cutting Analysis

### 3.1 FR→Module Coverage (108 FRs)

| Bucket | Count | Status |
|--------|-------|--------|
| FR-XX → module 存在 + 有對應 test_frXX.py | 106 | ✅ |
| FR-XX → module 存在 + test_frXX.py placeholder | (估) 30+ | ⚠️ |
| FR-XX → module **不存在** (SAB 標的) | 2 | ❌ FR-107, FR-108 (`tests.strategy`) |
| FR-XX → module 在 SAB 但實作在別處 | 1 | ⚠️ FR-44 (webhooks vs agent_card) |

**Test file coverage**: 108/108 全部存在 (zero-pad 兩位數驗證)。

### 3.2 Architecture Constraints Compliance

| Constraint | Status | Evidence |
|------------|--------|----------|
| `no_circular_dependencies` | ✅ PASS | import graph scan: 0 cycles |
| `api_layer_no_business_logic` | ✅ PASS | api/* 只 import `app.core.unified_message` (dataclass) |
| `infra_layer_no_domain_imports` | ❌ **VIOLATED** | `app/infra/security.py:350` imports `app.admin.gdpr` |
| `paladin_executes_before_pii` | ❌ UNVERIFIABLE | pipeline.py 是 stub,無 orchestration |
| `knowledge_query_after_dst_slot_resolution` | ❌ UNVERIFIABLE | pipeline.py 是 stub |

**Score**: 1 verified PASS / 1 trivial PASS / 1 FAIL / 2 UNVERIFIABLE = 嚴重未達 SAB binding contract。

### 3.3 High-Risk Modules Status

| Module | FRs | LOC | Architecture Risk Trait | Status |
|--------|-----|-----|-------------------------|--------|
| `app.core.paladin` | 10-17 | 1181 | Network LLM (L4) | ✅ Module 完整 |
| `app.core.knowledge` | 26-33 | 1416 | Network + retry | ✅ Module 完整 |
| `app.core.dst` | 34-38 | 617 | Shared mutable FSM | ✅ Module 完整 |
| `app.infra.circuit_breaker` | 99 | 307 | Shared mutable state | ✅ Module 完整 |
| `app.infra.redis_streams` | 80-81, 90 | 333 | Shared mutable + async | ✅ Module 完整 |
| `app.infra.rate_limit` | 21-25 | 211 | Optional cache | ✅ Module 完整 |
| `app.infra.jobs` | 75-79 | 418 | Retry + async | ✅ Module 完整 |
| `app.services.aee` | 39-45 | 1416 (5 files) | Network + retry | ✅ Module 完整 |
| `app.services.llm_judge` | 65-69 | 721 | Parallel network | ✅ Module 完整 |
| `app.services.media` | 100 | 380 | External process (ClamAV) | ✅ Module 完整 |

**所有 high-risk module 都有實作**,但 **沒有 integration test 驗證 NP-07 / NP-13 / NP-15 patterns 的實際行為** (TEST_SPEC.md §Step 1b 強制 patterns)。Tool evidence 寫 "integration tests across 108 files" 但實際 integration/ 目錄是空的。

### 3.4 NFR Targets vs Test Coverage

| NFR | Target | SAB Module | Test evidence | Gap |
|-----|--------|------------|---------------|-----|
| NFR-01 | p95 < 1000ms | pipeline | ❌ no perf test (no benchmarks found) | Missing benchmark |
| NFR-02 | p95 < 5ms (paladin) | paladin | ⚠️ test_fr10.py exists | No latency assertion |
| NFR-09 | >=2000 TPS | webhooks | ✅ k6_nfr09_2000tps.js exists | Manual run only |
| NFR-16 | >=95% block rate | paladin | ⚠️ test_fr10-17.py exist | Threshold not asserted |
| NFR-28 | >=92% Recall@3 | knowledge | ⚠️ test_fr29.py exists | No Recall assertion |
| NFR-32 | unit≥70%/integ≥20%/e2e≥10% | tests | ❌ `assert 0.70 == 0.70` placeholder | **Not measured** |

**6/38 NFR 有 measurement gap**。NFR-32 (test pyramid ratio) **完全沒實測**。

---

## 4. Recommendations (Priority Order)

### MUST-FIX before Phase 4 exit (阻擋 Gate 4)
1. **F-01 + F-05**: 實作 `app/core/pipeline.py` 真實 orchestration,加入 sequence assertion + integration test 驗證 PALADIN→PII→DST→Knowledge→Emotion→Response 順序
2. **F-02**: 建立 `app/api/main.py` FastAPI root application,組裝所有 routers + middleware chain
3. **F-03**: 建立 `tests/strategy.py` 模組,封裝 FR-107/108 邏輯,更新 SAB `fr_module_traceability`
4. **F-04**: 重構 `app/infra/security.py` 移除 `from app.admin.gdpr` 反向依賴

### SHOULD-FIX before Gate 4
5. **H-01**: Pipeline `get_context()` 改用 `app.infra.database` query
6. **H-02 / H-03**: 同步 SAD §2.1 §2.6 與 SAB.json (FR-44 module + portal 加入)
7. **H-04**: Tests 子目錄結構對齊 SAD §2.1 或更新 SAD 接受扁平
8. **M-01**: pyramid.py `InputSanitizer` mapping 改為 `app.core.paladin`
9. **M-03**: 實際執行 `mutmut run`,把 proxy score 改為實測 score

### NICE-TO-HAVE
10. **M-02**: test_fr107.py placeholder assertions 改為實際測量
11. **M-04 / M-05 / M-06**: 文件化設計漂移
12. **L-02**: 清理 `chain.py.bak`
13. **H-05**: 寫 ADR-010 記錄 AEE split 決策

---

## 5. Verification Commands (重現審計)

```bash
# Completeness: test files
ok=0; for n in $(seq 1 108); do
  f=$(printf "03-development/tests/test_fr%02d.py" $n)
  [ -f "$f" ] && ok=$((ok+1))
done; echo "Tests: $ok/108"

# Completeness: FR module mapping
python3 -c "
import json, os
sab = json.load(open('.methodology/SAB.json'))
missing = [(fr, mod) for fr, mod in sab['fr_module_traceability'].items()
           if mod == 'tests.strategy' or not os.path.exists(
               os.path.join('03-development', mod.replace('.', '/') + '.py')
           )]
print('Missing:', missing)
"

# Correctness: architecture constraint violations
grep -rn "from app.core\|from app.services\|from app.admin" \
  03-development/src/app/infra/ --include="*.py"
# EXPECTED VIOLATION: app/infra/security.py:350

# Correctness: pipeline orchestration
grep -n "handle_message\|PALADIN.*PII\|pipeline.*sequence" \
  03-development/src/app/core/pipeline.py
# EXPECTED: empty (pipeline is stub)

# Consistency: test directory structure
ls 03-development/tests/{unit,integration,e2e}/
# EXPECTED: all empty (SAD §2.1 violated)

# Consistency: SAB vs SAD reconciliation
diff <(python3 -c "import json; print('\n'.join(sorted(json.load(open('.methodology/SAB.json'))['layers'][0]['modules'])))") \
     <(grep -E "^\s*-\s*app\.api\." 02-architecture/SAD.md | sed 's/.*- //;s/[[:space:]]*$//' | sort)
```

---

## 6. Self-Review

### 可能錯誤 (Possible Errors)
1. **Test coverage 計算**: 假設 test files 存在 = 有對應 test。實際可能某些 test_frXX.py 只是 placeholder (`assert 0.70 == 0.70`)。需要進一步對每個 file 統計 assertion count 與邏輯複雜度。
2. **Architecture constraint 違規嚴重度**: F-04 是 *測試發現* 但實作可能刻意 (例如 GDPR delete 是 admin 職責,infra.security 只是 trigger)。需要看更廣 context 確認。
3. **Pipeline "stub" 判斷**: 可能 orchestrator 在別處 (例如 webhooks.py 或 middleware/chain.py)。已 grep 過 `handle_message`,但若命名為 `process_request` 或 `dispatch` 可能漏掉。
4. **AEE trailing slash**: SAB 寫 `app.services.aee/` 是 Python package convention,但 SAB parser 可能對此 strict。需 run sab_parser 看實際接受度。

### 未驗證假設 (Unverified Assumptions)
- Gate 2 PASS 是基於 0.12 weighted linting/type_safety/test_coverage + 0.1 mutation/integration。**未讀 gate 計算原始 source code 驗證加權公式**。
- mutmut cache `.mutmut-cache.unified_message.full` (36KB) 存在暗示之前有跑過 mutmut,tool evidence 寫 "mutmut not run" 可能只是當下這次沒跑。
- 我沒讀完整 TEST_SPEC.md (只讀前 80 行),可能 FR test 命名有更細規則我沒看到。

### 改進處 (Improvements)
- 沒跑實際 pytest 看 pass rate — 324 test functions 但 8 zero-assert 已標出 (1.6%),其餘品質未逐個 review
- 沒檢視 git log 看 FR-by-FR 提交歷史 (可能某些 FR 是 stub-only)
- 沒驗證 .methodology/audit_SRS_2026-06-17.md (30KB audit 報告) 是否已涵蓋這些 findings

### 信心等級 (Confidence Levels)
- **F-01 (pipeline stub)**: 高信心 (直接證據:pipeline.py 108 行 + grep empty)
- **F-02 (main.py 缺失)**: 高信心 (find + grep empty + pyproject scripts empty)
- **F-03 (strategy 缺失)**: 高信心 (find + import error)
- **F-04 (constraint 違反)**: 高信心 (grep 直接命中)
- **F-05 (sequence unverifiable)**: 推論信心 (依賴 F-01)
- **H-01 ~ H-05**: 中-高信心 (直接 grep 證據)
- **M-01 ~ M-06**: 中信心 (部分需要讀 source code 細節)
- **L-01 ~ L-05**: 高信心 (直接觀察)

### Truthfulness Markers
- [Fact] 所有 grep/find/wc 命令的 output 都是直接 terminal 回應,未修改
- [Fact] Gate 2 composite 89.544 來自 `.methodology/gate2_result.json` 直接讀取
- [Inference] "整個系統無法運行" 是基於 F-01 + F-02 的推論 (未實際 uvicorn import 嘗試過)
- [Speculation] "Phase 4 會被打回" 是基於 Gate 4 通過條件的推測 (未讀 phase4_plan 詳細需求)

---

## 7. Audit Metadata

- **Auditor**: Hermes (sequential-thinking MCP) + terminal/read_file/search_files
- **Method**: Phase 2 baseline (SAD/ADR/TEST_SPEC/SAB) → Phase 3 deliverables cross-reference
- **Time cost**: 8 sequential-thinking iterations + ~25 tool calls
- **Coverage**: 108/108 FRs scanned, 17,082 LOC source reviewed, 108 test files inventoried
- **Limitations**: 未實際執行 pytest / mutmut / pyright;未讀 TEST_SPEC.md 完整 2280 行;未稽核 SRS.md

---

> **End of Report**
