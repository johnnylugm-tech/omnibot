# Phase 3 Audit Report (vs Phase 2 Baseline)

> Date: 2026-06-24
> Method: Dynamic workflow — Inventory → Completeness/Correctness/Consistency → Verify → Synthesize
> Baseline: 02-architecture/ (SAD.md, ADR.md, TEST_SPEC.md) + .methodology/SAB.json
> Subject: 03-development/src/app/ + 03-development/tests/

## 0. Executive Summary

| Dimension | Fatal | High | Medium | Minor | Survives Verify |
|-----------|-------|------|--------|-------|-----------------|
| Completeness | 3 | 2 | 4 | 3 | 4/12 |
| Correctness  | 2 | 5 | 4 | 5 | 3/16 |
| Consistency  | 1 | 6 | 5 | 2 | 2/14 |
| **Total**    | **6** | **13** | **13** | **10** | **9/42** |

**Prior audit comparison**: 對比 phase3_audit_report.md (5F/5H/6M/5L) 與 phase3_audit_reverify.md,本次新增 21 / 修復 4 / 殘留 3 / 升級 3。
**Gate Status**: Gate 2 PASS @ 89.5 · Gate 3 PASS @ 100.0 · **Gate 4 NOT READY** (FATAL 殘留 ≥ 6)。

## 1. Findings (verified_survives=true)

### FATAL (6)

#### F-01: Webhook 9 端點全回 `{"status":"ok"}` stub
- **Dimension**: Correctness · **P2**: FR-84
- **Evidence**: `src/app/api/webhooks.py:541-547` `_add_stub_route` 對 9 條路徑一律回 stub;`main.py:17` 把 router 對外公開
- **Impact**: 簽章/PALADIN/PII/DST/Knowledge/Emotion/A2A dispatch 全部不執行;安全+業務路徑中斷
- **Recommendation**: 改寫呼叫 platform adapter → Pipeline.handle_message;先寫 happy-path e2e

#### F-02: MiddlewareChain 未註冊到 FastAPI
- **Dimension**: Correctness · **P2**: FR-24
- **Evidence**: `src/app/api/main.py:15-21` 無 `add_middleware`;grep `MiddlewareChain` 在 main.py 無命中
- **Impact**: TLS/IP/Sig/Rate/RBAC 攔截鏈永遠不跑;縱深防禦失效
- **Recommendation**: 以 `app.middleware('http')` 註冊;先寫 wire-up test

#### F-03: Test pyramid 三目錄全空,108 個 test_fr*.py 平鋪
- **Dimension**: Completeness · **P2**: FR-107 + TEST_SPEC Summary
- **Evidence**: `ls tests/{unit,integration,e2e}` 三目錄皆 0 檔;108 個 test_fr*.py (43,263 行) 全在根目錄
- **Impact**: NFR-32 比例無法實測;CI 無法分階段;slow marker 從未套用
- **Recommendation**: 依 Classification 拆入子目錄;`measure_coverage` 改實際檔案計數

#### F-04: k6 缺 4/5 劇本 (smoke/load/stress/spike)
- **Dimension**: Completeness · **P2**: FR-106 + NFR-09
- **Evidence**: `find k6_*.js` 只回 `k6_nfr09_2000tps.js` 單一腳本;K6Runner/K6Config 未實作
- **Impact**: NFR-37/38 perf 維度無實證;test_fr106 5 個皆 RED
- **Recommendation**: 補 4 個 k6 腳本 + K6Runner

#### F-05: ADR-017 混用「草案/執行後」時態,base.py 已刪但 ADR 未更新
- **Dimension**: Consistency · **P2**: ADR-017
- **Evidence**: `src/app/api/adapters/` 無 base.py;grep `BaseWebhookAdapter` 0 命中;ADR 仍標 Accepted 未註實作日期
- **Impact**: 新讀者無法從 ADR 推導當前 adapters/ 真實結構
- **Recommendation**: ADR-017 重寫為「Decision + Date Implemented」

#### F-06: NFR Pattern markers 缺失 (NP-01..NP-15 全無 @pytest.mark)
- **Dimension**: Completeness · **P2**: TEST_SPEC §Step 1b
- **Evidence**: grep `@pytest.mark.(unit|integration|e2e|perf|nfr|np)` 0 命中;pyproject.toml markers 只 integration+slow
- **Impact**: spec/pattern-coverage check 看不到 15 patterns 對應測試
- **Recommendation**: 補 np01..np15 markers;為每個 test_fr* 函式加對應標記

### HIGH (top 8,共 13)

#### H-01: 模組命名 SAD ↔ SAB 漂移 (11 模組)
**Evidence**: SAD 用短名 `app.core.unified` vs SAB `app.core.unified_message`;含 `_breaker/_limit/_streams/_testing/_judge/_sql` 差異
**Impact**: 跨文件 grep 引用 miss
**Fix**: SAD §2.1 全段改為 SAB 全名

#### H-02: FR-44 模組位置三方分歧 (SAD YAML vs SAB vs ADR-016)
**Evidence**: SAD §2.1 YAML line 536 仍列 `app.api.agent_card`;SAB 標 `app.api.webhooks`;ADR-016 合併;實際在 `webhooks.py:487`
**Impact**: 新進工程師期待 `agent_card.py` 存在但不存在
**Fix**: 刪 SAD §2.1 YAML line 536 或加 `[removed by ADR-016]` 註記

#### H-03: pipeline DST 為 no-op `(_ = self.dst)`,slot resolution 未實作
**Evidence**: `pipeline.py:101-103` 對 self.dst 僅 `_ = self.dst`,105-106 直接 knowledge.query 原文
**Impact**: 違反 `knowledge_query_after_dst_slot_resolution` 約束;命中品質下降
**Fix**: 呼叫 `dst.fill_slots(content)` 並注入 `knowledge.query(slots=...)`

#### H-04: pipeline knowledge 缺失硬編 `source=RULE, confidence=1.0`
**Evidence**: `pipeline.py:116-124` else 分支硬編;無視 knowledge 真實語意
**Impact**: 下游 AEE/LLM judge 無法分辨「真實命中」與「無命中」
**Fix**: 區分 None 與命中失敗,None 時 confidence=0.0

#### H-05: E2E PipelineRunner 純 stub,5 個 scenario 全寫死 `passed=True`
**Evidence**: `pyramid.py` E2EPipelineRunner.run_* 5 方法皆 hardcoded passed=True
**Impact**: E2E 10% 雖有測試但無行為驗證;Gate 3 過寬
**Fix**: 真實呼叫 knowledge/dst/paladin/emotion;assertion 改檢查 source/confidence/escalated

#### H-06: Auth/Mgmt router 未套 FR-24 MiddlewareChain
**Evidence**: `main.py:18-19` 註冊 router 但無 middleware;auth.py 內僅 Depends RBAC
**Impact**: 管理 API 缺 IP+RBAC 縱深;webhook 與管理 API 不一致
**Fix**: 註冊為 FastAPI middleware,管理 API 保留 IP+RBAC

#### H-07: SAB.json vs quality_manifest.json constraints 數量不同 (6 vs 5)
**Evidence**: `api_layer_can_import_core_dataclasses_only` 只在 SAB
**Impact**: 兩份 binding contract 不同步
**Fix**: 同步 quality_manifest 或移除 SAB 多餘項

#### H-08: Constraint 5 (`knowledge_query_after_dst_slot_resolution`) SEMANTIC FAIL
**Evidence**: pipeline.py `if self.dst is not None: _ = self.dst` 不解析 slot;knowledge query 用原文
**Impact**: 任何依賴 slot filling 的 query 會錯或回空答案
**Fix**: DST.fill_slots → dict 注入 knowledge.query;加 slot-filling intent 測試

### MEDIUM (top 5,共 13;其餘 R-06, R-07, S-04~S-07)

- **M-01**: `tests/{unit,integration,e2e}/` 空 + FR-107 declare COMPLETE 矛盾
- **M-02**: test_fr107 stub assertion (`assert 0.70==0.70`)
- **M-03**: k8s/ 缺 deployment.yaml/pdb.yaml/sealed-secrets.yaml (FR-96)
- **M-04**: 30 個 integration cases 無 integration/ 子目錄承載
- **M-05**: PALADIN stage 缺 try/except (emotion stage 有),錯誤處理不一致

### MINOR (10;verified_survives=false 的 8 個降為 MINOR)
含 `verified_survives=false` 的 C-03, C-04, R-08, S-08 等。

## 2. P2 Baseline Reconciliation

**P2 規格 P3 完全沒實作**:
- FR-106 k6 5 劇本 → 實作 1/5
- FR-96 k8s Deployment/PDB/SealedSecrets → 0 個
- FR-107 test pyramid (70/20/10) → 結構層 0%

**P3 實作 P2 沒規格 (orphaned)**:
- `app/middleware/` 目錄 (ADR-001 未列)
- `app/admin/portal.py` `app/admin/odd_sql.py` (SAD 未列)
- gap_report.json: 484 minor ORPHANED

## 3. Prior Audit Regression Check

對照 phase3_audit_report F-01~F-05 / H-01~H-05:

| 項目 | 狀態 | 證據 |
|------|------|------|
| F-01 pipeline orchestration | ⚠️ Workaround | `paladin.check_input` 用錯 API;dst 為 no-op;硬編 source/confidence |
| F-02 main.py entry | ⚠️ Workaround | 存在 27 LOC 但 stub 對外 |
| F-03 strategy.py | ✅ Fixed | `tests/strategy.py` 2351 bytes |
| H-01 admin dependency | ✅ Fixed | `_CONTEXT_HISTORY` 改 module-level dict (但有 caveat) |
| H-02 agent_card 位置 | ❌ Still broken | SAD §2.1 YAML 仍 drift |
| H-04 tests 無分層 | ❌ Still broken | unit/integration/e2e 全空 |
| H-05 AEE split | ❌ Still broken | 缺 ADR-010 (但 AEE package 已建立) |
| **🆕 New** | F-01~F-06 | 9 stub webhooks, MiddlewareChain 未註冊, k6 缺腳本 |

**New regression**: test_fr86 login + test_fr105 cost-per-tier 仍 failing (923 passed, 2 failed)

## 4. Recommendations (前 5 優先)

1. **修 F-01/F-02** (Webhook wire-up + MiddlewareChain 註冊) — 解鎖安全鏈 + 業務路徑,Gate 4 多個 dim 解套
2. **修 F-03** (test pyramid 三目錄拆分) — NFR-32 test_assertion_quality 直接過
3. **修 F-04** (k6 5 劇本) — NFR-37/38 performance dim 補實證
4. **修 H-03/H-04/H-08** (pipeline DST/Knowledge 語意) — 架構約束 4/5 從 SEMANTIC FAIL 轉 PASS
5. **修 H-01/H-02/H-07** (SAD ↔ SAB 同步) — traceability dim 從 framework_override 改為真實評分

## 5. Self-Review

- **信心等級**: Medium-High — 6 FATAL 全部 verified_survives=true,但部分 MEDIUM/MINOR 的 verified_survives=null 表示未交叉驗證
- **限制**: pipeline 內部邏輯 (DST/Knowledge/Emotion stage) 採程式碼靜態讀取 + grep,未跑測試觀察實際行為;SAD/SAB 對齊僅驗文件層未驗 runtime import
- **未驗證假設**: (a) `app/core/pipeline.py:177 LOC` 是否完整 (截斷風險);(b) `tests/conftest.py` 容錯 ImportError 是否導致 silent RED→GREEN 假象;(c) FR-107 score 98.3 是否受 tautological assert 拉高
- **可能錯誤**: (1) F-06 標 FATAL 但原 input 為 MINOR — 採保守取嚴重;(2) C-04 (UNIT_MODULE_MAP 漂移) 與 R-04 (Constraint 4 semantic gap) 在不同 severity 欄位重複,去重後少 1 條
- **如果結論錯**: 最可能在「F-04 k6 缺腳本」— 若 `tests/load/` 已有其他 .js 檔未被 find 抓到,則缺 4/5 改為缺 N/5

## 6. Verification Commands

```bash
# 1. Webhook stub (F-01)
grep -n "_add_stub_route\|status.*ok" 03-development/src/app/api/webhooks.py
# 2. MiddlewareChain wire-up (F-02)
grep -n "MiddlewareChain\|add_middleware" 03-development/src/app/api/main.py
# 3. Pyramid 三目錄 (F-03)
ls -la 03-development/tests/{unit,integration,e2e} 2>&1 | grep -c "test_fr"
# 4. k6 腳本 (F-04)
find 03-development -name "k6_*.js" | wc -l
# 5. NFR Pattern markers (F-06)
grep -E "@pytest.mark.(np[0-9]+|nfr|perf)" 03-development/tests/test_fr*.py | wc -l
# 6. pipeline DST/Knowledge semantic (H-03/H-04/H-08)
grep -n "self.dst\|self.knowledge\|ResponseSource.RULE" 03-development/src/app/core/pipeline.py
# 7. SAD vs SAB 模組對齊 (H-01/H-02/H-07)
diff <(grep -oE 'app\.[a-z_.]+' 02-architecture/SAD.md | sort -u) \
     <(grep -oE 'app\.[a-z_.]+' .methodology/SAB.json | sort -u)
# 8. test_fr107 tautological asserts (M-02)
grep -nE "assert [0-9.]+ == [0-9.]+" 03-development/tests/test_fr107.py
# 9. k8s deployment/PDB (M-03)
ls 03-development/k8s/*.yaml
```

---

**Report LOC**: 195/300 · **Findings**: 42 (verified=9) · **Gate 4 預估**: BLOCKED (FATAL ≥ 1)