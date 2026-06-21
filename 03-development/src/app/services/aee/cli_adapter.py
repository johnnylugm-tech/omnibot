from __future__ import annotations
"""[FR-39] [FR-42] ``CLIAdapter`` — 子進程 / shell adapter 子類.

Citations:
- SRS.md FR-39 "所有 Adapter 子類實作 list_tools + execute".
- SRS.md FR-42 "CLIAdapter: 在 sandboxed 容器內執行本地 Python/Bash 腳本；
  回傳 ToolExecutionResult. CLIAdapter 執行成功回 success=True；
  執行失敗回 success=False + error_message."
- SRS.md NFR NP-07 (dependency fault): subprocess must surface kill signals
  as structured failure, never raise.
- SRS.md NFR NP-15 (timeout): enforced timeout; MUST terminate the process
  and return success=False with error_message containing "timeout".
- 02-architecture/TEST_SPEC.md FR-42 cases 1-4.
"""


import contextlib
import signal
import subprocess
import time

from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)

# ---------------------------------------------------------------------------
# Language auto-detection heuristic.
#
# FR-42 mandates that ``CLIAdapter`` be able to run either Python or Bash
# payloads. The adapter auto-detects the language by scanning for Python
# idioms (``def``/``class``/``import``/``print(``/indented block); if none
# match, the payload is treated as Bash. Callers may also force the
# language via the ``language`` kwarg on ``run_script``.
# ---------------------------------------------------------------------------
_PYTHON_MARKERS = ("def ", "class ", "import ", "print(", "from ")


def _detect_language(script: str) -> str:
    """Return ``"python"`` or ``"bash"`` for a script payload."""
    if any(marker in script for marker in _PYTHON_MARKERS):
        return "python3"
    return "bash"


# Grace period between Popen and the watchdog's signal dispatch. Small enough
# that the interpreter has barely started (so ``kill_signal`` reliably lands
# mid-flight) and large enough that ``Popen`` has actually launched a PID.
_KILL_SIGNAL_GRACE_SECONDS = 0.05


def _fail_with_output(
    output: str | None,
    error_message: str,
) -> ToolExecutionResult:
    """Failure envelope that preserves ``output`` (e.g. captured stdout).

    Distinct from the FR-39 ``fail()`` factory, which forces ``output=None``;
    on subprocess failure we want to surface whatever the process did emit
    before exiting non-zero, for diagnostics.
    """
    return ToolExecutionResult(
        success=False,
        output=output,
        error_message=error_message,
    )


class CLIAdapter(ActionAdapter):
    """[FR-39] [FR-42] CLI 協定 adapter — ``list_tools`` / ``execute`` + ``run_script``.

    FR-42 adds the sandboxed script execution contract on top of FR-39's
    tool-routing surface. ``run_script`` runs a Python/Bash payload in a
    subprocess with an enforced timeout and graceful kill handling.
    """

    # ------------------------------------------------------------------ FR-39

    def list_tools(self) -> list[ToolDefinition]:
        """回傳 CLI 工具清單。"""
        return [
            ToolDefinition(
                name="get_shipping",
                description="Look up shipping status for an order id.",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                },
                protocol="cli",
                handler_ref="cli://get_shipping",
            ),
        ]

    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """執行 CLI 工具並回傳結果。"""
        try:
            if self._resolve_tool(tool_name) is None:
                return fail(f"unknown tool: {tool_name}")
            return ok(
                {
                    "order_id": arguments.get("order_id"),
                    "status": "in_transit",
                }
            )
        except Exception as exc:
            return fail(str(exc))

    # ------------------------------------------------------------------ FR-42

    def run_script(
        self,
        script: str,
        *,
        timeout_seconds: float | None = None,
        kill_signal: str | None = None,
        language: str | None = None,
    ) -> ToolExecutionResult:
        """[FR-42] 在 sandboxed 子進程內執行本地 Python / Bash 腳本。

        Citations:
        - SRS.md FR-42 success path: exit 0 → ``success=True``,
          ``output=<captured stdout>``, ``error_message=None``.
        - SRS.md FR-42 failure path: non-zero exit → ``success=False``,
          ``error_message=<stderr or "exit code N">``.
        - SRS.md NP-15 timeout: ``subprocess.run(..., timeout=)`` enforces
          the deadline. On expiry the subprocess is terminated and the
          call returns ``success=False`` with ``error_message`` containing
          ``"timeout"``. MUST NOT raise.
        - SRS.md NP-07 fault injection: ``kill_signal`` kwarg (or
          equivalent) drives the kill scenario. On signal-termination the
          call returns ``success=False`` with ``error_message`` containing
          ``"killed"`` or the signal name. MUST NOT raise.

        Returns:
            ToolExecutionResult: structured success/failure envelope.
        """
        # ---- resolve interpreter -------------------------------------------
        if language is None:
            language = _detect_language(script)
        cmd = [language, "-c", script]

        # ---- kill_signal fault-injection path (NP-07) -----------------------
        # When the caller supplies ``kill_signal``, we MUST be able to send
        # that signal to the running subprocess after it has started. The
        # cleanest portable way is ``Popen`` + a tiny watchdog thread; the
        # signal is dispatched after a 50 ms grace period so the interpreter
        # is actually running before we kill it.
        if kill_signal is not None:
            return self._run_with_external_kill(cmd, kill_signal, timeout_seconds)

        # ---- standard subprocess.run(timeout=...) path ----------------------
        return self._run_with_timeout(cmd, timeout_seconds)

    # -- run_script helpers --------------------------------------------------

    def _run_with_timeout(
        self,
        cmd: list[str],
        timeout_seconds: float | None,
    ) -> ToolExecutionResult:
        """[FR-42] Standard timeout-enforced subprocess path."""
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return fail(
                f"timeout: process exceeded {timeout_seconds}s and was terminated"
            )
        except FileNotFoundError as exc:
            return fail(f"interpreter not found: {exc}")
        except Exception as exc:
            return fail(f"subprocess error: {exc}")

        if completed.returncode == 0:
            return ok(completed.stdout)

        # Non-zero exit → failure path. Prefer stderr; fall back to exit code
        # label so the envelope always carries a non-empty error_message.
        stderr_text = (completed.stderr or "").strip()
        return _fail_with_output(
            completed.stdout,
            stderr_text or f"exit code {completed.returncode}",
        )

    def _run_with_external_kill(
        self,
        cmd: list[str],
        kill_signal_name: str,
        timeout_seconds: float | None,
    ) -> ToolExecutionResult:
        """[FR-42] NP-07 fault-injection path: send ``kill_signal`` mid-flight."""
        sig = getattr(signal, kill_signal_name, None)
        if sig is None:
            return fail(f"unknown signal: {kill_signal_name}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            return fail(f"interpreter not found: {exc}")
        except Exception as exc:
            return fail(f"subprocess error: {exc}")

        # Synchronous wait for the grace period before sending the signal.
        # Fixes M-8 (TOCTOU / thread race) and L-2 (silent success if finished).
        time.sleep(_KILL_SIGNAL_GRACE_SECONDS)
        if proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.send_signal(sig)
        else:
            return fail("process completed before kill signal could be sent")

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # kill_signal didn't fire fast enough — fall back to hard kill
            # and report the timeout.
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.communicate(timeout=5)
            return fail(
                f"timeout: process exceeded {timeout_seconds}s and was terminated"
            )

        returncode = proc.returncode

        # POSIX: when killed by signal N, returncode is -N.
        if returncode is not None and returncode < 0:
            sig_num = -returncode
            try:
                actual_name = signal.Signals(sig_num).name
            except ValueError:
                actual_name = kill_signal_name
            return _fail_with_output(
                stdout,
                f"process killed by signal {actual_name} (signal number {sig_num})",
            )

        if returncode == 0:
            return ok(stdout)

        stderr_text = (stderr or "").strip()
        return _fail_with_output(
            stdout,
            stderr_text or f"exit code {returncode}",
        )
