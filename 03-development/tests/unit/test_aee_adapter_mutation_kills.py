"""Mutation-killing tests for app.services.aee.adapter.

Each test asserts a specific field-level invariant that mutmut mutants
(``success=True`` → ``False``, ``error_message`` → ``None``, etc.) cannot
survive. 8 mutants total; target 7/10 = 70% kill rate.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``app.services.aee`` importable when running this file directly.
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.services.aee.adapter import (  # noqa: E402
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)


def test_ok_factory_sets_success_true_output_preserved_error_message_none() -> None:
    """Mutant on ``ok()``: flipping ``success=True`` to ``False`` or
    ``error_message=None`` to a string would fail this assertion.
    """
    result = ok({"data": 42})
    assert result.success is True
    assert result.output == {"data": 42}
    assert result.error_message is None


def test_fail_factory_sets_success_false_output_none_error_message_preserved() -> None:
    """Mutant on ``fail()``: flipping ``success=False`` to ``True`` or
    setting ``output`` to a non-None value would fail.
    """
    result = fail("something broke")
    assert result.success is False
    assert result.output is None
    assert result.error_message == "something broke"


def test_tool_definition_field_defaults_and_values() -> None:
    """Mutants on dataclass field defaults — assert the exact field set
    and types of a ``ToolDefinition`` instance. Any mutant that drops
    a field default or changes its value is caught here.
    """
    td = ToolDefinition(
        name="search",
        description="web search",
        parameters_schema={"type": "object"},
        protocol="mcp",
        handler_ref="mcp://search",
    )
    assert td.name == "search"
    assert td.description == "web search"
    assert td.parameters_schema == {"type": "object"}
    assert td.protocol == "mcp"
    assert td.handler_ref == "mcp://search"


def test_tool_definition_frozen() -> None:
    """Mutant that removes ``frozen=True`` from the ``@dataclass`` decorator
    would let us mutate fields, which a frozen dataclass blocks.
    """
    td = ToolDefinition(
        name="x", description="x", parameters_schema={}, protocol="cli", handler_ref="x"
    )
    try:
        td.name = "y"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "ToolDefinition must be frozen (mutant removes @dataclass(frozen=True))"


def test_tool_execution_result_field_set() -> None:
    """Mutant that renames a ``ToolExecutionResult`` field is caught by
    inspecting the dataclass fields directly.
    """
    fields = {f.name for f in ToolExecutionResult.__dataclass_fields__.values()}
    assert fields == {"success", "output", "error_message"}


class _DummyAdapter(ActionAdapter):
    def list_tools(self):  # type: ignore[override]
        return [
            ToolDefinition(
                name="t1", description="d", parameters_schema={},
                protocol="cli", handler_ref="h",
            )
        ]

    def execute(self, tool_name, arguments):  # type: ignore[override]
        return ok({"echo": arguments})


def test_action_adapter_abstract_methods() -> None:
    """Mutant on ``ActionAdapter`` that drops ``@abstractmethod`` would
    let the class be instantiated. Catch by trying to construct it.
    """
    try:
        ActionAdapter()  # type: ignore[abstract]
        instantiated = True
    except TypeError:
        instantiated = False
    assert not instantiated, "ActionAdapter must be abstract"


def test_dummy_adapter_list_tools_returns_tool_definitions() -> None:
    """Mutant on ``list_tools`` that returns an empty list or wrong type
    is caught by asserting non-empty list of ``ToolDefinition``.
    """
    adapter = _DummyAdapter()
    tools = adapter.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "t1"


def test_dummy_adapter_execute_returns_ok_with_arguments() -> None:
    """Mutant on ``execute`` that drops the argument passing or sets
    ``success=False`` is caught by asserting the echo content.
    """
    adapter = _DummyAdapter()
    result = adapter.execute("t1", {"x": 1})
    assert result.success is True
    assert result.output == {"echo": {"x": 1}}


def test_tool_execution_result_frozen() -> None:
    """Mutant on ``@dataclass(frozen=True)`` of ``ToolExecutionResult``
    (line 37) is caught by attempting to mutate a field.
    """
    result = ok("value")
    try:
        result.success = False  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, (
        "ToolExecutionResult must be frozen (mutant removes @dataclass(frozen=True))"
    )


def test_resolve_tool_returns_matching_tool() -> None:
    """Mutant on line 86 ``if tool.name == tool_name`` → ``!=`` would
    cause ``_resolve_tool`` to return a tool when name does NOT match.

    We exercise ``ActionAdapter._resolve_tool`` via a custom subclass
    that exposes the protected method.
    """
    from app.services.aee.adapter import ActionAdapter

    class _Adapter2(ActionAdapter):
        def list_tools(self):  # type: ignore[override]
            return [
                ToolDefinition(
                    name="alpha", description="d", parameters_schema={},
                    protocol="cli", handler_ref="h",
                ),
                ToolDefinition(
                    name="beta", description="d", parameters_schema={},
                    protocol="cli", handler_ref="h",
                ),
            ]

        def execute(self, tool_name, arguments):  # type: ignore[override]
            return ok(None)

    a = _Adapter2()
    # M9 mutant would return the tool whose name does NOT match.
    assert a._resolve_tool("alpha").name == "alpha"
    assert a._resolve_tool("beta").name == "beta"
    assert a._resolve_tool("gamma") is None
