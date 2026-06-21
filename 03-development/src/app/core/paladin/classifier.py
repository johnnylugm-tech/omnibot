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
class InjectionType(StrEnum):
    """[FR-13] Valid values for ``SemanticInjectionClassifier`` injection_type.

    Exactly four members per SRS FR-13 (the downstream FR-16 retrospective
    block branches on enum identity, so missing or extra values would
    break that branch). ``str`` mixin lets callers compare members to
    bare ``str`` literals when needed for logging.
    """

    DIRECT_PROMPT_INJECTION = "direct_prompt_injection"
    INDIRECT_INJECTION = "indirect_injection"
    JAILBREAK = "jailbreak"
    NONE = "none"


@dataclass(frozen=True)
class ClassificationResult:
    """[FR-13] Outcome of a single ``SemanticInjectionClassifier.classify`` call.

    The frozen dataclass shape is part of the public contract — the
    pipeline reads all four fields after each call, and FR-16 branches
    on ``injection_type`` enum identity, so the field set must stay
    stable.
    """

    is_injection: bool
    confidence: float
    injection_type: InjectionType
    is_unverified: bool = False


class SemanticInjectionClassifier:
    """[FR-13] PALADIN L4 — LLM-based semantic injection classifier.

    SRS FR-13: ``SemanticInjectionClassifier.classify()`` p95 < 200ms.

    Construction is zero-arg and side-effect-free (no network I/O at
    init, no module-level state mutation). The classifier routes on
    ``risk_level`` — ``"low"`` skips the LLM cost (FR-15); any other
    level calls ``_call_llm()`` once and translates its outcome into a
    ``ClassificationResult``. ``_call_llm()`` is intentionally a single
    instance-method hook so tests can monkeypatch the network call
    without touching the classifier logic.
    """

    DEFAULT_TIMEOUT_MS = 200.0
    _HIGH_RISK_LEVELS = frozenset({"medium", "high", "critical"})

    def __init__(self) -> None:
        # Zero-arg; no network I/O at init (so a unit-test fixture can
        # spin one up with no setup, and so construction stays cheap
        # on the request hot path).
        pass

    async def _call_llm(self, text: str, timeout_ms: float) -> dict:
        """[FR-13] Single network hook — tests monkeypatch this.

        Default implementation raises ``NotImplementedError``; the
        production wiring (omitted from the unit-test scope) supplies
        an OpenAI gpt-4o-mini call wrapped in ``asyncio.wait_for`` so
        an upstream stall surfaces as ``asyncio.TimeoutError`` rather
        than blocking the request. A downstream outage must surface
        as ``ConnectionError`` / ``OSError`` — classify() catches both
        and degrades to the unverified passthrough (NP-07).
        """
        raise NotImplementedError

    async def classify_async(
        self,
        text: str,
        *,
        risk_level: str = "medium",
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
    ) -> ClassificationResult:
        """[FR-15] Async variant of ``classify`` for use inside a running loop.

        The sync ``classify`` cannot be ``await``ed from inside an async
        pipeline without blocking the event loop (driving the coroutine
        to completion via a worker thread would serialize with any
        concurrent ``tier3_call`` gathered in the same ``asyncio.gather``
        — breaking FR-15's "L3 不等待 L4" rule on medium risk). This
        async variant performs the same routing but with a native
        ``await`` so it composes cleanly with ``asyncio.gather``.

        The injected ``_call_llm`` is responsible for honoring
        ``timeout_ms`` itself (production wiring wraps the network call
        in ``asyncio.wait_for``); we do NOT wrap a second ``wait_for``
        here so the pipeline does not double-cancel — and so FR-15
        tests can drive a deterministic slow coroutine past the
        pipeline's nominal 200ms budget to assert parallel execution.
        """
        if not isinstance(text, str):
            raise TypeError(
                "SemanticInjectionClassifier.classify_async requires str text"
            )

        if risk_level not in self._HIGH_RISK_LEVELS:
            return _make_passthrough(is_unverified=False)

        try:
            verdict = await self._call_llm(text, timeout_ms)
        except (TimeoutError, ConnectionError, OSError):
            return _make_passthrough(is_unverified=True)

        return _result_from_verdict(verdict)

    def classify(
        self,
        text: str,
        *,
        risk_level: str = "medium",
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
    ) -> ClassificationResult:
        """[FR-13] Classify ``text`` for prompt injection.

        Routing:
          - ``risk_level == "low"`` → skip the LLM cost (FR-15).
          - timeout / outage        → return ``is_unverified=True``
            (pipeline passthrough — never block on a stalled LLM).
          - success                 → return the upstream verdict.

        Args:
            text: Already L1-sanitized + L2-cleared user input.
            risk_level: Routing hint; one of ``"low"``, ``"medium"``,
                ``"high"``, ``"critical"``. Only ``"low"`` triggers
                the LLM-skip path; all other levels pay the LLM cost.
            timeout_ms: Maximum upstream wait in milliseconds. The
                call is wrapped in ``asyncio.wait_for(..., timeout=
                timeout_ms/1000)`` so a stalled LLM surfaces as
                ``asyncio.TimeoutError`` and is translated to the
                unverified passthrough.

        Returns:
            ``ClassificationResult`` carrying the three required fields
            (``is_injection``, ``confidence``, ``injection_type``)
            plus the ``is_unverified`` passthrough flag.

        Raises:
            TypeError: ``text`` is not a ``str``.

        Citations:
            - SRS.md FR-13 (PALADIN L4 acceptance criteria)
            - SRS.md FR-15 (low-risk L4 skip)
            - 03-development/tests/test_fr13.py:192-499 (cases 1-6)
        """
        if not isinstance(text, str):
            raise TypeError(
                "SemanticInjectionClassifier.classify requires str text"
            )

        # FR-15 routing — low risk does NOT pay the LLM cost.
        if risk_level not in self._HIGH_RISK_LEVELS:
            return _make_passthrough(is_unverified=False)

        try:
            verdict = self._call_llm(text, timeout_ms)
            # ``_call_llm`` is an ``async def`` in production but tests
            # monkeypatch it with sync fakes that return dicts directly;
            # handle both shapes on the same code path.
            if asyncio.iscoroutine(verdict):
                verdict = _await_coro_from_sync(verdict, timeout_ms)
        except (TimeoutError, ConnectionError, OSError, asyncio.TimeoutError):
            # Timeout OR downstream down → passthrough, do NOT block.
            # asyncio.TimeoutError is NOT a subclass of TimeoutError in py3.9
            return _make_passthrough(is_unverified=True)

        return _result_from_verdict(verdict)


def _make_passthrough(*, is_unverified: bool) -> ClassificationResult:
    """[FR-13] Safe default — used by both the low-risk skip path and
    the timeout / outage path.

    Both paths share the same field values (``is_injection=False``,
    ``confidence=0.0``, ``injection_type=NONE``); the only difference is
    the ``is_unverified`` flag, which the pipeline reads to decide
    whether to treat the call as a clean pass-through (low-risk skip)
    or as a degraded fallback (timeout / outage).
    """
    return ClassificationResult(
        is_injection=False,
        confidence=0.0,
        injection_type=InjectionType.NONE,
        is_unverified=is_unverified,
    )


def _await_coro_from_sync(coro, timeout_ms: float):
    """[FR-15] Drive an async coroutine to completion from sync code.

    ``classify`` is sync (FR-13 calls it without ``asyncio.run``), but
    FR-15's ``PALADINPipeline.process`` is async and calls ``classify``
    from inside a running event loop. Python forbids
    ``asyncio.run``/``loop.run_until_complete`` from within a running
    loop, so we fall back to a worker thread with a fresh event loop
    when one is already running. The no-running-loop case keeps the
    cheap ``asyncio.run`` path (preserves FR-13's sync-call
    performance budget).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run (FR-13 sync path).
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout_ms / 1000.0))

    # Running loop already exists (FR-15 async path). Run the
    # coroutine on a worker thread with its own fresh event loop.
    holder: dict = {}

    def _runner() -> None:
        new_loop = asyncio.new_event_loop()
        try:
            holder["v"] = new_loop.run_until_complete(
                asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
            )
        except BaseException as exc:  # propagate TimeoutError etc.
            holder["e"] = exc
        finally:
            new_loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=timeout_ms / 1000.0)
    if t.is_alive():
        raise TimeoutError(f"FR-15: _await_coro_from_sync timed out after {timeout_ms}ms")
    if "e" in holder:
        raise holder["e"]
    return holder["v"]


def _result_from_verdict(verdict: dict) -> ClassificationResult:
    """[FR-13] Map an upstream JSON-like dict to ``ClassificationResult``.

    Centralizes the field-by-field coercion so ``classify`` stays a
    flat routing function and any future normalization (range clamping,
    enum aliasing) lives in exactly one place.
    """
    return ClassificationResult(
        is_injection=bool(verdict.get("is_injection", False)),
        confidence=float(verdict.get("confidence", 0.0)),
        injection_type=InjectionType(verdict.get("injection_type", "none")),
        is_unverified=False,
    )


# ---------------------------------------------------------------------------
# [FR-14] PALADIN L5 — GroundingChecker
#
# SRS FR-14: "PALADIN L5 — GroundingChecker: 計算 LLM 輸出與 source_texts
# 之間 cosine similarity (text-embedding-3-small 1536維), 閾值 0.75;
# 延遲 < 5ms (本地計算). cosine score < 0.75 → grounded=False;
# cosine score ≥ 0.75 → grounded=True; 無 source_texts → grounded=False."

