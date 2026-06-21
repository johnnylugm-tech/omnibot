"""TDD-RED: failing tests for FR-98 — Rollback 策略
(knowledge 軟刪除 / schema downgrade / experiment abort).

Spec source: 02-architecture/TEST_SPEC.md (FR-98)
SRS source : SRS.md FR-98 (Module 22: Deployment — Rollback procedures)

Acceptance criteria (from SRS FR-98):
    knowledge_update  : version + is_active 軟刪除 (rollback restores
                        is_active=true on the previous version).
    model_switch      : A/B Testing 漸進 10% → 50% → 100%, 指標下降 > 5%
                        自動回退.
    schema_migration  : Alembic downgrade() must run, and the rollback
                        MUST NOT lose data (rows_preserved=True).
    experiment_abort  : status='aborted', 流量回 control.

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr98_knowledge_soft_delete_rollback
         Inputs: action="rollback"; expected_is_active="true"
         Type  : happy_path
    2. test_fr98_schema_downgrade_no_data_loss
         Inputs: migration="downgrade"; expected_rows_preserved="true"
         Type  : happy_path
    3. test_fr98_experiment_abort_restores_control
         Inputs: experiment_status="aborted"; expected_traffic="control"
         Type  : happy_path

Sub-assertion (per TEST_SPEC):
    fr98-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``RollbackStrategy`` is intentionally NOT YET exported
# by ``app.infra.rollback_strategy``. The import below is unguarded: pytest
# MUST fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/rollback_strategy.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these names
# and behaviours are observable):
#
#   - Canonical configuration constants
#       KNOWLEDGE_VERSION_FIELD   = "version"
#       KNOWLEDGE_IS_ACTIVE_FIELD = "is_active"
#       MIGRATION_DOWNGRADE       = "downgrade"
#       EXPERIMENT_STATUS_ABORTED = "aborted"
#       EXPERIMENT_TRAFFIC_CONTROL = "control"
#       AB_TEST_STAGES            = (10, 50, 100)   # 10%→50%→100%
#       AB_ROLLBACK_THRESHOLD_PCT = 5              # 指標下降 > 5% 自動回退
#
#   - RollbackStrategy
#       In-memory abstraction for the FR-98 rollback contract so unit
#       tests can exercise every guarantee without a live DB / Alembic /
#       A/B test controller. Required attributes / methods:
#
#           __init__(...) -> None
#               Construct with FR-98 defaults (knowledge soft-delete with
#               version+is_active, Alembic downgrade, experiment abort
#               routing traffic back to control).
#           rollback_knowledge_update(knowledge_id) -> KnowledgeRollbackResult
#               Soft-delete rollback: bumps ``version`` and restores
#               ``is_active=True`` on the previous live version. Returns
#               a ``KnowledgeRollbackResult`` whose ``is_active`` is True
#               in the happy path.
#           downgrade_schema(migration: str) -> SchemaMigrationResult
#               Execute an Alembic-style downgrade. The contract for
#               FR-98 is that the downgrade path must NOT lose data —
#               ``rows_preserved`` on the result MUST be True.
#           abort_experiment(experiment_id) -> ExperimentAbortResult
#               Abort the named experiment, set its status to "aborted",
#               and route 100% of subsequent traffic to the control arm.
#               Returns an ``ExperimentAbortResult`` whose ``traffic`` is
#               "control" in the happy path.
#           ab_test_progress(metric_drop_pct: float) -> ModelSwitchResult
#               Decide whether an in-flight A/B roll-forward should be
#               auto-rolled-back. The threshold is a strict > 5% metric
#               drop, which is the SRS FR-98 "指標下降 > 5% 自動回退"
#               invariant.
#
#   - KnowledgeRollbackResult
#       Required attributes / methods:
#           is_active: bool   (True once the previous version is restored)
#           version:   int    (the post-rollback version number, > 0)
#
#   - SchemaMigrationResult
#       Required attributes / methods:
#           migration:       str   ("downgrade" in the happy path)
#           rows_preserved:  bool  (True iff no data was lost)
#
#   - ExperimentAbortResult
#       Required attributes / methods:
#           status:  str  ("aborted" in the happy path)
#           traffic: str  ("control" in the happy path)
#
# The tests below intentionally avoid any real Alembic / DB / A/B
# controller I/O — they exercise the RollbackStrategy abstraction in
# isolation, which is the canonical unit-test shape for FR-98.
# ---------------------------------------------------------------------------
# Re-export the constants so the tests can assert against the same values
# the production code uses (and so the harness sees the same names in
# the import surface as the green implementation must expose).
from app.infra.rollback_strategy import (  # noqa: F401
    AB_ROLLBACK_THRESHOLD_PCT,
    AB_TEST_STAGES,
    EXPERIMENT_STATUS_ABORTED,
    EXPERIMENT_TRAFFIC_CONTROL,
    KNOWLEDGE_IS_ACTIVE_FIELD,
    KNOWLEDGE_VERSION_FIELD,
    MIGRATION_DOWNGRADE,
    ExperimentAbortResult,
    KnowledgeRollbackResult,
    RollbackStrategy,
    SchemaMigrationResult,
)


# ---------------------------------------------------------------------------
# 1. A knowledge_update rollback restores is_active=true (happy_path).
#
# Spec input: action="rollback"; expected_is_active="true".
# SRS FR-98: "knowledge_update（version + is_active 軟刪除）" — the rollback
# MUST put the previous knowledge version back into the active set.
# A regression that left is_active=False after rollback would silently
# blank the knowledge base; a regression that lost the ``version`` field
# would break the version-chain guarantee and make every subsequent
# rollback undecidable.
# ---------------------------------------------------------------------------
def test_fr98_knowledge_soft_delete_rollback():
    # Spec input literals — also used as trigger values for the fr98-ok
    # sub-assertion guard.
    action = "rollback"
    expected_is_active = "true"  # spec string sentinel

    # GREEN TODO: ``KNOWLEDGE_VERSION_FIELD`` MUST be exported from
    # ``app.infra.rollback_strategy`` and MUST equal "version" — the
    # canonical soft-delete version field mandated by FR-98.
    assert KNOWLEDGE_VERSION_FIELD == "version", (
        f"FR-98 KNOWLEDGE_VERSION_FIELD must be 'version'; got "
        f"{KNOWLEDGE_VERSION_FIELD!r}"
    )

    # GREEN TODO: ``KNOWLEDGE_IS_ACTIVE_FIELD`` MUST be exported and
    # MUST equal "is_active" — the canonical soft-delete flag mandated
    # by FR-98.
    assert KNOWLEDGE_IS_ACTIVE_FIELD == "is_active", (
        f"FR-98 KNOWLEDGE_IS_ACTIVE_FIELD must be 'is_active'; got "
        f"{KNOWLEDGE_IS_ACTIVE_FIELD!r}"
    )

    # GREEN TODO: ``RollbackStrategy()`` constructed with no arguments
    # MUST expose the FR-98 knowledge-update rollback entry point. GREEN
    # may spell the method however it likes so long as it accepts a
    # knowledge identifier and returns a ``KnowledgeRollbackResult``
    # that records ``is_active`` and ``version``.
    strategy = RollbackStrategy()
    assert hasattr(strategy, "rollback_knowledge_update") and callable(
        strategy.rollback_knowledge_update
    ), (
        "FR-98 RollbackStrategy must expose "
        "``rollback_knowledge_update(knowledge_id) -> "
        "KnowledgeRollbackResult``"
    )

    result = strategy.rollback_knowledge_update(
        knowledge_id="kb-fr98-fixture"
    )  # bind for the fr98-ok predicate

    # Spec fr98-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input literal
    # (action="rollback"). The harness parser requires a single
    # VAR == c literal in the trigger block — compound conditions are
    # not matched. So we wrap the predicate in a narrow guard on the
    # spec's first case-1 trigger variable.
    if action == "rollback":
        assert result is not None, "fr98-ok predicate: result must not be None"

    # Public surface contract: ``KnowledgeRollbackResult`` MUST expose
    # ``is_active`` so the harness can read the post-rollback activation
    # state. GREEN may spell it as an attribute or accessor; both forms
    # are checked below.
    assert hasattr(result, "is_active"), (
        "FR-98 KnowledgeRollbackResult must expose ``is_active``"
    )
    observed_is_active = (
        result.is_active()
        if callable(getattr(result, "is_active", None))
        else result.is_active
    )

    # The rollback MUST restore is_active=True — the FR's
    # "expected_is_active=true" guarantee. A GREEN that hard-coded
    # is_active=False here would keep the knowledge base empty after
    # every rollback and silently break the answer surface.
    if expected_is_active == "true":
        assert observed_is_active is True, (
            f"FR-98 knowledge rollback must restore is_active=True; "
            f"got {observed_is_active!r}"
        )

    # Companion invariant: the post-rollback version MUST be a positive
    # integer so the version chain remains usable for the next rollback.
    # A GREEN that left version=None or version=0 would break the chain
    # and make every subsequent soft-delete undecidable.
    assert hasattr(result, "version"), (
        "FR-98 KnowledgeRollbackResult must expose ``version``"
    )
    observed_version = (
        result.version()
        if callable(getattr(result, "version", None))
        else result.version
    )
    assert isinstance(observed_version, int) and observed_version > 0, (
        f"FR-98 knowledge rollback version must be a positive int; got "
        f"{observed_version!r}"
    )


# ---------------------------------------------------------------------------
# 2. A schema_migration downgrade preserves every row (happy_path).
#
# Spec input: migration="downgrade"; expected_rows_preserved="true".
# SRS FR-98: "schema_migration（Alembic downgrade()）" and the explicit
# acceptance criterion "schema rollback 不丟失資料". A regression that
# dropped rows on downgrade would violate the SRS hard guarantee and
# break every DR drill that relies on downgrade.
# ---------------------------------------------------------------------------
def test_fr98_schema_downgrade_no_data_loss():
    # Spec input literals.
    migration = "downgrade"  # spec string sentinel
    expected_rows_preserved = "true"  # spec string sentinel

    # GREEN TODO: ``MIGRATION_DOWNGRADE`` MUST be exported and MUST
    # equal "downgrade" — the canonical Alembic downgrade identifier
    # mandated by FR-98.
    assert MIGRATION_DOWNGRADE == "downgrade", (
        f"FR-98 MIGRATION_DOWNGRADE must be 'downgrade'; got "
        f"{MIGRATION_DOWNGRADE!r}"
    )

    # GREEN TODO: ``RollbackStrategy`` MUST expose a downgrade entry
    # point that accepts a migration direction. GREEN may spell the
    # method however it likes so long as it returns a
    # ``SchemaMigrationResult`` that records ``migration`` and
    # ``rows_preserved``.
    strategy = RollbackStrategy()
    assert hasattr(strategy, "downgrade_schema") and callable(
        strategy.downgrade_schema
    ), (
        "FR-98 RollbackStrategy must expose "
        "``downgrade_schema(migration: str) -> SchemaMigrationResult``"
    )

    # The downgrade MUST accept the "downgrade" direction — a GREEN
    # that hard-coded only "upgrade" would silently break FR-98's
    # schema-rollback leg.
    if migration == "downgrade":
        result = strategy.downgrade_schema(migration)

        # Public surface contract: ``SchemaMigrationResult`` MUST
        # expose ``rows_preserved`` so the harness can verify the
        # SRS "不丟失資料" guarantee. GREEN may spell it as an
        # attribute or accessor; both forms are checked below.
        assert hasattr(result, "rows_preserved"), (
            "FR-98 SchemaMigrationResult must expose ``rows_preserved``"
        )
        observed_rows_preserved = (
            result.rows_preserved()
            if callable(getattr(result, "rows_preserved", None))
            else result.rows_preserved
        )

        # The downgrade MUST preserve every row — the FR's
        # "expected_rows_preserved=true" guarantee. A GREEN that
        # returned rows_preserved=False for a happy-path downgrade
        # would violate the SRS hard acceptance criterion and break
        # every DR drill.
        if expected_rows_preserved == "true":
            assert observed_rows_preserved is True, (
                f"FR-98 schema downgrade must preserve all rows; got "
                f"rows_preserved={observed_rows_preserved!r}"
            )

        # The result MUST echo the migration direction so the
        # observability layer can distinguish downgrade from upgrade
        # in the audit log. A GREEN that hard-coded "upgrade" here
        # would silently break the audit trail.
        assert hasattr(result, "migration"), (
            "FR-98 SchemaMigrationResult must expose ``migration``"
        )
        observed_migration = (
            result.migration()
            if callable(getattr(result, "migration", None))
            else result.migration
        )
        assert observed_migration == "downgrade", (
            f"FR-98 schema downgrade result must record migration="
            f"'downgrade'; got {observed_migration!r}"
        )


# ---------------------------------------------------------------------------
# 3. An experiment_abort routes 100% of traffic back to control (happy_path).
#
# Spec input: experiment_status="aborted"; expected_traffic="control".
# SRS FR-98: "experiment_abort（status='aborted'，流量回 control）". A
# regression that left the treatment arm receiving traffic after an
# abort would silently expose users to the very change the abort was
# meant to retract; a regression that lost the "aborted" status would
# break the audit trail used to justify the rollback.
# ---------------------------------------------------------------------------
def test_fr98_experiment_abort_restores_control():
    # Spec input literals.
    experiment_status = "aborted"  # spec string sentinel
    expected_traffic = "control"  # spec string sentinel

    # GREEN TODO: ``EXPERIMENT_STATUS_ABORTED`` MUST be exported and
    # MUST equal "aborted" — the canonical abort status mandated by
    # FR-98.
    assert EXPERIMENT_STATUS_ABORTED == "aborted", (
        f"FR-98 EXPERIMENT_STATUS_ABORTED must be 'aborted'; got "
        f"{EXPERIMENT_STATUS_ABORTED!r}"
    )

    # GREEN TODO: ``EXPERIMENT_TRAFFIC_CONTROL`` MUST be exported and
    # MUST equal "control" — the canonical control-arm identifier
    # mandated by FR-98.
    assert EXPERIMENT_TRAFFIC_CONTROL == "control", (
        f"FR-98 EXPERIMENT_TRAFFIC_CONTROL must be 'control'; got "
        f"{EXPERIMENT_TRAFFIC_CONTROL!r}"
    )

    # Companion invariant for the SRS FR-98 model_switch leg:
    # "A/B Testing 漸進 10% → 50% → 100%". A GREEN that picked stages
    # like (25, 50, 75) here would silently break the rollout plan
    # the SRS pins to the FR.
    assert tuple(AB_TEST_STAGES) == (10, 50, 100), (
        f"FR-98 AB_TEST_STAGES must be (10, 50, 100); got "
        f"{tuple(AB_TEST_STAGES)!r}"
    )

    # Companion invariant for the SRS FR-98 model_switch leg:
    # "指標下降 > 5% 自動回退". A GREEN that picked a 3% or 10% threshold
    # here would either over- or under-trigger the auto-rollback and
    # silently break the SLA.
    assert AB_ROLLBACK_THRESHOLD_PCT == 5, (
        f"FR-98 AB_ROLLBACK_THRESHOLD_PCT must be 5; got "
        f"{AB_ROLLBACK_THRESHOLD_PCT!r}"
    )

    # GREEN TODO: ``RollbackStrategy`` MUST expose an experiment-abort
    # entry point. GREEN may spell the method however it likes so long
    # as it accepts an experiment identifier and returns an
    # ``ExperimentAbortResult`` that records ``status`` and
    # ``traffic``.
    strategy = RollbackStrategy()
    assert hasattr(strategy, "abort_experiment") and callable(
        strategy.abort_experiment
    ), (
        "FR-98 RollbackStrategy must expose "
        "``abort_experiment(experiment_id) -> ExperimentAbortResult``"
    )

    result = strategy.abort_experiment(
        experiment_id="exp-fr98-fixture"
    )

    # Public surface contract: ``ExperimentAbortResult`` MUST expose
    # ``status`` so the harness can verify the post-abort state.
    # GREEN may spell it as an attribute or accessor; both forms are
    # checked below.
    assert hasattr(result, "status"), (
        "FR-98 ExperimentAbortResult must expose ``status``"
    )
    observed_status = (
        result.status()
        if callable(getattr(result, "status", None))
        else result.status
    )

    # The status MUST be "aborted" — the FR's
    # "experiment_status='aborted'" guarantee. A GREEN that left
    # status="running" here would break the audit trail and let the
    # treatment arm keep receiving traffic.
    if experiment_status == "aborted":
        assert observed_status == "aborted", (
            f"FR-98 experiment abort must set status='aborted'; got "
            f"{observed_status!r}"
        )

    # Public surface contract: ``ExperimentAbortResult`` MUST expose
    # ``traffic`` so the harness can verify the post-abort traffic
    # routing. GREEN may spell it as an attribute or accessor; both
    # forms are checked below.
    assert hasattr(result, "traffic"), (
        "FR-98 ExperimentAbortResult must expose ``traffic``"
    )
    observed_traffic = (
        result.traffic()
        if callable(getattr(result, "traffic", None))
        else result.traffic
    )

    # The traffic MUST be routed to "control" — the FR's
    # "expected_traffic='control'" guarantee. A GREEN that left
    # traffic on "treatment" here would silently re-expose users to
    # the change the abort was meant to retract.
    if expected_traffic == "control":
        assert observed_traffic == "control", (
            f"FR-98 experiment abort must route traffic to 'control'; "
            f"got {observed_traffic!r}"
        )

# NFR coverage: NFR-22 (SOC2 audit trail)
