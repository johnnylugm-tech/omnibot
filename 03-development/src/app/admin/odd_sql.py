"""[FR-105] ODD SQL analytics queries + judge sampling config.

Spec source: 02-architecture/TEST_SPEC.md (FR-105)
SRS source : SRS.md Module 26 (ODD SQL 分析)
SAD mapping: app.admin.odd_sql — "ODD SQL analytics queries (FR-105)"

Acceptance criteria:
    - 10 ODD SQL queries execute correctly on staging
    - FCR calculation: scope_type='in_scope' only, within 30 days, non-NULL
    - Cost per tier: Tier 1=$0/Tier 2=$0.003/Tier 3=$0.009
    - Judge sampling default 0.20, valid range 0.01-1.0

Citations:
    test_fr105.py L53-57  — canonical imports / public surface
    test_fr105.py L65-78  — FR-105 all 10 ODD SQL queries execute on staging
    test_fr105.py L80-97  — FR-105 FCR query in_scope only, 30-day window
    test_fr105.py L100-123 — FR-105 cost per tier correct
    test_fr105.py L126-150 — FR-105 judge sample rate default 0.20
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Module-level constants — pinned by test_fr105.py L53-57
# ---------------------------------------------------------------------------

TIER_COSTS: dict[int, float] = {1: 0.0, 2: 0.003, 3: 0.009}
JUDGE_SAMPLE_RATE_DEFAULT: float = 0.20

# ---------------------------------------------------------------------------
# Shared SQL filter fragments — de-duplicated across all 10 ODD queries
# ---------------------------------------------------------------------------

_IN_SCOPE = "scope_type = 'in_scope'"
_LAST_30_DAYS = "created_at >= NOW() - INTERVAL '30 days'"

# ---------------------------------------------------------------------------
# ODD SQL query definitions — the 10 queries required by FR-105
# ---------------------------------------------------------------------------

_ODD_SQL_QUERIES: dict[str, str] = {
    "odd_fcr_rate": f"""
        SELECT
            COUNT(*) FILTER (WHERE odd_resolved_on_first_contact = TRUE)::FLOAT
            / NULLIF(COUNT(*), 0) AS fcr_rate
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND {_LAST_30_DAYS}
    """,
    "odd_resolution_time_p50": f"""
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_time_seconds)
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND resolved_at IS NOT NULL
    """,
    "odd_resolution_time_p95": f"""
        SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_time_seconds)
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND resolved_at IS NOT NULL
    """,
    "odd_escalation_rate": f"""
        SELECT
            COUNT(*) FILTER (WHERE escalated = TRUE)::FLOAT
            / NULLIF(COUNT(*), 0) AS escalation_rate
        FROM odd_conversations
        WHERE {_IN_SCOPE}
    """,
    "odd_avg_sentiment": f"""
        SELECT AVG(sentiment_score) AS avg_sentiment
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND sentiment_score IS NOT NULL
    """,
    "odd_tier_distribution": f"""
        SELECT tier, COUNT(*) AS query_count
        FROM odd_queries
        WHERE {_IN_SCOPE}
        GROUP BY tier
        ORDER BY tier
    """,
    "odd_daily_volume": f"""
        SELECT DATE(created_at) AS day, COUNT(*) AS volume
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND {_LAST_30_DAYS}
        GROUP BY DATE(created_at)
        ORDER BY day
    """,
    "odd_top_intents": f"""
        SELECT intent, COUNT(*) AS count
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND intent IS NOT NULL
        GROUP BY intent
        ORDER BY count DESC
        LIMIT 10
    """,
    "odd_csat_distribution": f"""
        SELECT csat_score, COUNT(*) AS count
        FROM odd_conversations
        WHERE {_IN_SCOPE}
          AND csat_score IS NOT NULL
        GROUP BY csat_score
        ORDER BY csat_score
    """,
    "odd_judge_sample_queries": f"""
        SELECT *
        FROM odd_queries
        WHERE {_IN_SCOPE}
          AND {_LAST_30_DAYS}
        ORDER BY RANDOM()
        LIMIT (SELECT COUNT(*) * {JUDGE_SAMPLE_RATE_DEFAULT}
               FROM odd_queries
               WHERE {_IN_SCOPE}
                 AND {_LAST_30_DAYS})
    """,
}


class ODDSqlRunner:
    """Runs ODD SQL analytics queries against an injected database connection.

    Accepts dependency-injected ``db`` (no real sockets in unit tests).
    """

    def __init__(self, db: Any, environment: str) -> None:
        self.db = db
        self.environment = environment

    def execute_all(self) -> dict[str, Any]:
        """Execute all 10 ODD SQL queries and return results keyed by query name."""
        results: dict[str, Any] = {}
        for name, sql in _ODD_SQL_QUERIES.items():
            results[name] = self.db.execute(sql)
        return results

    def build_fcr_query(self, scope_type: str, days: int) -> tuple[str, dict[str, Any]]:
        """Return the FCR (First Contact Resolution) SQL string.

        Filters on the given ``scope_type`` column value and includes a
        ``days``-day time window via INTERVAL.
        """
        return (
            """SELECT
    COUNT(*) FILTER (WHERE fcr_achieved = TRUE)::FLOAT
    / NULLIF(COUNT(*), 0) AS fcr_rate
FROM odd_conversations
WHERE scope_type = :scope_type
  AND created_at >= NOW() - INTERVAL '1 day' * :days
  AND fcr_achieved IS NOT NULL""",
            {"scope_type": scope_type, "days": days},
        )

    def calculate_cost(self, query_counts: dict[int, int]) -> dict[str, Any]:
        """Return total cost and per-tier cost breakdown.

        Args:
            query_counts: Mapping of tier number → number of queries executed.
        """
        by_tier: dict[int, float] = {}
        total = 0.0
        for tier, count in query_counts.items():
            rate = TIER_COSTS.get(tier, 0.0)
            tier_cost = round(count * rate, 6)
            by_tier[tier] = tier_cost
            total += tier_cost
        return {"total": round(total, 6), "by_tier": by_tier}

    def get_judge_sampling_config(self) -> dict[str, Any]:
        """Return the judge sampling configuration.

        Returns:
            dict with ``sample_rate`` (default 0.20) and ``valid_range``
            (0.01 to 1.0 inclusive).
        """
        return {
            "sample_rate": JUDGE_SAMPLE_RATE_DEFAULT,
            "valid_range": (0.01, 1.0),
        }
