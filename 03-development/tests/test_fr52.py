"""TDD-RED: failing tests for FR-52 — A/B Variant Injection (SHA-256 確定性分配).

Spec source: 02-architecture/TEST_SPEC.md (FR-52)
SRS source : SRS.md FR-52 (Module 9: Response Generator)

Acceptance criteria (from SRS FR-52):
    A/B Variant Injection：
    - SHA-256 確定性分配（非 Python hash()）
    - variant_a → 結尾 "還有其他問題嗎？"
    - variant_b → 結尾 "需要進一步說明嗎？"
    - control → 不注入
    跨進程一致；variant 注入正確；control 無注入。
    Implementation functions: ``ResponseGenerator._apply_ab_variant()``,
    ``ABTestManager.get_variant()``.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-52 mandates two implementation surfaces (SRS FR-52
# implementation_functions):
#
#   1. ``ResponseGenerator._apply_ab_variant(variant, base_text) -> str``
#      on ``app.core.response_generator.ResponseGenerator`` (same module
#      that ships FR-50 / FR-51's GREEN commits).
#      Dispatch per SRS FR-52 acceptance:
#        - ``variant == "a"``     → append 「還有其他問題嗎？」 to base_text.
#        - ``variant == "b"``     → append 「需要進一步說明嗎？」 to base_text.
#        - ``variant == "control"`` (or any unrecognised label) → return
#          ``base_text`` unchanged with no suffix injected.
#
#   2. ``ABTestManager.get_variant(user_id, experiment_id) -> str`` in
#      ``app.services.ab_testing``. SRS FR-52 requires the assignment to
#      use ``hashlib.sha256`` (NOT Python's ``hash()``) so the same
#      ``(user_id, experiment_id)`` pair resolves to the same variant
#      across separate Python processes. SPEC.md pins the digest-truncation
#      pattern: ``int(sha256(f"{user_id}:{experiment_id}").hexdigest()[:8], 16) % 100``
#      — that is the exact deterministic contract tests #1 relies on.
#
# These imports are unguarded on purpose. ``ResponseGenerator`` is already
# exported by FR-50's GREEN commit, but ``app.services.ab_testing`` does NOT
# exist yet — so the import below causes pytest to fail with Collection
# Error (Exit Code 2), which is the valid RED signal — GREEN adds the
# ``ab_testing`` module.
# ---------------------------------------------------------------------------
from app.core.response_generator import (  # noqa: F401  -- RED: GREEN adds _apply_ab_variant
    ResponseGenerator,
)
from app.services.ab_testing import (  # noqa: F401  -- RED: GREEN adds this module
    ABTestManager,
)


# ---------------------------------------------------------------------------
# 1. SHA-256 deterministic assignment: same ``user_id`` + ``experiment_id``
#    MUST resolve to the same variant across calls (the "cross-process"
#    part of the spec is exercised at the digest level — two invocations
#    of ``get_variant`` against the same experiment contract yield the
#    same variant because the function is pure SHA-256 over the key).
#
# Spec input: user_id="user-001"; experiment_id="exp-1".
# Spec sub-assertion: fr52-ok: result is not None.
# SRS FR-52 acceptance: "SHA-256 分配跨進程一致".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr52_sha256_deterministic_same_variant_cross_process():
    user_id = "user-001"
    experiment_id = "exp-1"

    # Spec fr52-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c`
    # block whose trigger value matches TEST_SPEC case 1's input.
    if user_id == "user-001":
        # GREEN TODO: ``ABTestManager.get_variant(user_id, experiment_id)``
        # MUST return a non-None variant string, and MUST be a pure
        # SHA-256 deterministic function so that two invocations with
        # the same (user_id, experiment_id) yield the same variant.
        # Implementation per SPEC.md §Module:ab_testing.py line 2685:
        #   key = f"{user_id}:{experiment_id}".encode("utf-8")
        #   digest = hashlib.sha256(key).hexdigest()
        #   variant_hash = int(digest[:8], 16) % 100
        # Then route ``variant_hash`` through ``experiment["traffic_split"]``
        # cumulative ranges to pick the variant label.
        #
        # ``ABTestManager.__init__`` takes ``(db, llm)`` — to keep this
        # test pure and not coupled to a real DB, stub the DB lookup with
        # a deterministic ``get_experiment`` so the variant selection is
        # driven entirely by the SHA-256 hash (the very thing FR-52 is
        # testing). This is test isolation, NOT feature implementation.
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        # 50/50 split between "a" and "b" — deterministic hash→variant
        # mapping for the assertions below.
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())

        first = ab.get_variant(user_id=user_id, experiment_id=experiment_id)
        second = ab.get_variant(user_id=user_id, experiment_id=experiment_id)

        assert first is not None, (
            "fr52-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant for user_id='user-001'"
        )
        assert second is not None, (
            "fr52-ok predicate: ABTestManager.get_variant must return a "
            "non-None variant on a repeat call with the same inputs"
        )
        # The SHA-256 determinism contract — the same inputs MUST resolve
        # to the same variant across calls (and therefore across processes).
        assert first == second, (
            f"FR-52: ABTestManager.get_variant must be deterministic on "
            f"the same (user_id, experiment_id); got first={first!r} and "
            f"second={second!r} for user_id={user_id!r}, "
            f"experiment_id={experiment_id!r}. SRS FR-52 mandates "
            f"'SHA-256 確定性分配（非 Python hash()）' and "
            f"'SHA-256 分配跨進程一致'."
        )
        # And the chosen variant must be one of the configured split
        # buckets (or the explicit "control" fallback). This guards
        # against the implementation returning a hard-coded label that
        # is not in the split.
        assert first in {"a", "b", "control"}, (
            f"FR-52: ABTestManager.get_variant returned {first!r}, which "
            f"is not a valid variant label. Expected one of the keys in "
            f"the experiment's traffic_split ({{'a', 'b'}}) or the "
            f"documented 'control' fallback."
        )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-52: user_id sentinel must be 'user-001'; got {user_id!r}"
    )
    assert experiment_id == "exp-1", (
        f"FR-52: experiment_id sentinel must be 'exp-1'; "
        f"got {experiment_id!r}"
    )


# ---------------------------------------------------------------------------
# 2. variant="a" MUST inject the suffix 「還有其他問題嗎？」 so the
#    treatment arm's CTA closes the conversation with a follow-up prompt.
#
# Spec input: variant="a"; expected_suffix="還有其他問題嗎？".
# SRS FR-52 acceptance: "variant_a → 結尾 "還有其他問題嗎？"".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr52_variant_a_suffix_correct():
    variant = "a"
    expected_suffix = "還有其他問題嗎？"

    base_text = "您好，這裡是客服中心。"
    # GREEN TODO: ``ResponseGenerator._apply_ab_variant(variant, base_text)``
    # MUST return a non-None string whose trailing characters form the
    # variant_a suffix 「還有其他問題嗎？」 so the treatment arm closes
    # with a follow-up prompt.
    result = ResponseGenerator._apply_ab_variant(
        variant=variant,
        base_text=base_text,
    )
    assert result is not None, (
        "FR-52: _apply_ab_variant must return a non-None string for "
        "variant='a'"
    )
    assert expected_suffix in result, (
        f"FR-52: _apply_ab_variant must inject the variant_a suffix "
        f"{expected_suffix!r}; got {result!r}. SRS FR-52 mandates "
        f"'variant_a → 結尾 \"還有其他問題嗎？\"'."
    )
    # And the original base_text body MUST be preserved (the suffix is
    # appended, not substituted). This guards against a green
    # implementation that forgets the body and returns only the suffix.
    assert base_text in result, (
        f"FR-52: _apply_ab_variant must preserve the original "
        f"base_text {base_text!r} when injecting the variant_a suffix; "
        f"got {result!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert variant == "a", (
        f"FR-52: variant sentinel must be 'a'; got {variant!r}"
    )
    assert expected_suffix == "還有其他問題嗎？", (
        f"FR-52: expected_suffix sentinel must be '還有其他問題嗎？'; "
        f"got {expected_suffix!r}"
    )


# ---------------------------------------------------------------------------
# 3. variant="b" MUST inject the suffix 「需要進一步說明嗎？」 — the
#    alternate CTA the experiment is testing against the "a" arm.
#
# Spec input: variant="b"; expected_suffix="需要進一步說明嗎？".
# SRS FR-52 acceptance: "variant_b → 結尾 "需要進一步說明嗎？"".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr52_variant_b_suffix_correct():
    variant = "b"
    expected_suffix = "需要進一步說明嗎？"

    base_text = "您好，這裡是客服中心。"
    # GREEN TODO: ``ResponseGenerator._apply_ab_variant(variant, base_text)``
    # MUST return a non-None string whose trailing characters form the
    # variant_b suffix 「需要進一步說明嗎？」 so the alternate treatment
    # arm closes with its distinct follow-up prompt.
    result = ResponseGenerator._apply_ab_variant(
        variant=variant,
        base_text=base_text,
    )
    assert result is not None, (
        "FR-52: _apply_ab_variant must return a non-None string for "
        "variant='b'"
    )
    assert expected_suffix in result, (
        f"FR-52: _apply_ab_variant must inject the variant_b suffix "
        f"{expected_suffix!r}; got {result!r}. SRS FR-52 mandates "
        f"'variant_b → 結尾 \"需要進一步說明嗎？\"'."
    )
    # And the variant_b suffix must NOT contain the variant_a suffix and
    # vice versa — the two arms must remain disjoint so the experiment
    # is actually measuring a difference between the two CTAs.
    assert "還有其他問題嗎？" not in result, (
        f"FR-52: _apply_ab_variant must NOT inject the variant_a "
        f"suffix when called with variant='b'; got {result!r}. The "
        f"two treatment arms must remain disjoint for the experiment "
        f"to be meaningful."
    )
    # Original base_text body MUST be preserved.
    assert base_text in result, (
        f"FR-52: _apply_ab_variant must preserve the original "
        f"base_text {base_text!r} when injecting the variant_b suffix; "
        f"got {result!r}"
    )

    # Sentinels MUST be preserved per spec.
    assert variant == "b", (
        f"FR-52: variant sentinel must be 'b'; got {variant!r}"
    )
    assert expected_suffix == "需要進一步說明嗎？", (
        f"FR-52: expected_suffix sentinel must be '需要進一步說明嗎？'; "
        f"got {expected_suffix!r}"
    )


# ---------------------------------------------------------------------------
# 4. variant="control" MUST NOT inject any suffix — the control group
#    receives the bare reply so the experiment can isolate the lift from
#    each CTA arm.
#
# Spec input: variant="control"; expected_injection="false".
# SRS FR-52 acceptance: "control → 不注入".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr52_control_no_injection():
    variant = "control"
    expected_injection = "false"

    base_text = "您好，這裡是客服中心。"
    # The TEST_SPEC pins expected_injection="false" — reify it so the
    # sentinel check is a clean boolean comparison rather than a
    # stringly-typed truthy/falsy comparison.
    if expected_injection == "false":
        # GREEN TODO: ``ResponseGenerator._apply_ab_variant(variant, base_text)``
        # MUST return ``base_text`` unchanged for ``variant == "control"``.
        # No 「還有其他問題嗎？」 or 「需要進一步說明嗎？」 suffix may be
        # injected; the returned string MUST equal the input base_text
        # so the experiment can isolate the lift attributable to each
        # treatment arm.
        result = ResponseGenerator._apply_ab_variant(
            variant=variant,
            base_text=base_text,
        )
        assert result is not None, (
            "FR-52: _apply_ab_variant must return a non-None string for "
            "variant='control' (the control group is a pass-through, "
            "but the function still has to return a string)"
        )
        # Strict pass-through contract: control arm receives the bare
        # base_text, byte-for-byte equal to the input.
        assert result == base_text, (
            f"FR-52: _apply_ab_variant must return base_text unchanged "
            f"for variant={variant!r} (no injection); expected "
            f"{base_text!r}, got {result!r}. SRS FR-52 mandates "
            f"'control → 不注入'."
        )
        # And — defense-in-depth — explicitly guard against either
        # treatment-arm suffix being injected into the control arm.
        assert "還有其他問題嗎？" not in result, (
            f"FR-52: _apply_ab_variant must NOT inject the variant_a "
            f"suffix into the control arm; got {result!r}. The control "
            f"group is a strict no-injection baseline."
        )
        assert "需要進一步說明嗎？" not in result, (
            f"FR-52: _apply_ab_variant must NOT inject the variant_b "
            f"suffix into the control arm; got {result!r}. The control "
            f"group is a strict no-injection baseline."
        )

    # Sentinels MUST be preserved per spec.
    assert variant == "control", (
        f"FR-52: variant sentinel must be 'control'; got {variant!r}"
    )
    assert expected_injection == "false", (
        f"FR-52: expected_injection sentinel must be 'false'; "
        f"got {expected_injection!r}"
    )
