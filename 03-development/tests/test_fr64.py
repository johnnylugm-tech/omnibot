"""TDD-RED: failing tests for FR-64 — auto_promote 自動勝出判定.

Spec source: 02-architecture/TEST_SPEC.md (FR-64)
SRS source : SRS.md FR-64 (Module 13: A/B Testing)
SAD mapping: app.services.ab_testing — "A/B test manager (FR-63–64)"

Acceptance criteria (from SRS FR-64 / TEST_SPEC.md):
    ABTestManager.auto_promote(experiment_id, results):
    - Minimum sample size 100; below 100 → return None (no judgement).
    - If metric diff between best and second-best variant ≥ 0.05
      AND total sample size ≥ 100 → best variant wins, experiment
      status is set to "completed".
    - If metric diff < 0.05 → no promotion (even at sufficient
      sample size); experiment remains in its prior status.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-64 mandates ``ABTestManager.auto_promote(experiment_id, results)``
# in ``app.services.ab_testing`` (SAD.md §2.2 / line 811, FR-64):
#
#     FR-64: "ABTestManager.auto_promote()"
#
# The GREEN contract pinned by this spec:
#
#   - ``ABTestManager`` MUST expose ``auto_promote(experiment_id, results)``
#     returning either ``None`` (insufficient sample) or the promoted
#     variant label (str).
#   - The promotion threshold is metric diff ≥ 0.05 AND sample size ≥ 100.
#   - On promotion, the experiment's status MUST be set to "completed".
#   - When diff < 0.05 (even at sufficient sample), no promotion happens
#     and status is left untouched.
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because
# ``auto_promote`` is not yet implemented on ABTestManager — that is
# the valid RED signal.
# ---------------------------------------------------------------------------
from app.services.ab_testing import (
    ABTestManager,
)


# ---------------------------------------------------------------------------
# 1. Below-minimum sample size guard: if the total number of observations
#    across all variants is below 100, ``auto_promote`` MUST return None
#    (no winner is declared when there is not enough evidence).
#
# Spec input: sample_size="80"; expected_result="None".
# Spec sub-assertion: fr64-ok: result is not None — BUT for the
# below-minimum branch the spec explicitly pins the return value as
# ``None`` (Q3 boundary), so the predicate is ``result is None``.
# SRS FR-64 acceptance: "樣本 < 100 不判定勝負".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr64_sample_below_100_returns_none():
    sample_size = "80"
    expected_result = "None"

    if sample_size == "80" and expected_result == "None":
        # GREEN TODO: ``ABTestManager.auto_promote(experiment_id, results)``
        # MUST return ``None`` when the total sample size (sum of
        # observations across all variants) is below 100, regardless of
        # the metric diff. This is the minimum-sample-size guard
        # mandated by SRS FR-64: "樣本 < 100 不判定勝負".
        #
        # Test isolation: stub the DB so the experiment lookup does not
        # touch real infra. The fixture provides 80 observations spread
        # across "a" (50) and "b" (30) — well below the 100 minimum.
        mock_db = MagicMock()
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
            "status": "running",
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())

        # results: {variant_label: [list of metric scores]}
        results = {
            "a": [0.80] * 50,
            "b": [0.74] * 30,  # 0.06 raw diff — would otherwise promote.
        }
        promoted = ab.auto_promote(experiment_id="exp-1", results=results)

        # Boundary contract: total sample < 100 MUST short-circuit to None
        # BEFORE any diff comparison runs.
        assert promoted is None, (
            f"FR-64: ABTestManager.auto_promote must return None when "
            f"total sample size is {sample_size} (< 100 minimum), "
            f"regardless of metric diff. Got {promoted!r}. "
            f"SRS FR-64 mandates '樣本 < 100 不判定勝負'."
        )

    # Sentinels MUST be preserved per spec.
    assert sample_size == "80", (
        f"FR-64: sample_size sentinel must be '80'; got {sample_size!r}"
    )
    assert expected_result == "None", (
        f"FR-64: expected_result sentinel must be 'None'; "
        f"got {expected_result!r}"
    )


# ---------------------------------------------------------------------------
# 2. Happy path: when total sample size ≥ 100 AND the metric diff between
#    the best and the second-best variant is ≥ 0.05, ``auto_promote``
#    MUST promote the best-performing variant.
#
# Spec input: diff="0.06"; sample_size="150"; expected_promoted="true".
# Spec sub-assertion: fr64-ok: result is not None.
# SRS FR-64 acceptance: "差異 ≥ 0.05 且樣本足夠時自動結束實驗";
#                      "最佳 variant 勝出".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr64_diff_above_005_promotes_best_variant():
    diff = "0.06"
    sample_size = "150"
    expected_promoted = "true"

    if diff == "0.06" and sample_size == "150" and expected_promoted == "true":
        # GREEN TODO: ``ABTestManager.auto_promote(experiment_id, results)``
        # MUST return the variant label with the highest mean metric when
        # both (a) total sample size ≥ 100 and (b) max-mean minus second-
        # max-mean ≥ 0.05. The promoted label is returned; the experiment's
        # status side-effect is asserted in test_fr64_promoted_status_set_completed.
        #
        # Test isolation: stub the DB so the experiment lookup does not
        # touch real infra. The fixture provides 100 observations for
        # "a" (mean = 0.80) and 50 for "b" (mean = 0.74), giving a
        # diff of 0.06 — above the 0.05 threshold — and a total of
        # 150 — above the 100 minimum.
        mock_db = MagicMock()
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
            "status": "running",
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())

        results = {
            "a": [0.80] * 100,  # mean = 0.80
            "b": [0.74] * 50,   # mean = 0.74; diff = 0.06
        }
        promoted = ab.auto_promote(experiment_id="exp-1", results=results)

        # fr64-ok predicate: result is not None.
        assert promoted is not None, (
            "fr64-ok predicate: ABTestManager.auto_promote must return a "
            "non-None variant when sample ≥ 100 and diff ≥ 0.05."
        )
        # Best variant (a, mean 0.80) must win over second-best (b, mean 0.74).
        assert promoted == "a", (
            f"FR-64: ABTestManager.auto_promote must promote the "
            f"best-performing variant when diff ≥ 0.05. Expected 'a' "
            f"(mean 0.80), got {promoted!r}. SRS FR-64 mandates "
            f"'最佳 variant 勝出'."
        )

    # Sentinels MUST be preserved per spec.
    assert diff == "0.06", f"FR-64: diff sentinel must be '0.06'; got {diff!r}"
    assert sample_size == "150", (
        f"FR-64: sample_size sentinel must be '150'; got {sample_size!r}"
    )
    assert expected_promoted == "true", (
        f"FR-64: expected_promoted sentinel must be 'true'; "
        f"got {expected_promoted!r}"
    )


# ---------------------------------------------------------------------------
# 3. Side-effect contract: on successful promotion (diff ≥ 0.05 AND
#    sample ≥ 100), the experiment's status MUST be set to "completed".
#    This is the canonical "自動結束實驗" (auto-end experiment) marker
#    called out in SRS FR-64 acceptance.
#
# Spec input: diff="0.07"; expected_status="completed".
# Spec sub-assertion: fr64-ok: result is not None.
# SRS FR-64 acceptance: "差異 ≥ 0.05 且樣本足夠時自動結束實驗"
#                      + "實驗 status 設 'completed'".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr64_promoted_status_set_completed():
    diff = "0.07"
    expected_status = "completed"

    if diff == "0.07" and expected_status == "completed":
        # GREEN TODO: ``ABTestManager.auto_promote(experiment_id, results)``
        # MUST set ``experiment["status"] = "completed"`` on the experiment
        # record when promotion succeeds. The status side-effect is
        # observable via the DB layer (the manager either persists via
        # ``db.update_experiment_status(experiment_id, "completed")``
        # or mutates a fetched record that the caller is responsible
        # for persisting — either way, the test pins the END STATE).
        #
        # Test isolation: stub the DB so we can assert on the resulting
        # experiment record without touching real infra. The DB stub
        # returns a mutable dict that the GREEN implementation can
        # update in-place (via a side-effect on ``get_experiment``).
        from unittest.mock import MagicMock as MagicMockClass

        mock_db = MagicMockClass()
        experiment_record = {
            "traffic_split": {"a": 50, "b": 50},
            "status": "running",
        }

        def _fake_get_experiment(_exp_id):
            return experiment_record

        def _fake_update_experiment_status(_exp_id, new_status):
            experiment_record["status"] = new_status

        mock_db.get_experiment.side_effect = _fake_get_experiment
        mock_db.update_experiment_status.side_effect = (
            _fake_update_experiment_status
        )
        ab = ABTestManager(db=mock_db, llm=MagicMockClass())

        results = {
            "a": [0.85] * 80,  # mean = 0.85
            "b": [0.78] * 70,  # mean = 0.78; diff = 0.07
        }
        promoted = ab.auto_promote(experiment_id="exp-1", results=results)

        # fr64-ok predicate: result is not None.
        assert promoted is not None, (
            "fr64-ok predicate: ABTestManager.auto_promote must return a "
            "non-None variant when diff=0.07 (> 0.05) and sample=150."
        )
        # Side-effect contract: experiment.status MUST be "completed"
        # after a successful promotion. This is the "auto-end experiment"
        # marker in SRS FR-64 acceptance.
        #
        # The test accepts either implementation strategy:
        #   (a) GREEN mutates the fetched record in-place
        #       (caller is responsible for persisting) — then
        #       ``experiment_record["status"]`` reflects "completed".
        #   (b) GREEN calls ``db.update_experiment_status(...)`` to
        #       persist — then our ``_fake_update_experiment_status``
        #       helper has already updated the dict to "completed".
        # Both strategies leave the same end state, which is what
        # the test pins.
        assert experiment_record["status"] == expected_status, (
            f"FR-64: after auto_promote, experiment.status must be "
            f"{expected_status!r}; got {experiment_record['status']!r}. "
            f"SRS FR-64 mandates '實驗 status 設 completed'."
        )

    # Sentinels MUST be preserved per spec.
    assert diff == "0.07", f"FR-64: diff sentinel must be '0.07'; got {diff!r}"
    assert expected_status == "completed", (
        f"FR-64: expected_status sentinel must be 'completed'; "
        f"got {expected_status!r}"
    )


# ---------------------------------------------------------------------------
# 4. Below-threshold diff: when total sample size ≥ 100 BUT the metric
#    diff between the best and second-best variant is < 0.05,
#    ``auto_promote`` MUST NOT promote (returns None / no winner).
#    This is the "差異 < 0.05 不判定勝負" branch — insufficient
#    evidence to call a winner even at adequate sample size.
#
# Spec input: diff="0.03"; sample_size="150"; expected_promoted="false".
# Spec sub-assertion: fr64-ok: result is not None — BUT for the
# below-threshold branch the spec explicitly pins the result as
# not-promoted (Q3 boundary), so the predicate is ``promoted is None``.
# SRS FR-64 acceptance: "差異 ≥ 0.05 且樣本足夠時自動結束實驗" — the
# contrapositive is "diff < 0.05 → 不結束".
# Test type: boundary (Q3 derivation).
# ---------------------------------------------------------------------------
def test_fr64_diff_below_005_no_promotion():
    diff = "0.03"
    sample_size = "150"
    expected_promoted = "false"

    if diff == "0.03" and sample_size == "150" and expected_promoted == "false":
        # GREEN TODO: ``ABTestManager.auto_promote(experiment_id, results)``
        # MUST return ``None`` when total sample ≥ 100 BUT the metric
        # diff between the best and second-best variant is < 0.05.
        # Sample size alone is not enough — the diff threshold is the
        # promotion gate. SRS FR-64 acceptance: "差異 ≥ 0.05 且樣本足夠
        # 時自動結束實驗" — the < 0.05 branch is "不結束".
        #
        # Test isolation: stub the DB so the experiment lookup does not
        # touch real infra. The fixture provides 100 observations for
        # "a" (mean = 0.80) and 50 for "b" (mean = 0.77), giving a
        # diff of 0.03 — below the 0.05 threshold — and a total of
        # 150 — above the 100 minimum.
        mock_db = MagicMock()
        mock_db.get_experiment.return_value = {
            "traffic_split": {"a": 50, "b": 50},
            "status": "running",
        }
        ab = ABTestManager(db=mock_db, llm=MagicMock())

        results = {
            "a": [0.80] * 100,  # mean = 0.80
            "b": [0.77] * 50,   # mean = 0.77; diff = 0.03 (< 0.05)
        }
        promoted = ab.auto_promote(experiment_id="exp-1", results=results)

        # Diff < 0.05 → no promotion, even at sufficient sample size.
        assert promoted is None, (
            f"FR-64: ABTestManager.auto_promote must return None when "
            f"diff < 0.05 (got {diff}) even at sample={sample_size} "
            f"(≥ 100). Got {promoted!r}. SRS FR-64 acceptance: "
            f"'差異 ≥ 0.05 且樣本足夠時自動結束實驗' — the < 0.05 "
            f"branch does not end the experiment."
        )

    # Sentinels MUST be preserved per spec.
    assert diff == "0.03", f"FR-64: diff sentinel must be '0.03'; got {diff!r}"
    assert sample_size == "150", (
        f"FR-64: sample_size sentinel must be '150'; got {sample_size!r}"
    )
    assert expected_promoted == "false", (
        f"FR-64: expected_promoted sentinel must be 'false'; "
        f"got {expected_promoted!r}"
    )

# NFR coverage: NFR-29 (>=95% agentic tool success)
