"""TDD-RED: failing tests for FR-105 — ODD SQL queries + judge sampling config.

Spec source: 02-architecture/TEST_SPEC.md (FR-105)
SRS source : SRS.md Module 26 (ODD SQL 分析)
SAD mapping: app.admin.odd_sql — "ODD SQL analytics queries (FR-105)"

Acceptance criteria (from SRS FR-105 / TEST_SPEC.md):
    - 10 ODD SQL queries execute correctly on staging
    - FCR calculation: scope_type='in_scope' only, within 30 days, non-NULL
    - Cost per tier: Tier 1=$0/Tier 2=$0.003/Tier 3=$0.009
    - Judge sampling default 0.20, valid range 0.01–1.0

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-105 resides in ``app.admin.odd_sql`` per SAD.md §2.2 line 853.
#
# The GREEN contract pinned by this spec:
#
#   ``ODDSqlRunner``
#     - __init__(db, environment: str) — accepts an injected DB connection
#       (dependency injection; no real sockets in unit tests).
#     - execute_all() -> dict[str, Any] — runs all 10 ODD SQL queries and
#       returns a dict mapping query name → result.
#     - build_fcr_query(scope_type: str, days: int) -> str — returns the
#       FCR SQL string with correct filters.
#     - calculate_cost(query_counts: dict[int, int]) -> dict — returns
#       total cost and per-tier cost breakdown.
#     - get_judge_sampling_config() -> dict — returns sample_rate and
#       valid_range.
#
#   ``TIER_COSTS``
#     - Module-level dict: {1: 0.0, 2: 0.003, 3: 0.009}
#
#   ``JUDGE_SAMPLE_RATE_DEFAULT``
#     - Module-level constant: 0.20
#     - Valid range [0.01, 1.0].
#
# These imports are unguarded on purpose. During the current RED step,
# pytest crashes with Collection Error (Exit Code 2) because
# ``app.admin.odd_sql`` does not exist yet — that is the valid RED signal.
# ---------------------------------------------------------------------------
from app.admin.odd_sql import (  # noqa: F401 -- RED: GREEN owns the names
    JUDGE_SAMPLE_RATE_DEFAULT,
    ODDSqlRunner,
    TIER_COSTS,
)


# ======================================================================
# Test cases — names match TEST_SPEC.md exactly
# ======================================================================


def test_fr105_all_sql_execute_on_staging():
    """All 10 ODD SQL queries execute on staging environment without error."""
    mock_db = MagicMock()
    runner = ODDSqlRunner(db=mock_db, environment="staging")

    results = runner.execute_all()

    assert results is not None, "execute_all() must return a result dict"
    assert len(results) == 10, (
        f"Expected 10 ODD SQL query results, got {len(results)}"
    )
    for name, result in results.items():
        assert result is not None, f"Query '{name}' returned None"


def test_fr105_fcr_query_in_scope_only():
    """FCR query must filter scope_type='in_scope' entries within 30 days."""
    runner = ODDSqlRunner(db=MagicMock(), environment="staging")

    fcr_sql = runner.build_fcr_query(scope_type="in_scope", days=30)

    # Must reference the scope_type column with value 'in_scope'
    assert "scope_type" in fcr_sql, (
        "FCR query must filter on scope_type column"
    )
    assert "'in_scope'" in fcr_sql or "= 'in_scope'" in fcr_sql, (
        "FCR query must restrict to scope_type = 'in_scope'"
    )
    # Must include a 30-day window constraint
    assert (
        "30" in fcr_sql
        and ("INTERVAL" in fcr_sql.upper() or "day" in fcr_sql.lower())
    ), "FCR query must include a 30-day time window"


def test_fr105_cost_per_tier_correct():
    """Monthly cost report uses correct per-tier pricing.

    Tier 1 = $0/query (free)
    Tier 2 = $0.003/query
    Tier 3 = $0.009/query
    """
    runner = ODDSqlRunner(db=MagicMock(), environment="staging")

    # Simulate query counts: 100 Tier-1, 50 Tier-2, 20 Tier-3
    query_counts = {1: 100, 2: 50, 3: 20}
    cost = runner.calculate_cost(query_counts)

    assert "total" in cost, "Cost result must include 'total' key"
    assert "by_tier" in cost, "Cost result must include 'by_tier' breakdown"

    # Tier 1: 100 * $0 = $0
    assert cost["by_tier"][1] == pytest.approx(0.0)
    # Tier 2: 50 * $0.003 = $0.15
    assert cost["by_tier"][2] == pytest.approx(0.15, rel=1e-6)
    # Tier 3: 20 * $0.009 = $0.18
    assert cost["by_tier"][3] == pytest.approx(0.18, rel=1e-6)
    # Total: 0 + 0.15 + 0.18 = 0.33
    assert cost["total"] == pytest.approx(0.33, rel=1e-6)


def test_fr105_judge_sample_rate_default_020():
    """Judge evaluation sampling rate defaults to 0.20 (20%).

    Valid range is 0.01 to 1.0 (configurable via admin API).
    Cost SQL must include judge_sample_rate column.
    """
    runner = ODDSqlRunner(db=MagicMock(), environment="staging")

    config = runner.get_judge_sampling_config()

    assert config["sample_rate"] == pytest.approx(0.20), (
        f"Default judge sample rate must be 0.20, got {config['sample_rate']}"
    )
    low, high = config["valid_range"]
    # Valid range is 0.01 to 1.0 inclusive
    assert low <= config["sample_rate"] <= high, (
        f"Sample rate {config['sample_rate']} must be within "
        f"valid range [{low}, {high}]"
    )
    assert low == pytest.approx(0.01), (
        f"Valid range lower bound must be 0.01, got {low}"
    )
    assert high == pytest.approx(1.0), (
        f"Valid range upper bound must be 1.0, got {high}"
    )
