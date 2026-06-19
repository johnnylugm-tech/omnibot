"""[FR-43] ToolExecutor — 工具註冊與分派層 + 預設物流工具.

Citations:
- SRS.md FR-43 (Module 7: Action Execution Engine (AEE)):
    "ToolExecutor：register(tool, handler) 綁定工具定義與 handler；
     execute(tool_name, arguments_json) 回傳 ToolExecutionResult；
     預設工具：get_shipping_status（查詢物流）、
     update_shipping_address（更新配送地址，出貨前才允許）;
     工具不存在回 success=False；
     update_shipping_address 在 shipped/delivered 狀態拒絕修改."
- 02-architecture/TEST_SPEC.md FR-43 cases 1-4.
- SRS.md FR-45 "ToolDefinition 統一定義"：本模組 re-import ToolDefinition
  / ToolExecutionResult 自 ``app.services.aee.adapter``，不重複定義。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Union

from app.services.aee.adapter import (
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)


# ---------------------------------------------------------------------------
# Default shipping tools (FR-43 預設工具).
#
# Handlers receive keyword arguments unpacked from the arguments payload.
# ``get_shipping_status`` returns a plain dict (auto-wrapped via ``ok()``).
# ``update_shipping_address`` returns a ``ToolExecutionResult`` directly
# because it carries a built-in failure branch when the order has
# already shipped / been delivered.
# ---------------------------------------------------------------------------
def _get_shipping_status_handler(order_id: str) -> dict:
    """[FR-43] 預設工具：查詢訂單物流狀態.

    Returns a shipping record dict with ``order_id``, ``status``,
    ``carrier`` and ``tracking_no`` — matches FR-43 spec.
    """
    return {
        "order_id": order_id,
        "status": "processing",
        "carrier": "黑貓宅急便",
        "tracking_no": f"TRK-{order_id}",
    }


def _update_shipping_address_handler(
    order_id: str,
    new_address: str,
    status: str = "processing",
) -> ToolExecutionResult:
    """[FR-43] 預設工具：更新配送地址（出貨前才允許）.

    Citations:
    - SRS.md FR-43 "update_shipping_address 在 shipped/delivered 狀態
      拒絕修改"：當 ``status in {"shipped", "delivered"}`` 直接回
      ``success=False``，error_message 必須包含 shipped / delivered /
      cannot 等關鍵字以便 caller / user 識別。
    """
    if status in {"shipped", "delivered"}:
        return fail(
            f"Cannot update shipping address: order {order_id} has "
            f"already been {status}."
        )
    return ok(
        {
            "order_id": order_id,
            "new_address": new_address,
            "status": status,
        }
    )


class ToolExecutor:
    """[FR-43] 工具註冊與分派層.

    Bind ``ToolDefinition`` to a Python handler via ``register()``; dispatch
    calls via ``execute(tool_name, arguments_json)``. Two default shipping
    tools (``get_shipping_status`` / ``update_shipping_address``) are
    pre-registered at construction time.

    Citations:
    - SRS.md FR-43 "register(tool, handler) 綁定工具定義與 handler；
      execute(tool_name, arguments_json) 回傳 ToolExecutionResult".
    - SRS.md NFR NP-07 (dependency fault): unknown tool / handler
      exceptions MUST surface as ``ToolExecutionResult(success=False)``,
      MUST NOT raise.
    """

    def __init__(
        self,
        handlers: Optional[dict[str, Callable[..., Any]]] = None,
        default_tools: bool = True,
    ) -> None:
        """Construct the executor; pre-register default shipping tools.

        Args:
            handlers: optional dict ``{tool_name: handler}`` for callers
                that want to seed additional tools up-front.
            default_tools: when ``True`` (the default) the two FR-43
                shipping tools are registered. Set to ``False`` for
                isolated test scenarios that supply their own handlers.
        """
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._tools: dict[str, ToolDefinition] = {}
        if default_tools:
            self._register_default_tools()
        if handlers:
            for tool_name, handler in handlers.items():
                self.register(
                    ToolDefinition(
                        name=tool_name,
                        description="",
                        parameters_schema={},
                        protocol="internal",
                        handler_ref=tool_name,
                    ),
                    handler,
                )

    # ------------------------------------------------------------------ FR-43
    def _register_default_tools(self) -> None:
        """[FR-43] 註冊預設物流工具 — get_shipping_status / update_shipping_address."""
        self.register(
            ToolDefinition(
                name="get_shipping_status",
                description="查詢訂單物流狀態",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                protocol="internal",
                handler_ref="get_shipping_status",
            ),
            _get_shipping_status_handler,
        )
        self.register(
            ToolDefinition(
                name="update_shipping_address",
                description="更新配送地址（出貨前才允許）",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "new_address": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["order_id", "new_address"],
                },
                protocol="internal",
                handler_ref="update_shipping_address",
            ),
            _update_shipping_address_handler,
        )

    def register(
        self,
        tool: ToolDefinition,
        handler: Callable[..., Any],
    ) -> None:
        """[FR-43] 綁定工具定義與 handler.

        Args:
            tool: tool metadata (``ToolDefinition``).
            handler: Python callable invoked with ``**arguments`` unpacked
                from the ``arguments_json`` payload. Its return value is
                wrapped via ``ok()`` on the success path; returning a
                ``ToolExecutionResult`` is also accepted and passed
                through unchanged.
        """
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    def execute(
        self,
        tool_name: str,
        arguments_json: Union[str, dict],
    ) -> ToolExecutionResult:
        """[FR-43] 分派工具呼叫並回傳 ``ToolExecutionResult``.

        Citations:
        - SRS.md FR-43 "execute(tool_name, arguments_json) 回傳
          ToolExecutionResult".
        - SRS.md FR-43 "工具不存在回 success=False" (NP-07 graceful
          degradation) — unknown tool MUST return
          ``success=False + non-empty error_message``; MUST NOT raise.
        - SRS.md FR-43: ``arguments_json`` MAY be a JSON-encoded ``str``
          (decoded via ``json.loads``) or an already-decoded ``dict``.

        Args:
            tool_name: registered tool name.
            arguments_json: JSON-encoded string or pre-decoded dict. When a
                string, MUST be valid JSON; invalid JSON yields
                ``success=False``.

        Returns:
            ``ToolExecutionResult`` — never raises.
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return fail(f"Tool '{tool_name}' is not registered")

        if isinstance(arguments_json, str):
            try:
                arguments = json.loads(arguments_json)
            except json.JSONDecodeError as exc:
                return fail(f"Invalid JSON arguments for '{tool_name}': {exc}")
        else:
            arguments = arguments_json

        try:
            result = handler(**arguments)
        except Exception as exc:  # noqa: BLE001 — surface as structured error
            return fail(f"Tool '{tool_name}' raised an exception: {exc}")

        # Handlers may return a plain value (wrapped via ok()) or a fully
        # formed ``ToolExecutionResult`` (passed through unchanged).
        if isinstance(result, ToolExecutionResult):
            return result
        return ok(result)