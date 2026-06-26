# OmniBot — 全情境使用者與開發者指南 (End-to-End User Guide)

> OmniBot 是一個企業級的跨平台多管道客服機器人 (Multi-platform customer service chatbot)。
> 單一 Bot 實例即可同時服務 Telegram / LINE / Messenger / WhatsApp / Web / A2A 等終端，並具備統一的對話狀態管理 (Dialogue State Tracking)、四層混合知識架構 (4-tier hybrid knowledge layer)，以及五層 Prompt-Injection 防禦機制 (PALADIN)。
>
> **狀態**: P1-P8 階段已全數完成 (Gate 4 PASS, 100 FRs registered)。

本指南涵蓋 OmniBot 的 **End-to-End 全生命週期**，並針對不同角色（終端使用者、知識管理者、客服主管、開發維運人員）提供專屬的使用情境導覽與操作說明。

---

## 1. 角色與情境導覽 (Roles & Scenarios Guide)

請根據您的角色，跳至對應的情境章節：

| 您的角色 | 關注重點 | 適用情境與章節 |
|---------|---------|-------------|
| **終端使用者 (End User)** | 跨平台互動、資安防護體驗 | [情境一：終端用戶體驗](#情境一終端用戶體驗-end-user-experience) |
| **知識管理者 (Knowledge Manager) / 業務邏輯設計師** | 匯入 FAQ 知識庫、配置對話意圖與流程 | [情境二：知識管理與業務邏輯配置](#情境二知識管理與業務邏輯配置-knowledge-manager--domain-expert) |
| **客服主管 (CS Supervisor) / 稽核員 (DPO)** | 人工客服接管機制、調閱對話紀錄與合規審查 | [情境三：客服主管與合規稽核](#情境三客服主管與合規稽核-cs-supervisor--dpo) |
| **開發人員 (Developer) / 維運 (DevOps)** | 系統架構、環境架設、開發測試與 CI/CD | [情境四：開發者與維運人員 onboarding](#情境四開發者與維運人員-developer--devops) |

---

## 情境一：終端用戶體驗 (End-User Experience)

終端使用者不需安裝任何應用程式，可直接透過熟悉的社群通訊軟體或網頁元件與 OmniBot 互動。

### 1.1 跨管道無縫整合
OmniBot 核心支援統一的對話狀態，無論使用者從何處進件皆可享有相同的服務體驗：
- **社群與即時通訊**：支援 LINE, Telegram, Messenger, WhatsApp。
- **網頁端與系統整合**：支援官方網站 Web Widget 以及 A2A (Application-to-Application) 伺服器整合。
- 機器人能維持上下文一致性，即使轉換話題也能精準捕捉意圖 (Intent)，不會發生鬼打牆或狀態卡死的情況。

### 1.2 企業級安全防護 (PALADIN)
使用者輸入的任何訊息都會經過底層 PALADIN 五層安全防禦機制的即時過濾：
- 阻擋各類提示詞注入攻擊 (Prompt Injection) 與越獄嘗試 (Jailbreak)。
- 若觸發紅旗警告 (Red-flag)，系統將拒絕回答並自動通報/升級至人工客服。
- 對於對話中可能包含的 PII（個人可識別資訊，如信用卡號、身分證），系統會在底層直接進行遮蔽與加密保護。

---

## 情境二：知識管理與業務邏輯配置 (Knowledge Manager & Domain Expert)

系統嚴格區分三種客服內容：**FAQ 知識庫** (RAG-grounded)、**業務邏輯** (槽位與狀態機) 以及 **路由規則**。管理者無需動到核心引擎碼，即可調整客服行為。

### 2.1 匯入 FAQ 知識庫 (Knowledge Base)
開發環境目前主要透過 Python API 進行操作。核心函數 `create_knowledge_with_chunks` (FR-77) 負責處理單筆寫入與非同步向量化 (Embedding)；大量匯入則請使用 `batch_import_knowledge` (FR-78)。

#### 透過 Python API 批次匯入 CSV 範例：
```python
# scripts/load_faq.py (開發輔助腳本)
import csv
from app.core.knowledge import batch_import_knowledge

def csv_to_entries(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            {
                "knowledge_id": f"kb_{row['id']}",
                "title": row["title"],
                "content": row["body"],
            } for row in csv.DictReader(f)
        ]

if __name__ == "__main__":
    result = batch_import_knowledge(csv_to_entries("faq.csv"), is_batch=True)
    print(f"enqueued={result.enqueued} failed={result.failed_chunk_ids}")
```
> **進階技巧**：若知識庫為靜態（如固定規章），建議使用 Alembic 資料遷移指令（位於 `alembic/versions/`）將資料寫入版本控制，確保跨環境部署時的強一致性。

### 2.2 自訂對話邏輯 (Slots, Intents & FSM)
對話狀態追蹤器 (DST) 依賴程式碼中的常數配置。開發團隊可協同業務單位在 `app/core/dst.py` 進行定義：
- **新增意圖與槽位 (Intent & Slots)**:
  ```python
  class DialogueSlot(enum.Enum):
      ORDER_ID = "order_id"
      SUBSCRIPTION_ID = "subscription_id" # 新增業務欄位

  INTENT_TO_SLOTS["cancel_subscription"] = (DialogueSlot.SUBSCRIPTION_ID, DialogueSlot.REASON)
  ```
- **設計對話狀態機 (FSM)**: 定義對話何時進入處理中、已完成或取消等狀態。
  ```python
  ALLOWED_TRANSITIONS["PROCESSING"].add("AWAITING_CANCEL_CONFIRMATION")
  ALLOWED_TRANSITIONS["AWAITING_CANCEL_CONFIRMATION"] = {"PROCESSING", "CANCELLED", "ESCALATED"}
  ```

---

## 情境三：客服主管與合規稽核 (CS Supervisor & DPO)

### 3.1 人工客服升級 (Escalation) 與防呆機制
OmniBot 具備完善的自動防呆與真人接手機制（由 `app.services.escalation.EscalationManager` 管理）。符合以下條件時，系統將自動建立工單寫入 `escalation_queue`，終止 AI 生成並轉移給人類：
1. **槽位填補失敗過多**：追問超過 `MAX_SLOT_FILLING_ROUNDS` (預設 3 次) 仍無法收集齊全業務必填資訊。
2. **意圖信心度偏低**：AI 判斷信心值低於 `INTENT_CONFIDENCE_THRESHOLD` (預設 0.65)。
3. **確認超時**：等待使用者回覆確認超過限制次數 (`MAX_AWAITING_CONFIRMATION_ROUNDS`)。
4. **資安攔截**：觸發上述提到的 PALADIN 紅旗。

### 3.2 對話紀錄調閱與 RBAC 權限管理
- **稽核員與 DPO (資料保護官)** 可透過 Admin WebUI 或直接呼叫 REST API (`GET /api/v1/conversations`) 分頁調閱對話紀錄。
- 系統內建 **RBAC (Role-Based Access Control)** 攔截器，嚴格確保只有被標記為 `dpo` 或具備 `escalate:read` 權限的帳號可檢視敏感對話。未經授權之 API 呼叫將在核心業務邏輯執行前被退回 (HTTP 403)。

---

## 情境四：開發者與維運人員 (Developer & DevOps)

本節涵蓋如何從零開始架設 OmniBot 開發環境、啟動微服務基礎設施，以及執行測試規範。

### 4.1 環境前置需求
| 軟體需求 | 最低版本 | 原因說明 |
|------|------|---------|
| Python | **≥ 3.11** | `pyproject.toml` 嚴格規範；`harness_cli` 將會拒絕執行於 Python 3.9 |
| Docker & Compose | ≥ 24 | 需運行 7 個服務的開發環境 (postgres×2, redis, clamav, otel, prom, grafana) |
| Git | ≥ 2.30 | 需支援 Git Submodule 功能 (`harness` 工具為 submodule) |
| `uv` 或 `pip` | latest | Python 依賴套件管理（官方極度推薦使用 `uv` 提升安裝速度） |

> **macOS 注意**：執行 `uv sync --extra dev` 時若遇到 `gitleaks` 解析失敗，請透過作業系統套件管理 `brew install gitleaks` 安裝，並單純使用 `uv sync` 來安裝核心 Python 依賴即可。

### 4.2 專案下載與依賴安裝
```bash
# 必須加上 --recurse-submodules 以正確下載 harness 稽核子模組
git clone --recurse-submodules https://github.com/johnnylugm-tech/omnibot.git
cd omnibot

# 驗證 submodule 已載入
ls harness/harness_cli.py

# 透過 uv 安裝虛擬環境與套件
uv sync
```

### 4.3 基礎設施與環境變數 (Infrastructure & Config)
請複製 `.env.example` 並補齊開發用的金鑰（包含 LLM API Key, 資料庫與 Redis 連線字串, Webhooks Tokens）。
```bash
cp .env.example .env

# (選擇性) 若 Redis 使用 TLS，產生自簽憑證
mkdir -p deployment/redis/tls
openssl req -x509 -newkey rsa:2048 -days 365 -nodes -keyout deployment/redis/tls/redis.key -out deployment/redis/tls/redis.crt -subj "/CN=localhost"
cp deployment/redis/tls/redis.crt deployment/redis/tls/ca.crt

# 啟動 7 個 Docker 基礎容器
docker compose up -d
docker compose ps # 約 30 秒內皆應顯示 healthy
```
*(提示：`pg-super` 預設 Port 為 5433，請確認 `.env` 中的 `DATABASE_URL` 設定正確無誤)*

### 4.4 啟動應用程式與資料庫遷移
```bash
# 透過 Alembic 執行 PostgreSQL Schema 遷移
.venv/bin/python -m alembic upgrade head

# 啟動 FastAPI 伺服器 (包含 FR-24 Middleware Chain)
.venv/bin/python -m uvicorn app.api.main:build_app --factory --host 0.0.0.0 --port 8000 --reload
```

### 4.5 測試、Linter 與 Mutation Testing
```bash
# 執行所有測試 (包含單元與整合測試，耗時較長)
.venv/bin/python -m pytest

# 僅執行快速單元測試
.venv/bin/python -m pytest -m "not integration and not slow"

# 程式碼檢查與型別檢查
.venv/bin/python -m ruff check 03-development/src
.venv/bin/python -m pyright 03-development/src

# 執行變異測試 (Mutation testing)
.venv/bin/python -m mutmut run
```

### 4.6 架構規範與 Harness CLI
OmniBot 嚴格執行清晰的分層架構 (Clean Architecture) 與溯源矩陣，由根目錄的 `harness_cli.py` 強制把關：
- **api_layer_no_business_logic**: `api/` 層僅負責路由，嚴禁包含業務邏輯。
- **infra_layer_no_domain_imports**: `infra/` 基礎設施不可 import 網域邏輯 (`core/`)。
- **paladin_executes_before_pii**: PALADIN 資安掃描必須在 PII 遮蔽前執行。

任何新模組建立前，皆需發起 SAB.json/SAD.md 的**架構修正案 (Architecture Amendment)**。修改代碼後，在 Push 前必須更新溯源簽章：
```bash
# 更新 Traceability Attestation 簽章
.venv/bin/python harness_cli.py build-trace-attestation --project . --write
```
*除錯提示：若 `harness_cli.py` 報錯不支援 Python 3.9，請確認是否誤用了系統全域 Python，必須使用 `.venv/bin/python`。*

---

## 5. 附錄與參考資源 (Appendix & Resources)

若需進一步了解系統底層設計與商業規格，請參閱：
- **業務規格與架構設計**：`PROJECT_BRIEF.md`, `01-requirements/SRS.md`, `02-architecture/SAD.md`
- **測試規範與品質矩陣**：`02-architecture/TEST_SPEC.md`, `01-requirements/TRACEABILITY_MATRIX.md`
- **AI 代理與交接資訊**：`CLAUDE.md`, `HANDOVER.md`

*Last updated: 2026-06-27 — 此版本已依據各端點角色（End Users, CS Supervisors, DPOs, DevOps）使用情境進行全量優化與重構。*