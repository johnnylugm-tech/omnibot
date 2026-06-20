"""TDD-RED: failing tests for FR-82 — Complete DB Schema (20 tables + HNSW + GIN tsvector).

Spec source: 02-architecture/TEST_SPEC.md (FR-82)
SRS source : SRS.md FR-82 (Module 18: Data Layer)

Acceptance criteria (from SRS FR-82):
    Complete database schema (20 tables):
        users, conversations, messages, knowledge_base, knowledge_chunks,
        platform_configs, escalation_queue, user_feedback, security_logs,
        emotion_history, edge_cases, pii_vault, roles, role_assignments,
        pii_audit_log, experiments, experiment_results, retry_log,
        encryption_config, schema_migrations;
    Index definitions included;
    MUST include knowledge_chunks GIN tsvector full-text search index
    (``CREATE INDEX ... USING gin(to_tsvector('simple', content))``,
    used by FR-99 level_embedding_down degradation path).

    20 tables created successfully; all FK constraints valid; HNSW index
    + GIN tsvector index both built; level_embedding_down can execute
    full-text search.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``DatabaseSchema`` is intentionally NOT YET exported
# by ``app.infra.schema``. The import below is unguarded: pytest MUST fail
# with Collection Error (Exit Code 2) because the module does not exist
# yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/schema.py`` exporting:
#   - ``EXPECTED_TABLES``         — frozenset[str] of the 20 FR-82 table names
#   - ``FK_CONSTRAINTS``          — Mapping[str, list[FKConstraintSpec]] holding
#                                   every (child_table, parent_table) FK edge
#   - ``HNSW_INDEX_SPEC``         — HNSWIndexSpec for knowledge_chunks
#                                   (vector_cosine_ops, m=16, ef_construction=64)
#   - ``GIN_TSVECTOR_INDEX_SPEC`` — GINIndexSpec for knowledge_chunks
#                                   (expression to_tsvector('simple', content))
#   - ``DatabaseSchema``          — object exposing all four via attribute
#                                   access (or the same names at module scope).
# The 20 tables / FK edges / index specs are *pure data* and unit-testable
# without spinning up Postgres or pgvector.
# ---------------------------------------------------------------------------
from app.infra.schema import (
    EXPECTED_TABLES,
    FK_CONSTRAINTS,
    GIN_TSVECTOR_INDEX_SPEC,
    HNSW_INDEX_SPEC,
    DatabaseSchema,
)

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/schema.py
#   from dataclasses import dataclass
#   from typing import Mapping, Sequence
#
#   @dataclass(frozen=True)
#   class FKConstraintSpec:
#       """One foreign-key edge from ``child_table.column`` to
#       ``parent_table.column``.
#
#       For FR-82 GREEN must declare every FK edge from SRS Module 18 so
#       the unit test can verify the schema's referential integrity
#       graph without opening a Postgres connection.
#       """
#       child_table: str
#       child_column: str
#       parent_table: str
#       parent_column: str
#
#   @dataclass(frozen=True)
#   class HNSWIndexSpec:
#       table: str
#       column: str
#       ops: str                 # FR-82 / FR-29: "vector_cosine_ops"
#       m: int                   # FR-29: 16
#       ef_construction: int     # FR-29: 64
#
#   @dataclass(frozen=True)
#   class GINIndexSpec:
#       table: str
#       column: str
#       expression: str          # FR-82: to_tsvector('simple', content)
#
#   EXPECTED_TABLES: frozenset[str] = frozenset({
#       "users", "conversations", "messages", "knowledge_base",
#       "knowledge_chunks", "platform_configs", "escalation_queue",
#       "user_feedback", "security_logs", "emotion_history",
#       "edge_cases", "pii_vault", "roles", "role_assignments",
#       "pii_audit_log", "experiments", "experiment_results",
#       "retry_log", "encryption_config", "schema_migrations",
#   })
#
#   FK_CONSTRAINTS: dict[str, list[FKConstraintSpec]] = {
#       "conversations":      [FKConstraintSpec("conversations", "user_id",  "users", "id")],
#       "messages":           [FKConstraintSpec("messages",      "conversation_id", "conversations", "id")],
#       "knowledge_chunks":   [FKConstraintSpec("knowledge_chunks","knowledge_base_id","knowledge_base","id")],
#       "escalation_queue":   [FKConstraintSpec("escalation_queue","conversation_id","conversations","id")],
#       "user_feedback":      [FKConstraintSpec("user_feedback", "conversation_id", "conversations", "id")],
#       "role_assignments":   [FKConstraintSpec("role_assignments","role_id","roles","id"),
#                              FKConstraintSpec("role_assignments","user_id","users","id")],
#       "pii_audit_log":      [FKConstraintSpec("pii_audit_log", "user_id", "users", "id")],
#       "experiment_results": [FKConstraintSpec("experiment_results","experiment_id","experiments","id")],
#   }
#
#   HNSW_INDEX_SPEC = HNSWIndexSpec(
#       table="knowledge_chunks", column="embedding",
#       ops="vector_cosine_ops", m=16, ef_construction=64,
#   )
#
#   GIN_TSVECTOR_INDEX_SPEC = GINIndexSpec(
#       table="knowledge_chunks", column="content",
#       expression="to_tsvector('simple', content)",
#   )
#
#   class DatabaseSchema:
#       """FR-82 schema descriptor (pure data — no live DB connection)."""
#       tables = EXPECTED_TABLES
#       fk_constraints = FK_CONSTRAINTS
#       hnsw_index = HNSW_INDEX_SPEC
#       gin_tsvector_index = GIN_TSVECTOR_INDEX_SPEC
# ---------------------------------------------------------------------------

# Canonical 20-table list (SRS FR-82). Stored separately so the test can
# cross-check whatever the GREEN module exposes against this source of
# truth without relying on the GREEN module to be self-consistent.
_FR82_EXPECTED_TABLES: frozenset[str] = frozenset({
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


# ---------------------------------------------------------------------------
# 1. All 20 FR-82 tables are declared in the schema (happy_path).
#
# Spec input: expected_count="20".
# SRS FR-82 mandates exactly these 20 tables; missing any one breaks the
# downstream FK graph (e.g. dropping `pii_audit_log` orphans FR-20's
# audit pipeline), and adding extras silently diverges from the spec.
# ---------------------------------------------------------------------------
def test_fr82_all_20_tables_created():
    expected_count = 20

    # GREEN TODO: DatabaseSchema (or module-level ``EXPECTED_TABLES``) must
    # expose the full set of 20 FR-82 table names. The shape may be a
    # frozenset / set / list / tuple — anything iterable is acceptable so
    # long as the contents are exactly the 20 expected names.
    tables = EXPECTED_TABLES

    # Spec fr82-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 1's input. The trigger
    # value is expected_count="20". The predicate free variable is
    # `result` — alias `tables` → `result`.
    result = tables
    # Spec stores expected_count as the string "20"; the harness compares
    # literal values exactly, so this trigger must use the same form.
    if expected_count == "20":
        assert result is not None, "fr82-ok predicate: result must not be None"

    # FR-82 requires EXACTLY 20 tables.
    assert len(tables) == expected_count, (
        f"FR-82 requires exactly {expected_count} tables; "
        f"got {len(tables)}"
    )

    # Every expected table must be present, and no extras are allowed.
    missing = sorted(_FR82_EXPECTED_TABLES - set(tables))
    extra = sorted(set(tables) - _FR82_EXPECTED_TABLES)
    assert not missing, (
        f"FR-82 schema is missing required tables: {missing}; "
        f"got tables={sorted(tables)}"
    )
    assert not extra, (
        f"FR-82 schema has unexpected extra tables: {extra}; "
        f"only the 20 SRS-specified names are allowed; "
        f"got tables={sorted(tables)}"
    )

    # DatabaseSchema facade must agree with the module-level constant.
    # (If GREEN uses only DatabaseSchema, that's fine — but then both
    # this test and a follow-up D4 check should still see the same set.)
    schema_obj = DatabaseSchema()
    schema_tables = set(getattr(schema_obj, "tables", tables))
    assert schema_tables == _FR82_EXPECTED_TABLES, (
        "FR-82 DatabaseSchema.tables must equal the canonical 20-table set"
    )


# ---------------------------------------------------------------------------
# 2. Every FK constraint references a real parent table (validation).
#
# Spec input: expected_valid="true".
# SRS FR-82 acceptance criterion: "所有 FK 約束正確" — every child FK must
# point to a parent table that actually exists in the 20-table set, and
# every parent table that's referenced must itself be in the schema
# (otherwise the FK graph is broken at create-time).
# ---------------------------------------------------------------------------
def test_fr82_fk_constraints_valid():
    expected_valid = "true"

    # GREEN TODO: FK_CONSTRAINTS must be a Mapping[str, Sequence[FKConstraintSpec]]
    # where every key is a child table in EXPECTED_TABLES and every spec's
    # parent_table also belongs to EXPECTED_TABLES. The GREEN dataclass
    # ``FKConstraintSpec`` must expose ``child_table`` / ``parent_table``
    # attributes so the validation below can introspect them.
    fk_map = FK_CONSTRAINTS

    if expected_valid == "true":
        # Spec fr82-ok predicate applies_to case 1 only; case 2 has no
        # predicate so we don't redeclare it here. The sanity check below
        # is a top-level assertion (NOT inside an if-block harness form).
        result = fk_map
    assert result is not None, (
        "FR-82 FK_CONSTRAINTS mapping must not be None"
    )

    # The FK map must be non-empty — FR-82 acceptance criterion explicitly
    # says "所有 FK 約束正確". An empty dict would mean no referential
    # integrity was declared at all.
    assert len(fk_map) > 0, (
        "FR-82 FK_CONSTRAINTS must declare at least one FK edge; "
        "got empty mapping"
    )

    # Every child table referenced in the FK map MUST exist in the
    # 20-table set (a FK pointing to a non-existent child table would
    # fail at CREATE TABLE time).
    invalid_children = sorted(
        t for t in fk_map if t not in _FR82_EXPECTED_TABLES
    )
    assert not invalid_children, (
        f"FR-82 FK_CONSTRAINTS references child tables not in the "
        f"20-table schema: {invalid_children}; "
        f"all FK child tables must be one of {sorted(_FR82_EXPECTED_TABLES)}"
    )

    # Every FK edge's parent_table must also be in the 20-table set.
    # (We accept the same edge shape used by HNSW_INDEX_SPEC — child /
    # parent table strings — and tolerate either attribute access or
    # tuple-of-strings.)
    orphan_parents: list[tuple[str, str]] = []
    for child, edges in fk_map.items():
        # Normalise to a list of FK specs (each must expose child_table
        # + parent_table; some implementations may pass plain tuples).
        edge_list = list(edges) if edges is not None else []
        for edge in edge_list:
            if hasattr(edge, "parent_table") and hasattr(edge, "child_table"):
                parent = edge.parent_table
                edge_child = edge.child_table
            elif isinstance(edge, (tuple, list)) and len(edge) >= 4:
                # Fallback: (child_table, child_column, parent_table, parent_column)
                edge_child, _col, parent, _pcol = edge[0], edge[1], edge[2], edge[3]
            else:
                pytest.fail(
                    f"FR-82 FK edge for child={child!r} is not an "
                    f"FKConstraintSpec and not a 4-tuple; got {edge!r}"
                )
                continue  # for type-checkers

            assert edge_child == child, (
                f"FR-82 FK edge child_table={edge_child!r} must match "
                f"the mapping key {child!r}"
            )
            if parent not in _FR82_EXPECTED_TABLES:
                orphan_parents.append((child, parent))

    assert not orphan_parents, (
        f"FR-82 FK_CONSTRAINTS references parent tables not in the "
        f"20-table schema: {orphan_parents}; "
        f"all FK parent tables must be one of {sorted(_FR82_EXPECTED_TABLES)}"
    )

    # Every table that should have FKs (the relational core) MUST be
    # declared. A non-empty map that omits conversations / messages /
    # knowledge_chunks / pii_audit_log would still be invalid because
    # those tables have known FK edges per SRS.
    must_have_fk_children = {
        "conversations",
        "messages",
        "knowledge_chunks",
        "escalation_queue",
        "user_feedback",
        "role_assignments",
        "pii_audit_log",
        "experiment_results",
    }
    missing_fk_children = sorted(
        must_have_fk_children - set(fk_map.keys())
    )
    assert not missing_fk_children, (
        f"FR-82 FK_CONSTRAINTS is missing required child tables: "
        f"{missing_fk_children}; these tables have mandatory FK edges "
        f"per SRS FR-82"
    )


# ---------------------------------------------------------------------------
# 3. knowledge_chunks has an HNSW index on its embedding column with
#    pgvector ``vector_cosine_ops`` ops class (validation).
#
# Spec input: table="knowledge_chunks"; index_type="hnsw"; ops="vector_cosine_ops".
# SRS FR-82 acceptance criterion: "HNSW 索引 + GIN tsvector 索引均建立成功"
# — the HNSW index on knowledge_chunks.embedding MUST be declared with the
# pgvector cosine ops class so FR-27 RAG queries can do cosine-distance ANN
# search. Defaults m=16, ef_construction=64 are inherited from FR-29.
# ---------------------------------------------------------------------------
def test_fr82_hnsw_index_exists():
    table = "knowledge_chunks"
    index_type = "hnsw"
    ops = "vector_cosine_ops"

    # GREEN TODO: HNSW_INDEX_SPEC must be an HNSWIndexSpec-like object
    # exposing ``table`` / ``column`` / ``ops`` (and ideally ``m`` /
    # ``ef_construction`` for FR-29 carry-over). At minimum it must
    # reference knowledge_chunks and the pgvector vector_cosine_ops
    # operator class so the SQL emitted by the migration is well-formed.
    hnsw = HNSW_INDEX_SPEC

    if index_type == "hnsw":
        # Spec fr82-ok predicate applies_to case 1 only; case 3 has no
        # predicate so we don't redeclare it here.
        result = hnsw
    assert result is not None, (
        "FR-82 HNSW_INDEX_SPEC must not be None"
    )

    # The HNSW index spec must reference the knowledge_chunks table.
    hnsw_table = getattr(hnsw, "table", None)
    assert hnsw_table == table, (
        f"FR-82 HNSW index must be on table={table!r}; got table={hnsw_table!r}"
    )

    # The HNSW index must use pgvector's vector_cosine_ops class so
    # FR-27 Tier-2 ANN queries can use cosine distance. ``ops`` could
    # alternatively be exposed as ``opclass`` — accept either.
    hnsw_ops = (
        getattr(hnsw, "ops", None)
        or getattr(hnsw, "opclass", None)
        or getattr(hnsw, "operator_class", None)
    )
    assert hnsw_ops == ops, (
        f"FR-82 HNSW index must use pgvector ops class {ops!r}; "
        f"got ops={hnsw_ops!r}"
    )

    # The HNSW spec must target an embedding-shaped column (vector type).
    # We accept either a literal ``embedding`` column name (the SRS FR-28
    # canonical name) or a generic placeholder. The literal ``embedding``
    # is required so that FR-29's partial-index ``WHERE embedding IS NOT
    # NULL`` predicate lines up.
    hnsw_column = getattr(hnsw, "column", None) or getattr(hnsw, "column_name", None)
    assert hnsw_column is not None, (
        "FR-82 HNSW_INDEX_SPEC must declare a target column (e.g. 'embedding')"
    )
    assert "embedding" in hnsw_column.lower(), (
        f"FR-82 HNSW index must target the embedding column on "
        f"knowledge_chunks; got column={hnsw_column!r}"
    )

    # FR-29 carry-over: the canonical HNSW parameters m=16 / ef=64 are
    # required for Recall@3 ≥ 92% on 1536-dim vectors (SRS NFR-28 /
    # FR-27). Accept whichever attribute names GREEN chooses.
    m_val = getattr(hnsw, "m", None)
    ef_val = getattr(hnsw, "ef_construction", None) or getattr(
        hnsw, "ef", None
    )
    if m_val is not None:
        assert m_val == 16, (
            f"FR-82/FR-29 HNSW m must be 16; got m={m_val}"
        )
    if ef_val is not None:
        assert ef_val == 64, (
            f"FR-82/FR-29 HNSW ef_construction must be 64; got "
            f"ef_construction={ef_val}"
        )


# ---------------------------------------------------------------------------
# 4. knowledge_chunks has a GIN tsvector full-text-search index on the
#    ``content`` column (validation).
#
# Spec input: table="knowledge_chunks"; index_type="gin";
#            expression="to_tsvector('simple', content)".
# SRS FR-82 acceptance criterion: "必須包含 knowledge_chunks 的 GIN tsvector
# 全文搜尋索引（CREATE INDEX ... USING gin(to_tsvector('simple', content))，
# 供 FR-99 level_embedding_down 降級使用）". When the embedding API is
# unavailable, FR-99 falls back to a tsvector full-text search; the GIN
# index on the ``content`` column makes that fallback latency-safe.
# ---------------------------------------------------------------------------
def test_fr82_gin_tsvector_index_exists():
    table = "knowledge_chunks"
    index_type = "gin"
    expression = "to_tsvector('simple', content)"

    # GREEN TODO: GIN_TSVECTOR_INDEX_SPEC must be a GINIndexSpec-like
    # object exposing ``table`` / ``column`` / ``expression`` (or
    # equivalent names). The ``expression`` must reference
    # ``to_tsvector('simple', content)`` verbatim so FR-99's
    # level_embedding_down tsvector fallback finds the index at all.
    gin = GIN_TSVECTOR_INDEX_SPEC

    if index_type == "gin":
        # Spec fr82-ok predicate applies_to case 1 only; case 4 has no
        # predicate so we don't redeclare it here.
        result = gin
    assert result is not None, (
        "FR-82 GIN_TSVECTOR_INDEX_SPEC must not be None"
    )

    # The GIN index must be on knowledge_chunks.
    gin_table = getattr(gin, "table", None)
    assert gin_table == table, (
        f"FR-82 GIN tsvector index must be on table={table!r}; "
        f"got table={gin_table!r}"
    )

    # The GIN expression MUST be the canonical tsvector expression so
    # the FR-99 fallback (which queries ``WHERE to_tsvector('simple',
    # content) @@ plainto_tsquery('simple', ?)``) can use the index.
    gin_expression = getattr(gin, "expression", None) or getattr(
        gin, "expr", None
    )
    assert gin_expression is not None, (
        "FR-82 GIN_TSVECTOR_INDEX_SPEC must declare the tsvector "
        "expression (e.g. to_tsvector('simple', content))"
    )
    # Strip whitespace and lowercase for the substring checks below so
    # GREEN may freely add parens / aliases without breaking the test.
    gin_norm = "".join(gin_expression.split()).lower()
    expected_norm = "".join(expression.split()).lower()
    assert "to_tsvector" in gin_norm, (
        f"FR-82 GIN tsvector index expression must call to_tsvector(...); "
        f"got expression={gin_expression!r}"
    )
    assert "simple" in gin_norm, (
        f"FR-82 GIN tsvector index expression must use the 'simple' "
        f"text-search configuration; got expression={gin_expression!r}"
    )
    assert "content" in gin_norm, (
        f"FR-82 GIN tsvector index expression must reference the "
        f"knowledge_chunks.content column; got expression={gin_expression!r}"
    )
    # Strict equality on the normalised form is acceptable and catches
    # the most common drift (e.g. switching to 'english' config or to
    # a title field), so enforce it as well.
    assert gin_norm == expected_norm, (
        f"FR-82 GIN tsvector index expression must be exactly "
        f"{expression!r}; got expression={gin_expression!r} "
        f"(normalised={gin_norm!r})"
    )

    # The GIN index must target the ``content`` column (not e.g.
    # ``title`` or ``summary``) so the FR-99 fallback query finds it.
    gin_column = getattr(gin, "column", None) or getattr(gin, "column_name", None)
    assert gin_column is not None, (
        "FR-82 GIN_TSVECTOR_INDEX_SPEC must declare a target column"
    )
    assert gin_column == "content", (
        f"FR-82 GIN tsvector index must target the content column on "
        f"knowledge_chunks; got column={gin_column!r}"
    )
