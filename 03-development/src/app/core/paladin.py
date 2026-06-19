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
import re
import unicodedata
from dataclasses import dataclass

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
# ``str`` as the literal Cyrillic ``А`` would — ``str.maketrans`` and
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

# C0 (U+0000..U+001F) + DEL (U+007F) + C1 (U+0080..U+009F).
_CONTROL_CHARS: dict[str, None] = {
    chr(cp): None for cp in (*range(0x00, 0x20), *range(0x7F, 0xA0))
}

# Pre-computed translate table: homoglyphs map to their ASCII
# counterpart, control chars map to ``None`` (delete). Built once at
# import time so the per-call sanitize() is a single ``.translate()``
# pass — replaces a two-stage join+get / join+in with one C-level sweep.
_TRANSLATE_TABLE: dict[int, int | str | None] = str.maketrans(
    {**_HOMOGLYPHS, **_CONTROL_CHARS}
)


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
        """
        if not isinstance(text, str):
            raise TypeError("InputSanitizer.sanitize requires str input")
        return unicodedata.normalize("NFKC", text).translate(_TRANSLATE_TABLE)


# ---------------------------------------------------------------------------
# [FR-11] PALADIN L2 — PromptInjectionDefense
#
# SRS FR-11: "PALADIN L2 — Pattern Detection：13 個 SUSPICIOUS_PATTERNS
# regex (ignore previous instructions, system:, pretend you, act as,
# forget everything 等) + Unicode 變體偵測；延遲 < 3ms p95。"
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
# SRS FR-12: "PALADIN L3 — Instruction Hierarchy：Sandwich Prompt 建構，
# 系統指令標記 PRIORITY: HIGHEST，用戶訊息標記 UNTRUSTED DATA BOUNDARY，
# 使用 Spotlighting delimiters（ICLR 2025）；L1-L3 合計延遲 < 5ms p95."
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
    self: "PromptInjectionDefense",
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
# SRS FR-13: "PALADIN L4 — SemanticInjectionClassifier：LLM-based
# (gpt-4o-mini 預設)，回傳 `{is_injection, confidence, injection_type:
# direct_prompt_injection | indirect_injection | jailbreak | none}`；
# p95 < 200ms；classifier 超時 → 放行並標記 'unverified'."
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
from enum import Enum


class InjectionType(str, Enum):
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
                verdict = asyncio.run(
                    asyncio.wait_for(verdict, timeout=timeout_ms / 1000.0)
                )
        except (asyncio.TimeoutError, ConnectionError, OSError):
            # Timeout OR downstream down → passthrough, do NOT block.
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
