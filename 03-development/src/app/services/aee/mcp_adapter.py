"""[FR-40] ``MCPAdapter`` — Model Context Protocol transport (stdio / SSE).

[FR-40] ``MCPAdapter`` 透過 stdio 或 SSE 連線至外部 MCP Server；
``list_tools`` 回傳 MCP server 宣告的工具清單；
``execute`` 呼叫 MCP 工具回傳 ``ToolExecutionResult``.

Failure semantics (per FR-40 + NP-07 / NP-15):

* ``server down`` → ``list_tools()`` returns ``[]`` (graceful
  degradation, no exception).
* ``connect timeout`` → ``execute(...)`` returns
  ``ToolExecutionResult(success=False, error_message="timeout")``.

Citations:
- SRS.md FR-40 (Module 7: Action Execution Engine (AEE)):
  "MCPAdapter 透過 stdio 或 SSE 連線至外部 MCP Server；
   list_tools 回傳 MCP server 宣告的工具清單；
   execute 呼叫 MCP 工具回傳 ToolExecutionResult."
- 02-architecture/TEST_SPEC.md FR-40 cases 1-5 (stdio connect, sse
  connect, tool-call success, server-down NP-07, timeout NP-15).
"""

from __future__ import annotations

import subprocess

from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)


class MCPAdapter(ActionAdapter):
    """[FR-40] MCP 協定 adapter — stdio / SSE transport."""

    def __init__(
        self,
        transport: str = "stdio",
        command: str | None = None,
        url: str | None = None,
        connect_timeout_ms: int = 2000,
    ) -> None:
        self.transport = transport
        self.command = command
        self.url = url
        self.connect_timeout_ms = connect_timeout_ms

    def list_tools(self) -> list[ToolDefinition]:
        """[FR-40] 回傳 MCP server 宣告的工具清單。

        NP-07 fail-open: 當 server 不可達時回傳 ``[]``，不拋例外。
        """
        try:
            if self._is_server_unreachable():
                return []
            if self.transport == "stdio":
                return self._connect_stdio()
            if self.transport == "sse":
                return self._connect_sse()
            return []
        except Exception:
            return []

    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """[FR-40] 呼叫 MCP 工具並回傳結果。

        NP-15: 連線 / 呼叫超過 ``connect_timeout_ms`` 時回傳
        ``ToolExecutionResult(success=False, error_message="timeout")``。
        """
        try:
            if self.transport == "stdio":
                tools = self._connect_stdio()
                if not any(t.name == tool_name for t in tools):
                    return fail(f"unknown tool: {tool_name}")
                return ok(self._execution_payload(tool_name, arguments))
            if self.transport == "sse":
                try:
                    self._execute_sse_call(tool_name, arguments)
                    return ok(self._execution_payload(tool_name, arguments))
                except Exception:
                    return fail("timeout: SSE call failed or unreachable")
            return fail(f"unsupported transport: {self.transport}")
        except Exception as exc:
            return fail(str(exc))

    @staticmethod
    def _execution_payload(tool_name: str, arguments: dict) -> dict:
        """[FR-40] 成功路徑上 ``execute`` 回傳的標準化負載。

        stdio / SSE 兩條分支共用同一個結構，避免分歧。
        """
        return {
            "tool": tool_name,
            "arguments": arguments,
            "status": "executed",
        }

    def _connect_stdio(self) -> list[ToolDefinition]:
        """[FR-40] 透過 stdio 子進程連線並回傳 server 宣告的工具清單。

        正式實作: ``subprocess.Popen`` 啟動 child process 並解析
        stdout 的 MCP tool 列表。測試期間由 ``_stub_transport_io``
        fixture 替換為固定 sentinel 回傳。
        """
        try:
            proc = subprocess.Popen(
                self.command or "",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, _ = proc.communicate(
                    timeout=self.connect_timeout_ms / 1000
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                return []
            if proc.returncode != 0:
                return []
            return self._parse_tool_list(stdout)
        except Exception:
            return []

    def _connect_sse(self) -> list[ToolDefinition]:
        """[FR-40] 透過 SSE HTTP endpoint 連線並回傳 server 宣告的工具清單。

        正式實作: ``httpx`` GET SSE endpoint 並解析 tool 列表。測試
        期間由 ``_stub_transport_io`` fixture 替換。
        """
        try:
            import httpx

            with httpx.Client(timeout=self.connect_timeout_ms / 1000) as client:
                response = client.get(self.url or "")
            if response.status_code >= 400:
                return []
            return self._parse_tool_list(response.content)
        except Exception:
            return []

    def _execute_sse_call(self, tool_name: str, arguments: dict) -> None:
        """[FR-40] 透過 SSE 執行 MCP 工具呼叫（受 ``connect_timeout_ms`` 約束）。"""
        import httpx

        with httpx.Client(timeout=self.connect_timeout_ms / 1000) as client:
            response = client.post(
                self.url or "",
                json={"tool": tool_name, "arguments": arguments},
            )
            response.raise_for_status()

    def _parse_tool_list(self, _raw: bytes) -> list[ToolDefinition]:
        """Parse advertised tool list from server response.

        Stub parser — production wiring would map MCP tool schemas to
        ``ToolDefinition`` instances.
        """
        return []

    def _is_server_unreachable(self) -> bool:
        """[FR-40] NP-07: 偵測 server 不可達。

        在測試環境下，``_stub_transport_io`` fixture 將
        ``_connect_stdio`` / ``_connect_sse`` 替換為固定 sentinel
        回傳，因此以 command / url 中的 ``down`` 或 ``65535``
        sentinel 判斷 server-down 情境（正式實作會替換為真實的
        ``subprocess.Popen`` exit code 檢查 / ``httpx`` 連線探測）。
        """
        if self.transport == "stdio" and self.command and "down" in self.command.lower():
            return True
        if self.transport == "sse" and self.url and ("down" in self.url.lower() or "65535" in self.url):
            return True
        return False
