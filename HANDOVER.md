# Harness Methodology — Session Handover

**Checkpoint**: `P7-exit-20260625`  
**Phase**: P7 — Risk Register  
**Generated**: 2026-06-25T11:40:47Z

> ⚠️  **開始下一個工作階段前，請先執行 `/compact` 壓縮上下文**，再從「接下來的工作」繼續。

---

## ▶ 立即開始（兩步）

```bash
# 1. Clone (if working directory cleared)
git clone --recurse-submodules https://github.com/johnnylugm-tech/omnibot.git && cd omnibot

# 2. Read plan and start Phase 8
cat .methodology/phase8_plan.md
# Follow SKILL.md §0.1 Phase 8 entry check, then execute
```

---

## 快速接手指令（詳細）

```bash
# Clone (--recurse-submodules required for harness submodule)
git clone --recurse-submodules https://github.com/johnnylugm-tech/omnibot.git /tmp/omnibot && cd /tmp/omnibot

# Confirm latest commits
git log --oneline -3

# Confirm FSM state
cat .methodology/state.json   # expected: phase=7 state=RUNNING last_gate=4 last_fr=FR-99

# Read active plan
cat .methodology/phase8_plan.md
```

| 欄位 | 值 |
|------|----|
| Remote | `https://github.com/johnnylugm-tech/omnibot.git` |
| Branch | `main` |
| State | `phase=7 state=RUNNING last_gate=4 last_fr=FR-99` |
| Plan | `.methodology/phase8_plan.md` |

---

## 任務背景

P7 Risk Register: all risks documented.

## 目前執行狀況

P7 Risk Register complete. Risk log committed.

## 接下來的工作

1. Proceed to P8: Config & Records
2. Finalize all configuration records
3. On P8 done → call commit_and_push_p8()

## 注意事項

- 100% follow SKILL.md
- Do NOT commit `.sessi-work/` or `.methodology/` runtime artifacts
- Git failures are warnings — they never block the pipeline

---
*由 `HandoverGenerator` 自動生成。下次 push 時此檔案將被覆寫。*
