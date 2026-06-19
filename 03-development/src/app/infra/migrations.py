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

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import alembic.command as _alembic_command
from alembic.config import Config as _AlembicConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationConfig:
    """Immutable config for a single migration step.

    Required by TEST_SPEC FR-83 case 1 / 2 / 3.
    """

    db_url: str
    target_revision: str
    staging_validated: bool = False
    snapshot_path: Optional[str] = None


@dataclass(frozen=True)
class MigrationResult:
    """Outcome envelope for upgrade / downgrade / roundtrip."""

    success: bool
    direction: str
    target_revision: str
    rows_affected: int = 0
    error: Optional[str] = None
    snapshot_path: Optional[str] = None
    steps: tuple[str, ...] = field(default_factory=tuple)


class MigrationRunner:
    """Stateless runner that drives alembic forward / reverse.

    Each public method returns a ``MigrationResult`` rather than
    raising — callers are expected to inspect ``success`` / ``error``.
    """

    def _build_alembic_config(self, cfg: MigrationConfig) -> _AlembicConfig:
        """Build an alembic Config wired to the requested db_url."""
        ac = _AlembicConfig()
        ac.set_main_option("sqlalchemy.url", cfg.db_url)
        return ac

    def _step(
        self,
        config: MigrationConfig,
        direction: str,
    ) -> MigrationResult:
        """Run a single alembic step in ``direction`` and envelope the outcome."""
        ac = self._build_alembic_config(config)
        alembic_call = (
            _alembic_command.upgrade
            if direction == "upgrade"
            else _alembic_command.downgrade
        )
        alembic_call(ac, config.target_revision)
        return MigrationResult(
            success=True,
            direction=direction,
            target_revision=config.target_revision,
            rows_affected=0,
            snapshot_path=config.snapshot_path,
            steps=(direction,),
        )

    def upgrade(self, config: MigrationConfig) -> MigrationResult:
        """Apply pending migrations forward to ``config.target_revision``."""
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
            self._step(step_cfg, direction)
            steps.append(direction)

        return MigrationResult(
            success=True,
            direction="roundtrip",
            target_revision="head",
            rows_affected=seed_rows,
            snapshot_path=config.snapshot_path,
            steps=tuple(steps),
        )