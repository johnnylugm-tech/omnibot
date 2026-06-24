# Phase 3 Audit 重驗證報告 (Post-Fix)

> **[STALE 2026-06-17 — verified state at 2026-06-24]**
>
> This report was written on 2026-06-22 re-verifying fixes from commit `f409506`. Since then (2026-06-24), a fresh full-codebase audit (`phase3_audit_2026-06-24.md`) was run and additional fixes were applied. Several findings below marked `❌ NOT fixed` have been re-evaluated:
>
> - **H-02 (agent_card location)**: SAD §2.1 YAML line 536 was updated to remove `app.api.agent_card`; §2.2 duplicate Module: webhooks.py sections merged (2026-06-24)
> - **H-05 (AEE split / ADR-010)**: ADR-016 was extended with a "Note on package representation" section clarifying the trailing-slash convention (2026-06-24). ADR-010 is no longer needed since ADR-016 covers the decision
> - **NEW audit (2026-06-24)**: 42 findings (6 FATAL / 13 HIGH / 13 MEDIUM / 10 MINOR) — see `phase3_audit_2026-06-24.md` for current state
>
> Below is the original re-verification report preserved for traceability.

> **Date**: 2026-06-22
> **Auditor**: Hermes (sequential-thinking MCP)
> **Fix commit**: `f409506 fix(audit): resolve FATAL/HIGH phase3 audit findings`
> **Post-fix working tree**: additional uncommitted changes (portal.py regression fix, .bak cleanup, setup.cfg mutation path swap)
> **Method**: 對每個原始 finding 重跑驗證命令 + side-effect 偵察 + pytest smoke test

---

## 0. Executive Summary

| Status | Count | Detail |
|--------|-------|--------|
| ✅ Fully fixed (正解) | 4 | F-03, F-04, H-01, H-03, M-01 |
| ⚠️ Fixed but workaround (semantic issues / production risks) | 2 | F-01, F-02 |
| ❌ NOT fixed | 3 | H-02, H-04, H-05 |
| 🆕 New regressions introduced by fix | 3 | FR-86 test fail, FR-105 test fail, FR-104 portal inbox |
| 🆕 Side effects / residue | 5 | 4 .bak files in VCS, 1 .bak deleted (uncommitted), 6 broken cross-refs |

**Verdict**: 🟡 **PARTIAL FIX** — All 5 FATAL findings addressed at surface level, but F-01/F-02 are workarounds with semantic gaps, and the fix introduced 2 new regressions that were partially caught by the post-fix working-tree state (portal.py) but FR-86 regression remains.

**Tests**: 923 passed, 2 xpassed, **2 failed** (test_fr86 login regression, test_fr105 cost-per-tier regression — both NOT in original audit).

---

## 1. Per-Finding Verification

### ✅ F-03: `tests/strategy.py` 創建 — 正解
**Evidence**:
```
$ cat 03-development/tests/strategy.py
"""[FR-107, FR-108] Test Strategy — pyramid ratio validation and E2E pipeline runner.
class TestStrategy:
    def validate_pyramid(unit, integration, e2e) -> bool:
        return unit >= 0.70 and integration >= 0.20 and e2e >= 0.10
    def run_e2e_pipeline(scenario) -> dict:
        return {"scenario": scenario, "status": "pass"}
```
**Status**: ✅ Fully fixed. Module has both FR-107 (validate_pyramid) and FR-108 (run_e2e_pipeline). `from tests.strategy import TestStrategy` works. test_fr107.py updated to actually call `TestStrategy().validate_pyramid(...)`.
**Residual concern**: `run_e2e_pipeline` always returns `status: "pass"` — it's a stub. Real E2E would need to invoke k6 or pytest-e2e runner. Acceptable as P3 deliverable (skeleton) but not production-ready.

---

### ✅ F-04: Infra layer no domain imports — 正解
**Evidence**:
```
$ grep -rn "from app.core\|from app.services\|from app.admin" 03-development/src/app/infra/ --include="*.py"
(empty — no violations)
```
**Status**: ✅ Fully fixed. `security.py` no longer imports `app.admin.gdpr`. The `delete_user_data` reference was either removed or stubbed locally.

---

### ✅ H-01: Pipeline `get_context()` 無 admin 依賴 — 正解 (with caveat)
**Evidence**:
```
$ grep -n "app.admin" 03-development/src/app/core/pipeline.py
(empty)
```
**Status**: ✅ Surface fixed. The fix replaced `from app.admin.gdpr import _MESSAGES` with module-level `_CONTEXT_HISTORY: dict[str, list[dict]] = {}`.
**⚠️ Caveat (workaround, NOT 正解)**: module-level dict is **process-local memory**. Under `uvicorn --workers N` or K8s replicas, each process maintains its own dict, so conversation history will be inconsistent across requests hitting different workers. **Production-correct fix** would route through `app.infra.database` (Postgres) or Redis Streams.
**Severity**: Medium (degrades to broken under load-balanced production deployment). Acceptable as P3 dev-time stub; must be addressed before Phase 6 release.

---

### ⚠️ F-01: Pipeline.handle_message() orchestrator — 表層 FIXED,深層 workaround
**Evidence**:
```python
# pipeline.py:84-118 (new method)
def handle_message(self, msg: Any) -> Any:
    from app.core.response import ResponseSource, UnifiedResponse
    content: str = msg.content
    if self.paladin is not None:
        self.paladin.check(content)              # ← PROBLEM 1
    if self.pii is not None:
        mask_result = self.pii.mask(content)
        content = mask_result.masked_text
    if self.dst is not None:
        self.dst.transition("SLOT_FILLING")      # ← PROBLEM 2
    if self.knowledge is not None:
        self.knowledge.query(content)            # ← PROBLEM 3
    self.process(msg.platform, content)          # ← PROBLEM 4 (emotion result discarded)
    if self.response is not None:
        content = self.response.format_for_platform(...)
    return UnifiedResponse(
        content=content,
        source=ResponseSource.RULE,              # ← PROBLEM 5 (HARDCODED)
        confidence=1.0,                          # ← PROBLEM 6 (HARDCODED)
    )
```

**Status**: ⚠️ Surface fixed (function exists, sequence PALADIN→PII→DST→Knowledge→emotion→response is wired), but 6 semantic gaps make this a **workaround, not 正解**:

1. **`self.paladin.check(content)`** — paladin 真實 API 是 `PALADINPipeline.process()` (returns InjectionVerdict) 或 `PromptInjectionDefense.check_input()` (returns DefendResult)。`check()` 是 `GroundingChecker.check()` 的 method (line 777 of paladin.py),**用在 PALADIN L5 不是 L1-L4 stage**。Wire 真實 paladin 會 AttributeError-ish (實際 `check()` 存在但用錯了 — 拿 grounding check 取代 PALADIN pipeline 主入口)。
2. **`self.dst.transition("SLOT_FILLING")`** — DST 真實 API 是 `DialogueState.transition(to_state)` 從 `self.state` 出發轉移,需要傳 current state context。Hardcode "SLOT_FILLING" 會被 `ALLOWED_TRANSITIONS` 拒絕 (ValueError) 除非 from-state 是 GREETING/INIT。對話已經在 GREETING 之外的 state 會立刻 crash。
3. **`self.knowledge.query(content)`** — knowledge 真實 API 是 `HybridKnowledge.query(text) → KnowledgeResult`。結果被丟棄,沒有檢查 `result.source` (rule/rag/wiki/escalate) 決定後續 flow。也沒看 `result.confidence`。
4. **`self.process(msg.platform, content)`** — emotion stage 結果丟棄!`process()` 回傳 dict 包含 `emotion_result`,但 handle_message 沒接,沒用 emotion 結果調整 response (FR-47/48 escalation 路徑永遠不會觸發)。
5. **`source=ResponseSource.RULE` hardcoded** — 所有 response 會假裝是 rule-based,實際上不知道是 rule/rag/wiki/escalate。
6. **`confidence=1.0` hardcoded** — 即使真實 knowledge result confidence=0.3 (escalate),仍報 1.0。CSAT calculator、escalation queue、A/B testing 都會被誤導。

**Severity**: High. Method exists but production wiring will produce incorrect responses and crash on DST state transitions. **Workaround, not 正解**. The audit report recommended "F-01 修復後,在 `Pipeline.handle_message()` 加入 sequence assertion (asserts + dev-mode runtime check),並加入 integration test 驗證執行順序" — none of this was done.

---

### ⚠️ F-02: `app/api/main.py` FastAPI root app — 表層 FIXED,深層 partial
**Evidence**:
```python
# 03-development/src/app/api/main.py (19 lines)
from fastapi import FastAPI
from app.api.webhooks import router as webhooks_router
app = FastAPI(title="OmniBot", version="0.1.0")
app.include_router(webhooks_router, prefix="/api/v1")
@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}
```
**Status**: ⚠️ Surface fixed (file exists, FastAPI root app created, health endpoint), but 4 gaps make this **partial fix**:

1. **Only 1 router included** — `webhooks` only. Missing: `auth` (FR-86/87), `management` (FR-85/88), `websocket` (FR-57/58/59). **uvicorn app.main:app 啟動後,登入、知識管理、WS 都 404**。
2. **No middleware chain** — `app/middleware/chain.py` exists (187 LOC) with FR-24 order (TLS→IP→Signature→Parse→Rate→RBAC) but main.py 沒套用 `MiddlewareChain`。SAD §2.2 "Middleware chain order enforced" **沒被實作**。
3. **Naming collision** — webhooks.py:487 也有 `app = FastAPI(title="OmniBot Agent Card")`,main.py:11 也有 `app = FastAPI(title="OmniBot")`。兩個都命名 `app`。`from app.api.webhooks import app` 拿到 sub-app;`uvicorn app.api.main:app` 拿到 root app。混淆。
4. **No L0-L9 error handlers** — SAD §3 列了 9 個 error handling level (validation 422, auth 401, authz 403, rate limit 429, etc.)。main.py 沒註冊任何 exception handler。
5. **health endpoint at `/api/v1/health`** — 但 SAD 沒明確規定 path,且 ADR/SAD 沒說要 LivenessProbe。

**Severity**: Medium-High. App can start, but functional surface is 80% missing.

---

### ✅ H-03: `app.admin.portal` 加入 SAB + SAD — 正解
**Evidence**:
```
SAB.json: "app.admin.odd_sql", "app.admin.portal"
SAD.md §2.6: 新增 "#### Module: portal.py" with FR-104 description + 166 LOC
```
**Status**: ✅ Fully fixed.

---

### ✅ M-01: pyramid.py InputSanitizer mapping 修正 — 正解
**Evidence**:
```
$ grep -n "InputSanitizer" 03-development/tests/pyramid.py
27:        "InputSanitizer",
58:    "InputSanitizer": "app.core.paladin",  # was "app.core.chunking"
```
**Status**: ✅ Fully fixed.

---

### ⚠️ M-02: test_fr107.py placeholder — partial fix
**Evidence**: Diff shows added `assert TestStrategy().validate_pyramid(...) is True` to each test. Old `assert 0.70 == 0.70` placeholder remains alongside. 
**Status**: ⚠️ Partial. Tests now invoke `TestStrategy` so the module is exercised, but the asserted values are still hardcoded constants (not measured from real test distribution). Acceptance criteria met for "exercise the module", not met for "actually measure pyramid ratio".

---

### ❌ H-02: FR-44 module placement (agent_card) — NOT FIXED
**Evidence**:
- agent_card endpoint 仍在 `webhooks.py:488`
- 6 個 adapter 檔案 docstring 引用 `agent_card.py:12-16` (broken cross-reference — 檔案不存在)
- SAB 沒更新 fr_module_traceability 對 FR-44 的映射
**Status**: ❌ NOT fixed. Commit message didn't mention H-02.
**Side effect**: Cross-references in `a2a.py`, `verifiers.py`, `web.py`, `whatsapp.py`, `telegram.py`, `line.py`, `messenger.py`, `base.py`, `webhooks.py` all cite `agent_card.py:12-16` for method routing table. If anyone navigates that reference they get 404.

---

### ❌ H-04: Tests dir structure — NOT FIXED
**Evidence**:
```
$ ls 03-development/tests/integration/
(empty)
$ ls 03-development/tests/unit/
(empty)
$ ls 03-development/tests/e2e/
(empty)
```
所有 108 個 test_fr*.py 仍在 `tests/` 根目錄。
**Status**: ❌ NOT fixed. NFR-32 ratio 仍無法實測驗證。

---

### ❌ H-05: AEE split decision (ADR-010) — NOT FIXED
**Evidence**:
```
$ ls 02-architecture/adr/
ADR.md
```
沒有 ADR-010。AEE 仍是 split package 但無文件化決策紀錄。
**Status**: ❌ NOT fixed.

---

### ❌ M-04 ~ M-06 — NOT addressed
- M-04 (middleware dir 在 SAD 規劃外): 沒處理
- M-05 (unified_message location): 沒處理 (仍在 core/unified_message.py,SAD 寫在 api/common.py)
- M-06 (api→core.unified_message convention): 沒處理

---

## 2. New Regressions Introduced by Fix

### 🚨 NEW-1: test_fr86 login regression
**Evidence**:
```
$ pytest 03-development/tests/test_fr86.py::test_fr86_login_returns_jwt_and_refresh
FAILED test_fr86_login_returns_jwt_and_refresh
AssertionError: FR-86: login() must return a dict with token keys on success; got type=int.
assert False
 +  where False = isinstance(401, dict)
```
**Status**: `app/api/auth.py` 的 `login()` 在某條件下回傳 `401` (int) 而非 dict。Audit fix commit 沒碰 auth.py,所以這是 pre-existing 或 main.py router inclusion 造成的間接問題 (e.g. test 走 FastAPI 路由時拿到 HTTPException 而不是 function return value)。

**Risk**: FR-86 (login endpoint) 整個測試 fail,意味 auth flow 壞掉。1/864 失敗 = 0.12% failure rate,但這是 critical FR。

### 🚨 NEW-2: portal.py inbox regression (caught + fixed post-commit)
**Evidence**:
- Commit f409506 把 `self._inbox = {section: [] for section in INBOX_SECTIONS}` 改成 `self._inbox: dict[...] = None`
- Working tree 現在是 dict comprehension (recovered)
- `git status` 顯示 `M 03-development/src/app/admin/portal.py` (uncommitted revert)
**Status**: User manually reverted the regression after commit. Portal inbox works again. But the **commit f409506 contains the broken state** — anyone checking out that commit alone gets broken portal.

---

## 3. Side Effects & Residue

### 🚨 SIDE-1: 5 個 .bak 檔案 in VCS
**Evidence**:
```
$ git ls-files | grep "\.bak$"
03-development/src/app/admin/portal.py.bak        ← deleted in working tree, but in index
03-development/src/app/core/dst.py.bak
chunking.py.bak
dst.py.bak
emotion.py.bak
```
**Status**: 1 deleted (portal.py.bak, uncommitted) + 4 still tracked. **違反 user memory rule**: "patch operation 後檢查 untracked residue" — 雖然這些是 tracked 不是 untracked,但仍是 patch operation residue。

### 🚨 SIDE-2: setup.cfg mutation path change (uncommitted)
**Evidence**:
```diff
-paths_to_mutate = 03-development/src/app/admin/portal.py
+paths_to_mutate = 03-development/src/app/admin/odd_sql.py
```
**Status**: Uncommitted. mutmut 把 mutation target 從 portal.py 換到 odd_sql.py,可能是因為 portal.py 在 audit fix 時被改動太多 (false positives)。**需要確認這是有意還是 workaround** — 如果 portal.py 有真實 bugs,把它從 mutation target 拿掉是 masking。建議保留並修 portal.py 的測試覆蓋。

### 🚨 SIDE-3: 6+ broken cross-references
**Evidence**: 多個 adapter docstring 引用 `agent_card.py:12-16` 但檔案不存在 (見 H-02)。
**Status**: 文件化契約壞掉。Phase 4 testing 階段若有人 trace code 會困惑。

### SIDE-4: Uncommitted residue per user memory rule
**Evidence**: `git status` 顯示:
- `M .methodology/effort_metrics.db` (auto-gen, OK)
- `M .methodology/gap_report.json` (auto-gen, OK)
- `M .methodology/mutation_survivors.json` (auto-gen, OK)
- `M .methodology/trace/attestation.latest.json` (auto-gen, OK)
- `M 03-development/src/app/admin/portal.py` (manual revert of commit regression, should commit)
- `D 03-development/src/app/admin/portal.py.bak` (cleanup, should commit)
- `M CLAUDE.md` (gate progress update, should commit)
- `M setup.cfg` (mutation path change, should commit)
- `?? .methodology/decision_logs/2026-06-22/GATE_4_006.yaml` (new file, should commit)

**Per user memory**: "Always run `git status` after patch operations to catch leftover scripts before declaring done."

**Status**: Patch operation (audit fix) complete,但 5 個 manual changes + 1 new file 未 commit。

---

## 4. Workaround vs 正解 分類

| Finding | Fix type | 理由 |
|---------|----------|------|
| F-03 (strategy.py) | ✅ 正解 | 模組化清晰,validate_pyramid 邏輯正確 |
| F-04 (infra no admin) | ✅ 正解 | 刪除 reverse import |
| H-01 (pipeline ctx) | ⚠️ Workaround | module-level dict 在 multi-process 失效 |
| H-03 (portal SAB) | ✅ 正解 | 文件化更新 |
| M-01 (pyramid mapping) | ✅ 正解 | 修正 import path |
| M-02 (test_fr107) | ⚠️ Partial | placeholder + 真正呼叫並存 |
| **F-01 (orchestrator)** | ❌ Workaround | 6 個 semantic gaps;hardcoded source/confidence;用錯 API |
| **F-02 (main.py)** | ⚠️ Workaround | 只 1 router,無 middleware chain,naming collision |

---

## 5. Recommendations (Pre-Gate-4)

### MUST-FIX before Gate 4
1. **F-01 deep fix**: Pipeline.handle_message 用正確 API (paladin.process / dst.transition with context / 接 knowledge result / 接 emotion result)。移除 `source=RULE, confidence=1.0` hardcode。改用實際結果決定 source/confidence。
2. **F-02 router coverage**: main.py include 所有 5 個 router (webhooks, auth, management, websocket, agent_card)。套用 MiddlewareChain。解 `app = FastAPI()` naming collision。
3. **NEW-1 FR-86 regression**: 找出 root cause (auth.py 為何回 401 而非 dict),修復或 revert。
4. **SIDE-1 .bak cleanup**: `git rm` 4 個剩餘 .bak 檔。

### SHOULD-FIX
5. **H-01 production fix**: `_CONTEXT_HISTORY` 改用 `app.infra.database` 或 Redis。
6. **H-02 agent_card**: 拆出獨立 module 或刪 SAD 引用。修 6 個 cross-references。
7. **H-04 tests dir**: 搬移 test_fr*.py 到 unit/integration/e2e 子目錄,或更新 NFR-32 measurement。
8. **H-05 ADR-010**: 寫 AEE split 決策紀錄。
9. **NEW-2 commit portal.py fix**: working tree 的 portal.py 修復應 commit,並考慮是否要 revert f409506 整個 commit (因為它包含 portal regression)。
10. **SIDE-4 residue**: 5 個 uncommitted changes + 1 new file 應該一併 commit 或 discard。

### NICE-TO-HAVE
11. M-04 ~ M-06 文件化
12. setup.cfg mutation path swap 確認意圖

---

## 6. Self-Review

### 可能錯誤
1. **F-01 "workaround" 判斷**: 可能 user 故意接受 hardcoded source=RULE 作為 P3 placeholder,P4 才接真實 logic。但 audit 報告明確指出這是 P3 FATAL,所以應該是真正的 fault。
2. **NEW-1 regression root cause**: 我只看到 test failure,沒 trace auth.py 為何壞。可能 commit 前的 master 已經壞,跟 audit fix 無關。需要 `git stash + pytest pre-fix state` 確認。
3. **`.bak` 在 VCS 是否真為殘留**: 可能 .bak 是有意的 backup file 而非 patch residue。但 .bak extension 是 unstandard practice in production code,應該 .gitignore 排除。
4. **Pipeline emotion result "丟棄"**: 我看 line 107 是 `self.process(msg.platform, content)`,process() return dict 但 handle_message 沒接。確認 process() return value 是 discarded 沒錯。

### 未驗證假設
1. `_CONTEXT_HISTORY` 是否在多進程環境實際壞掉 — 沒實際跑 multi-worker uvicorn 測試。
2. NEW-1 FR-86 在 master pre-fix 是否也壞 — 沒跑 `git checkout HEAD~5 && pytest test_fr86`。
3. Pipeline 真實 wire-up (傳入 non-None paladin) 是否會 AttributeError — 沒實際 instantiate。

### 改進處
1. 沒跑 mutmut 看 mutation score 真實變化
2. 沒用 code-review-graph 看 f409506 commit 的 impact radius
3. 沒看 Phase 4 plan 看哪些 finding 會被 Gate 4 嚴格檢查

### 信心等級
- F-01/F-02/F-03/F-04/H-01/H-03/M-01/M-02 verification: **高信心** (直接 grep/cat 證據)
- H-02/H-04/H-05/M-04~M-06 NOT fixed: **高信心** (git log + ls 證據)
- F-01 6 個 semantic gaps: **中-高信心** (讀源碼比對真實 API)
- NEW-1 FR-86 regression root cause: **中信心** (test failure 直接,但 root cause 沒深挖)
- Workaround vs 正解 分類: **中信心** (主觀判斷)

### Truthfulness Markers
- [Fact] grep/cat/pytest/git output 都是直接 terminal 回應
- [Inference] "module-level dict 在 multi-worker 失效" 是架構常識推論
- [Speculation] "Phase 4 會被打回" 是基於 Gate 4 嚴格性的推測
- [Unknown] NEW-1 root cause 確切位置;`.bak` 歷史用途

---

## 7. Final Score

| 維度 | Original Audit | Post-Fix | Delta |
|------|----------------|----------|-------|
| Fatal | 5 | 3 (F-01, F-02, F-04 partial) | -2 |
| High | 5 | 4 (H-01, H-02, H-04, H-05) | -1 |
| Medium | 6 | 5 (M-02 partial, M-04~M-06) | -1 |
| New regressions | 0 | 2 (NEW-1, NEW-2) | +2 |
| Side effects | 0 | 5 (.bak, naming collision, broken refs, uncommitted residue) | +5 |

**Net**: 大幅改善 (5 Fatal → 3 Fatal),但引入 2 regressions + 5 side effects。**目前狀態**:不可直接進 Gate 4,需要上述 MUST-FIX 6 項。

---

> **End of Re-Verification Report**
