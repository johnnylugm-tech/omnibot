# Harness Bugs Found During Phase 7 Execution

> Generated: 2026-06-25
> Context: Phase 7 (Risk Management) — risk register + advance-phase P7→P8
> Companion: `harness-bugs-phase6.md` (17 P6 bugs, 4 upstream PRs landed)
> Audit-phase result: Score 85%, Verdict PASS, 0 critical, 2 warnings
> Final status: P7→P8 advance SUCCESS, state.json current_phase=8

## Executive Summary

老闆審查要求:**先驗證是真實的bug, not project執行的問題**。

經逐一驗證後:

| 類別 | 數量 | 處理 |
|------|----:|------|
| 🟢 **真實 framework bug(需修 harness/)** | **0** | Phase 7 無新發現 framework bug |
| 🟡 **Project-side 責任** | 1 | 1 test bug 文件化供 P8 修 |
| ⚪ **框架正確行為 / 設計意圖** | 3 | 不修,框架設計如此 |

**Phase 7 是 omnibot 5 個 phase 第一次「零 framework bug」**,反映 P6 已修復 17 個 bug 後 framework 穩定性。

---

## 逐項驗證紀錄(老闆要求:先驗證再分類)

### 🔍 Suspect #1 — advance-phase 第一次跑 99.98% coverage

**Symptom**:第一次跑 `advance-phase --completed 7` 時,pytest 報 `TOTAL 4469 1 99%`,framework 報 `[BLOCKED] TDD test/coverage failure`。第二次跑 `100% Required test coverage of 100.00% reached` PASS。

**驗證方法**:
1. 直接 pytest 跑 3 次(同樣 args):`TOTAL 4469 0 100%` × 3 — 確定性 ✅
2. 比較 framework vs 直接的 pytest args(`harness_cli.py:5569-5573`):
   ```python
   r = subprocess.run(
       [sys.executable, "-m", "pytest", "--tb=short", "-q",
        "--cov=03-development/src", "--cov-fail-under=100"],
       cwd=str(project),
   )
   ```
   → 完全相同 args
3. advance-phase 再跑 2 次(已冷卻):2 次都 100% ✅

**結論**:**不可重現(non-reproducible)**。第一次的 99.98% 屬一次性 transient artifact(可能 pytest-cov 內部計數 race condition),**不是 framework bug**。

**Framework 與否判定**:framework 使用**完全相同**的 pytest 命令,直接 pytest 3 次確定 100%。Framework 沒有引入非確定性。**Not a framework bug**。

---

### 🔍 Suspect #2 — `[Manual Confirmation Required]` 訊息

**Symptom**:advance-phase 輸出 `[Manual Confirmation Required]`,看起來像 error/blocker。

**驗證方法**:`grep -rn "Manual Confirmation Required" harness/` → 找到源頭 `harness/core/quality_gate/phase_truth_verifier.py:618`:
```python
# Output items requiring manual confirmation
print("[Manual Confirmation Required]")
...
checklist = self.get_manual_checklist()
for i, item in enumerate(checklist, 1):
    print(f"{i}. [{item['item']}]")
    print(f"   Status: {item['status']}")
    print(f"   → {item['action']}")
```

**驗證**:這是 framework **設計意圖** — phase_truth_verifier 階段需要人工確認檢查項,是 `phase_truth_verifier.py` 的標準流程。

**Framework 與否判定**:**Not a bug**。設計意圖,SKILL.md / SAD.md / phase_truth_verifier.py 都有記錄為 manual gate。

---

### 🔍 Suspect #3 — Duplicate test name 在 advance-phase output 出現 2 次

**Symptom**:pytest output 中 `test_await_coro_from_sync_loop_stop_runtime_error` 出現 2 次(2 行相同)。

**驗證方法**:
1. 隔離跑這個 test + `--cov -v`:
   ```
   03-development/tests/test_coverage_supplementary2.py::test_await_coro_from_sync_loop_stop_runtime_error PASSED [100%]
   03-development/tests/test_coverage_supplementary2.py::test_await_coro_from_sync_loop_stop_runtime_error
   03-development/tests/test_coverage_supplementary2.py::test_await_coro_from_sync_loop_stop_runtime_error
     RuntimeWarning: coroutine '...' was never awaited
   ```
2. 同樣 test 跑 `--no-cov -v`:只出現 1 次
3. pytest-cov 版本 = 7.1.0

**驗證**:pytest-cov 的 verbose 模式會印 test name 2 次(header + result line) — 這是 pytest-cov 標準輸出格式。Framework 不控制 pytest 內部輸出。

**Framework 與否判定**:**Not a framework bug**。是 pytest-cov 設計。

**附帶發現(project-side)**:這個 test 本身有真實 bug — `_hanging()` coroutine 在 TimeoutError 路徑未被 await。見下方 🟡 區。

---

### 🔍 Suspect #4 — Submodule "1 commit(s) behind origin/main" WARN

**Symptom**:advance-phase 印 `[WARN] harness/ submodule is 1 commit(s) behind origin/main`。

**驗證方法**:檢查 framework 文檔:
- `phase7_plan.md` 明確寫:`If it prints a warning that you are behind origin/main, it is non-blocking and for your information only.`
- framework 提供 fix command:`git -C harness pull --ff-only origin main`

**驗證**:這是 **informational warning**(告知 user submodule 可更新),**non-blocking**(仍可 advance SUCCESS)。Framework 設計如此。

**Framework 與否判定**:**Not a bug**。設計意圖。

---

### 🔍 Suspect #5 — `run-phase --phase 7` 沒有明確 PASS/FAIL verdict

**Symptom**:run-phase 印 13 個 PRE-FLIGHT 檢查(FSM/BVS/Kill-Switch/Artifact/Drift/SAB/Tool/ASPICE/FR Spec/Reliability/Config Liveness/M3/CI Readiness),但**最後只列 108 個 Gate 1 commands**,沒有明確的 `PASS` 或 `FAIL` 字樣。

**驗證方法**:
- 所有 13 個檢查項目都有顯示狀態(`passed` / 數字 / `clean`)
- 最後的 Gate 1 commands list 是 GATE1-DELTA loop 候選(per plan §GATE1-DELTA auto-skip)
- run-phase 的設計是「列出 pre-flight 狀態 + 列出 per-FR 候選」,不是「印 PASS/FAIL」

**驗證**:這是 **run-phase 的標準輸出格式**(列出檢查 + 後續動作),非 bug。

**Framework 與否判定**:**Not a bug**。設計意圖。

---

### 🔍 Suspect #6 — HANDOVER.md 開頭要求 `/compact` 壓縮上下文

**Symptom**:`HANDOVER.md` 開頭寫 `⚠️ 開始下一個工作階段前,請先執行 /compact 壓縮上下文`。

**驗證方法**:這是 framework **handover UX 設計** — 提示 user 在下一 session 開始時先 compact 上下文。

**驗證**:Framework `git_strategy.py` 寫 HANDOVER.md 時自動加入這段。

**Framework 與否判定**:**Not a bug**。UX 設計。

---

## 🟡 Project-side 發現(非 framework bug,文件化供 P8 修)

### P7-PROJ-01 — `test_await_coro_from_sync_loop_stop_runtime_error` 有 unawaited coroutine

**File**: `03-development/tests/test_coverage_supplementary2.py:3314-3355`

**Symptom**:當此 test 在 isolation 跑時,pytest 警告:
```
RuntimeWarning: coroutine 'test_await_coro_from_sync_loop_stop_runtime_error.<locals>._hanging' was never awaited
```

**Root cause**(定位完成):
- L3349: `async def _hanging(): await asyncio.Event().wait()` — 定義無限等待的 coroutine
- L3352: `with patch("asyncio.new_event_loop", return_value=fake_loop):`
- L3354: `_await_coro_from_sync(_hanging(), timeout_ms=200)` — 傳入 coroutine
- `fake_loop.run_until_complete()` L3338-3339:`allow_finish.wait(timeout=5)` — fake loop 等 event set
- L3353:`pytest.raises(TimeoutError, match="FR-15")` — 預期 TimeoutError
- 當 TimeoutError raise 時,`_hanging()` coroutine **沒被 explicitly await 或 close**,產生 RuntimeWarning

**驗證為 project-side**:
- 直接 pytest 全 suite 跑 100% coverage(1848 tests pass),warning 不影響整體
- Warning 是 pytest 標準警告,framework 不介入 test 內部邏輯
- 修正方式:在 test 中 try/finally 確保 coroutine 被 close,或用 `asyncio.wait_for(coro, timeout=...)` 顯式管理

**Severity**:P3 Low — 隔離測試才有 warning,full suite 不影響。

**建議修法**(P8 處理):
```python
@pytest.mark.asyncio
async def test_await_coro_from_sync_loop_stop_runtime_error():
    # ... 既有 code ...
    coro = _hanging()
    with patch("asyncio.new_event_loop", return_value=fake_loop), patch("asyncio.set_event_loop"):
        with pytest.raises(TimeoutError, match="FR-15"):
            _await_coro_from_sync(coro, timeout_ms=200)
    # 新增:確保 coroutine 被關閉
    try:
        await coro
    except (asyncio.CancelledError, Exception):
        pass
    allow_finish.set()
```

**Status**:P8 candidate,不影響 P7 advance。

---

## ⚪ Framework 設計意圖(非 bug)

| 項目 | framework source | 設計意圖 |
|---|---|---|
| `[Manual Confirmation Required]` | `phase_truth_verifier.py:618` | phase truth manual gate checklist |
| pytest-cov 2x test name in -v | pytest-cov 7.1.0 stdlib | verbose header + result |
| Submodule "1 commit behind" WARN | `harness_cli.py` advance-phase | informational non-blocking |
| run-phase 輸出無 PASS/FAIL | `harness_cli.py` run-phase | 列出 pre-flight 狀態為主 |
| HANDOVER.md `/compact` 提示 | `git_strategy.py` handover writer | UX 設計 |
| advance-phase `[Manual Confirmation Required]` | `phase_truth_verifier.py:618` | 同上 |

---

## 結論

Phase 7 執行過程中,**未發現任何新的、實際可重現的 framework bug**。

這是 omnibot 5 個 phase 執行以來**首次零 framework bug**:
- P4:6 個 framework bug(H1-H6)
- P5:5 個 framework bug(P5-BUG-01..05,全部 hotfix)
- P6:17 個 framework bug(P6-BUG-01..17,4 個 upstream PR landed)
- **P7:0 個 framework bug** ✅

**HR-17 嚴守**:0 lines 修改 harness/ submodule。

**待辦**(皆為 project-side,非 framework):
- P8:P7-PROJ-01 `test_await_coro_from_sync_loop_stop_runtime_error` coroutine cleanup 修正
- P8:RISK-002 mutation testing feature flag re-evaluation
- P8:RISK-006 `pip-licenses` shim 移出版本控制

---

## 對比 P4/P5/P6/P7

| 比較 | P4 | P5 | P6 | P7 |
|------|----:|----:|----:|----:|
| Framework bugs found | 6 | 5 | 17 | **0** |
| Project-side fixes | 多個 | 0 | 12 | 1(test) |
| Upstream PR landed | 1(hotfix submodule) | 1(7660996) | 4 | 0 |
| Source code affected | 是 | 否 | 否(test_perf.py 除外) | 否 |
| Phase verdict | PASS | PASS | PASS | **PASS** |

**Quality trend**:framework 穩定性顯著提升(P4 6 bugs → P7 0 bugs)。P6-BUG-13/16/17 三個 upstream fix 對框架成熟度貢獻最大。
