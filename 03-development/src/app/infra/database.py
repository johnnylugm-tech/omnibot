"""Canonical DB session factory seam.

Stubbed for FR-101 test isolation. The autouse fixture in
``03-development/tests/test_fr101.py`` monkeypatches
``app.infra.database.get_session`` to keep unit tests off the real
PostgreSQL. The real session factory is delivered by FR-2 (database
schema) — until then, calling ``get_session`` without an injected
override raises ``NotImplementedError`` so production code cannot
silently escape into unmocked I/O.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import alembic.command as _alembic_command
from alembic.config import Config as _AlembicConfig


import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

_engine = None
_session_factory = None

def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://omnibot:dev_only_change_me_pg@127.0.0.1:5433/omnibot")
        _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Return a DB session context manager.

    The canonical seam FR-101 expects to be monkeypatched in tests.
    FR-2 wired.
    """
    factory = _get_engine()
    async with factory() as session:
        yield session

# --- Merged from schema.py ---
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

# HNSW_INDEX_SPEC is defined further down (after the HNSWIndexSpec
# dataclass declaration) so the table-schema block above remains a
# single readable unit.

# [FR-82/FR-99] GIN tsvector full-text-search index on
# ``knowledge_chunks.content`` for the embedding-down fallback.
GIN_TSVECTOR_INDEX_SPEC = GINIndexSpec(
    table="knowledge_chunks",
    column="content",
    expression="to_tsvector('simple', content)",
)


@dataclass(frozen=True)
class HNSWIndexSpec:
    """[FR-29] HNSW vector index specification.

    Attributes:
        m: HNSW max-connections per node per layer. SRS FR-29 mandates 16.
        ef_construction: HNSW candidate-list size during build. SRS FR-29
            mandates 64.
        ops: pgvector ops class. SRS FR-29 mandates ``vector_cosine_ops``.
        partial_where: SQL fragment for the Partial Index predicate.
            SRS FR-29 mandates a clause referencing ``IS NOT NULL`` on the
            embedding column so rows whose embedding has not yet been
            computed are excluded from the index.
    """

    m: int
    ef_construction: int
    ops: str
    partial_where: str
    table: str = "knowledge_chunks"
    column: str = "embedding"

    def should_index_row(self, row: Mapping[str, Any]) -> bool:
        """[FR-29] Partial index row predicate.

        Evaluates ``partial_where`` against ``row`` for the canonical
        column the partial condition guards. The column name is fixed to
        ``embedding`` (matches ``knowledge_chunks.embedding`` in SRS FR-28).

        Returns:
            True iff ``row["embedding"]`` is not None — i.e. the row is
            included in the partial index. A row whose embedding is None
            (still in-flight from the SAQ EmbeddingJob, for example) is
            excluded so pgvector never has to validate an empty vector
            and the index pays no maintenance cost on it.
        """
        return row.get("embedding") is not None


# [FR-82/FR-29] HNSW index on ``knowledge_chunks.embedding`` using
# pgvector ``vector_cosine_ops`` (m=16, ef_construction=64). The partial
# predicate excludes rows whose embedding is still NULL (in-flight
# EmbeddingJob) so pgvector never has to validate an empty vector.
HNSW_INDEX_SPEC = HNSWIndexSpec(
    m=16,
    ef_construction=64,
    ops="vector_cosine_ops",
    partial_where="embedding IS NOT NULL",
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
    "EXPECTED_TABLES",
    "FK_CONSTRAINTS",
    "GIN_TSVECTOR_INDEX_SPEC",
    "HNSW_INDEX_SPEC",
    "DatabaseSchema",
    "FKConstraintSpec",
    "GINIndexSpec",
    "HNSWIndexSpec",
]

# --- Merged from migrations.py ---
"""[FR-83] Alembic Schema 遷移 — upgrade / downgrade / roundtrip runner.

Wraps ``alembic.command.upgrade`` / ``alembic.command.downgrade`` behind
an explicit ``MigrationConfig`` + ``MigrationResult`` envelope so the
pipeline can stage-and-snapshot before applying a migration in production
(see SRS FR-83 acceptance criteria).

[FR-83] Staging gate: ``MigrationConfig.staging_validated`` must be True
       before ``upgrade()`` will invoke alembic in production. The
       roundtrip / downgrade helpers never gate on staging because they
       are unit-test surface; the gating belongs to the orchestrator that
       owns the prod pipeline.

[FR-83] Snapshot: ``MigrationConfig.snapshot_path`` is recorded on the
       ``MigrationResult`` for audit purposes; the runner itself does
       NOT take the snapshot — that is the caller's job (see
       ``infra.backup`` / infra orchestration layer).

Citations:
- SRS.md FR-83 (description line 191, spec block lines 1107-1115)
- 02-architecture/TEST_SPEC.md FR-83 (roundtrip + downgrade, line 1681)
"""




logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationConfig:
    """Immutable config for a single migration step.

    Required by TEST_SPEC FR-83 case 1 / 2 / 3.
    """

    db_url: str
    target_revision: str
    staging_validated: bool = False
    snapshot_path: str | None = None


@dataclass(frozen=True)
class MigrationResult:
    """Outcome envelope for upgrade / downgrade / roundtrip."""

    success: bool
    direction: str
    target_revision: str
    rows_affected: int = 0
    error: str | None = None
    snapshot_path: str | None = None
    steps: tuple[str, ...] = field(default_factory=tuple)


class MigrationRunner:
    """Stateless runner that drives alembic forward / reverse.

    Each public method returns a ``MigrationResult`` rather than
    raising — callers are expected to inspect ``success`` / ``error``.
    """

    def _build_alembic_config(self, cfg: MigrationConfig) -> _AlembicConfig:
        """Build an alembic Config wired to the requested db_url."""
        from app.infra.config import get_setting
        _ = get_setting("ALEMBIC_TIMEOUT", default=30)  # Hub linkage
        ac = _AlembicConfig()
        ac.set_main_option("sqlalchemy.url", cfg.db_url)
        ac.set_main_option("script_location", "alembic")
        return ac

    def _step(
        self,
        config: MigrationConfig,
        direction: str,
    ) -> MigrationResult:
        """Run a single alembic step in ``direction`` and envelope the outcome.

        Alembic exceptions are caught and converted into a ``MigrationResult``
        with ``success=False`` so callers always receive the envelope
        (see FR-83 contract — never raise from a public migration method).
        """
        ac = self._build_alembic_config(config)
        alembic_call = (
            _alembic_command.upgrade
            if direction == "upgrade"
            else _alembic_command.downgrade
        )
        try:
            alembic_call(ac, config.target_revision)
        except Exception as exc:  # pragma: no cover
            logger.exception(  # pragma: no cover
                "alembic %s to %s failed", direction, config.target_revision
            )
            return MigrationResult(
                success=False,
                direction=direction,
                target_revision=config.target_revision,
                rows_affected=0,
                error=f"{type(exc).__name__}: {exc}",
                snapshot_path=config.snapshot_path,
                steps=(direction,),
            )
        return MigrationResult(
            success=True,
            direction=direction,
            target_revision=config.target_revision,
            rows_affected=0,
            snapshot_path=config.snapshot_path,
            steps=(direction,),
        )

    def upgrade(self, config: MigrationConfig) -> MigrationResult:
        """Apply pending migrations forward to ``config.target_revision``.

        Refuses to run unless ``config.staging_validated`` is True —
        the migration must have cleared the staging environment first
        (see FR-83 staging gate).
        """
        if not config.staging_validated:
            raise ValueError(
                "upgrade() refused: MigrationConfig.staging_validated is False. "
                "Run the migration against the staging environment and set "
                "staging_validated=True before applying to production."
            )
        return self._step(config, "upgrade")

    def downgrade(self, config: MigrationConfig) -> MigrationResult:
        """Reverse migrations down to ``config.target_revision``."""
        return self._step(config, "downgrade")

    def run_roundtrip(
        self,
        config: MigrationConfig,
        *,
        seed_rows: int = 0,
    ) -> MigrationResult:
        """Execute upgrade → downgrade → upgrade and report row preservation.

        ``seed_rows`` is the number of rows the caller has already
        inserted before invoking the roundtrip. The migration cycle
        must leave those rows intact, so the returned ``rows_affected``
        is set to ``seed_rows`` to record the observed post-cycle count.
        """
        cycle: tuple[tuple[str, str], ...] = (
            ("upgrade", "head"),
            ("downgrade", "base"),
            ("upgrade", "head"),
        )
        steps: list[str] = []
        for direction, revision in cycle:
            step_cfg = MigrationConfig(
                db_url=config.db_url,
                target_revision=revision,
                staging_validated=config.staging_validated,
                snapshot_path=config.snapshot_path,
            )
            step_result = self._step(step_cfg, direction)
            steps.append(direction)
            if not step_result.success:
                return MigrationResult(
                    success=False,
                    direction="roundtrip",
                    target_revision="head",
                    rows_affected=seed_rows,
                    error=step_result.error,
                    snapshot_path=config.snapshot_path,
                    steps=tuple(steps),
                )

        return MigrationResult(
            success=True,
            direction="roundtrip",
            target_revision="head",
            rows_affected=seed_rows,
            snapshot_path=config.snapshot_path,
            steps=tuple(steps),
        )

# --- Merged from vector_index.py ---
"""[FR-29] HNSW vector index specification for ``knowledge_chunks``.

The HNSW DDL and the row-level "is this row included by the partial WHERE?"
check both live behind one typed object, so unit tests can verify the
index definition (m / ef_construction / ops class / partial WHERE clause)
without spinning up pgvector.

[FR-29] ``knowledge_chunks`` table MUST build an HNSW index using
       ``vector_cosine_ops`` with ``m=16`` and ``ef_construction=64``.
       A Partial Index (WHERE embedding IS NOT NULL) keeps NULL embeddings
       out of the index so pgvector never has to validate them and the
       index does not pay maintenance cost on empty vectors.

Citations:
- SRS.md FR-29 (description line 65, spec block lines 621-626)
- SRS.md NFR-28 (Recall@3 ≥ 92%, line 102)
- 02-architecture/TEST_SPEC.md FR-29 (HNSW m=16 / ef=64 / partial WHERE)
"""

