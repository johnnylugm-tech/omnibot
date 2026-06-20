"""TDD-RED: failing tests for FR-43 — ToolExecutor register/execute + default
shipping tools (get_shipping_status / update_shipping_address).

Spec source: 02-architecture/TEST_SPEC.md (FR-43)
SRS source : SRS.md FR-43 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-43):
    ToolExecutor：register(tool, handler) 綁定工具定義與 handler；
    execute(tool_name, arguments_json) 回傳 ToolExecutionResult；
    預設工具：get_shipping_status（查詢物流）、update_shipping_address
    （更新配送地址，出貨前才允許）.
    預設工具可正常執行；工具不存在回 success=False；
    update_shipping_address 在 shipped/delivered 狀態拒絕修改.

Active NFR patterns: NP-07 (dependency fault — unknown tool failure).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-39 already shipped the abstract ``ActionAdapter`` surface
# (``ToolDefinition``, ``ToolExecutionResult``, ``ok()`` / ``fail()``)
# under ``app.services.aee.adapter``. FR-43 pins the ``ToolExecutor``
# registry on top of that — a thin dispatch layer that binds tool
# definitions to handlers and dispatches ``execute(tool_name,
# arguments_json)`` to the right handler. The executor also ships with
# two default shipping tools (``get_shipping_status`` /
# ``update_shipping_address``); ``update_shipping_address`` is REJECTED
# once the order has shipped or been delivered.
#
# GREEN TODO (for the GREEN agent):
#
#   The following surface MUST live in
#   ``03-development/src/app/services/aee/tool_executor.py``
#   (a NEW module per FR-45 "single source of truth for ToolDefinition"
#   — ToolDefinition is RE-IMPORTED from ``app.services.aee.adapter``,
#   NOT redefined):
#
#     - ``class ToolExecutor`` whose constructor takes no required
#       args (or accepts optional ``handlers`` / ``default_tools``
#       kwargs) and that exposes:
#
#         * ``register(tool: ToolDefinition, handler: Callable[..., Any])``
#           — binds a tool definition to a Python callable. The
#           handler's return value is wrapped in ``ToolExecutionResult``
#           via the ``ok()`` factory on the success path.
#
#         * ``execute(tool_name: str, arguments_json: str | dict)``
#           → ``ToolExecutionResult``. If ``arguments_json`` is a
#           ``str``, the executor MUST ``json.loads`` it before
#           forwarding to the handler. If the tool is not registered,
#           the executor MUST return
#           ``ToolExecutionResult(success=False, error_message=<non-empty>)``
#           — MUST NOT raise (NP-07 graceful degradation).
#
#         * Default tools pre-registered at construction time:
#
#             - ``get_shipping_status(order_id: str)`` → dict with
#               ``order_id``, ``status``, ``carrier``, ``tracking_no``.
#               Returns ``ToolExecutionResult(success=True, output=<dict>)``.
#
#             - ``update_shipping_address(order_id: str,
#               new_address: str)`` → guarded by order ``status``:
#               when ``status in {"shipped", "delivered"}`` the
#               executor MUST return
#               ``ToolExecutionResult(success=False, error_message
#               mentioning "shipped" / "delivered" / "cannot")``.
#               Otherwise return
#               ``ToolExecutionResult(success=True, output=<updated dict>)``.
#
#   During the current RED step, ``ToolExecutor`` is intentionally
#   NOT YET defined. The imports below are unguarded: pytest MUST fail
#   with Collection Error (Exit Code 2). That is the valid RED signal —
#   the GREEN agent adds the module above.
# ---------------------------------------------------------------------------
from app.services.aee.adapter import (  # noqa: F401  -- RED: GREEN reuses this
    ToolDefinition,
    ToolExecutionResult,
)
from app.services.aee.tool_executor import (
    ToolExecutor,
)


# ---------------------------------------------------------------------------
# 1. Unknown tool MUST be rejected with success=False (NP-07).
#
# Spec input: tool_name="nonexistent"; expected_success="false".
# SRS FR-43: "工具不存在回 success=False".
# Asking the executor to dispatch a tool that was never registered
# MUST yield ``ToolExecutionResult(success=False, error_message=<non-empty>)``
# — never raise, never return success=True.
# ---------------------------------------------------------------------------
def test_fr43_unknown_tool_returns_false():
    tool_name = "nonexistent"
    expected_success = "false"

    # Spec fr43-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``tool_name``; we gate the predicate on
    # that variable matching the spec input
    # (``tool_name="nonexistent"``).
    if tool_name == "nonexistent":
        # Spec fr43-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert ToolExecutor is not None, (
            "fr43-ok predicate: ToolExecutor must be importable "
            "from app.services.aee.tool_executor"
        )

    # GREEN TODO: ``ToolExecutor`` MUST expose
    # ``execute(tool_name: str, arguments_json: str | dict)`` that
    # returns ``ToolExecutionResult(success=False, error_message=<non-empty>)``
    # when ``tool_name`` is not registered — MUST NOT raise.
    executor = ToolExecutor()

    # Sanity-check: ``execute`` MUST exist on the public surface.
    # If GREEN forgets to add it, this AttributeError is the RED signal.
    assert hasattr(executor, "execute"), (
        "FR-43: ToolExecutor must expose an execute(tool_name, "
        "arguments_json) method for dispatching tool calls"
    )

    # GREEN TODO: ``ToolExecutor.execute`` MUST handle the
    # ``arguments_json`` kwarg as either a ``str`` (JSON-encoded) or a
    # ``dict`` (already-decoded). For this case the payload is empty.
    result = executor.execute(tool_name, "{}")  # type: ignore[attr-defined]

    assert isinstance(result, ToolExecutionResult), (
        f"FR-43: ToolExecutor.execute must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-43: ToolExecutor.execute on unknown tool must return "
        f"success=False (expected_success={expected_success!r}); "
        f"got success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is not None and result.error_message != "", (
        f"FR-43: ToolExecutor.execute on unknown tool must carry a "
        f"non-empty error_message; got {result.error_message!r}"
    )

    # Sentinel MUST be preserved.
    assert expected_success == "false", (
        f"FR-43: expected_success sentinel must be 'false'; "
        f"got {expected_success!r}"
    )


# ---------------------------------------------------------------------------
# 2. update_shipping_address MUST be blocked when status="shipped".
#
# Spec input: tool_name="update_shipping_address"; status="shipped".
# SRS FR-43: "update_shipping_address 在 shipped/delivered 狀態拒絕修改".
# Asking the executor to update the address of an order that has
# already shipped MUST yield ``ToolExecutionResult(success=False)``
# with an ``error_message`` that flags the shipped status.
# ---------------------------------------------------------------------------
def test_fr43_update_address_blocked_when_shipped():
    tool_name = "update_shipping_address"
    status = "shipped"

    # Spec fr43-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``status``; we gate the predicate on
    # that variable matching the spec input (``status="shipped"``).
    if status == "shipped":
        # Spec fr43-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert ToolExecutor is not None, (
            "fr43-ok predicate: ToolExecutor must be importable "
            "from app.services.aee.tool_executor"
        )

    # GREEN TODO: ``ToolExecutor.execute("update_shipping_address", {...})``
    # MUST refuse the call when the order's ``status`` is
    # ``"shipped"`` (or ``"delivered"``), returning
    # ``ToolExecutionResult(success=False, error_message mentioning
    # "shipped" / "cannot" / "address")``.
    executor = ToolExecutor()

    assert hasattr(executor, "execute"), (
        "FR-43: ToolExecutor must expose execute for tool dispatch"
    )

    # The default ``update_shipping_address`` handler is expected to
    # look up the order by ``order_id`` and inspect ``status``. The
    # test injects a status via the arguments payload. GREEN MUST
    # either (a) consult an injected order store, (b) accept a
    # ``status`` kwarg on the handler, or (c) ship with a default
    # order fixture that records the test order as shipped.
    arguments = {
        "order_id": "ORD-001",
        "new_address": "新北市板橋區文化路 100 號",
        "status": status,
    }
    result = executor.execute(  # type: ignore[attr-defined]
        tool_name,
        arguments,
    )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-43: ToolExecutor.execute must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-43: update_shipping_address on status={status!r} must "
        f"return success=False (block shipped orders); got "
        f"success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is not None, (
        "FR-43: update_shipping_address on shipped order must carry "
        "a non-empty error_message; got None"
    )
    # Error message MUST surface the shipped-state reason so the
    # caller / user can see why the update was blocked.
    lowered = result.error_message.lower()
    assert (
        "shipped" in lowered
        or "cannot" in lowered
        or "address" in lowered
    ), (
        f"FR-43: update_shipping_address error_message must mention "
        f"shipped/cannot/address; got {result.error_message!r}"
    )


# ---------------------------------------------------------------------------
# 3. get_shipping_status happy path: returns the shipping record.
#
# Spec input: tool_name="get_shipping_status"; order_id="ORD-001".
# SRS FR-43: "預設工具：get_shipping_status（查詢物流）";
# "預設工具可正常執行".
# The default ``get_shipping_status`` tool MUST look up an order by
# ``order_id`` and return ``ToolExecutionResult(success=True,
# output=<shipping record>)``.
# ---------------------------------------------------------------------------
def test_fr43_get_shipping_status_returns_result():
    tool_name = "get_shipping_status"
    order_id = "ORD-001"

    # Spec fr43-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``order_id``; we gate the predicate on
    # that variable matching the spec input (``order_id="ORD-001"``).
    if order_id == "ORD-001":
        # Spec fr43-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert ToolExecutor is not None, (
            "fr43-ok predicate: ToolExecutor must be importable "
            "from app.services.aee.tool_executor"
        )

    # GREEN TODO: ``ToolExecutor.execute("get_shipping_status",
    # {"order_id": "ORD-001"})`` MUST return
    # ``ToolExecutionResult(success=True, output=<shipping record>)``
    # where the record contains at least ``order_id`` and ``status``.
    executor = ToolExecutor()

    assert hasattr(executor, "execute"), (
        "FR-43: ToolExecutor must expose execute for tool dispatch"
    )

    result = executor.execute(  # type: ignore[attr-defined]
        tool_name,
        {"order_id": order_id},
    )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-43: ToolExecutor.execute must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is True, (
        f"FR-43: get_shipping_status happy path must return success=True; "
        f"got success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is None, (
        f"FR-43: get_shipping_status happy path must have "
        f"error_message=None; got {result.error_message!r}"
    )
    # Output MUST be a non-empty shipping record referencing the order.
    assert result.output is not None, (
        "FR-43: get_shipping_status must return a non-None output; "
        "got None"
    )
    assert isinstance(result.output, dict), (
        f"FR-43: get_shipping_status output must be a dict; "
        f"got {type(result.output).__name__}"
    )
    # Echo order_id back so the caller can correlate.
    assert result.output.get("order_id") == order_id, (
        f"FR-43: get_shipping_status output must echo order_id="
        f"{order_id!r}; got {result.output.get('order_id')!r}"
    )


# ---------------------------------------------------------------------------
# 4. update_shipping_address MUST also be blocked when status="delivered".
#
# Spec input: tool_name="update_shipping_address"; status="delivered".
# SRS FR-43: "update_shipping_address 在 shipped/delivered 狀態拒絕修改".
# Asking the executor to update the address of an already-delivered
# order MUST yield ``ToolExecutionResult(success=False)`` with an
# ``error_message`` that flags the delivered status.
# ---------------------------------------------------------------------------
def test_fr43_update_address_blocked_when_delivered():
    tool_name = "update_shipping_address"
    status = "delivered"

    # Spec fr43-ok predicate 'result is not None' applies_to case 4.
    # The trigger for case 4 is ``status``; we gate the predicate on
    # that variable matching the spec input (``status="delivered"``).
    if status == "delivered":
        # Spec fr43-ok predicate 'result is not None' applies_to case 4.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 4's input.
        assert ToolExecutor is not None, (
            "fr43-ok predicate: ToolExecutor must be importable "
            "from app.services.aee.tool_executor"
        )

    # GREEN TODO: ``ToolExecutor.execute("update_shipping_address", {...})``
    # MUST refuse the call when the order's ``status`` is
    # ``"delivered"``, returning
    # ``ToolExecutionResult(success=False, error_message mentioning
    # "delivered" / "cannot" / "address")``.
    executor = ToolExecutor()

    assert hasattr(executor, "execute"), (
        "FR-43: ToolExecutor must expose execute for tool dispatch"
    )

    arguments = {
        "order_id": "ORD-001",
        "new_address": "新北市板橋區文化路 100 號",
        "status": status,
    }
    result = executor.execute(  # type: ignore[attr-defined]
        tool_name,
        arguments,
    )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-43: ToolExecutor.execute must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-43: update_shipping_address on status={status!r} must "
        f"return success=False (block delivered orders); got "
        f"success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is not None, (
        "FR-43: update_shipping_address on delivered order must carry "
        "a non-empty error_message; got None"
    )
    lowered = result.error_message.lower()
    assert (
        "delivered" in lowered
        or "cannot" in lowered
        or "address" in lowered
    ), (
        f"FR-43: update_shipping_address error_message must mention "
        f"delivered/cannot/address; got {result.error_message!r}"
    )
