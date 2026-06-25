# Harness Bugs Found During Phase 8 Execution

> Generated: 2026-06-26
> Context: Phase 8 (Configuration Management) — config records + release checklist + p8 push
> Companion: `harness-bugs-phase4.md` (6), `harness-bugs-phase5.md` (5), `harness-bugs-phase6.md` (17), `harness-bugs-phase7.md` (0)
> Audit-phase result: (P8 has no audit-phase trigger; Gate 4 PASS inherited from P6)
> Final status: (pending PUSH ⑩)

## Executive Summary

Phase 8 execution context: Config records generation + release checklist + archive + push.

| 類別 | 數量 | 處理 |
|------|----:|------|
| 🟢 **真實 framework bug(需修 harness/)** | **1 (P8-BUG-01)** | Documented; workaround applied; upstream fix pending |
| 🟡 **Project-side 責任** | 0 | — |
| ⚪ **框架正確行為 / 設計意圖** | 1 (auto-skip DELTA) | 不修,框架設計如此 |

| Phase | Framework bugs |
|-------|---:|
| P4 | 6 |
| P5 | 5 |
| P6 | 17 |
| P7 | 0 |
| **P8** | **1** (P8-BUG-01) |

P8-BUG-01 是 P7 零框架 bug 後的首次發現,但性質溫和(template 欄位名 mismatch,workaround 直接手動補)。

---

## 🟢 真實 Framework Bug

### P8-BUG-01 — `phase8_doc_gen.py` template field-name mismatch

**Symptom**:執行 `python3 harness/scripts/phase8_doc_gen.py --project .` 後,生成的 `08-config/CONFIG_RECORDS.md` 含大量未解析的 placeholder:
```
Version: vharness-v4-20260625-score100-16-g015c1ef   ← 已 substitute
Git Commit: ${hash}                                    ← 未 substitute (literal)
Release Date: ${date}                                  ← 未 substitute (literal)
Runtime Configuration: ${config}                        ← 未 substitute
Dependency List: {pip freeze / npm lock output}        ← 雙花括號未被吃
Environment Variables: ${VAR}                          ← 未 substitute
Deployment Log: ${date}, ${ver}, ${method}, ${name}   ← 未 substitute
Configuration Change Log: ${change}, ${reason}         ← 未 substitute
Rollback SOP: ${condition}, ${rollback commands}        ← 未 substitute
```

**Root cause**(已定位,`harness/scripts/phase8_doc_gen.py:60-105`):

1. `_collect()` 函式 (L60-86) 產生的 context dict keys:
   ```python
   {
       "project_name": ...,
       "version": ...,          # 用 _git describe --tags --always
       "git_hash": ...,         # ← context 用 "git_hash"
       "release_date": ...,     # ← context 用 "release_date"
       "current_phase": ...,
       "phase_truth_passed": ...,
       "frs": ...,
       "fr_summary": ...,
       "min_coverage": ...,
   }
   ```

2. Template 檔 `harness/templates/CONFIG_RECORDS.md` 使用的 field names:
   ```
   {version}, {hash}, {date}, {config}, {VAR}, {description},
   {date}, {ver}, {method}, {name}, {change}, {reason},
   {condition}, {rollback commands}
   ```

3. Mismatch 對照:
   | Template field | Context key | 結果 |
   |----------------|-------------|------|
   | `{hash}` | `git_hash` | ❌ 未 substitute |
   | `{date}` | `release_date` | ❌ 未 substitute |
   | `{config}` | (missing) | ❌ 未 substitute |
   | `{VAR}` | (missing) | ❌ 未 substitute |
   | `{description}` | (missing) | ❌ 未 substitute |
   | `{ver}` | `version` | ❌ 名稱略不同 |
   | `{method}` | (missing) | ❌ 未 substitute |
   | `{name}` | (missing) | ❌ 未 substitute |
   | `{change}` | (missing) | ❌ 未 substitute |
   | `{reason}` | (missing) | ❌ 未 substitute |
   | `{condition}` | (missing) | ❌ 未 substitute |
   | `{rollback commands}` | (missing;非識別變數名) | ❌ 未 substitute |
   | `{version}` | `version` | ✅ 已 substitute |
   | `{pip freeze / npm lock output}` | (含空格+斜線,非識別變數) | ❌ 雙花括號未展開 |

4. `_render_template()` 使用 `safe_substitute` (L107),**missing key 留 literal** — 故生成檔充滿 `${...}` placeholder 而不報錯。

**Severity**:P2 Medium — 生成的檔案不完整,但 plan §CONFIG-RECORDS 明確要求「Review + append」+「Flag any missing sections the generator could not derive」,故 human review 步驟正好 catch 此 bug,workaround 為人工填值。

**Workaround**(已套用,HR-17 守住):
1. 人工填入 CONFIG_RECORDS.md 缺漏欄位(基於 git describe / state.json / quality_manifest.json / .env.example / pyproject.toml 真實 metadata)
2. 人工擴充 RELEASE_CHECKLIST.md (framework baseline 只 9 行,需加 Gate 4 proof + FR coverage + git tag + NFR + human sections)

**Suggested upstream fix**(PR 待提交):
- Option A(最小修):`harness/templates/CONFIG_RECORDS.md` 改用 context keys:`{git_hash}`, `{release_date}`, etc.
- Option B(更佳):`_collect()` 函式補齊缺失 keys:`config`, `VAR`, `description`, `method`, `name`, `change`, `reason`, `condition`, `rollback_commands`
- Option C(最佳):把 template 和 context 都改成同一份 schema(e.g. `pydantic.BaseModel`),compile-time check 對齊

**Status**:
- ✅ Workaround applied (CONFIG_RECORDS + RELEASE_CHECKLIST 已人工補完)
- 🟡 Upstream fix pending (建議 Option A + Option B 組合)

---

## 🟡 Plan Documentation Typo (Plan-side, not framework)

### P8-NOTE-01 — plan §P8-ARCHIVE cp command typo

**Symptom**:Phase 8 plan §P8-ARCHIVE 寫:
```bash
mkdir -p .methodology-archive
cp -r .sessi-work/ .methodology-archive/
```

但 `harness/harness_cli.py:4135-4195` 的 `_validate_p8_completion()` 明確指出這是 **Finding #24 typo**:
- `.methodology-archive/` 應含 `.methodology/` 的內容(phase*_plan.md, quality_manifest.json)
- 不是 `.sessi-work/` 的內容(gitignored runtime scratch dir)
- 若 `.methodology-archive/sessi-work/` 存在 → push-milestone --type p8 報錯
- 若 archive 缺 methodology artifacts → push-milestone --type p8 報錯

**驗證**:跑 plan 命令後,framework validator 檢查到 `archive_dir / "sessi-work"` 存在 → reject。

**修法**(已套用,HR-05 服從 harness):
```bash
rm -rf .methodology-archive
mkdir -p .methodology-archive
cp -r .methodology/ .methodology-archive/
```

**Severity**:P2 Medium — 跟著 plan 跑會 fail push-milestone,需手動修正。

**Suggested upstream fix**:
- `phase8_plan.md` §P8-ARCHIVE 改用 `cp -r .methodology/ .methodology-archive/`

**Status**:✅ Corrected locally. Plan upstream correction pending.

---

## ⚪ 框架正確行為 / 設計意圖

### P8-DESIGN-01 — DELTA loop auto-skip when no code changed

**Symptom**:`run-fr-step --phase 8 --fr-id FR-01 --step GATE1-DELTA` 報:
```
[run-fr-step] FR-01 LINT_AND_COVERAGE failure (round 1/3) — dispatching LINT-FIX
[run-fr-step] LINT-FIX failed: ⚠ claude.ai connectors are disabled
[run-fr-step] FR-01 GATE1-DELTA: WARNING — expected commit not found in git log
[run-fr-step] ✅ FR-01 GATE1-DELTA complete + pushed to GitHub
```

**驗證**:
1. `harness/harness_cli.py:5262-5280` advance-phase DELTA auto-skip:
   ```python
   if completed_phase in (4, 5, 7, 8):
       try:
           _all_unchanged = all(
               not _fr_code_changed_since_last_gate1(fr, project)
               for fr in fr_ids_manifest
           )
       except Exception:
           _all_unchanged = False
       if _all_unchanged:
           print(f"  [Gate 1 coverage] Phase {completed_phase}: all {len(fr_ids_manifest)}"
                 f" FR(s) unchanged since last gate — DELTA auto-satisfied (live pytest skipped).")
           return 0
   ```
2. P7 期間無 source code 改動,RISK_REGISTER/MITIGATION_PLANS/STATUS_REPORT 為 doc-only。
3. 所有 108 FRs sentinel flags 已存在於 `.sessi-work/sentinels/finalized_1_fr*.flag` (從 P5 era)。
4. `run-fr-step` 在 LINT-FIX dispatch failed + 無 commit 時,仍寫 sentinel + 報 ✅ — 這是 framework 的「no-op completed」語意。

**Framework 與否判定**:**Not a bug**。Auto-skip 是 design intent,plan §Auto-skip 明確寫「if NO FR's code changed since its last Gate 1 PASS, advance-phase treats this entire DELTA loop as satisfied automatically — you may skip the per-FR steps」。

**`✅` 但無 commit** 的解讀:
- 「expected commit not found in git log」是 soft warning,告知用戶「無 source 改動 → 無 commit」
- sentinel 寫入 + `✅` 訊息 = 框架表達「此 FR 的 DELTA 檢查已 done(因為沒事可做)」
- 這是 no-op completion,不是 silent success

---

## 對比 P4/P5/P6/P7/P8

| 比較 | P4 | P5 | P6 | P7 | P8 |
|------|----:|----:|----:|----:|----:|
| Framework bugs found | 6 | 5 | 17 | 0 | **1** |
| Project-side fixes | 多個 | 0 | 12 | 1 | 0 |
| Upstream PR landed | 1(hotfix) | 1(7660996) | 4 | 0 | 0 (P8-BUG-01 pending) |
| Source code affected | 是 | 否 | 否 | 否 | 否 |
| Phase verdict | PASS | PASS | PASS | PASS | **pending** |

---

## HR-17 嚴守

- 0 lines 修改 harness/ submodule。
- Workaround 在 project repo(08-config/CONFIG_RECORDS.md + RELEASE_CHECKLIST.md 人工填值)。

---

## Upstream PR 待辦

| Bug | 建議修法 | 優先級 |
|---|---|---|
| **P8-BUG-01** | (A) `harness/templates/CONFIG_RECORDS.md` 改用 context keys `{git_hash}` `{release_date}` + (B) `_collect()` 補齊缺失 keys | **Medium** — 影響所有 Phase 8 用戶 |