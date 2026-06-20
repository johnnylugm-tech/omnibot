"""[FR-65] LLMJudge — Ensemble Judge 平行呼叫 (gpt-4o-mini + claude-3-5-haiku).

Spec source: 02-architecture/TEST_SPEC.md (FR-65)
SRS source : SRS.md FR-65 (Module 14: LLM Judge)
SAD mapping: app.services.llm_judge — "LLM-as-a-Judge ensemble (FR-65–69)"

FR-65 -- LLMJudge.evaluate：
    primary judge = gpt-4o-mini, secondary judge = claude-3-5-haiku.
    Both judges configured with temperature=0 (deterministic scoring).
    Both judges called CONCURRENTLY (parallel) — not sequentially.
    Each judge independently scores politeness + accuracy on a 1–5 scale.
    NP-07 graceful degradation: if one judge is down, evaluate() falls back
    to single-judge mode using only the surviving judge and still returns
    a non-None JudgeResult (does not propagate the exception).
    NP-15 timeout handling: if one judge exceeds its time budget, evaluate()
    returns a PARTIAL result based on the surviving judge (does not propagate
    TimeoutError).

Public surface pinned by this module:

    - ``JudgeResult(politeness, accuracy, judge_name="")`` — aggregated
      result exposing both 1-5 scores. Exposes ``politeness`` and
      ``accuracy`` so downstream FR-66 (politeness = max) and FR-67
      (accuracy = min) aggregation can derive final metrics from a
      single canonical shape.
    - ``LLMJudge(primary_judge, secondary_judge, ...)`` — ensemble
      judge coordinator with constructor injection of both LLM client
      callables (so unit tests can stub the LLM clients without real
      network I/O).
    - ``LLMJudge.evaluate(message, response)`` — async coroutine that
      calls both judges CONCURRENTLY (via ``asyncio.gather``) with a
      per-judge timeout, then aggregates into a JudgeResult.
    - ``LLMJudge.TEMPERATURE`` — class constant ``0`` pinning the
      deterministic-scoring config (SRS FR-65: "temperature=0 確保確定性").

Citations:
    - SRS.md FR-65 -- "Ensemble Judge：primary=gpt-4o-mini (temp=0) +
      secondary=claude-3-5-haiku (temp=0)；平行呼叫兩個 judge；各 judge
      分別評測 politeness + accuracy" (line 153).
    - SRS.md FR-65 -- acceptance "兩個 judge 並行呼叫；temperature=0
      確保確定性；各 judge 回傳 JudgeResult" (line 153).
    - SRS.md FR-65 -- implementation_functions: "LLMJudge.evaluate()" (line 153).
    - SRS.md FR-66 -- "Politeness 聚合：max(primary_score, secondary_score)
      （寬鬆評分，情感支持寧可寬容）" (line 154).
    - SRS.md FR-67 -- "Accuracy 聚合：min(primary_score, secondary_score)
      （保守評分，幻覺不可接受）" (line 155).
    - SAD.md -- "Module: llm_judge.py" (line 266).
    - SAD.md -- "LLMJudge.evaluate() (gpt-4o-mini + claude-3-5-haiku,
      temp=0, parallel) → FR-65" (line 267).
    - SAD.md -- "Architecture Risk: llm_judge.py makes parallel network
      calls to 2 LLM APIs → NP-07 + NP-15 forced" (line 273).
    - SAD.md -- module→FR mapping "app.services.llm_judge → FR-65" (line 813).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# JudgeResult — aggregated score shape.
#
# Carries both dimensions (politeness + accuracy) on a 1-5 scale per
# SRS FR-65 acceptance "各 judge 回傳 JudgeResult". ``judge_name`` is a
# debugging aid (which judge contributed the score) — it is not part
# of the spec's behavioural contract.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class JudgeResult:
    """[FR-65] Aggregated judge score (politeness + accuracy on a 1-5 scale).

    Exposes both dimensions so downstream FR-66 (politeness = max) and
    FR-67 (accuracy = min) can derive their final metrics from a single
    canonical shape. The 1-5 scale is the SRS FR-65 evaluation rubric:

        Politeness : 1=Rude, 2=Cold, 3=Professional, 4=Warm, 5=Exceptional
        Accuracy   : 1=False, 2=Incomplete, 3=Partially Correct,
                     4=Correct, 5=Excellent
    """

    politeness: int | float
    accuracy: int | float
    judge_name: str = ""


# ---------------------------------------------------------------------------
# LLMJudge — parallel ensemble orchestrator.
#
# The two judges are injected via constructor so unit tests can pass
# stub coroutines without touching real LLM network I/O. ``evaluate``
# is async because the FR-65 parallel contract is naturally expressed
# via ``asyncio.gather`` and a per-judge ``asyncio.wait_for`` timeout.
# ---------------------------------------------------------------------------
class LLMJudge:
    """[FR-65] Ensemble LLM judge — parallel gpt-4o-mini + claude-3-5-haiku.

    The two judges are called CONCURRENTLY via ``asyncio.gather`` so the
    wall-clock duration is bounded by ``max(latencies)`` rather than
    ``sum(latencies)`` (SRS FR-65: "兩個 judge 並行呼叫"; "平行呼叫兩個
    judge"). Per-judge exceptions (NP-07 dependency fault) and per-judge
    timeouts (NP-15) are treated as per-judge failures and the surviving
    judge's result is used — the exception is NEVER propagated to the
    caller (SRS FR-65: "fail-open"; "timeout 返回 partial result").

    Attributes:
        primary_judge: Async callable (coroutine function) producing a
            JudgeResult. In production this is the gpt-4o-mini scorer;
            in tests it is a stub coroutine.
        secondary_judge: Async callable producing a JudgeResult. In
            production this is the claude-3-5-haiku scorer; in tests it
            is a stub coroutine.
        temperature: Deterministic-scoring temperature. Pinned to ``0``
            per SRS FR-65 ("temperature=0 確保確定性"). Exposed as an
            instance attribute and a class constant so any of the
            spec's accepted shapes (instance attr / class constant /
            config dict / kwargs pass-through) sees the value.
        timeout_s: Per-judge wall-clock budget in seconds. Judges that
            exceed this budget are treated as failed and the surviving
            judge is used (NP-15 partial-result semantics).
    """

    # Class-level temperature constant — SRS FR-65 ("temperature=0
    # 確保確定性"). Also exposed as instance attribute below for
    # ergonomic access from the evaluate() code path.
    TEMPERATURE: int = 0

    # Default per-judge timeout in seconds. Sized so a single judge
    # exceeding the budget triggers NP-15 degradation well before the
    # outer test wall-clock cap (3s in FR-65's timeout test) and so the
    # happy-path parallel test (judges sleeping 100ms) does not trip the
    # budget. 2s is the natural "one judge is misbehaving" budget.
    DEFAULT_TIMEOUT_S: float = 2.0

    def __init__(
        self,
        primary_judge,
        secondary_judge,
        temperature: int = 0,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Wire the ensemble with two judge callables.

        Args:
            primary_judge: Async callable producing a JudgeResult
                (production: gpt-4o-mini scorer). MUST accept the
                message/response keyword args used by ``evaluate``.
            secondary_judge: Async callable producing a JudgeResult
                (production: claude-3-5-haiku scorer). Same calling
                contract as ``primary_judge``.
            temperature: Deterministic-scoring temperature; pinned to
                ``0`` by default per SRS FR-65.
            timeout_s: Per-judge wall-clock budget in seconds. Default
                ``DEFAULT_TIMEOUT_S`` (2.0s) — sized to give a clear
                NP-15 degradation signal before the outer test cap
                and to leave the happy-path parallel test well within
                its 0.16s wall-clock budget.
        """
        self.primary_judge = primary_judge
        self.secondary_judge = secondary_judge
        # Instance attribute mirrors the class constant so the test's
        # ``judge.temperature == 0`` check (FR-65 spec shape (a)) is
        # satisfied.
        self.temperature = temperature
        self.timeout_s = float(timeout_s)

    async def evaluate(self, message: str, response: str) -> JudgeResult:
        """Call both judges CONCURRENTLY and aggregate the results.

        Parallel contract (SRS FR-65: "兩個 judge 並行呼叫"):
            ``asyncio.gather`` schedules both judge invocations on the
            same event loop, so the wall-clock duration is bounded by
            ``max(latencies)`` rather than ``sum(latencies)``.

        Fault tolerance (NP-07 + NP-15):
            Each judge is wrapped in ``asyncio.wait_for`` with the
            configured ``timeout_s`` budget AND a try/except that
            swallows any per-judge exception (``ConnectionError``,
            ``TimeoutError``, or anything else raised by the judge
            callable). A failed judge contributes ``None``; the
            aggregate uses the surviving judge's score, and the
            exception is NEVER propagated to the caller.

        Single-survivor case:
            When exactly one judge succeeds, the aggregated result
            carries the survivor's raw scores verbatim — the FR-65
            timeout / fault-injection tests pin this exact behaviour
            (test_fr65_judge_api_down_degraded_single_judge and
            test_fr65_judge_timeout_returns_partial_result).

        Both-survivor case:
            Politeness = max (FR-66), accuracy = min (FR-67). FR-65
            only mandates that BOTH judges' results contribute to a
            valid JudgeResult; FR-66/FR-67 pin the aggregation rule
            on top.

        Args:
            message: The user's incoming message (judge input).
            response: The bot's outgoing response (judge input).

        Returns:
            A JudgeResult with politeness and accuracy on the 1-5
            scale. NEVER None; both-failed case returns a zero
            default.
        """
        # Build the per-judge coroutines BEFORE gather so both judge
        # callables are kicked off in the same event-loop tick — that
        # is what makes the wall-clock bounded by max(latencies).
        primary_coro = self._invoke_safely(self.primary_judge, message, response)
        secondary_coro = self._invoke_safely(
            self.secondary_judge, message, response
        )
        primary_result, secondary_result = await asyncio.gather(
            primary_coro, secondary_coro
        )
        return self._aggregate(primary_result, secondary_result)

    async def _invoke_safely(
        self,
        judge,
        message: str,
        response: str,
    ) -> JudgeResult | None:
        """Invoke one judge with a per-judge timeout; return None on any failure.

        Implements the NP-07 (dependency fault → graceful degradation)
        and NP-15 (per-judge timeout → partial result) contracts by
        catching every per-judge exception / timeout and returning
        ``None``. The caller treats ``None`` as "this judge failed;
        use the surviving one".

        ``asyncio.wait_for`` is used (rather than the newer
        ``asyncio.timeout`` context manager) because the test fixture
        only knows the per-judge budget as a numeric attribute and
        ``wait_for`` composes cleanly with the per-call coroutine
        pattern. The cancellation semantics are identical.
        """
        try:
            return await asyncio.wait_for(
                judge(message=message, response=response),
                timeout=self.timeout_s,
            )
        except Exception:  # noqa: BLE001  -- intentional: NP-07 + NP-15
            # Swallow per-judge failure (NP-07 ConnectionError, NP-15
            # TimeoutError, or anything else raised by the judge).
            # The aggregate decides whether to fall back to the
            # surviving judge; the exception is NOT propagated.
            return None

    @staticmethod
    def _aggregate(
        primary: JudgeResult | None,
        secondary: JudgeResult | None,
    ) -> JudgeResult:
        """Aggregate two per-judge results into a final JudgeResult.

        Aggregation rules (SRS FR-65 + FR-66 + FR-67):
            - Both None (both judges failed) → zero default JudgeResult
              (defensive; the contract is "non-None return value").
            - Exactly one survivor → return the survivor's raw scores
              verbatim. This is the NP-07 / NP-15 partial-result
              contract.
            - Both survivors → politeness = max (FR-66, "寬鬆評分，情感
              支持寧可寬容"), accuracy = min (FR-67, "保守評分，幻覺
              不可接受"). FR-65 only mandates the aggregated shape is
              a valid JudgeResult; the max/min rules are FR-66/FR-67.
        """
        if primary is None and secondary is None:
            return JudgeResult(politeness=0, accuracy=0, judge_name="degraded")
        if primary is None:
            return JudgeResult(
                politeness=secondary.politeness,
                accuracy=secondary.accuracy,
                judge_name=secondary.judge_name or "secondary",
            )
        if secondary is None:
            return JudgeResult(
                politeness=primary.politeness,
                accuracy=primary.accuracy,
                judge_name=primary.judge_name or "primary",
            )
        # Both judges succeeded — FR-66 politeness = max, FR-67
        # accuracy = min.
        return JudgeResult(
            politeness=max(primary.politeness, secondary.politeness),
            accuracy=min(primary.accuracy, secondary.accuracy),
            judge_name="ensemble",
        )
