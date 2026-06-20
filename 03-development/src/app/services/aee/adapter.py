"""[FR-39] ActionAdapter 抽象介面 + 結果 / 工具定義資料契約。

Citations:
- SRS.md FR-39 (Module 7: Action Execution Engine (AEE)):
    "ActionAdapter 抽象介面：list_tools() → List[ToolDefinition]；
     execute(tool_name, arguments) → ToolExecutionResult；
     ToolDefinition 欄位含 name, description, parameters_schema,
     protocol, handler_ref. 所有 Adapter 子類實作 list_tools + execute；
     ToolExecutionResult 包含 success, output, error_message."
- 02-architecture/TEST_SPEC.md FR-39 case 3
    ``result_fields='success,output,error_message'``（欄位命名鎖定
    ``error_message``，非 ``error`` / ``error_msg``）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    """工具的中介資料，由 ``ActionAdapter.list_tools()`` 回傳。

    [FR-39] ToolDefinition 欄位含 name, description, parameters_schema,
    protocol, handler_ref（SRS.md FR-39）。
    """

    name: str
    description: str
    parameters_schema: dict
    protocol: str  # "mcp" | "a2a" | "cli" | "internal"
    handler_ref: str


@dataclass(frozen=True)
class ToolExecutionResult:
    """``ActionAdapter.execute()`` 的回傳值。

    [FR-39] ToolExecutionResult 包含 success, output, error_message
    （SRS.md FR-39；TEST_SPEC.md FR-39 case 3 鎖定欄位名為
    ``error_message``）。
    """

    success: bool
    output: Any
    error_message: str | None


def ok(output: Any) -> ToolExecutionResult:
    """成功路徑的 ``ToolExecutionResult`` factory（[FR-39]）。"""
    return ToolExecutionResult(success=True, output=output, error_message=None)


def fail(error_message: str) -> ToolExecutionResult:
    """失敗路徑的 ``ToolExecutionResult`` factory（[FR-39]）。"""
    return ToolExecutionResult(success=False, output=None, error_message=error_message)


class ActionAdapter(ABC):
    """[FR-39] Action Execution Engine 的 adapter 抽象介面。

    Citations:
    - SRS.md FR-39 "ActionAdapter 抽象介面：list_tools() →
      List[ToolDefinition]；execute(tool_name, arguments) →
      ToolExecutionResult"。
    """

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """回傳此 adapter 暴露的工具清單（[FR-39]）。"""

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """執行指定工具並回傳結果（[FR-39]）。"""

    def _resolve_tool(self, tool_name: str) -> ToolDefinition | None:
        """以名稱查找已註冊的工具；找不到回傳 ``None``。

        共用於所有 adapter 子類 — 由子類 ``execute`` 在呼叫實際
        handler 之前先用此方法驗證 ``tool_name``。
        """
        for tool in self.list_tools():
            if tool.name == tool_name:
                return tool
        return None
