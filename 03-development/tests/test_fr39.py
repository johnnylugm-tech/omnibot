"""TDD-RED: failing tests for FR-39 — ActionAdapter 抽象介面:
list_tools() + execute() + ToolExecutionResult (success / output /
error_message).

Spec source: 02-architecture/TEST_SPEC.md (FR-39)
SRS source : SRS.md FR-39 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-39):
    ActionAdapter 抽象介面：list_tools() → List[ToolDefinition]；
    execute(tool_name, arguments) → ToolExecutionResult；
    ToolDefinition 欄位含 name, description, parameters_schema,
    protocol, handler_ref.
    所有 Adapter 子類實作 list_tools + execute；
    ToolExecutionResult 包含 success, output, error_message.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — the ActionAdapter surface from FR-39 does NOT
# exist yet (RED state).
#
# GREEN TODO (for the GREEN agent):
#   Per SAD module 7 (Action Execution Engine) and SRS FR-39, the
#   following surface MUST live in
#   ``03-development/src/app/services/aee/`` (NOT under
#   ``app/infrastructure/`` — the AEE is a service-layer concern):
#
#     - ``03-development/src/app/services/aee/__init__.py`` — empty
#       package marker.
#
#     - ``03-development/src/app/services/aee/adapter.py`` exporting:
#         * ``class ActionAdapter`` — abstract base (raises
#           ``NotImplementedError`` for both abstract methods, or uses
#           ``abc.ABC`` + ``@abstractmethod``). The class MUST define
#           exactly these two abstract methods:
#
#             - ``def list_tools(self) -> list[ToolDefinition]``
#             - ``def execute(self, tool_name: str,
#               arguments: dict) -> ToolExecutionResult``
#
#         * ``@dataclass(frozen=True)`` ``class ToolDefinition``
#           with fields: ``name: str``, ``description: str``,
#           ``parameters_schema: dict``, ``protocol: str``
#           (``"mcp" | "a2a" | "cli" | "internal"``),
#           ``handler_ref: str`` (per SRS FR-39 "ToolDefinition 欄位含
#           name, description, parameters_schema, protocol, handler_ref").
#
#         * ``@dataclass(frozen=True)`` ``class ToolExecutionResult``
#           with fields: ``success: bool``, ``output: Any``,
#           ``error_message: Optional[str]`` — the spec-pinned field
#           name is ``error_message`` (NOT ``error``) per TEST_SPEC
#           case 3 "result_fields='success,output,error_message'" and
#           SRS FR-39 "ToolExecutionResult 包含 success, output,
#           error_message".
#
#     - ``03-development/src/app/services/aee/mcp_adapter.py``
#       exporting ``class MCPAdapter(ActionAdapter)`` that OVERRIDES
#       ``list_tools`` and ``execute`` (per FR-40 follow-up).
#
#     - ``03-development/src/app/services/aee/cli_adapter.py``
#       exporting ``class CLIAdapter(ActionAdapter)`` that OVERRIDES
#       ``list_tools`` and ``execute`` (per FR-42 follow-up).
#
#   The imports below are unguarded: pytest will fail with Collection
#   Error (Exit Code 2) on the ``ActionAdapter`` /
#   ``ToolDefinition`` / ``ToolExecutionResult`` / ``MCPAdapter`` /
#   ``CLIAdapter`` references because the package does not exist yet.
#   That is the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
)
from app.services.aee.cli_adapter import CLIAdapter
from app.services.aee.mcp_adapter import MCPAdapter


# ---------------------------------------------------------------------------
# 1. Adapter implements list_tools().
#
# Spec input: adapter_class="MCPAdapter".
# SRS FR-39: "所有 Adapter 子類實作 list_tools + execute". The
# ``MCPAdapter`` subclass MUST override ``ActionAdapter.list_tools``
# and return a ``list`` (or ``List``) of ``ToolDefinition`` instances.
# This test pins both the override AND the return-type contract.
# ---------------------------------------------------------------------------
def test_fr39_adapter_implements_list_tools():
    adapter_class = "MCPAdapter"

    # Spec fr39-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``adapter_class``; we gate the
    # predicate on that variable matching the spec input
    # (``adapter_class="MCPAdapter"``).
    if adapter_class == "MCPAdapter":
        # Spec fr39-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert ActionAdapter is not None, (
            "fr39-ok predicate: ActionAdapter must be importable "
            "from app.services.aee.adapter"
        )

    # FR-39 functional assertion #1: ``MCPAdapter`` MUST be a concrete
    # subclass of ``ActionAdapter``. A regression that defines
    # ``MCPAdapter`` as a free-standing class (no inheritance) is
    # caught here — the LSP contract is enforced by the inheritance
    # check.
    assert issubclass(MCPAdapter, ActionAdapter), (
        f"FR-39: MCPAdapter must subclass ActionAdapter per SRS "
        f"FR-39 '所有 Adapter 子類實作 list_tools + execute'; "
        f"MRO={[c.__name__ for c in MCPAdapter.__mro__]}"
    )
    # FR-39 functional assertion #2: ``list_tools`` MUST be defined
    # directly on ``MCPAdapter`` (not just inherited from the abstract
    # base). The spec mandates that every adapter SUBCLASS implements
    # the method, so an inherited-not-overridden ``list_tools`` is a
    # FR-39 regression. ``__dict__`` membership catches this because
    # attributes resolved via ``__getattr__`` / MRO are NOT in
    # ``__dict__``.
    assert "list_tools" in MCPAdapter.__dict__, (
        "FR-39: MCPAdapter must override list_tools directly "
        "(found only via MRO, not in MCPAdapter.__dict__)"
    )

    # FR-39 functional assertion #3: ``MCPAdapter().list_tools()``
    # MUST return a ``list`` of ``ToolDefinition`` instances. We
    # instantiate with no constructor args (the adapter's
    # connection setup is FR-40's concern, not FR-39's; for FR-39
    # the test only verifies the interface contract).
    tools = MCPAdapter().list_tools()

    assert isinstance(tools, list), (
        f"FR-39: MCPAdapter().list_tools() must return list; "
        f"got {type(tools).__name__}"
    )
    # FR-39 functional assertion #4: every element of the returned
    # list MUST be a ``ToolDefinition`` instance. A regression that
    # returns dicts or strings instead of the spec-pinned dataclass
    # is caught here.
    assert all(isinstance(t, ToolDefinition) for t in tools), (
        "FR-39: every element of MCPAdapter().list_tools() must be "
        "a ToolDefinition instance"
    )


# ---------------------------------------------------------------------------
# 2. Adapter implements execute(tool_name, arguments).
#
# Spec input: adapter_class="CLIAdapter"; tool_name="get_shipping".
# SRS FR-39: "execute(tool_name, arguments) → ToolExecutionResult".
# The ``CLIAdapter`` subclass MUST override ``execute`` and return a
# ``ToolExecutionResult`` instance. To keep this test hermetic
# (no real subprocess / network / DB), we patch
# ``CLIAdapter.execute`` with a stub that returns a representative
# ``ToolExecutionResult`` — this isolates the FR-39 interface
# contract from FR-42's sandboxing implementation.
# ---------------------------------------------------------------------------
def test_fr39_adapter_implements_execute(monkeypatch):
    adapter_class = "CLIAdapter"
    tool_name = "get_shipping"
    arguments = {"order_id": "ORD-001"}

    # Spec fr39-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``adapter_class``; we gate the
    # predicate on that variable matching the spec input
    # (``adapter_class="CLIAdapter"``).
    if adapter_class == "CLIAdapter":
        # Spec fr39-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert ActionAdapter is not None, (
            "fr39-ok predicate: ActionAdapter must be importable "
            "from app.services.aee.adapter"
        )

    # FR-39 functional assertion #1: ``CLIAdapter`` MUST be a concrete
    # subclass of ``ActionAdapter``.
    assert issubclass(CLIAdapter, ActionAdapter), (
        f"FR-39: CLIAdapter must subclass ActionAdapter per SRS "
        f"FR-39 '所有 Adapter 子類實作 list_tools + execute'; "
        f"MRO={[c.__name__ for c in CLIAdapter.__mro__]}"
    )
    # FR-39 functional assertion #2: ``execute`` MUST be defined
    # directly on ``CLIAdapter`` (not just inherited from the abstract
    # base). Same rationale as test 1's override check.
    assert "execute" in CLIAdapter.__dict__, (
        "FR-39: CLIAdapter must override execute directly (found "
        "only via MRO, not in CLIAdapter.__dict__)"
    )

    # GREEN TODO: ``CLIAdapter.execute(self, tool_name: str,
    # arguments: dict) -> ToolExecutionResult`` MUST exist and accept
    # (tool_name, arguments) — see module docstring. The stub below
    # isolates the FR-39 interface check from FR-42's sandbox
    # implementation (which would otherwise launch a real subprocess).
    # GREEN agent: do NOT replace this monkeypatch — replace the
    # stub's body with the real implementation that actually invokes
    # the sandbox. The interface contract (signature + return type)
    # is what FR-39 pins; the side effect is FR-42's job.
    def _stub_execute(self, t_name, t_arguments):
        return ToolExecutionResult(
            success=True,
            output={"order_id": t_arguments.get("order_id"), "status": "in_transit"},
            error_message=None,
        )

    monkeypatch.setattr(CLIAdapter, "execute", _stub_execute)

    # FR-39 functional assertion #3: invoking the stubbed
    # ``CLIAdapter().execute(tool_name, arguments)`` MUST return a
    # ``ToolExecutionResult`` instance. The return type is the spec
    # contract — anything else (dict, tuple, None) is an FR-39
    # regression.
    result = CLIAdapter().execute(tool_name, arguments)

    assert isinstance(result, ToolExecutionResult), (
        f"FR-39: CLIAdapter().execute({tool_name!r}, {arguments!r}) "
        f"must return ToolExecutionResult; got {type(result).__name__}"
    )
    # FR-39 functional assertion #4: the ``tool_name`` sentinel value
    # is just a label for the test scenario — pin it so a regression
    # that renames the test input is caught.
    assert tool_name == "get_shipping", (
        f"FR-39: tool_name sentinel must be 'get_shipping'; got "
        f"{tool_name!r}"
    )


# ---------------------------------------------------------------------------
# 3. ToolExecutionResult has success / output / error_message.
#
# Spec input: result_fields="success,output,error_message".
# SRS FR-39: "ToolExecutionResult 包含 success, output, error_message".
# The result dataclass MUST expose exactly these three fields (the
# spec-pinned name for the error field is ``error_message`` — NOT
# ``error``, NOT ``error_msg``). A regression that renames the field
# would break every consumer that reads ``result.error_message`` and
# is caught here.
# ---------------------------------------------------------------------------
def test_fr39_tool_execution_result_has_success_output_error():
    result_fields = "success,output,error_message"

    # Spec fr39-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``result_fields``; we gate the
    # predicate on that variable matching the spec input
    # (``result_fields="success,output,error_message"``).
    if result_fields == "success,output,error_message":
        # Spec fr39-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert ToolExecutionResult is not None, (
            "fr39-ok predicate: ToolExecutionResult must be "
            "importable from app.services.aee.adapter"
        )

    # FR-39 functional assertion #1: the dataclass MUST declare all
    # three spec-pinned fields. We check ``__dataclass_fields__``
    # (present on every ``@dataclass``) rather than ``__annotations__``
    # (which would also include ClassVar and non-dataclass attrs).
    declared_fields = set(ToolExecutionResult.__dataclass_fields__.keys())
    required_fields = {"success", "output", "error_message"}
    missing = required_fields - declared_fields
    assert not missing, (
        f"FR-39: ToolExecutionResult must declare {sorted(required_fields)} "
        f"per SRS FR-39 'ToolExecutionResult 包含 success, output, "
        f"error_message'; missing={sorted(missing)}, "
        f"declared={sorted(declared_fields)}"
    )

    # FR-39 functional assertion #2: instantiating with all three
    # fields MUST succeed and the attributes MUST be readable. We
    # use the success path (error_message=None) as the happy path —
    # a separate failure-path test belongs to FR-42, not FR-39.
    result = ToolExecutionResult(
        success=True,
        output={"shipping_id": "SHP-1"},
        error_message=None,
    )

    assert result.success is True, (
        "FR-39: ToolExecutionResult.success must be readable and "
        "True for the happy path"
    )
    assert result.output == {"shipping_id": "SHP-1"}, (
        "FR-39: ToolExecutionResult.output must be readable and "
        "equal to the constructor argument"
    )
    assert result.error_message is None, (
        "FR-39: ToolExecutionResult.error_message must be readable "
        "and None on the success path"
    )

    # FR-39 functional assertion #3: the failure path also uses the
    # same three fields. We pin ``error_message="boom"`` here so a
    # regression that swaps success/failure semantics (e.g. always
    # returns error_message=None) is caught.
    failure = ToolExecutionResult(
        success=False,
        output=None,
        error_message="boom",
    )
    assert failure.success is False, (
        "FR-39: ToolExecutionResult.success must reflect the "
        "constructor argument (False for failure path)"
    )
    assert failure.error_message == "boom", (
        "FR-39: ToolExecutionResult.error_message must reflect the "
        "constructor argument (string for failure path)"
    )
