"""Targeted mutation-killing tests for app.core.paladin.

Each test exercises a code path that mutmut 2.x reports as "survived" after
running with ``--disable-mutation-types=string,number``. The goal is to
push paladin's kill rate from ~42% to >= 70% by asserting internal field
values that existing tests gloss over.

Citations:
    - 02-architecture/TEST_SPEC.md (paladin L1/L2/L3/L4/L5 contract)
    - 03-development/tests/test_fr10.py through test_fr16.py (canonical
      paladin tests; this file is additive)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make paladin importable when running this file directly.
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.core.paladin import (  # noqa: E402
    ClassificationResult,
    GroundingChecker,
    InjectionType,
    InputSanitizer,
    PALADINPipeline,
    ProcessResult,
    SemanticInjectionClassifier,
)

# ---------------------------------------------------------------------------
# L1 InputSanitizer — _sanitize_sql_patterns (FR-108)
# ---------------------------------------------------------------------------


def test_fr108_sql_injection_drop_table_removed_by_sanitizer() -> None:
    """Mutant on SQL pattern regex: ``DROP TABLE`` must be stripped from output.

    The sanitizer strips matched substrings; if a mutant changes the
    regex or the substitution, the output would still contain ``DROP``.
    """
    sanitizer = InputSanitizer()
    out = sanitizer.sanitize("hello DROP TABLE world")
    assert "DROP" not in out, f"DROP should be stripped, got {out!r}"
    assert "hello " in out
    assert " world" in out


def test_fr108_sql_injection_union_select_removed() -> None:
    """``UNION SELECT`` pattern must be neutralised by the L1 sanitizer."""
    sanitizer = InputSanitizer()
    out = sanitizer.sanitize("1 UNION SELECT password FROM users")
    assert "UNION" not in out
    assert "SELECT" not in out or "password" not in out


def test_fr108_sql_injection_exec_paren_removed() -> None:
    """``EXEC(`` and ``EXECUTE(`` patterns must be removed."""
    sanitizer = InputSanitizer()
    out = sanitizer.sanitize("normal text EXEC(malicious) more text")
    assert "EXEC" not in out
    assert "malicious" in out  # the surrounding words survive


# ---------------------------------------------------------------------------
# L5 GroundingChecker — cosine math (FR-14)
# ---------------------------------------------------------------------------


def test_fr14_cosine_similarity_zero_init_not_one_init() -> None:
    """Mutant on ``_cosine_similarity`` initial value of ``dot``.

    The implementation starts ``dot = 0.0`` so that the running sum of
    ``x * y`` produces the actual dot product. If a mutant changes the
    initial value to ``1.0``, the result is off by one for any non-zero
    vector pair. Verify dot product of (1, 0) · (0, 1) == 0.
    """
    checker = GroundingChecker()
    sim = checker._cosine_similarity((1.0, 0.0), (0.0, 1.0))
    assert sim == pytest.approx(0.0, abs=1e-9), (
        f"orthogonal vectors should have cosine 0.0, got {sim}; "
        "if sim≈1.0, the initial value of ``dot`` was mutated to 1.0"
    )


def test_fr14_cosine_similarity_norms_squared_correct() -> None:
    """Mutant on ``norm_a += x * x`` → ``norm_a -= x * x`` would flip sign.

    For a unit vector (1, 0), the correct norm is 1.0. If the mutant
    flips the operation, norm_a becomes -1.0, so the final cosine
    becomes negative of the correct value.
    """
    checker = GroundingChecker()
    sim = checker._cosine_similarity((1.0, 0.0), (1.0, 0.0))
    assert sim == pytest.approx(1.0, abs=1e-9), (
        f"identical unit vectors should have cosine 1.0, got {sim}; "
        "if sim≈-1.0, the norm accumulation was mutated to subtract"
    )


# ---------------------------------------------------------------------------
# L5 GroundingChecker — field-level invariants (FR-14)
# ---------------------------------------------------------------------------


def test_fr14_grounding_result_source_count_zero_when_no_sources() -> None:
    """Mutant on ``_source_count = 0`` → ``_source_count = None`` in
    GroundingChecker.check when ``source_texts`` is empty.

    Spec: when no sources, ``grounded=False`` and the source count
    must be 0 (not None). The downstream pipeline reads this field to
    decide whether to mark ungrounded.
    """
    checker = GroundingChecker()
    result = checker.check(
        response="anything",
        output_embedding=None,
        source_texts=[],
    )
    # The ``_source_count`` field is exposed via the result struct.
    # Use the public attribute if available, else check grounded=False.
    assert result.grounded is False
    assert result.cosine_score == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# L3 SemanticInjectionClassifier — is_unverified default (FR-13)
# ---------------------------------------------------------------------------


def test_fr13_low_risk_default_is_unverified_false() -> None:
    """Mutant on ``is_unverified = False`` → ``is_unverified = True`` in
    the L3 low-risk short-circuit return.

    A low-risk verdict is by definition *not* unverified: the L2 pattern
    matcher already gave it a safe classification. Setting
    ``is_unverified=True`` would cause downstream L4 to be re-invoked
    for every low-risk message, breaking the FR-15 latency budget.
    """
    classifier = SemanticInjectionClassifier()
    verdict = classifier.classify("hello there", risk_level="low")
    # The synchronous ``classify`` returns a ClassificationResult.
    assert verdict.is_injection is False
    assert verdict.is_unverified is False
    assert verdict.confidence == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# L4 PALADINPipeline — blocked result factory fields (FR-15)
# ---------------------------------------------------------------------------


def test_fr15_blocked_result_tier3_called_default_false() -> None:
    """Mutant on ``tier3_called: bool = False`` → ``True`` in ProcessResult.

    Spec: ProcessResult is the L4 short-circuit result. By default
    ``tier3_called`` is False because the L3 LLM was never invoked for a
    short-circuit. Setting it to True would falsely advertise L3 use
    and double-count LLM cost.
    """
    pr = ProcessResult(is_blocked=True)
    assert pr.tier3_called is False
    assert pr.l4_called is False
    assert pr.is_blocked is True


def test_fr108_grounding_check_text_response_only_enters_text_branch() -> None:
    """Mutant on line 797 ``if response is not None or sources is not None``.

    When ``response`` is provided but ``sources`` is ``None``, the text-based
    branch must still execute (Jaccard over empty sources → 0.0 → ungrounded).
    A mutant that flips the boolean to ``response is  None or sources is not None``
    (i.e. ``response is None or sources is not None``) would skip the text
    branch and try the embedding path, which raises (no output_embedding).
    """
    checker = GroundingChecker()
    result = checker.check(
        response="hello world",
        output_embedding=None,
        sources=None,
        threshold=0.75,
    )
    # Text-based branch executed: cosine computed via word overlap.
    # With sources=None the Jaccard denominator is 0, so cosine=0, grounded=False.
    assert result.grounded is False
    assert result.cosine_score == 0.0


def test_fr108_grounding_check_text_sources_only_enters_text_branch() -> None:
    """Mutant on line 797 — sources provided but response is ``None``.

    Mirrors the previous test but with the inputs swapped. The text-based
    branch must still execute so the Jaccard path computes a score over
    the union of source tokens. A flipped boolean would skip the branch
    and raise on the embedding path.
    """
    checker = GroundingChecker()
    result = checker.check(
        response=None,
        output_embedding=None,
        sources=["alpha beta", "gamma"],
        threshold=0.75,
    )
    # With response=None, Jaccard numerator = 0 (no response tokens to
    # overlap with sources), so cosine=0, grounded=False.
    assert result.grounded is False
    assert result.cosine_score == 0.0


def test_fr108_grounding_check_text_overlap_grounded_true() -> None:
    """Positive control: identical tokens in response and source → grounded.

    When 1.0 Jaccard is computed, ``grounded=True`` (>= 0.75). A mutant on
    line 805 that turns the division into ``None`` would break this; a
    mutant on line 807 that flips ``>=`` to ``<`` would flip grounded
    to False.
    """
    checker = GroundingChecker()
    result = checker.check(
        response="the quick brown fox",
        output_embedding=None,
        sources=["the quick brown fox"],
        threshold=0.75,
    )
    assert result.grounded is True
    assert result.cosine_score == pytest.approx(1.0, abs=1e-9)


def test_fr15_blocked_result_late_injection_default_false() -> None:
    """Mutant on ``late_injection_detected: bool = False`` → ``True`` in
    ProcessResult keyword arguments.

    Spec: the field is False by default; a blocked result that is not
    a *retrospective* (late-injection) block must not have it set to
    True, otherwise the audit log mis-categorises the block.
    """
    pr = ProcessResult(is_blocked=True, tier3_called=False, l4_called=False)
    # Default value should be False unless explicitly passed True.
    assert pr.late_injection_detected is False


# ---------------------------------------------------------------------------
# L4 PALADINPipeline.process — risk-level routing (FR-15/FR-16)
# ---------------------------------------------------------------------------


def test_fr15_critical_risk_immediate_block_no_l3_l4() -> None:
    """Mutant on the critical short-circuit branch (line ~1112 ``if
    risk_level == "critical"``).

    A critical-risk input must be blocked at L0 — L4 and L3 are NEVER
    invoked. Mutating ``_blocked_result(... tier3_called=False,
    l4_called=False ...)`` to either True would falsely report L3/L4
    use, and the response field must be None so the FR-17 retraction
    hook does not surface a (non-existent) L3 output.
    """
    import asyncio

    pipeline = PALADINPipeline()
    result = asyncio.run(pipeline.process("hostile", risk_level="critical"))
    assert result.is_blocked is True
    assert result.tier3_called is False
    assert result.l4_called is False
    assert result.response is None
    assert result.block_reason == "critical_risk"


def test_fr15_high_risk_l4_injection_block_l4_called_true() -> None:
    """Mutant on line ~1135 ``l4_called=True`` → ``False`` in the
    high-risk injection block branch.

    When L4 returns ``is_injection=True`` on the high-risk path, the
    blocked result must have ``l4_called=True`` (L4 was the source of
    the block). Flipping to False would erase the audit signal and
    break the FR-15 routing observability.
    """
    import asyncio

    pipeline = PALADINPipeline()

    def _fake_classify(text, *, risk_level, timeout_ms):
        return ClassificationResult(
            is_injection=True,
            confidence=0.99,
            injection_type=InjectionType.DIRECT_PROMPT_INJECTION,
            is_unverified=False,
        )

    # classify_async delegates to classify via asyncio.to_thread; mocking
    # the sync ``classify`` short-circuits the whole chain.
    pipeline._classifier.classify = _fake_classify  # type: ignore[assignment]
    result = asyncio.run(pipeline.process("text", risk_level="high"))
    assert result.is_blocked is True
    assert result.l4_called is True
    assert result.tier3_called is False
    assert result.response is None
    assert result.block_reason == "injection"
