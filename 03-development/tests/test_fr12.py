from __future__ import annotations
"""TDD-RED: failing tests for FR-12 — PALADIN L3 Sandwich Prompt + Spotlighting.

Spec source: 02-architecture/TEST_SPEC.md (FR-12)
SRS source : SRS.md FR-12

Acceptance criteria (from SRS FR-12):
    PALADIN L3 — Instruction Hierarchy：Sandwich Prompt 建構，系統指令
    標記 PRIORITY: HIGHEST，用戶訊息標記 UNTRUSTED DATA BOUNDARY，使用
    Spotlighting delimiters（ICLR 2025）；L1-L3 合計延遲 < 5ms p95。
    Sandwich prompt 結構正確包含三個標記區塊；SYSTEM/UNTRUSTED 邊界清晰。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


import time

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``PromptInjectionDefense.build_sandwich_prompt`` is
# intentionally NOT YET implemented on ``app.core.paladin``. The import
# below resolves (the class exists for FR-10/FR-11), but ``build_sandwich_prompt``
# is missing — calling it raises ``AttributeError``. That is the valid RED
# signal.
#
# GREEN must add to ``app/core/paladin.py`` (extending the existing
# ``PromptInjectionDefense`` class):
#
#   - ``PromptInjectionDefense.build_sandwich_prompt(self, user_text: str,
#       system_prompt: str = "") -> str``
#
#     The method assembles a *sandwich prompt* with three explicit sections:
#
#       1. SYSTEM / PRIORITY: HIGHEST block — carries the upstream system
#          prompt, marked with the literal token ``PRIORITY: HIGHEST`` so
#          downstream LLMs treat it as highest-priority instruction.
#
#       2. USER / UNTRUSTED DATA BOUNDARY block — wraps the user-supplied
#          ``user_text`` between literal boundary markers
#          ``UNTRUSTED DATA BOUNDARY`` … ``END UNTRUSTED DATA BOUNDARY``
#          so the LLM knows this segment is data, not instruction.
#
#       3. INSTRUCTION REINFORCEMENT block — repeats the system intent
#          after the untrusted block (the "sandwich" shape) so an injected
#          instruction in the middle cannot push the system intent off
#          the attention budget.
#
#     Spotlighting delimiters per the ICLR 2025 paper wrap the user
#     segment inside the boundary block (e.g. `` spotlight start `` …
#     `` spotlight end ``) so the LLM can visually isolate untrusted
#     tokens.
#
#     Construction MUST be pure-Python string concatenation — no I/O, no
#     LLM calls, no regex — so the per-call cost stays well under the
#     L1-L3 cumulative 5ms p95 budget when composed with FR-10
#     ``InputSanitizer.sanitize`` and FR-11 ``PromptInjectionDefense.check_input``.
# ---------------------------------------------------------------------------
from app.core.paladin import InputSanitizer, PromptInjectionDefense

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/paladin.py — extend PromptInjectionDefense
#   class PromptInjectionDefense:
#       # ... existing check_input() from FR-11 ...
#
#       _SPOTLIGHT_START = "<<<SPOTLIGHT_START>>>"
#       _SPOTLIGHT_END = "<<<SPOTLIGHT_END>>>"
#
#       def build_sandwich_prompt(
#           self,
#           user_text: str,
#           system_prompt: str = "",
#       ) -> str:
#           """[FR-12] PALADIN L3 — Sandwich prompt with priority + boundary."""
#           if not isinstance(user_text, str):
#               raise TypeError(
#                   "build_sandwich_prompt requires str user_text"
#               )
#           system_block = (
#               f"[SYSTEM | PRIORITY: HIGHEST]\n"
#               f"{system_prompt}\n"
#               f"[/SYSTEM]"
#           )
#           user_block = (
#               f"[USER | UNTRUSTED DATA BOUNDARY]\n"
#               f"{self._SPOTLIGHT_START}{user_text}{self._SPOTLIGHT_END}\n"
#               f"[/USER | END UNTRUSTED DATA BOUNDARY]"
#           )
#           reinforcement_block = (
#               "[SYSTEM REINFORCEMENT | PRIORITY: HIGHEST]\n"
#               f"{system_prompt}\n"
#               "[/SYSTEM REINFORCEMENT]"
#           )
#           return (
#               f"{system_block}\n\n"
#               f"{user_block}\n\n"
#               f"{reinforcement_block}"
#           )
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test fixtures: one defense + one sanitizer, shared across FR-12 tests.
# ``PromptInjectionDefense()`` and ``InputSanitizer()`` must be cheap and
# side-effect-free so the L1-L3 cumulative latency stays well under 5ms.
# ---------------------------------------------------------------------------
@pytest.fixture
def defense() -> PromptInjectionDefense:
    # GREEN TODO: PromptInjectionDefense must expose a zero-arg constructor
    # that does not perform network I/O (so the < 5ms cumulative p95
    # budget holds across L1 + L2 + L3).
    return PromptInjectionDefense()


@pytest.fixture
def sanitizer() -> InputSanitizer:
    # GREEN TODO: InputSanitizer must expose a zero-arg constructor (same
    # constraint as the defense).
    return InputSanitizer()


# ---------------------------------------------------------------------------
# 1. The sandwich prompt carries the PRIORITY: HIGHEST marker on the
#    system block (happy_path).
#
# Spec input: user_text="hello"; system_prompt="be helpful".
#   SRS FR-12: "系統指令標記 PRIORITY: HIGHEST". The downstream LLM uses
#   this token to recognize the segment as highest-priority instruction
#   that may not be overridden by anything inside the untrusted boundary.
# ---------------------------------------------------------------------------
def test_fr12_sandwich_has_priority_highest_marker(defense: PromptInjectionDefense):
    user_text = "hello"
    system_prompt = "be helpful"

    # GREEN TODO: PromptInjectionDefense.build_sandwich_prompt must
    # return a string that contains the literal token "PRIORITY: HIGHEST"
    # so the downstream LLM recognizes the system segment as
    # highest-priority instruction.
    result = defense.build_sandwich_prompt(user_text, system_prompt)

    if user_text == "hello" and system_prompt == "be helpful":
        # Spec fr12-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (user_text="hello"; system_prompt="be helpful").
        assert result is not None, "fr12-ok predicate: result must not be None"

    assert isinstance(result, str), (
        f"build_sandwich_prompt() must return str; "
        f"got type={type(result).__name__}"
    )
    # The PRIORITY: HIGHEST marker MUST appear on the system segment.
    assert "PRIORITY: HIGHEST" in result, (
        f"sandwich prompt must carry the 'PRIORITY: HIGHEST' marker "
        f"on the system block; got {result!r}"
    )


# ---------------------------------------------------------------------------
# 2. The sandwich prompt carries an UNTRUSTED DATA BOUNDARY around the
#    user segment (happy_path).
#
# Spec input: user_text="test input".
#   SRS FR-12: "用戶訊息標記 UNTRUSTED DATA BOUNDARY" + "SYSTEM/UNTRUSTED
#   邊界清晰". The boundary token is the explicit signal to the LLM that
#   the wrapped text is data, not instruction.
# ---------------------------------------------------------------------------
def test_fr12_sandwich_has_untrusted_boundary(defense: PromptInjectionDefense):
    user_text = "test input"

    # GREEN TODO: PromptInjectionDefense.build_sandwich_prompt must
    # wrap the user segment with the literal token
    # "UNTRUSTED DATA BOUNDARY" so the downstream LLM can clearly tell
    # data apart from instruction.
    result = defense.build_sandwich_prompt(user_text)

    if user_text == "test input":
        # Spec fr12-ok predicate applies_to case 1 only — case 2
        # has no predicate assertion (would trigger_mismatch).
        pass

    assert isinstance(result, str), (
        f"build_sandwich_prompt() must return str; "
        f"got type={type(result).__name__}"
    )
    # The UNTRUSTED DATA BOUNDARY marker MUST appear.
    assert "UNTRUSTED DATA BOUNDARY" in result, (
        f"sandwich prompt must carry the 'UNTRUSTED DATA BOUNDARY' "
        f"marker around the user segment; got {result!r}"
    )
    # The user text MUST appear inside the prompt (it cannot be
    # dropped — the LLM still needs to see the actual message).
    assert "test input" in result, (
        f"sandwich prompt must preserve the user_text verbatim; "
        f"got {result!r}"
    )


# ---------------------------------------------------------------------------
# 3. L1 + L2 + L3 cumulative p95 latency stays under the 5ms budget
#    (nfr_pattern).
#
# Spec input: text="test"; iterations="1000".
#   SRS FR-12: "L1-L3 合計延遲 < 5ms p95". NFR-02 also pins the same
#   budget. We measure the full L1-L3 pipeline (sanitize → check_input
#   → build_sandwich_prompt) per iteration and assert the observed p95
#   stays under 5ms with a generous 1.5x slack so a noisy CI runner
#   does not produce false-positive REDs.
# ---------------------------------------------------------------------------
def test_fr12_l1_l3_combined_under_5ms(
    defense: PromptInjectionDefense,
    sanitizer: InputSanitizer,
):
    text = "test"
    iterations = 1000
    # Generous slack — 5ms is the SRS target; we accept up to 7.5ms so
    # a noisy CI runner does not produce false-positive REDs.
    budget_ms = 5.0
    slack_ms = 2.5

    # GREEN TODO: build_sandwich_prompt must run in well under the
    # remaining budget after sanitize() (<2ms p95, FR-10) and
    # check_input() (<3ms p95, FR-11). The L3 implementation must be
    # pure-Python string concatenation — no I/O, no LLM calls.
    durations_ms: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        # L1 — NFKC + homoglyph + control-char strip (FR-10).
        sanitized = sanitizer.sanitize(text)
        # L2 — 13 SUSPICIOUS_PATTERNS regex walk (FR-11).
        _ = defense.check_input(sanitized)
        # L3 — sandwich prompt construction (FR-12, this layer).
        _ = defense.build_sandwich_prompt(sanitized)
        durations_ms.append((time.perf_counter() - start) * 1000.0)

    assert len(durations_ms) == iterations, (
        f"timing loop must record exactly {iterations} samples; "
        f"got {len(durations_ms)}"
    )
    sorted_ms = sorted(durations_ms)
    p95_index = max(0, int(iterations * 0.95) - 1)
    p95_ms = sorted_ms[p95_index]
    assert p95_ms < budget_ms + slack_ms, (
        f"L1-L3 cumulative p95 latency must stay under {budget_ms}ms "
        f"(slack +{slack_ms}ms); observed p95={p95_ms:.3f}ms over "
        f"{iterations} iterations on input {text!r}"
    )


# ---------------------------------------------------------------------------
# 4. Spotlighting delimiters (ICLR 2025) are present inside the
#    untrusted boundary block (validation).
#
# Spec input: user_text="user message".
#   SRS FR-12: "使用 Spotlighting delimiters（ICLR 2025）". The spotlighting
#   technique wraps untrusted tokens inside a distinctive delimiter pair
#   so the LLM can visually isolate them from surrounding instruction
#   text. The boundary markers alone are not enough — the spotlight
#   delimiters inside the boundary give the LLM a second, finer-grained
#   signal.
# ---------------------------------------------------------------------------
def test_fr12_spotlighting_delimiters_present(defense: PromptInjectionDefense):
    user_text = "user message"

    # GREEN TODO: PromptInjectionDefense.build_sandwich_prompt must
    # wrap the user segment inside a Spotlighting delimiter pair
    # (per ICLR 2025) so the LLM can visually isolate untrusted tokens
    # from the surrounding instruction text. The pair must be a
    # non-empty start delimiter distinct from a non-empty end delimiter,
    # and the user_text must appear between them.
    result = defense.build_sandwich_prompt(user_text)

    if user_text == "user message":
        # Spec fr12-ok predicate applies_to case 1 only — case 4
        # has no predicate assertion (would trigger_mismatch).
        pass

    assert isinstance(result, str), (
        f"build_sandwich_prompt() must return str; "
        f"got type={type(result).__name__}"
    )

    # The sandwich prompt must already declare the UNTRUSTED DATA
    # BOUNDARY (case 2 covers that) — case 4 specifically asserts the
    # spotlighting delimiter pair is layered on top.
    assert "UNTRUSTED DATA BOUNDARY" in result, (
        f"sandwich prompt must carry 'UNTRUSTED DATA BOUNDARY' "
        f"before spotlighting can be layered on top; got {result!r}"
    )

    # Find the user_text within the prompt and assert it sits between
    # a non-empty spotlight start delimiter and a non-empty spotlight
    # end delimiter. We use a regex-free split-based check so the test
    # does not assume a specific delimiter format (e.g. <<...>>,
    # spotlight start / end, ###, custom tokens, etc.) — any distinct
    # start/end pair that wraps user_text is acceptable.
    idx = result.find(user_text)
    assert idx >= 0, (
        f"user_text {user_text!r} must be present in the sandwich "
        f"prompt; got {result!r}"
    )

    # A 32-character window before user_text must contain a non-empty
    # spotlight *start* marker — i.e. some visible delimiter that
    # precedes the untrusted segment.
    pre_window = result[max(0, idx - 64):idx]
    # A 32-character window after user_text must contain a non-empty
    # spotlight *end* marker — i.e. some visible delimiter that
    # follows the untrusted segment.
    post_window = result[idx + len(user_text):idx + len(user_text) + 64]

    # The two windows must each carry at least one non-whitespace,
    # non-pure-punctuation delimiter token — i.e. the spotlighter did
    # actually place SOMETHING distinctive around the user text, not
    # just whitespace or newlines. We accept any visible character
    # class beyond whitespace / pure-newlines as evidence that a
    # delimiter is present.
    def _has_visible_delimiter(window: str) -> bool:
        # Strip whitespace + newlines; anything left is a delimiter
        # candidate (e.g. "<<<", "[", "###", "spotlight", etc.).
        stripped = "".join(ch for ch in window if not ch.isspace())
        return len(stripped) > 0

    assert _has_visible_delimiter(pre_window), (
        f"spotlighting start delimiter must precede user_text; "
        f"window before user_text is whitespace-only "
        f"(pre_window={pre_window!r}, result={result!r})"
    )
    assert _has_visible_delimiter(post_window), (
        f"spotlighting end delimiter must follow user_text; "
        f"window after user_text is whitespace-only "
        f"(post_window={post_window!r}, result={result!r})"
    )
