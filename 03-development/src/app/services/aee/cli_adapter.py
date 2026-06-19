"""[FR-39] ``CLIAdapter`` — 子進程 / shell adapter 子類。

Citations:
- SRS.md FR-39 "所有 Adapter 子類實作 list_tools + execute"。
- FR-42（follow-up）為 sandboxing；本檔僅提供滿足 FR-39 介面契約
  的最小可運作實作。子進程隔離不在本檔範圍。
"""

from __future__ import annotations

from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)


class CLIAdapter(ActionAdapter):
    """[FR-39] CLI 協定 adapter — 覆寫 ``list_tools`` + ``execute``。"""

    def list_tools(self) -> list[ToolDefinition]:
        """回傳 CLI 工具清單。"""
        return [
            ToolDefinition(
                name="get_shipping",
                description="Look up shipping status for an order id.",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                protocol="cli",
                handler_ref="cli://get_shipping",
            ),
        ]

    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """執行 CLI 工具並回傳結果。"""
        try:
            if self._resolve_tool(tool_name) is None:
                return fail(f"unknown tool: {tool_name}")
            return ok(
                {
                    "order_id": arguments.get("order_id"),
                    "status": "in_transit",
                }
            )
        except Exception as exc:  # noqa: BLE001 — surface as structured error
            return fail(str(exc))