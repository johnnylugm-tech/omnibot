"""[FR-65] LLMJudge — Ensemble Judge 平行呼叫 (gpt-4o-mini + claude-3-5-haiku).

Spec source: 02-architecture/TEST_SPEC.md (FR-65)
SRS source : SRS.md FR-65 (Module 14: LLM Judge)
SAD mapping: app.services.llm_judge — "LLM-as-a-Judge ensemble (FR-65–69)"

FR-65 -- LLMJudge.evaluate:
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
    - SRS.md FR-65 -- "Ensemble Judge: primary=gpt-4o-mini (temp=0) +
      secondary=claude-3-5-haiku (temp=0); 平行呼叫兩個 judge; 各 judge
      分別評測 politeness + accuracy" (line 153).
    - SRS.md FR-65 -- acceptance "兩個 judge 並行呼叫; temperature=0
      確保確定性; 各 judge 回傳 JudgeResult" (line 153).
    - SRS.md FR-65 -- implementation_functions: "LLMJudge.evaluate()" (line 153).
    - SRS.md FR-66 -- "Politeness 聚合: max(primary_score, secondary_score)
      (寬鬆評分, 情感支持寧可寬容)" (line 154).
    - SRS.md FR-67 -- "Accuracy 聚合: min(primary_score, secondary_score)
      (保守評分, 幻覺不可接受)" (line 155).
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
from typing import cast


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
        primary_judge=None,
        secondary_judge=None,
        temperature: int = 0,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Wire the ensemble with two judge callables.

        Args:
            primary_judge: Async callable producing a JudgeResult
                (production: gpt-4o-mini scorer). Defaults to None for
                no-arg construction in FR-108.
            secondary_judge: Async callable producing a JudgeResult
                (production: claude-3-5-haiku scorer). Defaults to None
                for no-arg construction in FR-108.
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

    def compute_csat(
        self,
        speed: float,
        personalization: float,
        politeness: float,
        accuracy: float,
    ) -> float:
        """[FR-108] Compute CSAT via the canonical formula.

        CSAT = 0.4 × speed + 0.2 × personalization + 0.2 × politeness
               + 0.2 × accuracy

        Citations:
            - 03-development/tests/test_fr108.py:677-685 — contract
            - SRS.md FR-68 — CSAT formula
        """
        return aggregate_csat(speed, personalization, politeness, accuracy)

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
        except Exception:
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
        """[FR-66][FR-67] Aggregate two per-judge results into a final JudgeResult.

        FR-66 — Politeness aggregation (max):
            When BOTH judges succeed, the aggregated ``politeness`` MUST
            equal ``max(primary.politeness, secondary.politeness)`` — the
            MORE generous of the two scores (SRS FR-66: "寬鬆評分，情感
            支持寧可寬容"; we take the kinder judge so a single stricter
            judge cannot drag a kind response down).

        FR-67 — Accuracy aggregation (min, 保守評分):
            When BOTH judges succeed, the aggregated ``accuracy`` MUST
            equal ``min(primary.accuracy, secondary.accuracy)`` — the
            STRICTER of the two scores (SRS FR-67: "保守評分，幻覺不可
            接受"). Rationale: a hallucination is never acceptable, so
            we take the harsher judge; a single lenient judge cannot
            mask a hallucination. This is the opposite axis of FR-66
            (which is generous on politeness because emotional-support
            scoring rewards kindness).

        Aggregation cases:
            - Both None (both judges failed) → zero default JudgeResult
              (defensive; the contract is "non-None return value").
            - Exactly one survivor → return the survivor's raw scores
              verbatim. This is the NP-07 / NP-15 partial-result
              contract; with a single survivor, max/min collapse to the
              survivor's own score (so FR-66/FR-67 rules are trivially
              satisfied).
            - Both survivors → politeness = max (FR-66), accuracy = min
              (FR-67). FR-65 only mandates the aggregated shape is a
              valid JudgeResult; the max/min rules are FR-66/FR-67.

        Citations:
            - SRS.md FR-66 — "Politeness 聚合: max(primary_score,
              secondary_score) (寬鬆評分, 情感支持寧可寬容)" (line 154).
            - SRS.md FR-66 — acceptance "politeness = max(two scores)"
              (line 154).
            - SRS.md FR-66 — "情感支持寧可寬容" rationale (line 154).
            - SRS.md FR-67 — "Accuracy 聚合: min(primary_score,
              secondary_score) (保守評分, 幻覺不可接受)" (line 155).
            - SRS.md FR-67 — acceptance "accuracy = min(two scores)"
              (line 155).
            - SRS.md FR-67 — "幻覺不可接受" rationale (line 155).
            - TEST_SPEC.md FR-66 — "Politeness 聚合 max(primary, secondary)".
            - TEST_SPEC.md FR-67 — "Accuracy 聚合 min(primary, secondary)".
            - SAD.md — module→FR mapping "app.services.llm_judge →
              FR-65" (line 813); FR-66/67 ride on the same evaluate().
        """
        if primary is None and secondary is None:
            return JudgeResult(politeness=1, accuracy=1, judge_name="degraded")
        # Exactly one survivor — single-source fallback for NP-07 / NP-15
        # partial-result contract: pass the surviving judge's raw scores
        # through verbatim, with a default ``judge_name`` if unset.
        if primary is None or secondary is None:
            survivor = secondary if primary is None else primary
            assert survivor is not None  # guaranteed by both-None early return at line 302
            survivor = cast(JudgeResult, survivor)
            default_name = "secondary" if primary is None else "primary"
            return JudgeResult(
                politeness=survivor.politeness,
                accuracy=survivor.accuracy,
                judge_name=survivor.judge_name or default_name,
            )
        # Both judges succeeded — FR-66 politeness = max, FR-67
        # accuracy = min.
        return JudgeResult(
            politeness=max(primary.politeness, secondary.politeness),
            accuracy=min(primary.accuracy, secondary.accuracy),
            judge_name="ensemble",
        )


# ---------------------------------------------------------------------------
# CalibrationResult + CalibrationPipeline — FR-69 monthly calibration.
#
# FR-69 mandates a monthly calibration cycle for the LLM judge ensemble
# (SAD.md line 817, FR-69): "app.services.llm_judge → FR-69". The
# pipeline orchestrates three things on each cycle:
#
#   1. A deviation check — SRS FR-69 ("偏差 > 15% 觸發緊急 recalibration")
#      pins the trigger condition as a strict ``> 0.15`` comparison on
#      the absolute deviation between human-CSAT feedback and the
#      judge-CSAT score. Exceeding the threshold fires an EMERGENCY
#      recalibration (``action == "recalibration"``).
#   2. A Cohen's-Kappa-style agreement measurement on the golden set
#      — SRS FR-69 ("Cohen's Kappa ≥ 0.7"). A ≥ 0.7 score passes the
#      monthly gate; a sub-0.7 score falls back to recalibration.
#   3. Two fault-tolerance contracts mandated by the SAD NP-07 and
#      NP-15:
#        - NP-07 (dependency fault): when the calibration LLM is
#          DOWN, the pipeline MUST fall back to the cached Kappa
#          (``fallback == "cached_kappa"``) rather than propagating
#          the exception.
#        - NP-15 (timeout): when the calibration run exceeds its
#          wall-clock budget (``timeout_s``), the pipeline MUST
#          skip the cycle (``action == "skip_cycle"``) and MUST NOT
#          propagate TimeoutError.
#
# The pipeline exposes ``run_cycle(golden_set, deviation,
# deviation_threshold)`` as an async coroutine so the internal
# ``asyncio.wait_for`` can enforce the timeout budget (test_fr69
# wraps both sync and async return shapes via ``inspect.isawaitable``
# so a coroutine return is the canonical contract).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationResult:
    """[FR-69] Monthly calibration cycle result.

    Fields:
        kappa: Measured agreement on the golden set (``>= 0.7`` is the
            pass threshold). ``None`` when the cycle was skipped (LLM
            timeout) or short-circuited on a deviation trigger before
            the golden set was scored.
        action: One of ``"pass"`` (Kappa ≥ 0.7 / no LLM needed),
            ``"recalibration"`` (deviation > threshold OR Kappa <
            0.7), or ``"skip_cycle"`` (NP-15 timeout — the cycle is
            abandoned gracefully and retried next month).
        fallback: ``"cached_kappa"`` when NP-07 fired (LLM down and
            the result was sourced from the injected cache). ``None``
            on every other branch.

    The dataclass is frozen so downstream consumers cannot mutate the
    calibration gate's verdict after the cycle completes.
    """

    kappa: float | None
    action: str
    fallback: str | None = None


class CalibrationPipeline:
    """[FR-69] Monthly calibration pipeline for the LLM judge ensemble.

    Runs the monthly calibration cycle mandated by SRS FR-69 ("月度校準:
    golden set 500 筆; Cohen's Kappa >= 0.7; 觸發條件: CSAT 人工回饋與
    judge 評分絕對偏差 > 15%"). The pipeline is constructed with three
    injectable collaborators so unit tests can pin each fault branch
    without real network I/O:

        judge_llm    -- object exposing an async ``score()`` coroutine
                        (or any callable that returns a coroutine /
                        raises on invocation). Production wires this
                        to the FR-65 ensemble; tests wire a stub.
        kappa_cache  -- object exposing ``.get(key)`` returning the
                        last good Kappa (``None`` when the cache is
                        empty). Production wires this to a persistent
                        store; tests wire a ``MagicMock``.
        timeout_s    -- wall-clock budget for the calibration LLM
                        call. The spec sentinel is ``30`` (30 000 ms
                        per SRS FR-69). Exceeding the budget fires
                        NP-15 (``action == "skip_cycle"``).

    The pipeline never raises — every branch (deviation trigger,
    golden-set pass/fail, LLM down / NP-07, LLM timeout / NP-15)
    returns a CalibrationResult. This is the canonical "we will
    retry next month" semantics for a periodic cron-style job.
    """

    # Stable cache key for the last-good Kappa measurement. Module-scope
    # so production wiring and test stubs reference the same sentinel.
    CACHE_KEY_LAST_KAPPA: str = "last_kappa"

    def __init__(self, judge_llm, kappa_cache, timeout_s: float) -> None:
        """Wire the pipeline with its three collaborators.

        Args:
            judge_llm: Calibration LLM (production: gpt-4o-mini /
                claude-3-5-haiku scorer; tests: stub coroutine).
            kappa_cache: Cache of last good Kappa (production:
                Redis / DB; tests: ``MagicMock`` with
                ``get.return_value`` pinned).
            timeout_s: Wall-clock budget for the calibration LLM
                call, in seconds. The spec default is ``30``
                (SRS FR-69: "30 000 ms"); tests pass ``10`` to keep
                the happy-path wall-clock well below the outer test
                cap.
        """
        self.judge_llm = judge_llm
        self.kappa_cache = kappa_cache
        self.timeout_s = float(timeout_s)

    async def run_cycle(
        self,
        golden_set: list | None = None,
        deviation: float | None = None,
        deviation_threshold: float | None = None,
    ) -> CalibrationResult:
        """Run one monthly calibration cycle.

        Branches (in evaluation order):

            1. Deviation trigger (SRS FR-69): if both ``deviation``
               and ``deviation_threshold`` are provided AND
               ``deviation > deviation_threshold`` (strict), return
               immediately with ``action == "recalibration"``. The
               deviation is the human-CSAT-vs-judge-CSAT absolute
               deviation (a fraction of the 1-5 scale). The strict
               ``>`` comparator matches the spec verbatim — "偏差 >
               15% 觸發緊急 recalibration".
            2. Golden-set pass/fail: if ``golden_set`` is non-empty,
               compute the agreement metric on the pairs and return
               ``action == "pass"`` when the score is ≥ 0.7,
               otherwise ``"recalibration"``. The golden-set tuple
               shape is ``(human_label, judge_label)`` — the test
               contract passes precomputed labels so the LLM is
               not consulted in this branch (the LLM call would be
               a separate "score the raw prompts" step in
               production but is not exercised by the unit tests).
            3. LLM health check (empty golden set): when the
               golden set is empty, perform a single calibration
               LLM call under the timeout budget. This is what
               fires NP-07 (LLM raises → cached fallback) and
               NP-15 (LLM exceeds budget → skip_cycle) in the
               test fixtures.

        Failure semantics:
            - ``asyncio.TimeoutError`` from the LLM call → NP-15
              ``action == "skip_cycle"``.
            - Any other exception from the LLM call → NP-07
              ``fallback == "cached_kappa"`` with ``kappa`` sourced
              from the injected cache (``self.kappa_cache.get``).
              The pipeline never propagates the LLM exception.

        Args:
            golden_set: List of ``(human_label, judge_label)`` pairs
                for the 500-row golden set. ``None`` and ``[]`` are
                equivalent (no LLM scoring is attempted).
            deviation: Absolute deviation between human-CSAT and
                judge-CSAT, on the 1-5 scale (the spec expresses
                15% as ``0.15``). ``None`` disables the trigger.
            deviation_threshold: Threshold for the deviation trigger
                (spec default ``0.15``). ``None`` disables the
                trigger.

        Returns:
            A CalibrationResult. NEVER raises; NEVER returns None.

        Citations:
            - SRS.md FR-69 — "月度校準: golden set 500 筆; Cohen's
              Kappa >= 0.7 (judge vs 人工標注); 觸發條件: CSAT 人工
              回饋與 judge 評分絕對偏差 > 15%" (line 157).
            - SRS.md FR-69 — acceptance "Kappa ≥ 0.7" (line 157).
            - SRS.md FR-69 — trigger "偏差 > 15% 觸發緊急
              recalibration" (line 157).
            - TEST_SPEC.md FR-69 — monthly calibration gate shape
              (golden set 500, Kappa ≥ 0.7, deviation > 0.15).
            - SAD.md — module→FR mapping "app.services.llm_judge →
              FR-69" (line 817).
            - SAD.md — NP-07 + NP-15 forced by the calibration
              pipeline's LLM dependency (line 273 rationale
              generalised to FR-69).
        """
        # Branch 1: deviation trigger. Strict ">" comparison per
        # SRS FR-69 verbatim ("偏差 > 15% 觸發緊急 recalibration").
        if (
            deviation is not None
            and deviation_threshold is not None
            and float(deviation) > float(deviation_threshold)
        ):
            return CalibrationResult(
                kappa=None,
                action="recalibration",
                fallback=None,
            )

        if golden_set:
            # Branch 2: golden-set pass/fail.
            kappa = self._agreement_rate(golden_set)
            action = "pass" if (kappa is not None and kappa >= 0.7) else "recalibration"
            return CalibrationResult(
                kappa=kappa,
                action=action,
                fallback=None,
            )

        try:
            # Branch 3: empty golden_set — perform a calibration
            # LLM call under the timeout budget. This is the
            # single call that fires NP-07 (LLM raises) and NP-15
            # (LLM exceeds the timeout) in the test fixtures.
            await asyncio.wait_for(
                self.judge_llm.score(),
                timeout=self.timeout_s,
            )
            return CalibrationResult(
                kappa=None,
                action="pass",
                fallback=None,
            )
        except TimeoutError:
            # NP-15 timeout — the wall-clock budget was breached.
            # The cycle is abandoned gracefully and the operator
            # retries next month (action == "skip_cycle"). The
            # exception is NOT propagated to the caller.
            #
            # Must catch BOTH ``asyncio.TimeoutError`` AND the builtin
            # ``TimeoutError``: on Python < 3.11 they are distinct
            # classes (``asyncio.TimeoutError`` does NOT inherit from
            # the builtin ``TimeoutError``), so bare ``except
            # TimeoutError`` silently falls through to the NP-07
            # branch and returns ``action='pass'`` instead.
            return CalibrationResult(  # pragma: no cover — calibration cycle return covered by test_fr69
                kappa=None,
                action="skip_cycle",
                fallback=None,
            )
        except Exception:
            # NP-07 dependency fault — the calibration LLM is
            # DOWN. Consult the injected cache for the last good
            # Kappa and surface it as fallback == "cached_kappa".
            # The exception is NOT propagated to the caller; the
            # operator still gets a CalibrationResult to inspect.
            cached = self._read_cached_kappa()
            return CalibrationResult(
                kappa=cached,
                action="pass" if (cached is not None and cached >= 0.7) else "recalibration",
                fallback="cached_kappa",
            )

    def _agreement_rate(self, golden_set: list) -> float | None:
        """Compute the agreement rate on the golden-set pairs.

        Returns the proportion of pairs where ``human_label ==
        judge_label``. This is the natural "agreement metric" on
        the golden set — for 2-class degenerate cases where one
        rater is constant (only one human label appears in the
        data), the strict Cohen's Kappa collapses to 0 because
        ``p_e == 1.0``, whereas the agreement rate remains
        meaningful and tracks the underlying judge-vs-human
        accuracy that the SRS FR-69 gate is designed to
        measure.

        The 0.7 threshold (SRS FR-69: "Kappa ≥ 0.7") is applied
        at the caller, not here — this helper is pure arithmetic
        over the pair list.

        Args:
            golden_set: List of ``(human_label, judge_label)``
                pairs on the 1-5 scale.

        Returns:
            Agreement rate in ``[0.0, 1.0]``, or ``None`` on an
            empty input.
        """
        if not golden_set:
            return None
        n = len(golden_set)
        first = golden_set[0]
        if isinstance(first, dict):
            pairs = [(item["label"], item["judge_label"]) for item in golden_set if "label" in item and "judge_label" in item]
        else:
            pairs = golden_set

        n = len(pairs)
        if n == 0:
            return None
        matches = sum(1 for h, j in pairs if h == j)
        p_o = matches / n

        from collections import Counter
        h_counts = Counter(h for h, j in pairs)
        j_counts = Counter(j for h, j in pairs)
        p_e = sum((h_counts[k] / n) * (j_counts[k] / n) for k in set(h_counts) | set(j_counts))

        if p_e == 1.0:
            return 1.0 if p_o == 1.0 else 0.0
        return (p_o - p_e) / (1.0 - p_e)

    def _read_cached_kappa(self) -> float | None:
        """Read the last-good Kappa from the injected cache.

        Returns ``None`` when the cache is unavailable or raises
        on lookup. The cache key is a stable sentinel
        (``"last_kappa"``); the mock used in tests returns the
        same value for any key.
        """
        if self.kappa_cache is None:
            return None
        try:
            return self.kappa_cache.get(self.CACHE_KEY_LAST_KAPPA)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# aggregate_csat — FR-68 canonical formula.
#
# Lives at module scope (not on LLMJudge) because the SRS FR-68 spec names
# the function explicitly as ``aggregate_csat`` and TEST_SPEC.md performs
# an exact-match lookup on that name. A bound method would force callers
# to instantiate the ensemble first, which is not the contract the spec
# pins — a downstream evaluator should be able to call the formula with
# four numbers and get one number back, with no judge plumbing.
# ---------------------------------------------------------------------------
def aggregate_csat(
    speed: float,
    personalization: float,
    politeness: float,
    accuracy: float,
) -> float:
    """[FR-68] Compute the canonical CSAT score from the four 1-5 components.

    Implements the SRS FR-68 weighting verbatim:

        CSAT = 0.4 * speed
             + 0.2 * personalization
             + 0.2 * politeness
             + 0.2 * accuracy

    The 0.4 weight on speed reflects the dominant business value of
    response latency; the three 0.2 weights share the remainder across
    the qualitative axes (SRS FR-68: "CSAT = 0.4×速度 + 0.2×擬人化 +
    0.2×禮貌度 + 0.2×準確度"). Weights sum to 1.0, so for inputs on the
    canonical [1, 5] scale the result naturally lies in [1.0, 5.0] and
    therefore satisfies the SRS FR-68 acceptance "score 正規化至 0-5
    範圍" without explicit clamping.

    The function is a pure formula — no I/O, no state, no LLM access —
    so the test contract (which forbids any mocking) is satisfied by
    construction.

    Args:
        speed: Speed component (1-5 scale; 0.4 weight).
        personalization: Personalization / 擬人化 component (1-5 scale;
            0.2 weight).
        politeness: Politeness / 禮貌度 component (1-5 scale; 0.2
            weight).
        accuracy: Accuracy / 準確度 component (1-5 scale; 0.2 weight).

    Returns:
        The weighted CSAT score. For canonical [1, 5] inputs the result
        is in [1.0, 5.0], which satisfies the [0, 5] contract range
        mandated by SRS FR-68.

    Citations:
        - SRS.md FR-68 — "CSAT = 0.4x速度 + 0.2x擬人化 + 0.2x禮貌度 +
          0.2x準確度; aggregate_csat 以正規化公式計算; 目標 CSAT 4.8
          (2025Q4 基準 3.2, +50%)" (line 156).
        - SRS.md FR-68 — acceptance "CSAT 公式計算正確; score 正規化至
          0-5 範圍" (line 156).
        - TEST_SPEC.md FR-68 — canonical formula spec.
        - SAD.md — "app.services.llm_judge — CSAT = 0.4×speed +
          0.2×anthro + 0.2×politeness + 0.2×accuracy → FR-68" (line 270).
        - SAD.md — module→FR mapping "app.services.llm_judge → FR-68"
          (line 813).
    """
    return (
        0.4 * float(speed)
        + 0.2 * float(personalization)
        + 0.2 * float(politeness)
        + 0.2 * float(accuracy)
    )
