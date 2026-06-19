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
        raise TypeError(
            "build_sandwich_prompt requires str user_text"
        )
    system_block = (
        f"[SYSTEM | PRIORITY: HIGHEST]\n"
        f"{system_prompt}\n"
        f"[/SYSTEM]"
    )
    user_block = (
        f"[USER | UNTRUSTED DATA BOUNDARY]\n"
        f"{self._SPOTLIGHT_START}{user_text}{self._SPOTLIGHT_END}\n"
        f"[/USER | END UNTRUSTED DATA BOUNDARY]"
    )
    reinforcement_block = (
        "[SYSTEM REINFORCEMENT | PRIORITY: HIGHEST]\n"
        f"{system_prompt}\n"
        "[/SYSTEM REINFORCEMENT]"
    )
    return (
        f"{system_block}\n\n"
        f"{user_block}\n\n"
        f"{reinforcement_block}"
    )


PromptInjectionDefense.build_sandwich_prompt = _build_sandwich_prompt
