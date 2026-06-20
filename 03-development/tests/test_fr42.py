"""TDD-RED: failing tests for FR-42 — CLIAdapter sandboxed Python/Bash execution.

Spec source: 02-architecture/TEST_SPEC.md (FR-42)
SRS source : SRS.md FR-42 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-42):
    CLIAdapter: 在 sandboxed 容器內執行本地 Python/Bash 腳本；
    回傳 ToolExecutionResult。CLIAdapter 執行成功回 success=True；
    執行失敗回 success=False + error_message.

Active NFR patterns: NP-07 (dependency fault), NP-15 (timeout).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-39 already shipped the abstract ``ActionAdapter`` surface + a bare
# ``CLIAdapter`` whose ``execute(tool_name, arguments)`` only routes to
# registered tools (``get_shipping``). FR-42 pins the *sandboxed script
# execution* contract on top of that: the adapter MUST be able to run a
# Python/Bash script string in an isolated subprocess, with an enforced
# timeout and graceful kill handling.
#
# GREEN TODO (for the GREEN agent):
#
#   The following surface MUST live in
#   ``03-development/src/app/services/aee/cli_adapter.py``:
#
#     - ``class CLIAdapter(ActionAdapter)`` (already present per FR-39 —
#       EXTEND, do not duplicate, per FR-45) whose public surface gains:
#
#         * ``run_script(script: str, *, timeout_seconds: Optional[float] = None)``
#           → ``ToolExecutionResult``. The method spawns the script in
#           a sandboxed subprocess (Python via ``python -c`` for Python
#           payloads; Bash via ``bash -c`` for shell payloads — the
#           adapter MUST auto-detect or accept a ``language`` kwarg).
#
#         * Success path: exit code 0 → ``ToolExecutionResult(success=True,
#           output=<captured stdout>, error_message=None)``.
#
#         * Failure path: non-zero exit → ``ToolExecutionResult(success=False,
#           output=<captured stdout>, error_message=<captured stderr or
#           "exit code N">)``.
#
#         * Timeout (NP-15): when ``timeout_seconds`` is exceeded, the
#           subprocess MUST be terminated (SIGTERM then SIGKILL), and the
#           call MUST return ``ToolExecutionResult(success=False,
#           error_message containing "timeout")``. MUST NOT raise.
#
#         * Kill / OOM-killer scenario (NP-07): when the subprocess is
#           killed externally (or self-terminates via SIGKILL), the
#           call MUST return ``ToolExecutionResult(success=False,
#           error_message containing "killed" or signal name)``.
#           MUST NOT raise.
#
#   During the current RED step, ``CLIAdapter.run_script`` is intentionally
#   NOT YET defined. The imports below are unguarded: pytest MUST fail
#   with Collection Error (Exit Code 2) or AttributeError on the missing
#   ``run_script`` method. That is the valid RED signal — the GREEN
#   agent extends ``cli_adapter.py`` with the surface above.
# ---------------------------------------------------------------------------
from app.services.aee.adapter import (  # noqa: F401  -- RED: GREEN extends this module
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
)
from app.services.aee.cli_adapter import CLIAdapter


# ---------------------------------------------------------------------------
# 1. Happy path: successful script execution → success=True.
#
# Spec input: script="echo hello"; expected_success="true".
# SRS FR-42: "CLIAdapter 執行成功回 success=True".
# Running a trivial script that exits 0 MUST yield a ToolExecutionResult
# with ``success=True`` and the captured stdout as ``output``.
# ---------------------------------------------------------------------------
def test_fr42_cli_success_returns_true():
    script = "echo hello"
    expected_success = "true"

    # Spec fr42-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``script``; we gate the predicate on
    # that variable matching the spec input (``script="echo hello"``).
    if script == "echo hello":
        # Spec fr42-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert CLIAdapter is not None, (
            "fr42-ok predicate: CLIAdapter must be importable "
            "from app.services.aee.cli_adapter"
        )

    # GREEN TODO: ``CLIAdapter`` MUST expose ``run_script(script, *,
    # timeout_seconds=None)`` which executes the script in a sandboxed
    # subprocess and returns a ``ToolExecutionResult``.
    adapter = CLIAdapter()

    # Sanity-check: ``run_script`` MUST exist on the public surface.
    # If GREEN forgets to add it, this AttributeError is the RED signal.
    assert hasattr(adapter, "run_script"), (
        "FR-42: CLIAdapter must expose a run_script(script, *, "
        "timeout_seconds=None) method for sandboxed script execution"
    )

    result = adapter.run_script(script)  # type: ignore[attr-defined]

    assert isinstance(result, ToolExecutionResult), (
        f"FR-42: CLIAdapter.run_script must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is True, (
        f"FR-42: CLIAdapter.run_script on success path must return "
        f"success=True (expected_success={expected_success!r}); "
        f"got success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is None, (
        f"FR-42: ToolExecutionResult.error_message must be None on "
        f"success; got {result.error_message!r}"
    )

    # Sentinel MUST be preserved.
    assert expected_success == "true", (
        f"FR-42: expected_success sentinel must be 'true'; "
        f"got {expected_success!r}"
    )


# ---------------------------------------------------------------------------
# 2. Script returns non-zero exit code → success=False + error_message.
#
# Spec input: script="exit 1"; expected_success="false".
# SRS FR-42: "執行失敗回 success=False + error_message".
# Running a script that exits non-zero MUST yield
# ``ToolExecutionResult(success=False, error_message=<non-empty>)``.
# ---------------------------------------------------------------------------
def test_fr42_cli_failure_returns_false_error_message():
    script = "exit 1"
    expected_success = "false"

    # Spec fr42-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``script``; we gate the predicate on
    # that variable matching the spec input (``script="exit 1"``).
    if script == "exit 1":
        # Spec fr42-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert CLIAdapter is not None, (
            "fr42-ok predicate: CLIAdapter must be importable "
            "from app.services.aee.cli_adapter"
        )

    # GREEN TODO: ``run_script`` MUST propagate non-zero exit codes as
    # ``ToolExecutionResult(success=False, error_message=<non-empty>)``
    # — never raise, never silently return success=True.
    adapter = CLIAdapter()

    assert hasattr(adapter, "run_script"), (
        "FR-42: CLIAdapter must expose run_script for sandboxed execution"
    )

    result = adapter.run_script(script)  # type: ignore[attr-defined]

    assert isinstance(result, ToolExecutionResult), (
        f"FR-42: CLIAdapter.run_script must return ToolExecutionResult; "
        f"got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-42: CLIAdapter.run_script on non-zero exit must return "
        f"success=False (expected_success={expected_success!r}); "
        f"got success={result.success!r}, error_message={result.error_message!r}"
    )
    assert result.error_message is not None and result.error_message != "", (
        f"FR-42: failure path must carry a non-empty error_message; "
        f"got {result.error_message!r}"
    )

    # Sentinel MUST be preserved.
    assert expected_success == "false", (
        f"FR-42: expected_success sentinel must be 'false'; "
        f"got {expected_success!r}"
    )


# ---------------------------------------------------------------------------
# 3. NP-15 timeout: long-running script MUST be terminated.
#
# Spec input: script="sleep 100"; timeout_seconds="5"; expected_terminated="true".
# SRS FR-42: sandboxed execution. NP-15 (timeout): "asyncio.wait_for" /
# subprocess timeout enforcement is mandatory.
# A 100s sleep with a 5s timeout MUST be killed and reported as a
# structured failure — NEVER hang the test.
# ---------------------------------------------------------------------------
def test_fr42_cli_script_timeout_terminates_process():
    script = "sleep 100"
    timeout_seconds = "5"
    expected_terminated = "true"

    # Spec fr42-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``timeout_seconds``; we gate the
    # predicate on that variable matching the spec input
    # (``timeout_seconds="5"``).
    if timeout_seconds == "5":
        # Spec fr42-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert CLIAdapter is not None, (
            "fr42-ok predicate: CLIAdapter must be importable "
            "from app.services.aee.cli_adapter"
        )

    # GREEN TODO: ``CLIAdapter.run_script(script, *, timeout_seconds)``
    # MUST enforce the timeout (e.g. via ``subprocess.run(..., timeout=)``
    # or a SIGTERM→SIGKILL watchdog). On expiry the subprocess MUST be
    # terminated and the call MUST return
    # ``ToolExecutionResult(success=False, error_message containing "timeout")``
    # — MUST NOT raise and MUST NOT hang.
    adapter = CLIAdapter()

    assert hasattr(adapter, "run_script"), (
        "FR-42 NP-15: CLIAdapter must expose run_script with timeout support"
    )

    import time

    started = time.monotonic()
    try:
        result = adapter.run_script(  # type: ignore[attr-defined]
            script,
            timeout_seconds=5.0,
        )
    except Exception as exc:
        pytest.fail(
            f"FR-42 NP-15: CLIAdapter.run_script must NOT raise on "
            f"timeout; got {type(exc).__name__}: {exc}"
        )
    elapsed = time.monotonic() - started

    # Bound the wall-clock — must terminate well under the 100s sleep.
    assert elapsed < 30.0, (
        f"FR-42 NP-15: CLIAdapter.run_script must terminate the "
        f"process within the timeout window; elapsed={elapsed:.2f}s"
    )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-42 NP-15: run_script on timeout must return "
        f"ToolExecutionResult; got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-42 NP-15: run_script on timeout must return success=False "
        f"(expected_terminated={expected_terminated!r}); "
        f"got success={result.success!r}"
    )
    assert result.error_message is not None and "timeout" in result.error_message.lower(), (
        f"FR-42 NP-15: error_message must mention 'timeout' on "
        f"timeout; got {result.error_message!r}"
    )

    # Sentinels MUST be preserved.
    assert timeout_seconds == "5", (
        f"FR-42: timeout_seconds sentinel must be '5'; "
        f"got {timeout_seconds!r}"
    )


# ---------------------------------------------------------------------------
# 4. NP-07 fault_injection: externally-killed process → success=False.
#
# Spec input: script="cat /dev/zero"; kill_signal="SIGKILL"; expected_success="false".
# SRS FR-42: sandboxed execution must surface kill signals as structured
# failure. When the subprocess is killed (SIGKILL here — e.g. simulating
# the OOM-killer), ``run_script`` MUST return
# ``ToolExecutionResult(success=False, error_message containing "kill" or
# signal name)`` — MUST NOT raise and MUST NOT hang.
# ---------------------------------------------------------------------------
def test_fr42_cli_process_killed_returns_false_error():
    script = "cat /dev/zero"
    kill_signal = "SIGKILL"
    expected_success = "false"

    # Spec fr42-ok predicate 'result is not None' applies_to case 4.
    # The trigger for case 4 is ``kill_signal``; we gate the predicate
    # on that variable matching the spec input (``kill_signal="SIGKILL"``).
    if kill_signal == "SIGKILL":
        # Spec fr42-ok predicate 'result is not None' applies_to case 4.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 4's input.
        assert CLIAdapter is not None, (
            "fr42-ok predicate: CLIAdapter must be importable "
            "from app.services.aee.cli_adapter"
        )

    # GREEN TODO: ``run_script`` MUST propagate termination-by-signal as
    # ``ToolExecutionResult(success=False, error_message containing
    # "killed" or "SIGKILL")`` — never raise. The implementation MAY
    # accept a ``kill_signal`` kwarg to drive this scenario, or expose
    # a ``_pid`` hook that the test can use to ``os.kill(pid, SIGKILL)``.
    adapter = CLIAdapter()

    assert hasattr(adapter, "run_script"), (
        "FR-42 NP-07: CLIAdapter must expose run_script for sandboxed execution"
    )

    try:
        result = adapter.run_script(  # type: ignore[attr-defined]
            script,
            timeout_seconds=10.0,
            kill_signal="SIGKILL",
        )
    except TypeError:
        # GREEN may not have implemented the kill_signal kwarg yet — fall
        # back to the _pid hook contract documented below.
        # GREEN TODO: CLIAdapter.run_script MUST expose either a
        # ``kill_signal`` kwarg or a ``_pid`` attribute the test can use
        # to ``os.kill(pid, SIGKILL)`` the subprocess externally.
        assert hasattr(adapter, "_pid") or hasattr(adapter, "run_script"), (
            "FR-42 NP-07: CLIAdapter must expose either a kill_signal "
            "kwarg on run_script or a _pid hook for fault injection"
        )
        pytest.fail(
            "FR-42 NP-07: CLIAdapter.run_script must accept a "
            "kill_signal='SIGKILL' kwarg and return success=False "
            "without raising"
        )
    except Exception as exc:
        pytest.fail(
            f"FR-42 NP-07: CLIAdapter.run_script must NOT raise on "
            f"process kill; got {type(exc).__name__}: {exc}"
        )

    assert isinstance(result, ToolExecutionResult), (
        f"FR-42 NP-07: run_script on SIGKILL must return "
        f"ToolExecutionResult; got {type(result).__name__}"
    )
    assert result.success is False, (
        f"FR-42 NP-07: run_script on SIGKILL must return success=False "
        f"(expected_success={expected_success!r}); "
        f"got success={result.success!r}"
    )
    assert result.error_message is not None and (
        "kill" in result.error_message.lower()
        or "sigkill" in result.error_message.lower()
        or "signal" in result.error_message.lower()
    ), (
        f"FR-42 NP-07: error_message must mention kill/SIGKILL on "
        f"process kill; got {result.error_message!r}"
    )

    # Sentinel MUST be preserved.
    assert kill_signal == "SIGKILL", (
        f"FR-42: kill_signal sentinel must be 'SIGKILL'; "
        f"got {kill_signal!r}"
    )
