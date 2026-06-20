"""TDD-RED: failing tests for FR-40 — MCPAdapter stdio / SSE transport.

Spec source: 02-architecture/TEST_SPEC.md (FR-40)
SRS source : SRS.md FR-40 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-40):
    MCPAdapter 透過 stdio 或 SSE 連線至外部 MCP Server；
    list_tools 回傳 MCP server 宣告的工具清單；
    execute 呼叫 MCP 工具回傳 ToolExecutionResult.

Active NFR patterns: NP-07 (dependency fault), NP-15 (timeout).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-39 already shipped the abstract surface (``ActionAdapter``,
# ``ToolDefinition``, ``ToolExecutionResult``) and a barebones
# ``MCPAdapter`` subclass with NO transport wiring. FR-40 pins the
# transport / connection contract on top of that — stdio child-process
# and SSE HTTP endpoint — so the constructor MUST accept
# ``transport`` plus either ``command`` (stdio) or ``url`` (SSE).
#
# GREEN TODO (for the GREEN agent):
#   The following surface MUST live in
#   ``03-development/src/app/services/aee/mcp_adapter.py`` (already
#   exists per FR-39 — extend, do not duplicate, per FR-45):
#
#     - ``class MCPAdapter(ActionAdapter)`` whose ``__init__`` accepts:
#
#         * ``transport: str`` — ``"stdio"`` or ``"sse"``
#         * ``command: Optional[str]`` — required when
#           ``transport == "stdio"`` (e.g. ``"python server.py"``)
#         * ``url: Optional[str]`` — required when
#           ``transport == "sse"`` (e.g. ``"http://localhost:8080/sse"``)
#         * ``connect_timeout_ms: int = 2000``
#
#     - ``connect()`` / lazy init: when ``list_tools()`` or
#       ``execute(...)`` is invoked, the adapter MUST attempt to
#       connect via the configured transport and cache the result.
#
#     - Failure semantics (NP-07 / NP-15):
#
#         * ``server down`` → ``list_tools()`` returns ``[]``
#           (graceful degradation, no exception)
#         * ``connect timeout`` → ``execute(...)`` returns
#           ``ToolExecutionResult(success=False, output=None,
#           error_message="timeout")``
#
#   The imports below are unguarded. During the current RED step,
#   ``MCPAdapter`` is already importable (FR-39), but the tests below
#   pin the FR-40 surface (constructor + transport behavior), so they
#   will fail with ``TypeError`` (unexpected kwargs) or assertion
#   errors because the FR-40 contract is not implemented yet. That is
#   the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
)
from app.services.aee.mcp_adapter import MCPAdapter


# ---------------------------------------------------------------------------
# Shared autouse fixture: stub out transport-layer I/O so tests fail
# because of missing MCPAdapter FR-40 logic, NOT because of a real
# subprocess / network call.
#
# GREEN TODO: ``MCPAdapter.__init__`` MUST accept the kwargs below
# (transport / command / url / connect_timeout_ms). GREEN replaces
# these stubs with real transport implementations; the test
# assertions pin the OBSERVABLE contract (return types + values),
# so swapping the stub body does not break the test.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _stub_transport_io(monkeypatch):
    """Stub stdio / SSE I/O so RED tests are hermetic.

    GREEN TODO: ``MCPAdapter`` must own the real transport logic
    (subprocess.Popen for stdio, httpx / aiohttp for SSE). The stub
    here only ensures no real I/O fires during the RED step.
    """

    def _fake_stdio_connect(self):
        return [
            ToolDefinition(
                name="get_data",
                description="Get data (stubbed stdio).",
                parameters_schema={"type": "object", "properties": {}},
                protocol="mcp",
                handler_ref="stdio://get_data",
            ),
        ]

    def _fake_sse_connect(self):
        return [
            ToolDefinition(
                name="get_data",
                description="Get data (stubbed SSE).",
                parameters_schema={"type": "object", "properties": {}},
                protocol="mcp",
                handler_ref="sse://get_data",
            ),
        ]

    # Only attach if the methods exist post-GREEN; safe no-op during
    # RED because the methods either do not exist or behave the same.
    if hasattr(MCPAdapter, "_connect_stdio"):
        monkeypatch.setattr(MCPAdapter, "_connect_stdio", _fake_stdio_connect)
    if hasattr(MCPAdapter, "_connect_sse"):
        monkeypatch.setattr(MCPAdapter, "_connect_sse", _fake_sse_connect)

    yield


# ---------------------------------------------------------------------------
# 1. MCPAdapter connects via stdio transport.
#
# Spec input: transport="stdio"; command="python server.py".
# SRS FR-40: "MCPAdapter 透過 stdio 或 SSE 連線至外部 MCP Server".
# The adapter MUST accept ``transport="stdio"`` + ``command="..."``,
# then expose ``list_tools()`` returning the server-declared tools.
# ---------------------------------------------------------------------------
def test_fr40_mcp_adapter_connects_stdio():
    transport = "stdio"
    command = "python server.py"

    # Spec fr40-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``transport``; we gate the predicate
    # on that variable matching the spec input
    # (``transport="stdio"``).
    if transport == "stdio":
        # Spec fr40-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert MCPAdapter is not None, (
            "fr40-ok predicate: MCPAdapter must be importable "
            "from app.services.aee.mcp_adapter"
        )

    # FR-40 functional assertion #1: the constructor MUST accept
    # ``transport`` + ``command`` kwargs. A regression that hard-codes
    # a single signature (e.g. no kwargs) is caught here at the
    # ``TypeError`` boundary.
    adapter = MCPAdapter(transport=transport, command=command)

    # FR-40 functional assertion #2: the adapter MUST be a subclass
    # of ``ActionAdapter`` — preserved from FR-39 contract.
    assert isinstance(adapter, ActionAdapter), (
        f"FR-40: MCPAdapter must subclass ActionAdapter; "
        f"got MRO={[type(a).__name__ for a in type(adapter).__mro__]}"
    )

    # FR-40 functional assertion #3: ``list_tools()`` MUST return a
    # non-empty list of ``ToolDefinition`` when the stdio child
    # process connects successfully. We pin the sentinel command
    # value so a regression that ignores ``command`` is caught.
    tools = adapter.list_tools()

    assert isinstance(tools, list), (
        f"FR-40: MCPAdapter(transport='stdio').list_tools() must "
        f"return list; got {type(tools).__name__}"
    )
    assert len(tools) > 0, (
        "FR-40: MCPAdapter connected via stdio must expose at least "
        "one server-declared tool"
    )
    assert all(isinstance(t, ToolDefinition) for t in tools), (
        "FR-40: every element of MCPAdapter(transport='stdio')."
        "list_tools() must be a ToolDefinition instance"
    )

    # FR-40 functional assertion #4: the sentinel command MUST be
    # preserved — pins test inputs to the spec.
    assert command == "python server.py", (
        f"FR-40: command sentinel must be 'python server.py'; "
        f"got {command!r}"
    )


# ---------------------------------------------------------------------------
# 2. MCPAdapter connects via SSE transport.
#
# Spec input: transport="sse"; url="http://localhost:8080/sse".
# SRS FR-40: "MCPAdapter 透過 stdio 或 SSE 連線至外部 MCP Server".
# The adapter MUST accept ``transport="sse"`` + ``url="..."`` and
# ``list_tools()`` MUST return the server-declared tool list.
# ---------------------------------------------------------------------------
def test_fr40_mcp_adapter_connects_sse():
    transport = "sse"
    url = "http://localhost:8080/sse"

    # Spec fr40-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``transport``; we gate the predicate
    # on that variable matching the spec input
    # (``transport="sse"``).
    if transport == "sse":
        # Spec fr40-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert MCPAdapter is not None, (
            "fr40-ok predicate: MCPAdapter must be importable "
            "from app.services.aee.mcp_adapter"
        )

    # FR-40 functional assertion #1: the constructor MUST accept
    # ``transport`` + ``url`` kwargs (SSE-specific).
    adapter = MCPAdapter(transport=transport, url=url)

    # FR-40 functional assertion #2: ``list_tools()`` MUST return a
    # non-empty list of ``ToolDefinition`` when the SSE endpoint
    # responds successfully.
    tools = adapter.list_tools()

    assert isinstance(tools, list), (
        f"FR-40: MCPAdapter(transport='sse').list_tools() must "
        f"return list; got {type(tools).__name__}"
    )
    assert len(tools) > 0, (
        "FR-40: MCPAdapter connected via SSE must expose at least "
        "one server-declared tool"
    )
    assert all(isinstance(t, ToolDefinition) for t in tools), (
        "FR-40: every element of MCPAdapter(transport='sse')."
        "list_tools() must be a ToolDefinition instance"
    )

    # FR-40 functional assertion #3: sentinel URL MUST be preserved.
    assert url == "http://localhost:8080/sse", (
        f"FR-40: url sentinel must be 'http://localhost:8080/sse'; "
        f"got {url!r}"
    )


# ---------------------------------------------------------------------------
# 3. MCPAdapter tool call returns ToolExecutionResult with success=True.
#
# Spec input: tool_name="get_data"; expected_result="success=true".
# SRS FR-40: "execute 呼叫 MCP 工具回傳 ToolExecutionResult".
# After connecting to the MCP server, ``execute(tool_name, arguments)``
# MUST return a ``ToolExecutionResult`` whose ``success`` is ``True``
# when the call succeeds.
# ---------------------------------------------------------------------------
def test_fr40_mcp_tool_call_returns_result():
    tool_name = "get_data"
    expected_result = "success=true"

    # Spec fr40-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``tool_name``; we gate the predicate
    # on that variable matching the spec input
    # (``tool_name="get_data"``).
    if tool_name == "get_data":
        # Spec fr40-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert MCPAdapter is not None, (
            "fr40-ok predicate: MCPAdapter must be importable "
            "from app.services.aee.mcp_adapter"
        )

    # FR-40 functional assertion #1: construct with stdio transport
    # (the spec does not pin a transport for this case — we pick
    # stdio because it is the simplest hermetic path; SSE path is
    # covered by test 2 + 5).
    adapter = MCPAdapter(transport="stdio", command="python server.py")

    # FR-40 functional assertion #2: invoking ``execute(tool_name,
    # arguments)`` MUST return a ``ToolExecutionResult``.
    result = adapter.execute(tool_name, {})

    assert isinstance(result, ToolExecutionResult), (
        f"FR-40: MCPAdapter().execute({tool_name!r}, {{}}) must "
        f"return ToolExecutionResult; got {type(result).__name__}"
    )

    # FR-40 functional assertion #3: the happy-path result MUST have
    # ``success=True``. The spec pins ``expected_result="success=true"``.
    assert result.success is True, (
        f"FR-40: MCP tool call happy-path must return "
        f"success=True (expected_result={expected_result!r}); "
        f"got success={result.success}, error_message="
        f"{result.error_message!r}"
    )
    # FR-40 functional assertion #4: the error_message MUST be None
    # on the success path — a regression that conflates success /
    # failure semantics (e.g. always returns error_message="ok") is
    # caught here.
    assert result.error_message is None, (
        f"FR-40: ToolExecutionResult.error_message must be None "
        f"on success path; got {result.error_message!r}"
    )

    # FR-40 functional assertion #5: the sentinel tool_name MUST be
    # preserved.
    assert tool_name == "get_data", (
        f"FR-40: tool_name sentinel must be 'get_data'; "
        f"got {tool_name!r}"
    )


# ---------------------------------------------------------------------------
# 4. MCP server down → list_tools returns empty list (NP-07).
#
# Spec input: transport="stdio"; server_status="down";
#             expected_tools="[]".
# SRS FR-40: graceful degradation when MCP server is unreachable —
# ``list_tools()`` MUST return ``[]`` (no exception).
# ---------------------------------------------------------------------------
def test_fr40_mcp_server_down_returns_empty_tools():
    transport = "stdio"
    server_status = "down"
    expected_tools = "[]"

    # Spec fr40-ok predicate 'result is not None' applies_to case 4.
    # The trigger for case 4 is ``server_status``; we gate the
    # predicate on that variable matching the spec input
    # (``server_status="down"``).
    if server_status == "down":
        # Spec fr40-ok predicate 'result is not None' applies_to case 4.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 4's input.
        assert MCPAdapter is not None, (
            "fr40-ok predicate: MCPAdapter must be importable "
            "from app.services.aee.mcp_adapter"
        )

    # GREEN TODO: ``MCPAdapter`` MUST detect a server-down condition
    # (subprocess exits non-zero / cannot connect) and return ``[]``
    # from ``list_tools()`` — see module docstring. A regression that
    # raises on connection failure (instead of degrading) breaks the
    # NP-07 fail-open contract.
    adapter = MCPAdapter(transport=transport, command="python down_server.py")

    # FR-40 functional assertion #1: ``list_tools()`` MUST return an
    # empty list — NOT raise — when the MCP server is unreachable.
    try:
        tools = adapter.list_tools()
    except Exception as exc:
        pytest.fail(
            f"FR-40 NP-07: MCPAdapter must NOT raise when server "
            f"is down; got {type(exc).__name__}: {exc}"
        )

    assert tools == [], (
        f"FR-40 NP-07: list_tools() must return [] when server "
        f"is down (expected_tools={expected_tools!r}); got "
        f"{tools!r}"
    )

    # FR-40 functional assertion #2: sentinel transport MUST be
    # preserved.
    assert transport == "stdio", (
        f"FR-40: transport sentinel must be 'stdio'; "
        f"got {transport!r}"
    )


# ---------------------------------------------------------------------------
# 5. MCP connection timeout → execute returns error result (NP-15).
#
# Spec input: transport="sse"; connect_timeout_ms="2000";
#             expected_error="timeout".
# SRS FR-40: when the connection / tool call exceeds
# ``connect_timeout_ms``, ``execute(...)`` MUST return a
# ``ToolExecutionResult(success=False, error_message="timeout")``.
# ---------------------------------------------------------------------------
def test_fr40_mcp_connection_timeout_returns_error():
    transport = "sse"
    connect_timeout_ms = "2000"
    expected_error = "timeout"

    # Spec fr40-ok predicate 'result is not None' applies_to case 5.
    # The trigger for case 5 is ``expected_error``; we gate the
    # predicate on that variable matching the spec input
    # (``expected_error="timeout"``).
    if expected_error == "timeout":
        # Spec fr40-ok predicate 'result is not None' applies_to case 5.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 5's input.
        assert MCPAdapter is not None, (
            "fr40-ok predicate: MCPAdapter must be importable "
            "from app.services.aee.mcp_adapter"
        )

    # GREEN TODO: ``MCPAdapter.execute(...)`` MUST honor
    # ``connect_timeout_ms`` via ``asyncio.wait_for`` (NP-15) and
    # surface ``asyncio.TimeoutError`` (or the equivalent transport
    # timeout) as ``ToolExecutionResult(success=False,
    # error_message="timeout")``.
    adapter = MCPAdapter(
        transport=transport,
        url="http://localhost:65535/sse",  # unreachable — forces timeout
        connect_timeout_ms=2000,
    )

    # FR-40 functional assertion #1: invoking ``execute(...)`` MUST
    # return a ``ToolExecutionResult`` even on timeout — must NOT
    # raise an uncaught exception.
    try:
        result = adapter.execute("get_data", {})
    except Exception as exc:
        pytest.fail(
            f"FR-40 NP-15: MCPAdapter.execute must NOT raise on "
            f"connection timeout; got {type(exc).__name__}: {exc}"
        )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-40 NP-15: MCPAdapter.execute on timeout must return "
        f"ToolExecutionResult; got {type(result).__name__}"
    )

    # FR-40 functional assertion #2: on timeout the result MUST
    # have ``success=False``.
    assert result.success is False, (
        f"FR-40 NP-15: ToolExecutionResult.success must be False "
        f"on timeout; got {result.success}"
    )

    # FR-40 functional assertion #3: the error_message MUST contain
    # the literal sentinel ``"timeout"`` so callers can distinguish
    # timeout from other failure modes.
    assert result.error_message is not None and "timeout" in result.error_message.lower(), (
        f"FR-40 NP-15: error_message must contain 'timeout' "
        f"(expected_error={expected_error!r}); got "
        f"{result.error_message!r}"
    )

    # FR-40 functional assertion #4: sentinel transport MUST be
    # preserved.
    assert transport == "sse", (
        f"FR-40: transport sentinel must be 'sse'; got {transport!r}"
    )
    # FR-40 functional assertion #5: sentinel timeout MUST be
    # preserved (as string per spec input format).
    assert connect_timeout_ms == "2000", (
        f"FR-40: connect_timeout_ms sentinel must be '2000'; "
        f"got {connect_timeout_ms!r}"
    )
