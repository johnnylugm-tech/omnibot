"""TDD-RED: failing tests for FR-15 — PALADIN L4 Parallel Pipeline.

Spec source: 02-architecture/TEST_SPEC.md (FR-15)
SRS source : SRS.md FR-15

Acceptance criteria (from SRS FR-15):
    PALADIN L4 平行化執行策略：low risk → 跳過 L4 直接 L3；
    medium risk → L4 與 L3 平行（L3 不等待 L4）；
    high/critical → 同步 L4 阻擋（不呼叫 L3）；
    L4 觸發率 < 5% 總流量.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import asyncio
import time

# ---------------------------------------------------------------------------
# Source under test — ``PALADINPipeline`` is intentionally NOT YET exported
# by ``app.core.paladin``. The import below resolves (the module exists for
# FR-10/11/12/13/14), but ``PALADINPipeline`` is missing — accessing it
# raises ``ImportError`` / ``AttributeError``. That is the valid RED signal.
#
# GREEN must add to ``app/core/paladin.py``:
#
#   - ``ProcessResult`` dataclass:
#         is_blocked: bool          # True when the pipeline short-circuits
#         response: str | None      # L3 (or stub) response when not blocked
#         classification: ClassificationResult | None
#         tier3_called: bool        # observability for FR-15 routing
#         l4_called: bool           # observability for FR-15 routing
#         block_reason: str | None  # 'injection' | 'critical_risk' | None
#
#   - ``PALADINPipeline`` class:
#         * ``__init__(self, *, classifier=None, tier3_call=None)``
#             - ``classifier`` defaults to a fresh
#               ``SemanticInjectionClassifier()`` if not supplied.
#             - ``tier3_call`` is an **async** callable
#               ``(text: str) -> str``; GREEN must NOT call it
#               synchronously (medium-risk needs concurrency).
#
#         * ``async process(self, text: str, *, risk_level: str,
#                            timeout_ms: float = 200.0) -> ProcessResult``
#
#         Routing rules (from SRS FR-15):
#             - risk_level == "low":
#                 * MUST NOT invoke ``classifier._call_llm`` (skip L4
#                   entirely; FR-13 already encodes the same skip).
#                 * MUST call ``tier3_call(text)`` and return its
#                   response wrapped in ProcessResult(is_blocked=False,
#                   tier3_called=True, l4_called=False).
#             - risk_level == "medium":
#                 * MUST run ``classifier.classify(...)`` and
#                   ``tier3_call(text)`` **concurrently** (via
#                   ``asyncio.gather`` / ``asyncio.create_task``).
#                 * If classification reports ``is_injection=True`` →
#                   return ProcessResult(is_blocked=True,
#                   block_reason='injection', tier3_called=True,
#                   l4_called=True) WITHOUT surfacing the L3 response.
#                 * Otherwise → return ProcessResult(is_blocked=False,
#                   tier3_called=True, l4_called=True) with the L3
#                   response.
#             - risk_level == "high":
#                 * MUST run ``classifier.classify(...)`` synchronously
#                   FIRST (await before invoking L3).
#                 * If classification reports ``is_injection=True``
#                   OR ``is_unverified=True`` → return
#                   ProcessResult(is_blocked=True, tier3_called=False,
#                   l4_called=True) and MUST NOT invoke ``tier3_call``.
#                 * Otherwise → call ``tier3_call(text)`` and return
#                   ProcessResult(is_blocked=False, tier3_called=True,
#                   l4_called=True).
#             - risk_level == "critical":
#                 * MUST short-circuit immediately:
#                   return ProcessResult(is_blocked=True,
#                   block_reason='critical_risk', tier3_called=False,
#                   l4_called=False) and MUST NOT call the classifier
#                   OR ``tier3_call``.
#
#         * Unknown risk_level values MUST raise ``ValueError`` (do not
#           silently fall through to a default branch — that would hide
#           routing bugs that this FR is designed to surface).
# ---------------------------------------------------------------------------
from app.core.paladin import PALADINPipeline

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/paladin.py — append below the FR-14 grounding code
#   from dataclasses import dataclass
#   from typing import Optional
#
#   @dataclass
#   class ProcessResult:
#       """[FR-15] Outcome of a single ``PALADINPipeline.process`` call."""
#       is_blocked: bool
#       response: Optional[str] = None
#       classification: Optional[ClassificationResult] = None
#       tier3_called: bool = False
#       l4_called: bool = False
#       block_reason: Optional[str] = None
#
#   _RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
#
#   class PALADINPipeline:
#       """[FR-15] PALADIN routing orchestrator.
#
#       SRS FR-15: ``low → skip L4; medium → parallel L4+L3; high /
#       critical → sync L4 (block on injection, immediate block on
#       critical)``.
#
#       Construction is dependency-injected so tests can substitute
#       the L4 classifier and the Tier-3 LLM call without a network
#       round-trip. ``process`` is async so the medium-risk branch can
#       gather L3 and L4 concurrently.
#       """
#
#       DEFAULT_TIMEOUT_MS = 200.0
#
#       def __init__(
#           self,
#           *,
#           classifier: Optional[SemanticInjectionClassifier] = None,
#           tier3_call: Optional[Callable[[str], Awaitable[str]]] = None,
#       ) -> None:
#           self._classifier = classifier or SemanticInjectionClassifier()
#           self._tier3_call = tier3_call
#
#       async def process(
#           self,
#           text: str,
#           *,
#           risk_level: str,
#           timeout_ms: float = DEFAULT_TIMEOUT_MS,
#       ) -> ProcessResult:
#           """[FR-15] Route ``text`` through PALADIN per ``risk_level``."""
#           if risk_level not in _RISK_LEVELS:
#               raise ValueError(
#                   f"PALADINPipeline.process: unknown risk_level="
#                   f"{risk_level!r}; expected one of {sorted(_RISK_LEVELS)}"
#               )
#
#           # ---- critical: immediate block (no L4, no L3) ----
#           if risk_level == "critical":
#               return ProcessResult(
#                   is_blocked=True,
#                   block_reason="critical_risk",
#                   tier3_called=False,
#                   l4_called=False,
#               )
#
#           # ---- low: skip L4, go straight to L3 ----
#           if risk_level == "low":
#               response = await self._tier3_call(text)
#               return ProcessResult(
#                   is_blocked=False,
#                   response=response,
#                   tier3_called=True,
#                   l4_called=False,
#               )
#
#           # ---- high: synchronous L4, then L3 only if clean ----
#           if risk_level == "high":
#               verdict = self._classifier.classify(
#                   text, risk_level=risk_level, timeout_ms=timeout_ms
#               )
#               if verdict.is_injection or verdict.is_unverified:
#                   return ProcessResult(
#                       is_blocked=True,
#                       classification=verdict,
#                       block_reason="injection",
#                       tier3_called=False,
#                       l4_called=True,
#                   )
#               response = await self._tier3_call(text)
#               return ProcessResult(
#                   is_blocked=False,
#                   response=response,
#                   classification=verdict,
#                   tier3_called=True,
#                   l4_called=True,
#               )
#
#           # ---- medium: parallel L4 + L3 ----
#           async def _l4() -> ClassificationResult:
#               return self._classifier.classify(
#                   text, risk_level=risk_level, timeout_ms=timeout_ms
#               )
#           async def _l3() -> str:
#               return await self._tier3_call(text)
#
#           verdict, response = await asyncio.gather(_l4(), _l3())
#           if verdict.is_injection:
#               return ProcessResult(
#                   is_blocked=True,
#                   classification=verdict,
#                   block_reason="injection",
#                   tier3_called=True,
#                   l4_called=True,
#               )
#           return ProcessResult(
#               is_blocked=False,
#               response=response,
#               classification=verdict,
#               tier3_called=True,
#               l4_called=True,
#           )
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers: monkeypatch hooks for the L4 classifier and the Tier-3 call.
# Each test wires its own pair so call counts / delays / return values
# are explicit per case.
# ---------------------------------------------------------------------------
def _track_call_llm(call_counter: dict, payload: dict):
    """Build an ``_call_llm`` replacement that increments ``call_counter``."""

    async def _fake(self, text, timeout_ms):
        call_counter["n"] += 1
        return payload

    return _fake


def _track_tier3(call_counter: dict, response: str = "tier3-answer"):
    """Build a Tier-3 async callable that increments ``call_counter``."""

    async def _fake(text):
        call_counter["n"] += 1
        return response

    return _fake


# ---------------------------------------------------------------------------
# 1. low risk → L4 is skipped, L3 (Tier-3) runs immediately (happy_path).
#
# Spec input: risk_level="low"; expected_l4_calls="0".
#   SRS FR-15: "low risk → 跳過 L4 直接 L3".
#
# A pipeline that still routes low-risk through L4 wastes a 200ms LLM
# hop on every benign message and blows the 5% L4-trigger budget in
# FR-15 itself. The classifier MUST NOT be touched on this branch.
# ---------------------------------------------------------------------------
def test_fr15_low_risk_skips_l4(monkeypatch):
    risk_level = "low"
    expected_l4_calls = "0"

    from app.core.paladin import SemanticInjectionClassifier

    l4_counter = {"n": 0}
    l3_counter = {"n": 0}

    # GREEN TODO: ``PALADINPipeline.process`` MUST NOT invoke the
    # injected classifier (``SemanticInjectionClassifier.classify``
    # internally calls ``_call_llm``) when ``risk_level == "low"``.
    # The skip is the central invariant of this FR — every benign
    # message in production routes through this path.
    monkeypatch.setattr(
        SemanticInjectionClassifier,
        "_call_llm",
        _track_call_llm(
            l4_counter,
            {
                "is_injection": False,
                "confidence": 0.9,
                "injection_type": "none",
            },
        ),
    )

    # GREEN TODO: ``PALADINPipeline`` MUST accept an injected
    # ``tier3_call`` async callable (``(text: str) -> Awaitable[str]``)
    # so the L3 hot path is mockable in unit tests without a real
    # LLM round-trip. The pipeline must ``await`` the callable — never
    # call it synchronously.
    tier3_call = _track_tier3(l3_counter, response="clean-tier3-answer")

    pipeline = PALADINPipeline(tier3_call=tier3_call)

    # GREEN TODO: ``process`` MUST be ``async`` (medium-risk requires
    # concurrent L3 + L4 execution via ``asyncio.gather``). It MUST
    # accept ``risk_level`` as a keyword argument.
    result = asyncio.run(pipeline.process("hello", risk_level=risk_level))

    if risk_level == "low" and expected_l4_calls == "0":
        # Spec fr15-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr15-ok predicate: PALADINPipeline.process must return a "
            "non-None ProcessResult even on the low-risk fast path"
        )

    # The whole point of the low-risk branch: zero L4 hops.
    assert l4_counter["n"] == 0, (
        f"low risk MUST NOT invoke the L4 classifier (SRS FR-15: "
        f"'low risk → 跳過 L4 直接 L3'); observed {l4_counter['n']} L4 "
        f"call(s)"
    )

    # L3 MUST run — the pipeline skips L4 because Tier-3 is trusted
    # to answer directly on the low-risk path.
    assert l3_counter["n"] == 1, (
        f"low risk MUST call Tier-3 exactly once; observed "
        f"{l3_counter['n']} L3 call(s)"
    )

    # The result must carry the L3 response and not be blocked.
    assert getattr(result, "is_blocked", None) is False, (
        f"clean low-risk response must not be blocked; "
        f"got is_blocked={getattr(result, 'is_blocked', None)!r}"
    )
    assert getattr(result, "response", None) == "clean-tier3-answer", (
        f"low-risk ProcessResult.response must echo the Tier-3 output; "
        f"got {getattr(result, 'response', None)!r}"
    )


# ---------------------------------------------------------------------------
# 2. medium risk → L4 and L3 run concurrently (happy_path).
#
# Spec input: risk_level="medium"; expected_parallel="true".
#   SRS FR-15: "medium risk → L4 與 L3 平行 (L3 不等待 L4)".
#
# A sequential pipeline (await classifier, then await tier3) wastes
# 200ms on every medium-risk message and makes L3 wait on the
# classification verdict that it's allowed to ignore until L4
# finishes. We assert concurrency by giving L4 a long delay (300ms)
# and L3 a short delay (50ms) — parallel ⇒ total ~300ms, sequential
# ⇒ total ~350ms. The threshold 320ms sits between the two.
# ---------------------------------------------------------------------------
def test_fr15_medium_risk_l4_parallel_l3(monkeypatch):
    risk_level = "medium"
    expected_parallel = "true"

    from app.core.paladin import SemanticInjectionClassifier

    l4_counter = {"n": 0}
    l3_counter = {"n": 0}
    call_order: list[tuple[str, float]] = []

    l4_delay_seconds = 0.30
    l3_delay_seconds = 0.05

    async def _slow_clean_classify(self, text, timeout_ms):
        l4_counter["n"] += 1
        call_order.append(("l4_start", time.perf_counter()))
        await asyncio.sleep(l4_delay_seconds)
        call_order.append(("l4_end", time.perf_counter()))
        return {
            "is_injection": False,
            "confidence": 0.9,
            "injection_type": "none",
        }

    monkeypatch.setattr(
        SemanticInjectionClassifier,
        "_call_llm",
        _slow_clean_classify,
    )

    async def _fast_tier3(text):
        l3_counter["n"] += 1
        call_order.append(("l3_start", time.perf_counter()))
        await asyncio.sleep(l3_delay_seconds)
        call_order.append(("l3_end", time.perf_counter()))
        return "medium-tier3-answer"

    pipeline = PALADINPipeline(tier3_call=_fast_tier3)

    # GREEN TODO: on medium-risk, ``PALADINPipeline.process`` MUST
    # schedule ``classifier.classify(...)`` and ``tier3_call(text)``
    # concurrently via ``asyncio.gather`` (or equivalent). Running
    # them sequentially with ``await ... await ...`` breaks the
    # 'L3 不等待 L4' guarantee from SRS FR-15 and inflates the
    # medium-risk p95 by ~200ms (the full L4 budget).
    t0 = time.perf_counter()
    result = asyncio.run(pipeline.process("hello", risk_level=risk_level))
    elapsed = time.perf_counter() - t0

    if risk_level == "medium" and expected_parallel == "true":
        # Spec fr15-ok predicate applies_to case 1 only — case 2 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # Both branches MUST be exercised on the medium-risk path.
    assert l4_counter["n"] == 1, (
        f"medium risk MUST invoke L4 exactly once; "
        f"got {l4_counter['n']} call(s)"
    )
    assert l3_counter["n"] == 1, (
        f"medium risk MUST invoke Tier-3 exactly once; "
        f"got {l3_counter['n']} call(s)"
    )

    # Concurrency proof: total wall-clock must be close to the longer
    # branch (0.30s), not the sum (0.35s). We sit just above the
    # longer branch and well below the sum so a CI runner with mild
    # jitter does not produce false-positive REDs.
    parallel_ceiling = l4_delay_seconds + 0.02  # +20ms scheduling slack
    sequential_floor = l4_delay_seconds + l3_delay_seconds - 0.01
    assert elapsed < parallel_ceiling, (
        f"medium risk MUST run L3 and L4 in parallel (SRS FR-15: "
        f"'medium risk → L4 與 L3 平行'); sequential execution would "
        f"take ≥{sequential_floor:.3f}s, parallel takes ~"
        f"{l4_delay_seconds:.3f}s. observed={elapsed:.3f}s "
        f"(ceiling={parallel_ceiling:.3f}s)"
    )

    # Sanity-check the order trace: L3 must START before L4 ends.
    l3_start = next(ts for tag, ts in call_order if tag == "l3_start")
    l4_end = next(ts for tag, ts in call_order if tag == "l4_end")
    assert l3_start < l4_end, (
        f"on medium-risk, L3 MUST START while L4 is still running "
        f"(concurrent, not sequential); observed l3_start="
        f"{l3_start:.4f}, l4_end={l4_end:.4f}"
    )

    # A clean L4 verdict must not block the Tier-3 response.
    assert getattr(result, "is_blocked", None) is False, (
        f"clean medium-risk verdict must not block; "
        f"got is_blocked={getattr(result, 'is_blocked', None)!r}"
    )
    assert getattr(result, "response", None) == "medium-tier3-answer", (
        f"medium-risk ProcessResult.response must carry the Tier-3 "
        f"output; got {getattr(result, 'response', None)!r}"
    )


# ---------------------------------------------------------------------------
# 3. high risk → L4 runs sync, blocks L3 if injection detected
#    (happy_path).
#
# Spec input: risk_level="high"; expected_l3_blocked="true".
#   SRS FR-15: "high/critical → 同步 L4 阻擋（不呼叫 L3）".
#
# A pipeline that runs L3 before L4 on high-risk would surface a
# possibly-poisoned response to the user before the L4 verdict
# arrives. Conversely, a pipeline that skips L4 entirely on
# high-risk violates the "synchronous L4" guarantee. The blocked
# result must NOT have invoked tier3_call even once.
# ---------------------------------------------------------------------------
def test_fr15_high_risk_l4_sync_blocks_l3(monkeypatch):
    risk_level = "high"
    expected_l3_blocked = "true"

    from app.core.paladin import SemanticInjectionClassifier

    l4_counter = {"n": 0}
    l3_counter = {"n": 0}

    async def _classify_injection(self, text, timeout_ms):
        l4_counter["n"] += 1
        return {
            "is_injection": True,
            "confidence": 0.95,
            "injection_type": "direct_prompt_injection",
        }

    monkeypatch.setattr(
        SemanticInjectionClassifier,
        "_call_llm",
        _classify_injection,
    )

    async def _tier3(text):
        l3_counter["n"] += 1
        return "high-tier3-answer"

    pipeline = PALADINPipeline(tier3_call=_tier3)

    # GREEN TODO: on high-risk, ``PALADINPipeline.process`` MUST await
    # ``classifier.classify(...)`` BEFORE invoking ``tier3_call``.
    # When the verdict reports ``is_injection=True`` (or
    # ``is_unverified=True``) the pipeline MUST short-circuit with
    # ``is_blocked=True`` and MUST NOT invoke ``tier3_call`` even
    # once — surfacing a Tier-3 response before the L4 verdict would
    # leak a possibly-poisoned answer to the user.
    result = asyncio.run(pipeline.process("hello", risk_level=risk_level))

    if risk_level == "high" and expected_l3_blocked == "true":
        # Spec fr15-ok predicate applies_to case 1 only — case 3 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # L4 must have run exactly once.
    assert l4_counter["n"] == 1, (
        f"high risk MUST invoke L4 synchronously; "
        f"got {l4_counter['n']} call(s)"
    )

    # The injection verdict MUST short-circuit BEFORE L3 runs.
    assert l3_counter["n"] == 0, (
        f"high risk with L4 injection verdict MUST NOT invoke "
        f"Tier-3 (SRS FR-15: 'high/critical → 同步 L4 阻擋，不呼叫 "
        f"L3'); observed {l3_counter['n']} L3 call(s)"
    )

    # The result must be blocked with a recognizable reason so the
    # FR-16 retrospective-block path can pick it up.
    assert getattr(result, "is_blocked", False) is True, (
        f"high-risk injection verdict MUST yield is_blocked=True; "
        f"got is_blocked={getattr(result, 'is_blocked', None)!r}"
    )
    assert getattr(result, "block_reason", None) == "injection", (
        f"high-risk injection block must surface block_reason="
        f"'injection' (FR-16 retrospective block hooks here); "
        f"got {getattr(result, 'block_reason', None)!r}"
    )
    assert getattr(result, "response", "NOT_NONE") is None, (
        f"high-risk blocked result must NOT carry a response; "
        f"got {getattr(result, 'response', None)!r}"
    )


# ---------------------------------------------------------------------------
# 4. critical risk → immediate block (validation).
#
# Spec input: risk_level="critical"; expected_response="blocked".
#   SRS FR-15: "high/critical → 同步 L4 阻擋 (不呼叫 L3)".
#
# Critical risk is the highest tier — the pipeline MUST short-circuit
# at the routing layer without paying either LLM cost. Any L4 or L3
# invocation on this branch leaks load to upstream services during a
# known-bad traffic spike (e.g. an active attack) and defeats the
# 'fail-secure' intent of the critical bucket.
# ---------------------------------------------------------------------------
def test_fr15_critical_risk_immediate_block(monkeypatch):
    risk_level = "critical"
    expected_response = "blocked"

    from app.core.paladin import SemanticInjectionClassifier

    l4_counter = {"n": 0}
    l3_counter = {"n": 0}

    async def _classify(self, text, timeout_ms):
        l4_counter["n"] += 1
        return {
            "is_injection": True,
            "confidence": 0.99,
            "injection_type": "direct_prompt_injection",
        }

    monkeypatch.setattr(
        SemanticInjectionClassifier,
        "_call_llm",
        _classify,
    )

    async def _tier3(text):
        l3_counter["n"] += 1
        return "critical-tier3-answer"

    pipeline = PALADINPipeline(tier3_call=_tier3)

    # GREEN TODO: on critical-risk, ``PALADINPipeline.process`` MUST
    # return ProcessResult(is_blocked=True, block_reason=
    # 'critical_risk', tier3_called=False, l4_called=False)
    # WITHOUT awaiting ``classifier.classify`` AND WITHOUT awaiting
    # ``tier3_call``. Any of those calls defeats the fail-secure
    # intent of the critical bucket.
    result = asyncio.run(pipeline.process("hello", risk_level=risk_level))

    if risk_level == "critical" and expected_response == "blocked":
        # Spec fr15-ok predicate applies_to case 1 only — case 4 has
        # no predicate assertion (would trigger_mismatch).
        pass

    # Critical must short-circuit — zero L4 hops and zero L3 hops.
    assert l4_counter["n"] == 0, (
        f"critical risk MUST NOT invoke L4 (SRS FR-15: 'high/critical → "
        f"同步 L4 阻擋'; critical is the short-circuit sub-case); "
        f"observed {l4_counter['n']} L4 call(s)"
    )
    assert l3_counter["n"] == 0, (
        f"critical risk MUST NOT invoke Tier-3; "
        f"observed {l3_counter['n']} L3 call(s)"
    )

    # The result must be blocked with the critical-specific reason so
    # FR-16 retrospective-block / FR-99 circuit-breaker counters can
    # tell critical short-circuits apart from L4-verdict blocks.
    assert getattr(result, "is_blocked", False) is True, (
        f"critical risk MUST yield is_blocked=True; "
        f"got is_blocked={getattr(result, 'is_blocked', None)!r}"
    )
    assert getattr(result, "block_reason", None) == "critical_risk", (
        f"critical-risk short-circuit must surface block_reason="
        f"'critical_risk'; got "
        f"{getattr(result, 'block_reason', None)!r}"
    )
    assert getattr(result, "response", "NOT_NONE") is None, (
        f"critical-risk blocked result must NOT carry a response; "
        f"got {getattr(result, 'response', None)!r}"
    )

# NFR coverage: NFR-01 (pipeline p95 < 1000ms)
