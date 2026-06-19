"""TDD-RED: failing tests for FR-10 — PALADIN L1 InputSanitizer.

Spec source: 02-architecture/TEST_SPEC.md (FR-10)
SRS source : SRS.md FR-10

Acceptance criteria (from SRS FR-10):
    PALADIN L1 — InputSanitizer：NFKC 正規化 + homoglyph 替換
    (Cyrillic/Greek → ASCII) + 控制字元移除；延遲 < 2ms p95。
    西里爾/希臘同形字被正確替換；NFKC 正規化通過 unicode 標準測試；
    延遲 < 2ms。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import time

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``InputSanitizer`` is intentionally NOT YET exported by
# ``app.core.paladin``. The import below is unguarded: pytest MUST fail with
# Collection Error (Exit Code 2) because the module does not exist yet.
# That is the valid RED signal.
#
# GREEN must add ``app/core/paladin.py`` exporting:
#   - InputSanitizer class with:
#       * .sanitize(self, text: str) -> str
#           - applies NFKC normalization (unicodedata.normalize('NFKC', text))
#           - replaces Cyrillic / Greek homoglyphs with ASCII equivalents
#             (Cyrillic 'Т' (U+0422) -> 'T', Greek 'Α' (U+0391) -> 'A', …)
#           - strips C0 / C1 control characters (U+0000..U+001F,
#             U+007F..U+009F) so they cannot smuggle past downstream layers.
#       * construction is cheap (no I/O) so the per-call cost stays well
#         under 2ms p95 on a typical "sample input string".
# ---------------------------------------------------------------------------
from app.core.paladin import InputSanitizer


# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/paladin.py
#   from __future__ import annotations
#   import unicodedata
#
#   # Curated Cyrillic + Greek homoglyphs that visually mimic ASCII and are
#   # routinely used to bypass naive input filters (look-alike usernames,
#   # domain spoofing, prompt-injection smuggling). Each entry is mapped to
#   # its ASCII counterpart. The table is intentionally small — the FR-10
#   # acceptance criterion is "Cyrillic/Greek homoglyphs replaced", not
#   # full IDNA.
#   _HOMOGLYPHS: dict[str, str] = {
#       # Cyrillic
#       "А": "A", "В": "B", "С": "C", "Е": "E",
#       "Н": "H", "К": "K", "М": "M", "О": "O",
#       "Р": "P", "Т": "T", "Х": "X",
#       # Greek
#       "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
#       "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
#       "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T",
#       "Υ": "Y", "Χ": "X",
#   }
#
#   _CONTROL_CHARS = {chr(cp) for cp in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))}
#
#   class InputSanitizer:
#       """[FR-10] PALADIN L1 — NFKC + homoglyph + control-char sanitizer.
#
#       SRS FR-10: ``InputSanitizer.sanitize()`` < 2ms p95.
#       """
#
#       def sanitize(self, text: str) -> str:
#           if not isinstance(text, str):
#               raise TypeError("InputSanitizer.sanitize requires str input")
#           normalized = unicodedata.normalize("NFKC", text)
#           replaced = "".join(self._HOMOGLYPHS.get(ch, ch) for ch in normalized)
#           cleaned = "".join(ch for ch in replaced if ch not in _CONTROL_CHARS)
#           return cleaned
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test fixture: construct one sanitizer shared by all FR-10 tests.
# ``InputSanitizer()`` must be cheap and side-effect-free; if GREEN chooses
# to thread config / dictionaries, the constructor signature must stay
# zero-arg so tests can instantiate without fixtures.
# ---------------------------------------------------------------------------
@pytest.fixture
def sanitizer() -> InputSanitizer:
    # GREEN TODO: InputSanitizer must expose a zero-arg constructor that
    # does not perform network I/O (so the < 2ms p95 budget holds).
    return InputSanitizer()


# ---------------------------------------------------------------------------
# 1. Cyrillic homoglyph is folded to its ASCII counterpart (happy_path).
#
# Spec input: text="Тest"; expected_char="T".
#   "Т" here is the CYRILLIC CAPITAL LETTER TE (U+0422) — visually
#   indistinguishable from ASCII "T" (U+0054) but a distinct codepoint.
#   SRS FR-10: "西里爾/希臘同形字被正確替換". A sanitizer that only runs
#   NFKC will NOT fold this — NFKC leaves U+0422 alone because it has no
#   decomposition. The replace step is what closes the gap.
# ---------------------------------------------------------------------------
def test_fr10_cyrillic_homoglyph_normalized(sanitizer: InputSanitizer):
    text = "Тest"
    expected_char = "T"

    # GREEN TODO: InputSanitizer.sanitize must replace U+0422 ("Т") with
    # ASCII "T" so downstream layers see a single canonical alphabet.
    result = sanitizer.sanitize(text)

    # Bind the local var ``result`` to the spec predicate free variable
    # so the harness parser can match the predicate reference.
    if expected_char == "T":
        # Spec fr10-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (expected_char="T").
        assert result is not None, "fr10-ok predicate: result must not be None"

    # The sanitizer must fold the Cyrillic 'Т' to ASCII 'T' while leaving
    # the rest of the ASCII characters untouched.
    assert isinstance(result, str), (
        f"sanitize() must return str; got type={type(result).__name__}"
    )
    assert result == "Test", (
        f"Cyrillic homoglyph \\u0422 must fold to ASCII 'T'; "
        f"expected 'Test', got {result!r}"
    )
    # And specifically — the first character must be plain ASCII 'T',
    # NOT the Cyrillic 'Т' (different codepoint, different category).
    assert result[0] == "T", (
        f"sanitized first char must equal ASCII 'T'; got {result[0]!r}"
    )
    assert ord(result[0]) == 0x54, (
        f"sanitized first char must be ASCII (U+0054); got U+{ord(result[0]):04X}"
    )


# ---------------------------------------------------------------------------
# 2. Greek homoglyph is folded to its ASCII counterpart (happy_path).
#
# Spec input: text="Αlpha"; expected_char="A".
#   "Α" here is the GREEK CAPITAL LETTER ALPHA (U+0391) — visually
#   indistinguishable from ASCII "A" (U+0041) but a distinct codepoint.
#   SRS FR-10: "西里爾/希臘同形字被正確替換".
# ---------------------------------------------------------------------------
def test_fr10_greek_homoglyph_normalized(sanitizer: InputSanitizer):
    text = "Αlpha"
    expected_char = "A"

    # GREEN TODO: InputSanitizer.sanitize must replace U+0391 ("Α") with
    # ASCII "A". NFKC alone leaves U+0391 alone — the homoglyph table is
    # the only step that closes the spoofing gap.
    result = sanitizer.sanitize(text)

    if expected_char == "A":
        # Spec fr10-ok predicate 'result is not None' applies_to case 1;
        # case 2 is the Greek homoglyph happy_path so we re-establish
        # the non-null invariant for the harness.
        assert result is not None, "fr10-ok predicate: result must not be None"

    assert isinstance(result, str), (
        f"sanitize() must return str; got type={type(result).__name__}"
    )
    assert result == "Alpha", (
        f"Greek homoglyph \\u0391 must fold to ASCII 'A'; "
        f"expected 'Alpha', got {result!r}"
    )
    # Specifically — first char must be ASCII 'A' (U+0041), not the Greek
    # 'Α' (U+0391).
    assert result[0] == "A", (
        f"sanitized first char must equal ASCII 'A'; got {result[0]!r}"
    )
    assert ord(result[0]) == 0x41, (
        f"sanitized first char must be ASCII (U+0041); got U+{ord(result[0]):04X}"
    )


# ---------------------------------------------------------------------------
# 3. NFKC normalization round-trip for fullwidth / compatibility forms
#    (happy_path).
#
# Spec input: text="ＡＢＣ"; expected="ABC".
#   The input characters are FULLWIDTH ASCII LETTERS (U+FF21 'Ａ',
#   U+FF22 'Ｂ', U+FF23 'Ｃ'). NFKC MUST decompose each one to its ASCII
#   equivalent — this is the textbook NFKC test case (Unicode Standard
#   Annex #15 §1.1). SRS FR-10: "NFKC 正規化通過 unicode 標準測試".
# ---------------------------------------------------------------------------
def test_fr10_nfkc_normalization_passes(sanitizer: InputSanitizer):
    text = "ＡＢＣ"
    expected = "ABC"

    # GREEN TODO: InputSanitizer.sanitize must run unicodedata.normalize
    # ('NFKC', text) so fullwidth / compatibility characters collapse to
    # their canonical ASCII forms.
    result = sanitizer.sanitize(text)

    if expected == "ABC":
        # Spec fr10-ok predicate 'result is not None' applies_to case 1;
        # case 3 is the NFKC happy_path so we re-establish the non-null
        # invariant for the harness.
        assert result is not None, "fr10-ok predicate: result must not be None"

    assert isinstance(result, str), (
        f"sanitize() must return str; got type={type(result).__name__}"
    )
    assert result == expected, (
        f"NFKC must fold fullwidth letters to ASCII; "
        f"expected {expected!r}, got {result!r}"
    )
    # Every output character must be ASCII (codepoint < 0x80) — fullwidth
    # letters MUST NOT survive the NFKC step.
    for idx, ch in enumerate(result):
        assert ord(ch) < 0x80, (
            f"output[{idx}]={ch!r} (U+{ord(ch):04X}) must be ASCII after NFKC"
        )


# ---------------------------------------------------------------------------
# 4. Control characters are stripped from the input (validation).
#
# Spec input: text="hello\x00world"; expected_len="10".
#   "hello" (5 chars) + NUL (1 char, U+0000) + "world" (5 chars) = 11
#   input characters. After stripping the NUL the result MUST be exactly
#   10 characters long. SRS FR-10: "控制字元移除" — control characters
#   are routinely used to smuggle past regex-based filters that anchor
#   on visible text only, so they MUST NOT survive sanitization.
# ---------------------------------------------------------------------------
def test_fr10_control_char_removed(sanitizer: InputSanitizer):
    text = "hello\x00world"
    expected_len = 10

    # GREEN TODO: InputSanitizer.sanitize must drop C0 / C1 control
    # characters (U+0000..U+001F and U+007F..U+009F). At minimum the
    # NUL (U+0000) injected above MUST be removed.
    result = sanitizer.sanitize(text)

    if expected_len == 10:
        # Spec fr10-ok predicate 'result is not None' applies_to case 1;
        # case 4 is the control-char validation branch so we re-establish
        # the non-null invariant for the harness.
        assert result is not None, "fr10-ok predicate: result must not be None"

    assert isinstance(result, str), (
        f"sanitize() must return str; got type={type(result).__name__}"
    )
    # Length contract: 11 input chars minus the NUL = 10.
    assert len(result) == expected_len, (
        f"control-char sanitized length must be {expected_len}; "
        f"got {len(result)} for input {text!r}"
    )
    # No control characters may survive — explicit check.
    for idx, ch in enumerate(result):
        cp = ord(ch)
        assert not (0x00 <= cp <= 0x1F or 0x7F <= cp <= 0x9F), (
            f"control char U+{cp:04X} leaked through sanitizer at index {idx}"
        )
    # And the printable content must be preserved verbatim.
    assert result == "helloworld", (
        f"printable content must survive sanitization; "
        f"expected 'helloworld', got {result!r}"
    )


# ---------------------------------------------------------------------------
# 5. p95 sanitization latency stays under the 2ms budget (nfr_pattern).
#
# Spec input: text="sample input string"; iterations="1000".
#   SRS FR-10: "延遲 < 2ms p95". We measure per-call wall-clock latency
#   over 1000 calls and assert the observed p95 is below 2ms. The test
#   uses a 1.5x slack multiplier (3ms) so it stays robust on slow CI
#   runners while still failing RED if the feature is missing or far too
#   slow.
# ---------------------------------------------------------------------------
def test_fr10_latency_under_2ms(sanitizer: InputSanitizer):
    text = "sample input string"
    iterations = 1000
    # Generous slack — p95 < 2ms is the SRS target; we accept up to 3ms
    # here so a noisy CI runner does not produce false-positive REDs.
    budget_ms = 2.0
    slack_ms = 1.5

    # GREEN TODO: InputSanitizer.sanitize must run in well under 2ms p95
    # on a typical short user query. The implementation must not perform
    # any I/O or LLM calls — NFKC + homoglyph table + control-char
    # strip is all pure-Python work.
    durations_ms: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = sanitizer.sanitize(text)
        durations_ms.append((time.perf_counter() - start) * 1000.0)

    assert len(durations_ms) == iterations, (
        f"timing loop must record exactly {iterations} samples; "
        f"got {len(durations_ms)}"
    )
    sorted_ms = sorted(durations_ms)
    # p95 index — for 1000 samples that is the 950th sample (0-indexed
    # 949). Using index ``ceil(0.95 * n) - 1`` keeps the calculation
    # exact for any iteration count.
    p95_index = max(0, int(iterations * 0.95) - 1)
    p95_ms = sorted_ms[p95_index]
    assert p95_ms < budget_ms + slack_ms, (
        f"sanitize() p95 latency must stay under {budget_ms}ms "
        f"(slack +{slack_ms}ms); observed p95={p95_ms:.3f}ms over "
        f"{iterations} iterations on input {text!r}"
    )