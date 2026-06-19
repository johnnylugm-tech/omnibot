"""[FR-39] ``MCPAdapter`` — Model Context Protocol 子類。

Citations:
- SRS.md FR-39 "所有 Adapter 子類實作 list_tools + execute"。
- FR-40（follow-up）為 MCP transport / connection；本檔僅提供滿足
  FR-39 介面契約的最小可運作實作。
"""

from __future__ import annotations

from typing import Any

from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
)


class MCPAdapter(ActionAdapter):
    """[FR-39] MCP 協定 adapter — 覆寫 ``list_tools`` + ``execute``。"""

    def list_tools(self) -> list[ToolDefinition]:
        """回傳 MCP 協定暴露的工具清單。"""
        return [
            ToolDefinition(
                name="mcp.echo",
                description="Echo input back as output (MCP default tool).",
                parameters_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                protocol="mcp",
                handler_ref="mcp://echo",
            ),
        ]

    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """呼叫 MCP 工具並回傳結果。"""
        try:
            tools = {t.name: t for t in self.list_tools()}
            if tool_name not in tools:
                return ToolExecutionResult(
                    success=False,
                    output=None,
                    error_message=f"unknown tool: {tool_name}",
                )
            payload: Any = {"echo": arguments.get("text", "")}
            return ToolExecutionResult(
                success=True, output=payload, error_message=None
            )
        except Exception as exc:  # noqa: BLE001 — surface as structured error
            return ToolExecutionResult(
                success=False, output=None, error_message=str(exc)
            )
