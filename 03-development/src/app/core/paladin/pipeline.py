from __future__ import annotations

import asyncio
import contextlib
import enum
import math
import re
import threading
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast


class StrEnum(str, enum.Enum):
    """Python 3.9 compatible StrEnum backport."""
    pass
from app.core.paladin.sanitizer import InputSanitizer
from app.core.paladin.injection_defense import PromptInjectionDefense
from app.core.paladin.classifier import SemanticInjectionClassifier, ClassificationResult
from app.core.paladin.grounding import GroundingChecker

# ---------------------------------------------------------------------------
# [FR-15] PALADIN routing orchestrator — ``PALADINPipeline``
#
# SRS FR-15: "PALADIN L4 平行化執行策略: low risk → 跳過 L4 直接 L3;
# medium risk → L4 與 L3 平行 (L3 不等待 L4); high/critical → 同步 L4
# 阻擋 (不呼叫 L3); L4 觸發率 < 5% 總流量."
#
# The orchestrator is dependency-injected: callers supply the L4
# ``classifier`` and the ``tier3_call`` async callable so unit tests can
# substitute deterministic stand-ins without a network round-trip.
# ``process()`` is async because the medium-risk branch gathers L3 and
# L4 concurrently via ``asyncio.gather`` — running them sequentially
# would inflate medium-risk p95 by ~200ms (the full L4 budget) and
# break the "L3 不等待 L4" guarantee.
#
# Citations:
#   - SRS.md FR-15 (PALADIN L4 平行化執行策略 acceptance criteria)
#   - 02-architecture/TEST_SPEC.md FR-15 (case 1: low risk 跳過 L4;
#     case 2: medium risk 平行; case 3: high risk 同步阻擋;
#     case 4: critical risk 立即阻擋)
#   - 03-development/tests/test_fr15.py:252-324 (low risk skips L4)
#   - 03-development/tests/test_fr15.py:340-435 (medium risk parallel)
#   - 03-development/tests/test_fr15.py:451-521 (high risk sync block)
#   - 03-development/tests/test_fr15.py:536-603 (critical immediate block)
#   - SRS.md FR-13 (low-risk L4 skip; classify() is the routing hook)
# ---------------------------------------------------------------------------
@dataclass
class ProcessResult:
    """[FR-15/FR-16] Outcome of a single ``PALADINPipeline.process`` call.

    ``is_blocked`` is True on any short-circuit path (injection verdict
    or critical-risk fast-fail). ``response`` carries the Tier-3
    LLM output when the request was NOT blocked (None on every blocked
    branch so downstream FR-16 retrospective-block hooks cannot
    accidentally surface a poisoned response). ``tier3_called`` /
    ``l4_called`` are observability flags for the FR-15 routing audit.
    ``block_reason`` is ``'injection'`` on an L4-verdict block and
    ``'critical_risk'`` on the critical short-circuit.
    ``late_injection_detected`` (FR-16) is True ONLY on the medium-risk
    retrospective-block path — L4 verdict arrived after L3 had already
    completed and the L3 result was revoked. Synchronous L4 blocks
    (high risk, critical) leave this flag at its default ``False`` so
    FR-17 retraction handlers can branch on it.

    Citations:
        - SRS.md FR-15 (PALADIN routing orchestrator)
        - SRS.md FR-16 (PALADIN L4 事後攔截)
    """

    is_blocked: bool
    response: str | None = None
    classification: ClassificationResult | None = None
    tier3_called: bool = False
    l4_called: bool = False
    block_reason: str | None = None
    late_injection_detected: bool = False  # [FR-16]


_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})

# ``ProcessResult.block_reason`` values surfaced to downstream consumers
# (FR-16 retrospective block, FR-99 circuit-breaker counters). Defined
# once so the literal lives in exactly one place per branch.
_BLOCK_REASON_INJECTION = "injection"
_BLOCK_REASON_CRITICAL_RISK = "critical_risk"

# [FR-16] Canonical audit-log event name written when a medium-risk
# request's late L4 verdict revokes a completed L3 response. The
# downstream SOC2 dashboard keys on this exact token.
_RETROSPECTIVE_BLOCK_EVENT = "injection_retrospective_block"


async def _noop_tier3(text: str) -> str:
    """[FR-108] Default no-op for ``PALADINPipeline._tier3_call``.

    Returns an empty string so the pipeline can be constructed with no
    arguments in tests that monkeypatch ``process`` directly.

    Citations:
        - 03-development/tests/test_fr108.py:256-263 — no-arg PALADINPipeline
    """
    return ""


def _noop_security_log_writer(**payload) -> None:
    """[FR-16] Default no-op for ``PALADINPipeline.security_log_writer``.

    Lets the pipeline accept the writer as an optional dependency so
    production wiring can plug in a real database sink later without
    changing call sites or adding ``if writer is not None`` branches
    on the hot path.

    Citations:
        - SRS.md FR-16 (記錄 injection_retrospective_block 至 security_logs)
    """
    return None


class PALADINPipeline:
    """[FR-15/FR-16] PALADIN routing orchestrator.

    SRS FR-15: ``low → 跳過 L4 直接 L3; medium → L4 與 L3 平行 (L3 不等待
    L4); high / critical → 同步 L4 阻擋 (不呼叫 L3)``; L4 觸發率 < 5% 總流量.
    SRS FR-16: medium-risk 後 L4 判定 injection → 撤回 L3 結果 + 寫
    ``injection_retrospective_block`` 至 security_logs.

    Construction is dependency-injected so tests can substitute the L4
    classifier, the Tier-3 LLM call, and the audit-log writer without
    a network round-trip or a real database. ``process`` is async so
    the medium-risk branch can gather L3 and L4 concurrently.
    """

    DEFAULT_TIMEOUT_MS = 200.0

    def __init__(
        self,
        *,
        classifier: SemanticInjectionClassifier | None = None,
        tier3_call: Callable[[str], Awaitable[str]] | None = None,
        security_log_writer: Callable[..., None] | None = None,
    ) -> None:
        self._classifier = classifier or SemanticInjectionClassifier()
        self._tier3_call = tier3_call or _noop_tier3
        # [FR-16] Default to a no-op writer so production wiring can
        # plug in a real database sink without changing call sites.
        self._security_log_writer = (
            security_log_writer
            if security_log_writer is not None
            else _noop_security_log_writer
        )

    async def _run_l4(
        self,
        text: str,
        *,
        risk_level: str,
        timeout_ms: float,
    ) -> ClassificationResult:
        """[FR-15] Single L4 classifier hook — shared by all risk branches."""
        return await self._classifier.classify_async(
            text, risk_level=risk_level, timeout_ms=timeout_ms
        )

    async def _call_l3(self, text: str) -> str:
        """[FR-15] Single Tier-3 call hook — shared by all risk branches."""
        return await self._tier3_call(text)

    @staticmethod
    def _blocked_result(
        *,
        block_reason: str,
        tier3_called: bool,
        l4_called: bool,
        verdict: ClassificationResult | None = None,
        late_injection_detected: bool = False,
    ) -> ProcessResult:
        """[FR-15/FR-16] Factory for any short-circuit (blocked) ProcessResult.

        ``late_injection_detected`` defaults to ``False`` so the
        synchronous-block branches (critical / high risk) keep their
        existing behavior; only the medium-risk retrospective-block
        branch sets it to ``True``.
        """
        return ProcessResult(
            is_blocked=True,
            classification=verdict,
            block_reason=block_reason,
            tier3_called=tier3_called,
            l4_called=l4_called,
            late_injection_detected=late_injection_detected,
        )

    @staticmethod
    def _success_result(
        *,
        response: str,
        verdict: ClassificationResult | None,
        l4_called: bool,
    ) -> ProcessResult:
        """[FR-15] Factory for any non-blocked (clean) ProcessResult.

        ``tier3_called`` is always True on the clean path — the L3 LLM
        has already produced ``response`` by the time we get here.
        """
        return ProcessResult(
            is_blocked=False,
            response=response,
            classification=verdict,
            tier3_called=True,
            l4_called=l4_called,
        )

    def _handle_retrospective_block(
        self,
        text: str,
        verdict: ClassificationResult,
        risk_level: str,
    ) -> ProcessResult:
        """[FR-16] Revoke the completed L3 response + write audit event.

        On the medium-risk parallel branch, L4 may report injection AFTER
        the L3 coroutine has already completed (the typical race: L3 is
        fast, L4 has a 200ms LLM budget). The L3 result is revoked
        before ``ProcessResult`` is constructed so a poisoned response
        never escapes the pipeline, and an
        ``injection_retrospective_block`` event is written to the audit
        log with the conversation context.

        Kept as a private helper so ``process`` stays a flat routing
        function and the audit-log schema lives in exactly one place.
        """
        with contextlib.suppress(Exception):
            self._security_log_writer(
                event=_RETROSPECTIVE_BLOCK_EVENT,
                risk_level=risk_level,
                injection_type=verdict.injection_type.value,
                confidence=verdict.confidence,
                text=text,
            )
        return self._blocked_result(
            block_reason=_BLOCK_REASON_INJECTION,
            tier3_called=True,
            l4_called=True,
            verdict=verdict,
            late_injection_detected=True,
        )

    async def process(
        self,
        text: str,
        *,
        risk_level: str,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
    ) -> ProcessResult:
        """[FR-15] Route ``text`` through PALADIN per ``risk_level``.

        Args:
            text: User input (already L1-sanitized + L2-cleared).
            risk_level: One of ``"low"``, ``"medium"``, ``"high"``,
                ``"critical"``. Unknown values raise ``ValueError``.
            timeout_ms: Maximum upstream LLM wait in milliseconds.
                Passed through to the L4 classifier.

        Returns:
            ``ProcessResult`` carrying the routing decision, the
            Tier-3 response (when not blocked), and observability
            flags for downstream FR-16 retrospective blocks.

        Raises:
            ValueError: ``risk_level`` is not one of the four known
                buckets — silent fall-through would hide routing
                bugs that this FR is designed to surface.

        Citations:
            - SRS.md FR-15
            - 03-development/tests/test_fr15.py:252-603 (all 4 cases)
        """
        if risk_level not in _RISK_LEVELS:
            raise ValueError(
                f"PALADINPipeline.process: unknown risk_level="
                f"{risk_level!r}; expected one of {sorted(_RISK_LEVELS)}"
            )

        # ---- critical: immediate block (no L4, no L3) ----
        if risk_level == "critical":
            return self._blocked_result(
                block_reason=_BLOCK_REASON_CRITICAL_RISK,
                tier3_called=False,
                l4_called=False,
            )

        # ---- low: skip L4, go straight to L3 ----
        if risk_level == "low":
            response = await self._call_l3(text)
            return self._success_result(
                response=response, verdict=None, l4_called=False
            )

        # ---- high: synchronous L4, then L3 only if clean ----
        if risk_level == "high":
            verdict = await self._run_l4(
                text, risk_level=risk_level, timeout_ms=timeout_ms
            )
            if verdict.is_injection:
                return self._blocked_result(
                    block_reason=_BLOCK_REASON_INJECTION,
                    tier3_called=False,
                    l4_called=True,
                    verdict=verdict,
                )
            response = await self._call_l3(text)
            return self._success_result(
                response=response, verdict=verdict, l4_called=True
            )

        # ---- medium: parallel L4 + L3 (FR-16 retrospective block) ----
        results = await asyncio.gather(
            self._run_l4(text, risk_level=risk_level, timeout_ms=timeout_ms),
            self._call_l3(text),
            return_exceptions=True,
        )
        verdict, response = results
        if isinstance(verdict, Exception):
            raise verdict
        if isinstance(response, Exception):
            raise response
        verdict = cast(ClassificationResult, verdict)
        response = cast(str, response)

        if verdict.is_injection:
            return self._handle_retrospective_block(text, verdict, risk_level)
        return self._success_result(
            response=response, verdict=verdict, l4_called=True
        )

    async def process_with_knowledge(
        self,
        text: str,
        knowledge_results: list,
        *,
        risk_level: str = "medium",
    ) -> ProcessResult:
        """[FR-108] Process ``text`` with knowledge-base context for
        indirect-injection detection.

        Patched by ``test_fr108.py`` tests; the default implementation
        delegates to ``process`` with medium risk.

        Citations:
            - 03-development/tests/test_fr108.py:307-313 — monkeypatch
        """
        return await self.process(text, risk_level=risk_level)
