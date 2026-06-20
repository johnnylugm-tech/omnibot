"""[FR-82] Complete database schema descriptor (20 tables + HNSW + GIN tsvector).

Pure-data schema spec for the FR-82 Data Layer (SRS Module 18). The unit
tests introspect the module-level constants and the ``DatabaseSchema``
facade to verify the table list, FK graph, and index specs without
spinning up Postgres or pgvector.

[FR-82] The 20 tables and their FK edges form the relational core of
       omnibot. ``knowledge_chunks`` carries both a pgvector HNSW index
       (used by FR-27/FR-29 ANN search) and a GIN tsvector full-text
       index (used by FR-99 ``level_embedding_down`` degradation path).

Citations:
- SRS.md FR-82 (Module 18: Data Layer, description line 90, spec block
  lines 749-770 — 20 tables, FK constraints, HNSW + GIN tsvector indexes)
- SRS.md FR-29 (HNSW m=16 / ef_construction=64 / vector_cosine_ops,
  lines 621-626)
- SRS.md FR-99 (level_embedding_down tsvector fallback, line 195)
- 02-architecture/TEST_SPEC.md FR-82 (4 cases: 20 tables, FK validation,
  HNSW index, GIN tsvector index)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FKConstraintSpec:
    """[FR-82] One foreign-key edge from ``child_table.column`` to
    ``parent_table.column``.

    The unit test introspects ``child_table`` / ``parent_table`` to
    verify every FK edge in the schema's referential-integrity graph
    points to a parent table that actually exists in the 20-table set.
    """

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class HNSWIndexSpec:
    """[FR-82/FR-29] HNSW vector index specification for ``knowledge_chunks``.

    Defaults ``m=16`` and ``ef_construction=64`` are inherited from
    FR-29; ``ops="vector_cosine_ops"`` is the pgvector operator class
    required by FR-27 Tier-2 cosine-distance ANN search.
    """

    table: str
    column: str
    ops: str  # FR-82 / FR-29: "vector_cosine_ops"
    m: int  # FR-29: 16
    ef_construction: int  # FR-29: 64


@dataclass(frozen=True)
class GINIndexSpec:
    """[FR-82/FR-99] GIN tsvector full-text-search index specification.

    ``expression`` MUST reference ``to_tsvector('simple', content)``
    verbatim so the FR-99 ``level_embedding_down`` tsvector fallback
    (``WHERE to_tsvector('simple', content) @@ plainto_tsquery(...)``)
    finds the index.
    """

    table: str
    column: str
    expression: str  # FR-82: to_tsvector('simple', content)


# [FR-82] Canonical 20-table list (SRS Module 18). Order is irrelevant
# (frozenset), but the names are exact and must not be aliased — the
# test cross-checks against the same canonical set.
EXPECTED_TABLES: frozenset[str] = frozenset({
    "users",
    "conversations",
    "messages",
    "knowledge_base",
    "knowledge_chunks",
    "platform_configs",
    "escalation_queue",
    "user_feedback",
    "security_logs",
    "emotion_history",
    "edge_cases",
    "pii_vault",
    "roles",
    "role_assignments",
    "pii_audit_log",
    "experiments",
    "experiment_results",
    "retry_log",
    "encryption_config",
    "schema_migrations",
})

# [FR-82] Foreign-key graph for the 20 tables. Every child table listed
# here is a real table in ``EXPECTED_TABLES`` and every parent_table
# referenced is also in ``EXPECTED_TABLES`` (verified by the unit test).
FK_CONSTRAINTS: dict[str, list[FKConstraintSpec]] = {
    "conversations": [
        FKConstraintSpec("conversations", "user_id", "users", "id"),
    ],
    "messages": [
        FKConstraintSpec("messages", "conversation_id", "conversations", "id"),
    ],
    "knowledge_chunks": [
        FKConstraintSpec(
            "knowledge_chunks", "knowledge_base_id", "knowledge_base", "id"
        ),
    ],
    "escalation_queue": [
        FKConstraintSpec(
            "escalation_queue", "conversation_id", "conversations", "id"
        ),
    ],
    "user_feedback": [
        FKConstraintSpec(
            "user_feedback", "conversation_id", "conversations", "id"
        ),
    ],
    "role_assignments": [
        FKConstraintSpec("role_assignments", "role_id", "roles", "id"),
        FKConstraintSpec("role_assignments", "user_id", "users", "id"),
    ],
    "pii_audit_log": [
        FKConstraintSpec("pii_audit_log", "user_id", "users", "id"),
    ],
    "experiment_results": [
        FKConstraintSpec(
            "experiment_results", "experiment_id", "experiments", "id"
        ),
    ],
}

# [FR-82/FR-29] HNSW index on ``knowledge_chunks.embedding`` using
# pgvector ``vector_cosine_ops`` (m=16, ef_construction=64).
HNSW_INDEX_SPEC = HNSWIndexSpec(
    table="knowledge_chunks",
    column="embedding",
    ops="vector_cosine_ops",
    m=16,
    ef_construction=64,
)

# [FR-82/FR-99] GIN tsvector full-text-search index on
# ``knowledge_chunks.content`` for the embedding-down fallback.
GIN_TSVECTOR_INDEX_SPEC = GINIndexSpec(
    table="knowledge_chunks",
    column="content",
    expression="to_tsvector('simple', content)",
)


class DatabaseSchema:
    """[FR-82] Schema descriptor facade.

    Pure data — no live DB connection. Exposes the same four artefacts
    as the module-level constants so callers can pass around a single
    object instead of importing each constant individually.
    """

    tables = EXPECTED_TABLES
    fk_constraints = FK_CONSTRAINTS
    hnsw_index = HNSW_INDEX_SPEC
    gin_tsvector_index = GIN_TSVECTOR_INDEX_SPEC


__all__ = [
    "DatabaseSchema",
    "EXPECTED_TABLES",
    "FK_CONSTRAINTS",
    "FKConstraintSpec",
    "GIN_TSVECTOR_INDEX_SPEC",
    "GINIndexSpec",
    "HNSW_INDEX_SPEC",
    "HNSWIndexSpec",
]
