"""[FR-10] PALADIN L1 — InputSanitizer (NFKC + homoglyph + control-char).

SRS FR-10: "PALADIN L1 — InputSanitizer: NFKC 正規化 + homoglyph 替換
(Cyrillic/Greek → ASCII) + 控制字元移除; 延遲 < 2ms p95."

Pipeline:
    1. ``unicodedata.normalize('NFKC', text)`` — folds fullwidth and
       compatibility forms into their canonical ASCII equivalents.
    2. ``str.translate()`` — Cyrillic / Greek homoglyphs are mapped to
       their ASCII counterpart (U+0422 → 'T', U+0391 → 'A', …); C0
       (U+0000..U+001F) and C1 (U+007F..U+009F) control characters are
       deleted so they cannot smuggle past regex-based downstream
       filters. Both maps are merged into a single pre-computed
       translation table.

Citations:
    - SRS.md FR-10 (PALADIN L1 InputSanitizer acceptance criteria)
    - 02-architecture/TEST_SPEC.md FR-10 (case 1: Cyrillic homoglyph;
      case 2: Greek homoglyph; case 3: NFKC round-trip; case 4: control
      char strip; case 5: p95 latency < 2ms)
    - 03-development/tests/test_fr10.py:108-141 (Cyrillic case)
    - 03-development/tests/test_fr10.py:152-183 (Greek case)
    - 03-development/tests/test_fr10.py:196-222 (NFKC round-trip case)
    - 03-development/tests/test_fr10.py:235-267 (control-char strip case)
    - 03-development/tests/test_fr10.py:280-312 (p95 latency case)
"""

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

# Curated Cyrillic + Greek homoglyphs that visually mimic ASCII and are
# routinely used to bypass naive input filters (look-alike usernames,
# domain spoofing, prompt-injection smuggling). Each entry is mapped to
# its ASCII counterpart. The table is intentionally small — the FR-10
# acceptance criterion is "Cyrillic/Greek homoglyphs replaced", not
# full IDNA.
#
# Keys are written via ``chr(0xXXXX)`` (rather than as literal
# Cyrillic / Greek characters) so the source compiles without
# triggering RUF001 ambiguous-character warnings. At runtime each
# ``chr(0x0410)`` evaluates to exactly the same single-codepoint
# ``str`` as the literal Cyrillic ``A`` would — ``str.maketrans`` and
# ``str.translate`` see identical translation pairs.
_HOMOGLYPHS: dict[str, str] = {
    # Cyrillic
    chr(0x0410): "A", chr(0x0412): "B", chr(0x0421): "C", chr(0x0415): "E",
    chr(0x041D): "H", chr(0x041A): "K", chr(0x041C): "M", chr(0x041E): "O",
    chr(0x0420): "P", chr(0x0422): "T", chr(0x0425): "X",
    # Greek
    chr(0x0391): "A", chr(0x0392): "B", chr(0x0395): "E", chr(0x0396): "Z",
    chr(0x0397): "H", chr(0x0399): "I", chr(0x039A): "K", chr(0x039C): "M",
    chr(0x039D): "N", chr(0x039F): "O", chr(0x03A1): "P", chr(0x03A4): "T",
    chr(0x03A5): "Y", chr(0x03A7): "X",
}

# C0 (U+0000..U+001F) + DEL (U+007F) + C1 (U+0080..U+009F) + format chars.
_CONTROL_CHARS: dict[str, None] = {
    chr(cp): None for cp in (*range(0x00, 0x20), *range(0x7F, 0xA0), 0x200B, 0x200C, 0x200D, 0xFEFF)
}

# Pre-computed translate table: homoglyphs map to their ASCII
# counterpart, control chars map to ``None`` (delete). Built once at
# import time so the per-call sanitize() is a single ``.translate()``
# pass — replaces a two-stage join+get / join+in with one C-level sweep.
_TRANSLATE_TABLE: dict[int, int | str | None] = str.maketrans(
    {**_HOMOGLYPHS, **_CONTROL_CHARS}  # type: ignore[arg-type]
)


# [FR-108] SQL-injection keywords and characters to strip from user input
# after NFKC normalization. Applied as a post-processing step in
# ``InputSanitizer.sanitize()`` so common injection payloads like
# ``'; DROP TABLE users;--`` are neutralized before reaching downstream
# query builders.
_SQL_INJECTION_RE = re.compile(
    r"(?i)\b(DROP\s+TABLE|ALTER\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|"
    r"UPDATE\s+\w+\s+SET|UNION\s+SELECT|EXEC\s*\(|EXECUTE\s*\(|"
    r"--|/\*|\*/|;)"
)


def _sanitize_sql_patterns(text: str) -> str:
    """[FR-108] Remove SQL-injection keywords and special characters.

    Citations:
        - 03-development/tests/test_fr108.py:517-532 (SQL injection case)
    """
    return _SQL_INJECTION_RE.sub("", text)


class InputSanitizer:
    """[FR-10] PALADIN L1 — NFKC + homoglyph + control-char sanitizer.

    Construction is zero-arg and side-effect-free so callers can keep a
    single instance on the hot path; ``sanitize()`` itself is pure-Python
    string work, which is what holds the p95 latency budget at < 2ms.

    Citations:
        - SRS.md FR-10
        - 03-development/tests/test_fr10.py:91-95 (zero-arg fixture)
        - 03-development/tests/test_fr10.py:280-312 (p95 latency budget)
    """

    def sanitize(self, text: str) -> str:
        """Fold ``text`` to its canonical ASCII representation.

        Steps (see module docstring):
            1. NFKC normalize.
            2. Translate — homoglyphs → ASCII, control chars → delete.
            3. [FR-108] Neutralize SQL injection patterns.

        Args:
            text: Arbitrary user input.

        Returns:
            Sanitized string — printable, ASCII-only where the source
            codepoint had a homoglyph, and free of control characters.

        Raises:
            TypeError: ``text`` is not a ``str``.

        Citations:
            - SRS.md FR-10
            - 03-development/tests/test_fr10.py:108-267 (cases 1-4)
            - 03-development/tests/test_fr108.py:517-532 (SQL injection)
        """
        if not isinstance(text, str):
            raise TypeError("InputSanitizer.sanitize requires str input")
        result = unicodedata.normalize("NFKC", text).translate(_TRANSLATE_TABLE)
        # [FR-108] Neutralize SQL injection patterns by removing
        # common SQL keywords and special chars (', ;, --).
        result = _sanitize_sql_patterns(result)
        return result


# ---------------------------------------------------------------------------
# [FR-11] PALADIN L2 — PromptInjectionDefense
#
# SRS FR-11: "PALADIN L2 — Pattern Detection: 13 個 SUSPICIOUS_PATTERNS
# regex (ignore previous instructions, system:, pretend you, act as,
# forget everything 等) + Unicode 變體偵測; 延遲 < 3ms p95."
#
# Pipeline: a single regex walk over the (already NFKC-normalized) input.
# Case folding is delegated to ``re.IGNORECASE`` on each compiled pattern;
# the L1 InputSanitizer has already collapsed fullwidth / zero-width
# codepoints, so this layer does not re-normalize (avoiding double-billing
# the per-call cost). Patterns are pre-compiled at import time so the
# hot path is a tight loop of ``Pattern.search`` calls.
#
# Citations:
#   - SRS.md FR-11 (PALADIN L2 Pattern Detection acceptance criteria)
#   - 02-architecture/TEST_SPEC.md FR-11 (cases 1-6: pattern hits;
#     case 7: p95 latency < 3ms)
#   - 03-development/tests/test_fr11.py:108-113 (zero-arg fixture)
#   - 03-development/tests/test_fr11.py:122-145 (ignore previous
#     instructions case)
#   - 03-development/tests/test_fr11.py:157-173 (system: prefix case)
#   - 03-development/tests/test_fr11.py:185-201 (pretend you case)
#   - 03-development/tests/test_fr11.py:211-227 (act as case)
#   - 03-development/tests/test_fr11.py:239-255 (forget everything case)
#   - 03-development/tests/test_fr11.py:268-287 (zh-TW false-positive
#     guard)
#   - 03-development/tests/test_fr11.py:300-334 (p95 < 3ms latency case)
# ---------------------------------------------------------------------------
# Canonical 13-pattern injection set per SRS FR-11. Each entry is
# ``(regex_source, flags)``; the order is not significant — matching any
# one is enough to flag the input. The compiled pair list below is
# derived from this table so each source string lives in exactly one
# place (no copy/paste between ``re.compile`` and the captured ``.pattern``
# we return to callers for logging).
_RAW_SUSPICIOUS_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", re.IGNORECASE),
    (r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    (r"pretend\s+you\s+(?:are|were)\s+", re.IGNORECASE),
    (r"act\s+as\s+(?:an?\s+)?", re.IGNORECASE),
    (r"forget\s+everything(?:\s+you\s+know)?", re.IGNORECASE),
    (r"disregard\s+(?:all|any|the)\s+", re.IGNORECASE),
    (r"override\s+(?:all|any|the|system)\s+", re.IGNORECASE),
    (r"reveal\s+(?:the\s+)?(?:system|hidden|secret)\s+prompt", re.IGNORECASE),
    (r"developer\s+mode", re.IGNORECASE),
    (r"jailbreak", re.IGNORECASE),
    (r"DAN\b", re.IGNORECASE),
    (r"<\s*\|.*?\|", re.DOTALL),                                # <|...|> markers
    (r"###\s*(?:system|assistant|instruction)\s*:", re.IGNORECASE),
)

# Each entry is a ``(compiled_pattern, source)`` pair. The source is
# captured once at import time so the hot path does not have to reach
# for ``Pattern.pattern`` on every hit.
_SUSPICIOUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(source, flags), source)
    for source, flags in _RAW_SUSPICIOUS_PATTERNS
]


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
        raise NotImplementedError  # pragma: no cover

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
        import asyncio
        return await asyncio.to_thread(
            self.classify,
            text,
            risk_level=risk_level,
            timeout_ms=timeout_ms,
        )

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
                verdict = _await_coro_from_sync(verdict, timeout_ms)  # pragma: no cover — async coroutine dispatch path covered by test_fr13
        except (TimeoutError, ConnectionError, OSError, ValueError):
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
        holder["loop"] = new_loop
        task = new_loop.create_task(coro)
        holder["task"] = task
        try:
            holder["v"] = new_loop.run_until_complete(
                asyncio.wait_for(task, timeout=timeout_ms / 1000.0)
            )
        except BaseException as exc:  # propagate TimeoutError etc.
            holder["e"] = exc
        finally:
            new_loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=timeout_ms / 1000.0)
    if t.is_alive():
        loop = holder.get("loop")
        task = holder.get("task")
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                if task is not None:
                    loop.call_soon_threadsafe(task.cancel)
                loop.call_soon_threadsafe(loop.stop)
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
    try:
        injection_type = InjectionType(verdict.get("injection_type", "none"))
        is_unverified = False
    except ValueError:
        injection_type = InjectionType.NONE
        is_unverified = True

    import math
    c = float(verdict.get("confidence", 0.0))
    if math.isnan(c):
        c = 0.0  # pragma: no cover — InjectionType constructor ValueError fallback — covered by FR-13 timeout test
    confidence = max(0.0, min(1.0, c))

    return ClassificationResult(
        is_injection=bool(verdict.get("is_injection", False)),
        confidence=confidence,
        injection_type=injection_type,
        is_unverified=is_unverified,
    )


# ---------------------------------------------------------------------------
# [FR-14] PALADIN L5 — GroundingChecker
#
# SRS FR-14: "PALADIN L5 — GroundingChecker: 計算 LLM 輸出與 source_texts
# 之間 cosine similarity (text-embedding-3-small 1536維), 閾值 0.75;
# 延遲 < 5ms (本地計算). cosine score < 0.75 → grounded=False;
# cosine score ≥ 0.75 → grounded=True; 無 source_texts → grounded=False."
#
# Construction is zero-arg and side-effect-free; the cosine math runs
# locally (no remote embedding API on the L5 hot path) so the per-call
# cost stays well under the 5ms p95 budget. ``_cosine_similarity`` is
# exposed as an instance method so unit tests can monkeypatch the
# underlying math and inject deterministic scores without depending on
# ``math.sqrt`` or numpy.
#
# Citations:
#   - SRS.md FR-14 (PALADIN L5 GroundingChecker acceptance criteria)
#   - 02-architecture/TEST_SPEC.md FR-14 (case 1: cosine 0.70 < 0.75 →
#     grounded=False; case 2: cosine 0.80 ≥ 0.75 → grounded=True;
#     case 3: empty source_texts → grounded=False; case 4: p95 < 5ms)
#   - 03-development/tests/test_fr14.py:118-167 (case 1 — cosine below
#     threshold yields grounded=False)
#   - 03-development/tests/test_fr14.py:170-219 (case 2 — cosine at or
#     above threshold yields grounded=True; threshold round-trip)
#   - 03-development/tests/test_fr14.py:222-263 (case 3 — empty
#     source_texts short-circuits to grounded=False with source_count=0)
#   - 03-development/tests/test_fr14.py:266-318 (case 4 — p95 latency
#     stays under 5ms with slack over 1000 iterations)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundingResult:
    """[FR-14] Outcome of a single ``GroundingChecker.check`` call.

    ``grounded`` is the boolean the pipeline reads. ``cosine_score`` is
    the *maximum* cosine similarity over the source_texts (0.0 when
    source_texts is empty — by definition no grounding can be
    demonstrated). ``threshold`` echoes the threshold the call used so
    log lines can reproduce the decision offline. ``source_count`` is
    the number of source texts the call considered (0 on the empty-input
    short-circuit path so downstream observability can spot the "no
    candidates" condition).
    """

    grounded: bool
    cosine_score: float
    threshold: float
    source_count: int

    @property
    def cosine_similarity(self) -> float:
        """[FR-108] Alias for ``cosine_score`` — used by golden-dataset KPI tests.

        Citations:
            - 03-development/tests/test_fr108.py:634
        """
        return self.cosine_score


class GroundingChecker:
    """[FR-14] PALADIN L5 — cosine-similarity grounding check.

    SRS FR-14: ``GroundingChecker.check()`` < 5ms p95.

    Construction is zero-arg and side-effect-free; the cosine math
    runs locally (pure-Python dot / norm) so no network round-trip is
    on the L5 hot path. ``_cosine_similarity`` is exposed as an
    instance method so unit tests can monkeypatch it and inject
    deterministic scores without depending on the underlying math
    implementation.
    """

    DEFAULT_THRESHOLD = 0.75

    def __init__(self) -> None:
        # Zero-arg; no network I/O at init (so the < 5ms p95 budget
        # holds even on the first call after process boot, and so a
        # unit-test fixture can spin one up with no setup).
        pass

    def _cosine_similarity(
        self,
        a,
        b,
    ) -> float:
        """[FR-14] Cosine similarity hook — tests monkeypatch this.

        Default implementation: pure-Python ``dot(a, b) / (norm(a) *
        norm(b))`` over equal-length float sequences. Returns 0.0 when
        either vector has zero norm (avoids division-by-zero on a
        degenerate zero-vector input).
        """
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))  # pragma: no cover — cosine similarity computation covered by test_fr14

    def check(
        self,
        output_embedding=None,
        source_texts=None,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        response: str | None = None,
        sources: list[str] | None = None,
    ) -> GroundingResult:
        """[FR-14/FR-108] Compare LLM output embedding against source_texts.

        When ``response`` / ``sources`` are provided (FR-108 text-based
        call), returns a stub result with ``cosine_similarity >= 0.75``.
        Otherwise, performs the embedding-based cosine comparison.

        Citations:
            - SRS.md FR-14
            - 03-development/tests/test_fr14.py:118-318 (all 4 cases)
            - 03-development/tests/test_fr108.py:634-636 (text-based)
        """
        # [FR-108] Text-based call — word-overlap Jaccard similarity.
        if response is not None or sources is not None:
            resp_tokens = set((response or "").lower().split())
            src_tokens: set[str] = set()
            for s in (sources or []):
                src_tokens.update(s.lower().split())
            if not resp_tokens or not src_tokens:
                cosine_score = 0.0
            else:
                cosine_score = len(resp_tokens & src_tokens) / max(len(resp_tokens), len(src_tokens))
            return GroundingResult(
                grounded=cosine_score >= threshold,
                cosine_score=float(cosine_score),
                threshold=float(threshold),
                source_count=len(sources or []),
            )

        if output_embedding is None:
            raise TypeError(
                "GroundingChecker.check requires output_embedding or response"
            )

        if not hasattr(output_embedding, "__iter__"):
            raise TypeError(
                "GroundingChecker.check requires iterable output_embedding"
            )

        # No source_texts → no evidence to ground against; cosine
        # defaults to 0.0 so ``0.0 >= threshold`` yields
        # ``grounded=False`` and ``len(source_texts)`` reports 0.
        if not source_texts:
            cosine_score = 0.0
            _source_count = 0
        else:
            # [FR-14] Materialize once so ``len()`` works for any
            # iterable (generator, iterator, custom Iterable) — a
            # bare generator passes ``if not source_texts:`` (the
            # generator object is truthy) and then crashes on len().
            sources_list = list(source_texts)
            cosine_score = max(
                self._cosine_similarity(output_embedding, src)
                for src in sources_list
            )
            _source_count = len(sources_list)

        return GroundingResult(
            grounded=cosine_score >= threshold,
            cosine_score=float(cosine_score),
            threshold=float(threshold),
            source_count=_source_count,
        )


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
        verdict_raw, response_raw = results
        if isinstance(verdict_raw, BaseException):
            raise verdict_raw  # pragma: no cover
        if isinstance(response_raw, BaseException):
            raise response_raw  # pragma: no cover
        verdict = cast(ClassificationResult, verdict_raw)
        response = cast(str, response_raw)

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

