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
@dataclass
class _DetectionResult:
    """Outcome of a single ``PromptInjectionDefense.check_input`` call.

    ``__bool__`` is overridden so callers can use ``if defense.check_input(t):``
    directly while still keeping the matched pattern available for logging.
    """

    is_suspicious: bool
    matched_pattern: str | None = None

    def __bool__(self) -> bool:
        return self.is_suspicious


class PromptInjectionDefense:
    """[FR-11] PALADIN L2 — SUSPICIOUS_PATTERNS regex pass.

    SRS FR-11: ``PromptInjectionDefense.check_input()`` < 3ms p95.

    The constructor is zero-arg and side-effect-free; ``check_input`` is
    pure-Python regex work so the per-call cost stays well under the
    3ms p95 budget. Callers upstream are expected to have already run
    the L1 InputSanitizer (NFKC + homoglyph + control-char strip) so
    NFKC re-normalization is intentionally not performed here.

    Citations:
        - SRS.md FR-11
        - 03-development/tests/test_fr11.py (all 7 cases)
    """

    # Class-level attributes assigned after the class body (FR-12
    # spotlighting delimiters + sandwich-prompt builder). Declared
    # here so pyright recognises them as valid attributes.
    _SPOTLIGHT_START: str
    _SPOTLIGHT_END: str
    build_sandwich_prompt: Callable[..., str]

    def check_input(self, text: str) -> _DetectionResult:
        """Flag ``text`` if it matches any of the 13 SUSPICIOUS_PATTERNS.

        Args:
            text: Already NFKC-normalized user input.

        Returns:
            ``_DetectionResult`` whose ``bool()`` is True iff at least
            one pattern matched; ``matched_pattern`` records the regex
            source of the first hit (None on the negative path).

        Raises:
            TypeError: ``text`` is not a ``str``.

        Citations:
            - SRS.md FR-11
            - 03-development/tests/test_fr11.py:122-334 (cases 1-7)
        """
        if not isinstance(text, str):
            raise TypeError("PromptInjectionDefense.check_input requires str input")
        for pattern, source in _SUSPICIOUS_PATTERNS:
            if pattern.search(text):
                return _DetectionResult(is_suspicious=True, matched_pattern=source)
        return _DetectionResult(is_suspicious=False, matched_pattern=None)


# ---------------------------------------------------------------------------
# [FR-12] PALADIN L3 — Sandwich Prompt + Spotlighting (ICLR 2025)
#
# SRS FR-12: "PALADIN L3 — Instruction Hierarchy: Sandwich Prompt 建構,
# 系統指令標記 PRIORITY: HIGHEST, 用戶訊息標記 UNTRUSTED DATA BOUNDARY,
# 使用 Spotlighting delimiters (ICLR 2025); L1-L3 合計延遲 < 5ms p95."
#
# Construction is pure-Python string concatenation — no I/O, no LLM
# calls, no regex — so the per-call cost stays well under the L1-L3
# cumulative 5ms p95 budget when composed with FR-10
# ``InputSanitizer.sanitize`` and FR-11 ``PromptInjectionDefense.check_input``.
# The sandwich shape (SYSTEM → USER → SYSTEM REINFORCEMENT) protects the
# system intent from attention-budget dilution by an injected
# instruction inside the untrusted boundary.
#
# Citations:
#   - SRS.md FR-12 (PALADIN L3 Sandwich Prompt + Spotlighting acceptance)
#   - 02-architecture/TEST_SPEC.md FR-12 (case 1: PRIORITY: HIGHEST;
#     case 2: UNTRUSTED DATA BOUNDARY; case 3: L1-L3 p95 < 5ms;
#     case 4: Spotlighting delimiters ICLR 2025)
#   - 03-development/tests/test_fr12.py:136-161 (PRIORITY: HIGHEST case)
#   - 03-development/tests/test_fr12.py:173-201 (UNTRUSTED DATA BOUNDARY case)
#   - 03-development/tests/test_fr12.py:215-252 (L1-L3 p95 < 5ms case)
#   - 03-development/tests/test_fr12.py:267-337 (Spotlighting delimiters case)
# ---------------------------------------------------------------------------
# Spotlighting delimiters per the ICLR 2025 paper wrap the untrusted
# tokens inside a distinctive pair so the downstream LLM can visually
# isolate them from surrounding instruction text. Defined as
# ``PromptInjectionDefense`` class attributes so ``self.<name>`` lookups
# on the hot path cost nothing.
PromptInjectionDefense._SPOTLIGHT_START = "<<<SPOTLIGHT_START>>>"
PromptInjectionDefense._SPOTLIGHT_END = "<<<SPOTLIGHT_END>>>"

# Sandwich-prompt section markers. Defined once so the literal tokens
# (PRIORITY: HIGHEST, UNTRUSTED DATA BOUNDARY) live in exactly one place
# — every block builder reads from this table, no copy/paste.
_PRIORITY_TAG = "PRIORITY: HIGHEST"
_UNTRUSTED_TAG = "UNTRUSTED DATA BOUNDARY"


def _wrap_priority_block(label: str, body: str) -> str:
    """Wrap ``body`` in a ``[LABEL | PRIORITY: HIGHEST] … [/LABEL]`` block.

    Used for both the leading system intent block and the trailing
    reinforcement block — same shape, different label.
    """
    return f"[{label} | {_PRIORITY_TAG}]\n{body}\n[/{label}]"


def _build_sandwich_prompt(
    self: PromptInjectionDefense,
    user_text: str,
    system_prompt: str = "",
) -> str:
    """[FR-12] Assemble a sandwich prompt with priority + boundary.

    The three blocks are emitted in order:

      1. ``[SYSTEM | PRIORITY: HIGHEST]`` — carries the upstream
         system intent marked with the literal token
         ``PRIORITY: HIGHEST`` so the downstream LLM recognizes it as
         the highest-priority instruction that may not be overridden
         by anything inside the untrusted boundary.
      2. ``[USER | UNTRUSTED DATA BOUNDARY]`` — wraps ``user_text``
         between the literal boundary markers
         ``UNTRUSTED DATA BOUNDARY`` … ``END UNTRUSTED DATA BOUNDARY``
         and the Spotlighting delimiter pair so the LLM knows the
         segment is data, not instruction.
      3. ``[SYSTEM REINFORCEMENT | PRIORITY: HIGHEST]`` — repeats the
         system intent after the untrusted block (the "sandwich"
         shape) so an injected instruction in the middle cannot push
         the system intent off the attention budget.

    Args:
        user_text: User-supplied message (already L1-sanitized +
            L2-cleared; this layer does not re-normalize).
        system_prompt: Upstream system intent (may be empty).

    Returns:
        The assembled sandwich prompt as a single ``str``.

    Raises:
        TypeError: ``user_text`` is not a ``str``.

    Citations:
        - SRS.md FR-12
        - 03-development/tests/test_fr12.py:136-337 (all 4 cases)
    """
    if not isinstance(user_text, str):
        raise TypeError("build_sandwich_prompt requires str user_text")

    system_block = _wrap_priority_block("SYSTEM", system_prompt)
    reinforcement_block = _wrap_priority_block(
        "SYSTEM REINFORCEMENT", system_prompt
    )
    user_block = (
        f"[USER | {_UNTRUSTED_TAG}]\n"
        f"{self._SPOTLIGHT_START}{user_text}{self._SPOTLIGHT_END}\n"
        f"[/USER | END {_UNTRUSTED_TAG}]"
    )
    return f"{system_block}\n\n{user_block}\n\n{reinforcement_block}"


PromptInjectionDefense.build_sandwich_prompt = _build_sandwich_prompt


# ---------------------------------------------------------------------------
# [FR-13] PALADIN L4 — SemanticInjectionClassifier
#
# SRS FR-13: "PALADIN L4 — SemanticInjectionClassifier: LLM-based
# (gpt-4o-mini 預設), 回傳 `{is_injection, confidence, injection_type:
# direct_prompt_injection | indirect_injection | jailbreak | none}`;
# p95 < 200ms; classifier 超時 → 放行並標記 'unverified'."
#
# Construction is zero-arg and side-effect-free; the only network hop is
# ``_call_llm()``, exposed as an instance method so unit tests can
# monkeypatch the upstream LLM call without touching the classifier
# logic. The classify() routing:
#   - risk_level == "low"          → skip the LLM, return a safe default
#                                     (FR-15 routing — "low risk → 跳過 L4").
#   - asyncio.TimeoutError / OS    → return is_unverified=True
#                                     (pipeline passthrough — do NOT block
#                                     on a stalled or down classifier,
#                                     per NP-07 fault-injection contract).
#   - success                      → map the upstream JSON-like dict to
#                                     a frozen ClassificationResult.
#
# Citations:
#   - SRS.md FR-13 (PALADIN L4 SemanticInjectionClassifier acceptance)
#   - 02-architecture/TEST_SPEC.md FR-13 (case 1: valid JSON; case 2:
#     timeout passthrough; case 3: 4-value enum; case 4: p95 < 200ms;
#     case 5: low-risk skip; case 6: outage graceful degradation)
#   - 03-development/tests/test_fr13.py:192-230 (case 1: valid JSON)
#   - 03-development/tests/test_fr13.py:233-280 (case 2: timeout
#     passthrough)
#   - 03-development/tests/test_fr13.py:283-341 (case 3: 4-value enum)
#   - 03-development/tests/test_fr13.py:344-396 (case 4: p95 < 200ms)
#   - 03-development/tests/test_fr13.py:399-453 (case 5: low-risk skip)
#   - 03-development/tests/test_fr13.py:456-499 (case 6: outage graceful
#     degradation)
#   - SRS.md FR-15 (low-risk L4 skip; classify() is the routing hook)
# ---------------------------------------------------------------------------
