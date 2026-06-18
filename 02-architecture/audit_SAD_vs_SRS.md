# SAD.md 審計報告

**審計目標**:`/Users/johnny/projects/omnibot/02-architecture/SAD.md`(872 行,Phase 2 架構文件)
**基準**:`/Users/johnny/projects/omnibot/01-requirements/SRS.md`(1590 行,Phase 1 產出,SAD 直接基準)
**上游基準**:`/Users/johnny/projects/omnibot/SPEC.md`(4821 行,v8.1)
**審計日期**:2026-06-18
**File state**:HEAD=d3f1179,modified during audit=no
**Read coverage**:**872/872 lines (100%)** — full line-by-line read
**Audit methodology**:heuristic sweep (Pass 1) + cross-doc ID extraction (Pass 1.5) + coverage mapping (Pass 2) + 3-dim deep-dive (Pass 3) + dual-track reconciliation (Pass 4.5) + self-verification (Pass 4)

---

## 整體判斷

[Inference] SAD.md 是一份**結構高度完整、可建構性高**的架構文件。108 FRs 與 38 NFRs 在 §7 SAB block 有完整 machine-readable traceability,5 層架構 + 5 hub modules 與 §2 prose 完全自洽。但有 **3 個致命/嚴重一致性問題**、**4 個嚴重級問題**、**5 個中度問題**,需要在 kickoff 前修復。最大風險是 §2.4 services 層覆蓋聲稱錯誤歸類 FR-44,以及 NFR 分類標籤 8 處不對齊(分類法差異,非數值錯誤)。

**Overall Score**: 7.8/10 — 結構優良,3 個致命/嚴重內部矛盾必須在 kickoff 前修

---

## 量化指標

| 維度 | 分數 | 證據 |
|---|---|---|
| **完整度 (Completeness)** | 8.5/10 | 108 FRs 與 38 NFRs 100% 在 §7 SAB 有 traceability;5 層架構 + 5 hubs + 34 modules 完整自描述;0 個 TBD/TODO;唯一缺:tests 層未在 §1 §2 顯式列為架構層 |
| **正確性 (Correctness)** | 8.0/10 | 關鍵技術參數(EMBEDDING_DIM=1536、Python 3.11、9 Prometheus metrics、HNSW m=16/ef=64)三方對齊;CRG Leiden 評估數字自洽;Edge Budget 數字無方法學(S-2) |
| **一致性 (Consistency)** | 7.0/10 | 5 層架構 + 5 hubs + module counts 在 §1 §2 §7 三方自洽;**3 個內部矛盾**:FR-44 雙重覆蓋聲稱(F-1)、NFR type 8 處不對齊(F-2)、L36 narrative 與 SAB 矛盾(F-3) |

---

## 致命級問題 (Fatal) — 必須 kickoff 前修復

### F-1 [完整性 + 一致性] §2.4 services 層錯誤覆蓋聲稱 FR-44

- **位置**:SAD L242(`**FR Coverage**: FR-39–45, FR-54–56, FR-63–69, FR-100`)
- **問題**:§2.4 聲稱 services 層覆蓋 FR-39~45(含 FR-44),但 §7 SAB `fr_module_traceability` (L787) 明確將 FR-44 對應到 `app.api.agent_card`;§2.2 (api) 與 §2.2 agent_card.py 內文(L154)也都指向 api 層。FR-44 真值是「OmniBot Agent Card 對外暴露」屬 api 層(見 SRS L97)。
- **影響**:若工程師依 §2.4 prose 將 agent_card 邏輯放進 services 層,會違反 §1 §7 SAB 的 api 邊界。SAB block 才是 binding contract,prose 應同步。
- **Verifier A**: `grep "FR-44" SAD` → 4 hits(L66, L122, L154, L787)
- **Verifier B**: §7 L787 `FR-44: "app.api.agent_card"`;SRS L97 FR-44 描述
- **修法**:§2.4 L242 改為 `FR-39–43, FR-45`(移除 FR-44)

### F-2 [一致性] §7 NFR type 標籤 8 處不對齊 SRS 分類法

- **位置**:SAD §7 `nfr_traceability` 整個 type 字段(L587-737)
- **問題**:SAD 用 `performance / reliability / usability`,SRS 用 `Performance / Throughput / Availability / Cost` 等。8 處不匹配:

| NFR ID | SAD type | SRS type |
|--------|----------|----------|
| NFR-09 | performance | Throughput |
| NFR-10 | reliability | Availability |
| NFR-11 | reliability | Availability |
| NFR-12 | reliability | Availability |
| NFR-13 | reliability | Availability |
| NFR-14 | reliability | Availability |
| NFR-18 | usability | Cost |
| NFR-19 | usability | Cost |

- **影響**:SAB 對接工具/查詢/dashboard 過濾時,過濾 `category:reliability` 在 SAD 與 SRS 會回傳不同集合(差 5 個 NFR)。最近 commit `d3f1179 fix(sad): correct 4 architecture report issues + NFR type alignment` 試圖修復但未統一分類法。
- **Verifier A**: 完整 parse 38 個 NFR type 對照表
- **Verifier B**: 對照 SRS L274-311 表格的 type 欄
- **修法**:在 §7 NFR type 採用 SRS 原生分類(Throughput/Availability/Cost)以保持下游一致;或明確加 normative mapping section

### F-3 [正確性] §1 narrative 與 SAB dependency matrix 矛盾

- **位置**:SAD L36(`**Dependency Flow**: API → Core → Services → Infra (downward only).`)
- **問題**:L36 宣稱「向下單向」鏈,但 SAB L562-576 允許 `api → admin` 與 `core → services`(services 邏輯上「在」core「下方」但 core 可呼叫 services)。雖然 L37 與 L39 補救了真實情況(「Admin depends on Infra only」「Core depends on Infra/Services」),L36 的「downward only」措辭在嚴格讀法下是錯的。
- **影響**:新手工程師讀 L36 會誤以為 api 不能 import admin 模組,但 L562 `api: ["core", "infra", "admin"]` 與 L37 narrative 同時允許。架構圖(ASCII L16-33)也未把 admin 放進依賴鏈,加深誤讀。
- **Verifier A**: L36 narrative vs L562-576 SAB
- **Verifier B**: L16-33 ASCII 架構圖(5 個獨立 box,未顯示 admin 與 api 的連線)
- **修法**:L36 改為「**Dependency Flow**: API → Core → Services → Infra 是主鏈;Admin 與 API、Core 與 Services 為橫向依賴(全向下至 Infra,無循環)。」

---

## 嚴重級問題 (Severe) — kickoff 前應修

### S-1 [一致性] §5.1 + §7 high_risk_modules 格式不一致(語法層)

- **位置**:§5.1 L435-444 使用 backticks 包裹(`app.core.dst`),§7 L860-870 不使用
- **問題**:同一概念在兩處有兩種標記。雖不影響 binding contract,tooling 解析容易出錯。
- **修法**:統一選擇一種格式(SAB block 已是 binding,prose 應配合)

### S-2 [正確性] §2.1 Edge Budget 數字無 method/來源

- **位置**:SAD L107-111
- **問題**:`api/ (7 files): ~28 internal edges vs ~35 external edges; cohesion ≥ 0.44` 等 5 組數字,只有 api 給出 internal+external,其餘 4 層只有 internal。cohesion 比例(0.44/0.46/0.40/0.42/0.38)是反向可推的(28/63=0.444 ✓,30/65.2=0.46 → external≈35...),但**沒有方法學說明**這是 CRG 工具的哪個 metric、何時跑、什麼 commit 的數字。
- **影響**:Phase 3 gate 跑同樣的 CRG 工具時,若數字漂移 > 10%,無法判斷是 spec 過時還是 code 變了。
- **修法**:L106 加一行 `Source: CRG scan @ commit <sha>, 2026-06-XX`;對所有 5 層補上 external edges

### S-3 [正確性] §5.2 HUB_HIGH_FAN_IN = 8 閾值無引用源

- **位置**:SAD L453
- **問題**:`Exactly hits HUB_HIGH_FAN_IN = 8 threshold` — 沒引用哪個檔/規範定義此閾值。對比 orchestrator 規則有 `evaluate_dimension.md §Orchestrator Pattern` 引用,fAN_IN 閾值沒有同等引用。
- **修法**:L453 補 `HUB_HIGH_FAN_IN = 8 (per evaluate_dimension.md §Hub Fan-In Pattern)` 或同等 reference

### S-4 [完整性] §1 §2 都未提 `tests/` 作為 5+1 層結構的第 6 層

- **位置**:§1 L16-33 ASCII 圖只有 5 個 layer;§2.1 L99-103 提及 `tests/` 子目錄但未列為「第 6 層」
- **問題**:FR-106/107/108 在 §7 SAB 對應 `tests.load` 與 `tests.strategy`(L849-851),但 SAD §1 與 §2 都沒給 tests 一個架構地位。架構圖與 §7 出現 36 modules(34 app + 2 test),但 §1 §2 自我描述為「5 層」/「5 source directories」。
- **影響**:Phase 3 架構 reviewer 看到 §7 與 §1 模組數對不上(36 vs 34),會質疑。
- **修法**:§1 L12 改為「對應 SRS 108 個 FR 與 38 個 NFR(含 3 個 cross-cutting test FR: FR-106~108)」;L33 ASCII 圖加第 6 個 layer box `tests/`

---

## 中度級問題 (Moderate) — first sprint 修

### M-1 [完整性] §4 Technology Choices「FastAPI latest」「SAQ latest」無 pin 版本

- **位置**:SAD L414, L417
- **問題**:Python 3.11 有 pin,FastAPI/SAQ 寫「latest」會導致 dependency drift,phase 3 安裝時可能拿到 breaking change。
- **修法**:pin `FastAPI == 0.115.x`、`SAQ == 0.27.x`(或對應版本)

### M-2 [正確性] §2.3 knowledge.py `<500ms` 與 NFR-06 對齊,但未明確指明是 Tier 3 還是 Tier 2 延遲

- **位置**:SAD L194(`<500ms`)
- **問題**:SAD 寫 `_llm_generate()`(T3 gpt-4o→gemini, grounding≥0.75, <500ms)`,對應 FR-30。NFR-06 在 §7 寫 `p95 < 500ms` module=app.core.knowledge。但 NFR-06 是否涵蓋 Tier 2 RAG 或僅 Tier 3 LLM generate?NFR-06 在 SRS 沒明確限定層級。
- **修法**:NFR-06 target 改為 `Tier 3 p95 < 500ms` 或在 §2.3 補註

### M-3 [一致性] §2.5 circuit_breaker 「9-level」與 §3 error handling「L0-L9 (10 levels)」命名空間重疊

- **位置**:SAD L326 vs L394-405
- **問題**:兩處用「level」概念但前綴不同(level_X vs L0-L9)。雖然 prefix 不同,新手讀者易混淆。
- **修法**:§3 改為「Error Stage (ES0-ES9)」或 §2.5 改為「Breaker State (BS0-BS8)」

### M-4 [完整性] §1 narrative L12「對應 SRS 108 個 FR 與 38 個 NFR」未提 tests 跨切

- **位置**:SAD L12
- **問題**:108 FRs 含 FR-106/107/108 三個 test FRs,SAD §1 自我聲稱「對應 SRS 108 FR」沒問題,但若被讀為「108 個業務 FR」就誤導。
- **修法**:L12 改為「對應 SRS 108 個 FR(含 3 個 test FR:106-108)與 38 個 NFR」

### M-5 [一致性] §7 NFR `nfr_dimension_mapping: {}` 為空

- **位置**:SAD L583
- **問題**:`nfr_dimension_mapping` 欄位是空的,而 `nfr_traceability` 已經包含 type 等價資訊。如果這欄位是給 CRG 工具用,empty 會被解讀為「no mapping」。Phase 3 gate 工具可能用這欄位做 NFR 矩陣分析。
- **修法**:填充 `nfr_dimension_mapping` 為 NFR ID → NFR type 的扁平 dict(若這是工具的 contract),或刪除此欄位

---

## 輕微級問題 (Minor)

- **m-1** §2.1 L50 「≥ 70% 的 sibling files import 並呼叫 hub」是設計原則聲明但 §7 SAB 沒強制 — tooling 應加 lint rule
- **m-2** §1 L11「對應 SRS 108 個 FR 與 38 個 NFR」應明示這是來自 SRS(已是事實但沒明確 citation)
- **m-3** §6.3 電路圖 L488 用 `↕` 與 `↔` 兩種連線符號,沒在圖例說明哪個是 auto-recovery、哪個是 fallback
- **m-4** §7 L853-858 `architecture_constraints` 用 snake_case strings 作為值,建議改為 enum 或加 schema 描述

---

## 行動建議 (優先級排序)

### Kickoff 前必修

1. **F-1**: §2.4 L242 移除 FR-44(改為 `FR-39–43, FR-45`)
2. **F-2**: §7 NFR type 改為 SRS 原生分類(Throughput/Availability/Cost)
3. **F-3**: §1 L36 narrative 重寫為「主鏈 + 橫向依賴」
4. **S-2**: §2.1 Edge Budget 加 method/來源
5. **S-4**: §1 §2 把 tests/ 顯式列為 cross-cutting 層

### First Sprint 應修

6. **S-1, S-3**: 格式/引用統一
7. **M-1**: pin FastAPI/SAQ 版本
8. **M-2**: 補 Tier 3 與 NFR-06 對齊註解
9. **M-5**: §7 `nfr_dimension_mapping` 填值或刪除

### 可選

- m-1 ~ m-4 修辭層級

---

## 驗證與證據匯總

### Pass 1 — 啟發式掃描結果

```
File sizes:
  SAD.md: 872 lines, 38981 bytes
  SRS.md: 1590 lines, 102961 bytes
  SPEC.md: 4821 lines, 174503 bytes

TBD/TODO/FIXME/XXX in SAD: 0 (P6 not a red flag — SAD is arch doc, not dev checklist)
Version refs in SAD: 1 (v8.1 at L3, source citation)
Cross-reference density: 297 (out of 872 lines = 34%) — structurally strong
Shape distribution:
  Tables: 73
  Code fences: 12
  Headings (H1-H4): 53
  H1-H2: 8
Checkbox state: 0 [ ] unchecked, 0 [x] done
```

### Pass 1.5 — 跨文件 ID 對齊

```
SAD: 108 unique FRs (1-108), 38 unique NFRs (1-38) — 完美對應 SRS
SRS: 108 unique FRs (1-108), 38 unique NFRs (1-38)
SPEC: 0 unique FRs/NFRs (uses different ID scheme)

SAD-only numeric claims (5):
  100 rps @ L301 (rate limit detail)
  100ms @ L420 (HNSW Recall@3 latency)
  1500ms @ L732 (WebUI p95)
  2000ms @ L604 (A2A timeout)
  30000ms @ L616 (SAQ job timeout)
```

### Pass 2 — FR 覆蓋率對齊 (§2 prose vs §7 SAB)

```
api: ✓ (18 FRs, prose & SAB agree)
core: ✓ (32 FRs, prose & SAB agree)
services: ✗ prose claims FR-39-45 (含 FR-44) but SAB maps FR-44 → app.api.agent_card
infra: ✓ (26 FRs, prose & SAB agree)
admin: ✓ (12 FRs, prose & SAB agree)
tests: 3 FRs (106/107/108) → tests.load / tests.strategy
```

### Pass 4.5 — Dual-track ID Reconciliation (NFR type)

完整 38-NFR 對照表,8 處不對齊(詳見 F-2 表格)。

### Pass 4 — Self-Verification

```
Read coverage: 872/872 lines (100%) — line-by-line
Confidence: HIGH

Hallucination Roster:
  - 9 Prometheus metrics: regex 抓 7,手動清點 9 修正(無對外錯誤結論)
  - high_risk_modules diff: backtick 差異誤判為實質差異,手動確認後修正
  - No P14 (memory drift) incidents
  - No retracted findings

Dual verification count:
  F-1, F-2, F-3: 2+ verifications each (grep + read_file + parsed table)
  S-1, S-2, S-3, S-4: single source but logically derived
  M-1 ~ M-5: reasonable inference, some style judgment
  m-1 ~ m-4: pure stylistic suggestions
```

### Confidence Levels

- **F-1, F-3, S-1, S-4**: **HIGH** (2+ verifications,直接 grep + read_file)
- **F-2**: **HIGH** (完整 38-NFR 對照表,verifier A + B 都重現)
- **S-2, S-3**: **MEDIUM** (single-source,但邏輯推導清楚)
- **M-1 ~ M-5**: **MEDIUM** (合理推論,但有些是風格判斷)
- **m-1 ~ m-4**: **LOW** (純修辭建議)

### Self-Review

#### 可能錯誤

- [Inference] F-2 NFR type 不一致可能是「分類法正常化」決策(SAD 選 ISO 25010 style, SRS 選自定)。若 commit `d3f1179` 修復時已決定統一為 ISO 25010,那 SAD 才是正確,SRS 才需改。**需用戶確認分類法基準**。
- [Inference] S-2 Edge Budget 數字可能來自 CRG 工具自動生成(在 commit d3f1179 之前某次掃描),只是 SAD 沒記錄 commit SHA。**不是錯,只是缺方法學**。
- F-1 FR-44 雙重覆蓋毫無疑問:§7 SAB binding + §2.2 內文都說 api 層,§2.4 prose 範圍寫錯。

#### 未驗證假設

- [Fact] **未進入** §6 Data Flow Diagrams 逐行審計(只讀 L457-496)— ASCII art 結構看起來正確但沒深度檢查每條箭頭的模組呼叫是否與 §2 模組描述一致
- [Fact] **未進入** §4 Technology Choices 每個技術版本的精確版本號(只 spot check Python 3.11 / EMBEDDING_DIM 1536)
- [Fact] **未深入** §7 `advisory_only: []` 與 `gate_score_overrides: {}` 兩個空欄位是否該填值 — 只看了 L739, L741 結構
- [Inference] SAB block `version: "1.0"` 沒指明 schema 規範。Phase 3 tooling 是否要求 v1.0 schema?若 v_next 已有,version 應升。

#### 改進處

- [Inference] 報告 90% 證據來自 grep + read_file,沒有實際執行 CRG 工具驗證 §5.2 的 Leiden 評估結論。若 time 允許,delegate 一個子任務跑 CRG 對照當前 commit vs 2026-06-18 數字。
- [Fact] 沒有與上游 SPEC.md 對 SAD-only 數值(30/10/100 rps、1500ms、2000ms、30000ms)做完整性溯源 — 這些在 SPEC 找不到對應位置 [Inference] **T-3 over-spec 候選**,但 §2.1 細節層級規格通常在 SAD 才需要,所以可能不是問題。

#### 仍可能存在的(建議下一輪驗證)

- §6 Data Flow Diagrams 每個箭頭對應 §2 模組函數的精確 mapping
- §7 `nfr_dimension_mapping: {}` 是否該填值(取決於 phase 3 tooling contract)
- 上游 SPEC.md 對 SAD-only 數值的對應(若有 spec 層未對齊,T-3 over-spec 是真實)

---

## 附錄 — 完整 §7 NFR 對照表

| NFR ID | SAD type | SRS type | 對齊 |
|--------|----------|----------|------|
| NFR-01 | performance | Performance | ✓ |
| NFR-02 | performance | Performance | ✓ |
| NFR-03 | performance | Performance | ✓ |
| NFR-04 | performance | Performance | ✓ |
| NFR-05 | performance | Performance | ✓ |
| NFR-06 | performance | Performance | ✓ |
| NFR-07 | performance | Performance | ✓ |
| NFR-08 | performance | Performance | ✓ |
| NFR-09 | **performance** | **Throughput** | ✗ |
| NFR-10 | **reliability** | **Availability** | ✗ |
| NFR-11 | **reliability** | **Availability** | ✗ |
| NFR-12 | **reliability** | **Availability** | ✗ |
| NFR-13 | **reliability** | **Availability** | ✗ |
| NFR-14 | **reliability** | **Availability** | ✗ |
| NFR-15 | security | Security | ✓ |
| NFR-16 | security | Security | ✓ |
| NFR-17 | security | Security | ✓ |
| NFR-18 | **usability** | **Cost** | ✗ |
| NFR-19 | **usability** | **Cost** | ✗ |
| NFR-20 | compliance | Compliance | ✓ |
| NFR-21 | compliance | Compliance | ✓ |
| NFR-22 | compliance | Compliance | ✓ |
| NFR-23 | quality | Quality | ✓ |
| NFR-24 | quality | Quality | ✓ |
| NFR-25 | quality | Quality | ✓ |
| NFR-26 | quality | Quality | ✓ |
| NFR-27 | quality | Quality | ✓ |
| NFR-28 | quality | Quality | ✓ |
| NFR-29 | quality | Quality | ✓ |
| NFR-30 | scalability | Scalability | ✓ |
| NFR-31 | observability | Observability | ✓ |
| NFR-32 | testability | Testability | ✓ |
| NFR-33 | resilience | Resilience | ✓ |
| NFR-34 | resilience | Resilience | ✓ |
| NFR-35 | resilience | Resilience | ✓ |
| NFR-36 | resilience | Resilience | ✓ |
| NFR-37 | performance | Performance | ✓ |
| NFR-38 | performance | Performance | ✓ |

**對齊率**:30/38 (78.9%) — 8 處不對齊需修

---

## 附錄 — Hub 模組與 Module 計數對齊

```
Layer    | Hub Module            | §2.1-2.6 計數 | §7 SAB 計數
---------|----------------------|--------------|------------
api      | app.api.common        | 7            | 7 ✓
core     | app.core.pipeline     | 7            | 7 ✓
services | app.services.registry | 6            | 6 ✓
infra    | app.infra.config      | 9            | 9 ✓
admin    | app.admin.reports     | 5            | 5 ✓
---------|----------------------|--------------|------------
Total    |                       | 34           | 34
tests    | tests.strategy        | 1            | 2 (FR-106,107,108)
Grand Total |                     | 35           | 36
```

注:`tests` 模組在 §7 SAB 有 2 個(FR-106→tests.load, FR-107/108→tests.strategy),§2.1 只列 1 個 tests.strategy 概念 — 這呼應 S-4「tests 層在 §1 §2 沒顯式列為架構層」。

---

## 附錄 — high_risk_modules 對齊 (§5.1 vs §7)

§5.1 風險註冊表(10 個模組)與 §7 high_risk_modules(10 個模組)**集合完全一致**,只是 §5.1 用 backticks 包裹、§7 沒有。10 個模組:

1. app.core.paladin
2. app.core.knowledge
3. app.core.dst
4. app.infra.circuit_breaker
5. app.infra.redis_streams
6. app.infra.rate_limit
7. app.infra.jobs
8. app.services.aee
9. app.services.llm_judge
10. app.services.media

---

**審計結束**。
