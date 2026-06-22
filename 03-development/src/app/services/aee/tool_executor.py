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

import inspect
import json
import logging
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.services.aee.adapter import (
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# [H-18] Handler safety whitelist.
#
# Only top-level ``def`` functions, bound methods, and C builtins are
# accepted as tool handlers. Callable classes / instances / arbitrary
# objects with ``__call__`` are REJECTED so that callers cannot inject
# code that bypasses the registry's audit surface (callable instances
# can carry arbitrary closure state and re-enter the executor with
# unexpected semantics).
# ---------------------------------------------------------------------------
_ALLOWED_HANDLER_PREDICATES: tuple[Callable[[Any], bool], ...] = (
    inspect.isfunction,
    inspect.ismethod,
    inspect.isbuiltin,
)


def _validate_handler(handler: Any, *, context: str) -> None:
    """[H-18] Reject handlers that are not in the safety whitelist.

    Args:
        handler: the candidate handler to validate.
        context: human-readable label (typically the tool name) used
            in the error message so misconfiguration is debuggable.

    Raises:
        TypeError: when ``handler`` is not callable, or is callable
            but its type is not in ``_ALLOWED_HANDLER_PREDICATES``.
    """
    if not callable(handler):
        raise TypeError(
            f"{context}: handler must be callable; got "
            f"{type(handler).__name__}"
        )
    if not any(predicate(handler) for predicate in _ALLOWED_HANDLER_PREDICATES):
        raise TypeError(
            f"{context}: handler type {type(handler).__name__!r} is "
            f"not in the safety whitelist; allowed: top-level "
            f"functions, bound methods, or C builtins"
        )

# Order statuses that BLOCK address updates per SRS FR-43: "出貨前才允許".
_BLOCKED_ADDRESS_STATUSES: frozenset[str] = frozenset({"shipped", "delivered"})

# Default shipping tool definitions (FR-43 預設工具). Promoted to module
# scope so the JSON schemas are inspectable / reusable and not buried
# inside an instance method.
_GET_SHIPPING_STATUS_TOOL = ToolDefinition(
    name="get_shipping_status",
    description="查詢訂單物流狀態",
    parameters_schema={
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
    },
    protocol="internal",
    handler_ref="get_shipping_status",
)

_UPDATE_SHIPPING_ADDRESS_TOOL = ToolDefinition(
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
)


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
      拒絕修改"：當 ``status in BLOCKED_ADDRESS_STATUSES`` 直接回
      ``success=False``，error_message 必須包含 shipped / delivered /
      cannot 等關鍵字以便 caller / user 識別。
    """
    if status in _BLOCKED_ADDRESS_STATUSES:
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
        handlers: dict[str, Callable[..., Any]] | None = None,
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
                # [H-18] Reject arbitrary callables up-front so the
                # security boundary is enforced at construction time,
                # not deferred to the first ``execute()`` call.
                _validate_handler(handler, context=f"handlers[{tool_name!r}]")
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
        self.register(_GET_SHIPPING_STATUS_TOOL, _get_shipping_status_handler)
        self.register(_UPDATE_SHIPPING_ADDRESS_TOOL, _update_shipping_address_handler)

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
        # [H-18] Defense in depth: even if the ``handlers`` kwarg path
        # is bypassed, ``register()`` itself enforces the whitelist.
        _validate_handler(handler, context=f"register({tool.name!r})")
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    @staticmethod
    def _decode_arguments(arguments_json: str | dict) -> dict | ToolExecutionResult:
        """[FR-43] Decode ``arguments_json`` (str or dict) → dict.

        On invalid JSON, returns a pre-built ``ToolExecutionResult``
        failure so the caller can pass it through unchanged.
        """
        if not isinstance(arguments_json, str):
            return arguments_json
        try:
            return json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            return fail(f"Invalid JSON arguments: {exc}")

    def execute(
        self,
        tool_name: str,
        arguments_json: str | dict,
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
        # Invariant: ``_handlers`` and ``_tools`` are kept in lockstep
        # by ``register()``; the handler lookup above guarantees a
        # matching ``ToolDefinition`` exists.
        tool = self._tools[tool_name]

        arguments = self._decode_arguments(arguments_json)
        if isinstance(arguments, ToolExecutionResult):
            return arguments
        # [H-19] Pre-decoded (or freshly decoded) arguments MUST be a
        # JSON object; lists / scalars / ``None`` are not valid tool
        # arguments regardless of what the schema says.
        if not isinstance(arguments, dict):
            return fail(
                f"Tool '{tool_name}' arguments must be a JSON object; "
                f"got {type(arguments).__name__}"
            )

        # [H-19] Validate arguments against the tool's declared
        # ``parameters_schema``. Applied to BOTH the string-decoded and
        # pre-decoded-dict paths (the bug was that the pre-decoded path
        # skipped validation entirely).
        if tool.parameters_schema:
            try:
                Draft202012Validator(tool.parameters_schema).validate(arguments)
            except ValidationError as exc:
                return fail(
                    f"Tool '{tool_name}' arguments failed schema "
                    f"validation: {exc.message}"
                )

        _handler_timeout = 5.0
        try:
            import asyncio
            import inspect
            from functools import partial

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                def _thread_run():
                    async def _inner():
                        if inspect.iscoroutinefunction(handler):
                            return await asyncio.wait_for(handler(**arguments), timeout=_handler_timeout)
                        else:
                            inner_loop = asyncio.get_running_loop()
                            return await asyncio.wait_for(
                                inner_loop.run_in_executor(None, partial(handler, **arguments)),
                                timeout=_handler_timeout
                            )
                    return asyncio.run(_inner())

                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    result = pool.submit(_thread_run).result()
            else:
                async def _run_handler():
                    if inspect.iscoroutinefunction(handler):
                        return await asyncio.wait_for(handler(**arguments), timeout=_handler_timeout)
                    else:
                        inner_loop = asyncio.get_running_loop()
                        return await asyncio.wait_for(
                            inner_loop.run_in_executor(None, partial(handler, **arguments)),
                            timeout=_handler_timeout
                        )
                result = asyncio.run(_run_handler())

        except BaseException as exc:
            import asyncio
            if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or type(exc).__name__ == "TimeoutError":
                return fail(f"timeout: Tool '{tool_name}' exceeded {_handler_timeout}s timeout")
            # [M-09] NP-07: ``MemoryError`` / ``RecursionError`` are
            # subclasses of ``Exception`` and therefore land here; the
            # prior explicit ``raise`` is removed so the executor NEVER
            # propagates raw exceptions to the caller.
            #
            # [L-03] Log the full traceback (which may include
            # internal paths / DSNs / stack frames) for operators via
            # the standard logging channel, but return a SANITIZED
            # generic message to the caller — the raw ``exc`` text is
            # never embedded in the user-visible error_message.
            _log.exception(
                "Tool %s raised an exception during execute()",
                tool_name,
            )
            return fail(f"Tool '{tool_name}' raised an exception")

        # Handlers may return a plain value (wrapped via ok()) or a fully
        # formed ``ToolExecutionResult`` (passed through unchanged).
        if isinstance(result, ToolExecutionResult):
            return result
        return ok(result)
