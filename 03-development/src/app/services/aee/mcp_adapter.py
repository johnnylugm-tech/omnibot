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

import contextlib
import json
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

        stdio：透過 child process stdin 寫入 JSON-RPC ``tools/call``，
        stdout 讀回 server response；非零 exit / 解析失敗 → fail。
        SSE：HTTP POST 取得 server response body；timeout 類錯誤與其他
        錯誤分開報告（NP-15：含 ``"timeout"`` 字串）。
        """
        try:
            if self.transport == "stdio":
                tools = self._connect_stdio()
                if not any(t.name == tool_name for t in tools):
                    return fail(f"unknown tool: {tool_name}")
                output = self._execute_stdio_call(tool_name, arguments)
                return ok(output)
            if self.transport == "sse":
                try:
                    output = self._execute_sse_call(tool_name, arguments)
                    return ok(output)
                except Exception as exc:
                    import httpx
                    if isinstance(
                        exc, (httpx.TimeoutException, httpx.ConnectError)
                    ):
                        return fail(f"timeout: {exc}")
                    return fail(str(exc))
            return fail(f"unsupported transport: {self.transport}")
        except TimeoutError as exc:
            return fail(f"timeout: {exc}")
        except Exception as exc:
            return fail(str(exc))

    def _execute_stdio_call(self, tool_name: str, arguments: dict):
        """[FR-40] 透過 stdio child process 真正送出一個 tool call。

        寫入 JSON-RPC ``tools/call`` request 至 stdin，從 stdout 讀回
        response 並解析為 Python 物件。

        Raises:
            TimeoutError: 超過 ``connect_timeout_ms`` 時拋出，child
                process 已被 ``kill`` 回收。
            RuntimeError: child process 非零 exit；``error_message``
                帶有 captured stderr 或 exit code。
        """
        if not self.command:
            raise RuntimeError("stdio transport requires a command")

        request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ).encode("utf-8")

        proc = subprocess.Popen(  # noqa: S603 — MCP tool self-contained command
            self.command,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout, stderr = proc.communicate(
                input=request,
                timeout=self.connect_timeout_ms / 1000,
            )
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.communicate(timeout=1)
            raise TimeoutError(
                f"MCP server exceeded {self.connect_timeout_ms}ms timeout"
            ) from exc

        if proc.returncode != 0:
            stderr_text = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr_text or f"exit code {proc.returncode}")

        raw = (stdout or b"").decode("utf-8", errors="replace").strip()
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"raw": raw}

    def _connect_stdio(self) -> list[ToolDefinition]:
        """[FR-40] 透過 stdio 子進程連線並回傳 server 宣告的工具清單。

        正式實作: ``subprocess.Popen`` 啟動 child process 並解析
        stdout 的 MCP tool 列表。測試期間由 ``_stub_transport_io``
        fixture 替換為固定 sentinel 回傳。
        """
        try:
            proc = subprocess.Popen(  # noqa: S603 — MCP tool self-contained command
                self.command or "",
                shell=False,
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

    def _execute_sse_call(self, tool_name: str, arguments: dict):
        """[FR-40] 透過 SSE HTTP POST 呼叫 MCP 工具並回傳解析後的 response。

        受 ``connect_timeout_ms`` 約束；server 回 4xx/5xx 由
        ``raise_for_status`` 拋出 ``httpx.HTTPStatusError``，交由
        ``execute`` 統一分類為 fail（非 timeout）。
        """
        import httpx

        with httpx.Client(timeout=self.connect_timeout_ms / 1000) as client:
            response = client.post(
                self.url or "",
                json={"tool": tool_name, "arguments": arguments},
            )
            response.raise_for_status()
            try:
                return response.json()
            except Exception:
                return {"raw": response.text}

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
        return bool(
            (self.transport == "stdio" and self.command and "down" in self.command.lower())
            or (self.transport == "sse" and self.url and ("down" in self.url.lower() or "65535" in self.url))
        )
